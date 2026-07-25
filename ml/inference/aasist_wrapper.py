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


_model = None
_device = None
_lock = threading.Lock()


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

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = Model(config["model_config"]).to(device)
    state_dict = torch.load(CHECKPOINT_PATH, map_location=device)
    model.load_state_dict(state_dict)
    model.eval()

    _model = model
    _device = device


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
    x = torch.from_numpy(samples).unsqueeze(0).to(_device)  # (1, nb_samp)

    with torch.no_grad():
        _, logits = _model(x)
        probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()

    spoof_prob, bonafide_prob = float(probs[0]), float(probs[1])
    is_ai_generated = spoof_prob > bonafide_prob

    return PredictionResult(
        prediction=PREDICTION_AI_GENERATED if is_ai_generated else PREDICTION_REAL,
        confidence=max(spoof_prob, bonafide_prob),
        fraud_score=round(spoof_prob * 100, 2),
    )
