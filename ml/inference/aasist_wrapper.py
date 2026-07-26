"""
Thin wrapper around the untouched AASIST model (ml/aasist/models/AASIST.py).

Per the PRD's non-goals, the AASIST architecture itself is never modified —
everything here just loads it, runs a forward pass, and translates the raw
output into something the rest of the app can use.

Scoring convention (verified against ml/aasist/main.py's
`produce_evaluation_file`): the model outputs 2 logits, index 1 is the
"bonafide" class and index 0 is "spoof" (this matches
ml/aasist/data_utils.py's `genSpoof_list`, which labels bonafide=1). AASIST's
own eval script uses the raw bonafide logit directly as an EER-ranking score
since EER doesn't need a calibrated probability. For a user-facing confidence
percentage, this wrapper instead takes a softmax over the 2 logits — an
interpretable probability, not the raw score AASIST's own benchmarking uses.

Attention extraction (Phase 6, explainability): captures the temporal graph
attention layer's (`GAT_layer_T`) internal attention map via a monkeypatched
`_derive_att_map` — this observes a value the layer already computes
internally but doesn't return, without changing any computed value or the
model's actual forward-pass behavior at all, so it stays true to "the AASIST
architecture itself is never modified." See `extract_attention_regions()`
for the caveat on what this attention map does and doesn't tell you.

Known limitation: unlike the rest of this file, attention extraction has
NOT been verified against a real forward pass — building it required no
torch install, but running it does, and no torch install completed in the
environment this was built in (disk space, not a fundamental blocker — see
ml/README.md). Verify this on a real machine before relying on it.
"""
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent.parent
AASIST_ROOT = ML_ROOT / "aasist"
CHECKPOINT_PATH = ML_ROOT / "checkpoints" / "AASIST.pth"
CONFIG_PATH = AASIST_ROOT / "config" / "AASIST.conf"

PREDICTION_AI_GENERATED = "ai_generated"
PREDICTION_REAL = "real"


class ModelNotReadyError(RuntimeError):
    """Raised when the AASIST repo or checkpoint isn't in place yet."""


@dataclass
class PredictionResult:
    prediction: str  # PREDICTION_AI_GENERATED | PREDICTION_REAL
    confidence: float  # 0..1, softmax probability of the predicted class
    fraud_score: float  # 0..100, probability the audio is AI-generated
    attention_regions: list[dict] | None = None  # see extract_attention_regions()


_model = None
_device = None
_lock = threading.Lock()
_attention_patched = False


def _patch_attention_capture():
    """Monkeypatches GraphAttentionLayer._derive_att_map to stash its
    result on the instance as `self.last_att_map`, in addition to
    returning it exactly as before. This is an observation, not a
    modification: the returned value and every downstream computation are
    identical to the unpatched model — nothing about what the model
    computes or predicts changes. Applied once per process, at model load
    time, not per-inference."""
    global _attention_patched
    if _attention_patched:
        return

    sys.path.insert(0, str(AASIST_ROOT)) if str(AASIST_ROOT) not in sys.path else None
    from models.AASIST import GraphAttentionLayer  # noqa: E402

    original = GraphAttentionLayer._derive_att_map

    def patched(self, x):
        att_map = original(self, x)
        self.last_att_map = att_map.detach()
        return att_map

    GraphAttentionLayer._derive_att_map = patched
    _attention_patched = True


def _load_model():
    """Loads the AASIST model + pretrained weights once per process.
    Celery workers run one model instance per worker process (not per
    task), so this cost is paid once at worker startup, not per request."""
    global _model, _device

    if not AASIST_ROOT.exists():
        raise ModelNotReadyError(
            f"AASIST source not found at {AASIST_ROOT}. It should already be "
            "committed in this repo under ml/aasist — if it's missing, see "
            "ml/README.md."
        )
    if not CHECKPOINT_PATH.exists():
        raise ModelNotReadyError(
            f"AASIST checkpoint not found at {CHECKPOINT_PATH}. It should "
            "already be committed in this repo under ml/checkpoints — if "
            "it's missing, see ml/README.md."
        )

    # Imported lazily so anything that doesn't need inference (the FastAPI
    # web process, Phase 2's upload-only path) never needs torch installed.
    import json

    import torch

    if str(AASIST_ROOT) not in sys.path:
        sys.path.insert(0, str(AASIST_ROOT))
    from models.AASIST import Model  # noqa: E402 -- path must be set first

    _patch_attention_capture()

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = Model(config["model_config"]).to(device)
    state_dict = torch.load(CHECKPOINT_PATH, map_location=device)
    model.load_state_dict(state_dict)
    model.eval()

    _model = model
    _device = device


