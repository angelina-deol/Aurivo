# ml/

Wraps the official [AASIST repo](https://github.com/clovaai/aasist) for use
as Aurivo's inference engine. Per the PRD's non-goals, **the AASIST
architecture itself is never modified** — `ml/aasist/` is an untouched copy
of the upstream repo; everything else here is a thin layer around it.

## Layout

```
ml/
  aasist/         <- untouched clone of https://github.com/clovaai/aasist
  checkpoints/    <- pretrained weights (AASIST.pth, AASIST-L.pth)
  preprocessing/  <- audio loading/resampling/padding before AASIST
  inference/      <- the wrapper: loads model once, runs prediction, returns score
  evaluation/     <- (empty for now) sanity-checks against known AASIST results
```

## Correction from Phase 1

Phase 1's version of this README said the pretrained checkpoints weren't
bundled in the AASIST repo and needed a manual Google Drive download. That
was wrong — `models/weights/AASIST.pth` and `AASIST-L.pth` are actually
committed directly in the upstream repo, and are copied here at
`ml/checkpoints/`. No separate download step is needed.

## How inference works

1. `ml/preprocessing/audio.py` reads the uploaded file (any sample rate,
   mono or stereo), downmixes to mono, resamples to 16kHz (matching AASIST's
   training data), and pads/tiles to the fixed 64,600-sample window
   (`nb_samp` in `ml/aasist/config/AASIST.conf`) using the same
   tile-and-truncate convention as AASIST's own `data_utils.py::pad()` —
   zero-padding a short clip would shift the input away from what the
   pretrained weights expect.
2. `ml/inference/aasist_wrapper.py` loads `ml/aasist/models/AASIST.py`'s
   `Model` class once per worker process (not per request), loads
   `AASIST.pth`, and runs a forward pass.
3. The model outputs 2 logits (index 0 = spoof, index 1 = bonafide, per
   `ml/aasist/data_utils.py::genSpoof_list`'s labeling). The wrapper takes a
   softmax over them for an interpretable confidence/fraud-score percentage
   — AASIST's own benchmarking script uses the raw bonafide logit directly,
   which is fine for computing EER but isn't a calibrated probability.

## Installing dependencies

The FastAPI web process never imports torch — only the Celery worker does.
Install `backend/requirements-worker.txt` (which layers on top of the base
`requirements.txt`) wherever the worker runs:

```bash
pip install -r backend/requirements.txt
pip install -r backend/requirements-worker.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

The `--extra-index-url` matters on Linux: plain `pip install torch` from
PyPI pulls in CUDA runtime packages (~2GB) even with no GPU to use them.
`docker/worker.Dockerfile` already does this correctly.

## Known limitation

This integration was built and code-reviewed against the real upstream
AASIST source (cloned and read directly, not guessed from memory), and the
preprocessing module was tested directly (resampling, tiling, stereo
downmix all verified against real generated audio, including after the
`scipy` version fix below). The actual PyTorch forward pass through the
loaded model, however, has still **not** been run end-to-end anywhere this
was built.

**Correction:** an earlier version of this note claimed the CPU-only
PyTorch wheel wasn't reachable due to network restrictions in the build
sandbox. That was wrong — `download.pytorch.org` turned out to be
reachable after all. The real blockers, found and fixed along the way:

- `scipy==1.13.1` (originally pinned here) has no wheel for Python 3.13 on
  any platform — it predates 3.13's release. Verified and fixed to
  `1.14.1`, which does, and confirmed the preprocessing module still works
  correctly with it.
- `torch==2.3.1` (originally pinned here) has no Python 3.13 wheel either,
  for the same reason. Verified and fixed to `2.7.1`, which has real cp313
  wheels for both macOS arm64 and Linux x86_64 via the CPU index.
- The actual full install of `torch==2.7.1` still couldn't be completed in
  the sandbox this was built in — not network access this time, but disk
  space (a large wheel plus its dependencies didn't fit in the space
  available there). This is specific to that sandbox, not a statement
  about your machine.

Test the forward pass directly on your machine before relying on it:
install `requirements-worker.txt`, run the worker, upload a real audio
file, and confirm you get back a sensible prediction.