def _bucket_node_salience_to_regions(
    node_salience: list[float], original_duration_seconds: float, num_regions: int
) -> list[dict] | None:
    """Pure-Python bucketing/time-folding/normalization math, deliberately
    separated from the torch-tensor-touching code in
    extract_attention_regions() so this part — the part that doesn't need
    a real model or torch to verify — can be tested directly with plain
    lists of numbers."""
    from ml.preprocessing.audio import AASIST_NUM_SAMPLES, AASIST_SAMPLE_RATE

    num_nodes = len(node_salience)
    if num_nodes == 0:
        return None

    analyzed_window_seconds = AASIST_NUM_SAMPLES / AASIST_SAMPLE_RATE
    num_regions = min(num_regions, num_nodes)
    nodes_per_region = max(1, num_nodes // num_regions)

    regions = []
    for r in range(num_regions):
        node_start = r * nodes_per_region
        node_end = num_nodes if r == num_regions - 1 else (r + 1) * nodes_per_region
        if node_start >= node_end:
            continue

        region_salience = sum(node_salience[node_start:node_end]) / (node_end - node_start)
        window_start = (node_start / num_nodes) * analyzed_window_seconds
        window_end = (node_end / num_nodes) * analyzed_window_seconds

        # Caveat 2: fold tiled (short-clip) windows back onto the original timeline.
        if 0 < original_duration_seconds < analyzed_window_seconds:
            window_start = window_start % original_duration_seconds
            window_end = window_end % original_duration_seconds
            if window_end <= window_start:
                window_end = original_duration_seconds

        regions.append(
            {"start": round(window_start, 2), "end": round(window_end, 2), "salience": region_salience}
        )

    if not regions:
        return None

    # Min-max normalize salience to 0..1 for interpretability.
    saliences = [r["salience"] for r in regions]
    lo, hi = min(saliences), max(saliences)
    spread = hi - lo
    for r in regions:
        r["salience"] = round((r["salience"] - lo) / spread, 3) if spread > 0 else 0.5

    return regions


def extract_attention_regions(
    model, original_duration_seconds: float, num_regions: int = 8
) -> list[dict] | None:
    """Turns the captured temporal attention map into a small list of
    {"start", "end", "salience"} time regions, in the ORIGINAL clip's
    timeline (not the model's internal fixed-length window) — see the two
    important caveats below.

    Returns None if no attention map was captured (e.g. a forward pass
    hasn't run yet, or the patch didn't apply).

    Caveat 1 — what "salience" means: GAT_layer_T's attention softmaxes
    per query node over all key nodes (see the module docstring). This
    computes, per node j, the AVERAGE incoming attention weight across all
    query nodes — a standard simplified salience proxy for one attention
    layer, not a full attention-rollout through all of AASIST's later
    fusion stages. It reflects the model's *first-stage* temporal
    attention, not a complete gradient-based attribution of the final
    verdict.

    Caveat 2 — time alignment: AASIST always analyzes a fixed ~4.06s
    window (see ml/preprocessing/audio.py). For clips longer than that,
    only the first ~4.06s was analyzed, so regions map directly onto the
    original timeline. For clips shorter than that, the clip was tiled
    (repeated) to fill the window — this folds each region's time back
    onto the original clip using modulo, so a region past the original
    clip's own length is really pointing at a repeat of an earlier part of
    the same clip, not new content.
    """
    att_map = getattr(model.GAT_layer_T, "last_att_map", None)
    if att_map is None:
        return None

    # att_map shape: (batch, node_i, node_j, 1). Average over the query
    # axis (node_i) to get one salience score per key node j — see Caveat 1.
    # .tolist() converts to plain Python floats immediately, so everything
    # after this line is torch-free and independently testable.
    node_salience = att_map.mean(dim=1).squeeze(-1).squeeze(0).tolist()

    return _bucket_node_salience_to_regions(node_salience, original_duration_seconds, num_regions)


def predict(audio_path: str) -> PredictionResult:
    """Runs AASIST on a single audio file and returns an interpretable
    prediction. Raises ModelNotReadyError if the model/weights aren't in
    place; raises whatever soundfile/torch raise for unreadable audio."""
    global _model

    if _model is None:
        with _lock:
            if _model is None:  # re-check inside the lock
                _load_model()

    import torch

    from ml.preprocessing.audio import load_for_aasist

    samples = load_for_aasist(audio_path)

    # Re-derive the pre-pad/tile duration from the raw file for accurate
    # attention time-folding — load_for_aasist's output is always exactly
    # AASIST_NUM_SAMPLES long (padded/tiled), which isn't the original
    # clip's actual duration.
    import soundfile as sf

    original_duration = sf.info(audio_path).duration

    x = torch.from_numpy(samples).unsqueeze(0).to(_device)  # (1, nb_samp)

    with torch.no_grad():
        _, logits = _model(x)
        probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()

    spoof_prob, bonafide_prob = float(probs[0]), float(probs[1])
    is_ai_generated = spoof_prob > bonafide_prob

    attention_regions = extract_attention_regions(_model, original_duration)

    return PredictionResult(
        prediction=PREDICTION_AI_GENERATED if is_ai_generated else PREDICTION_REAL,
        confidence=max(spoof_prob, bonafide_prob),
        fraud_score=round(spoof_prob * 100, 2),
        attention_regions=attention_regions,
    )
