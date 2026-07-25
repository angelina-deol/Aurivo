# ml/

This folder wraps the official [AASIST repo](https://github.com/clovaai/aasist)
for use as Aurivo's inference engine. Per the PRD's non-goals, **the AASIST
architecture itself is never modified** — everything here is a thin layer
around it.

## Layout

```
ml/
  aasist/         <- clone of https://github.com/clovaai/aasist goes here, untouched
  checkpoints/    <- pretrained AASIST / AASIST-L weights (not committed to git)
  configs/        <- Aurivo-specific inference configs (sample rate, chunking, etc.)
  preprocessing/  <- audio loading/resampling/feature extraction before AASIST
  inference/      <- the actual wrapper: load model once, run prediction, return score
  evaluation/     <- scripts to sanity-check the wrapped model against known AASIST results
```

## Getting the model in place (do this before Phase 3)

```bash
git clone https://github.com/clovaai/aasist.git ml/aasist
pip install -r ml/aasist/requirements.txt
```

Pretrained checkpoints referenced by the AASIST README are not bundled in
that repo's git history — follow the "Pre-trained models" section of
`ml/aasist/README.md` to obtain `AASIST.pth` / `AASIST-L.pth` and place them
under `ml/checkpoints/`.

## What Phase 3 adds here

- `inference/aasist_wrapper.py` — loads `ml/aasist/models/AASIST.py`'s `Model`
  class once at worker startup (not per-request) and exposes a single
  `predict(audio_path) -> (label, confidence)` function.
- `preprocessing/audio.py` — resampling to 16kHz, trimming/padding to the
  fixed length AASIST expects, using `torchaudio`/`librosa`.
- Wiring into `backend/workers/` as a Celery task so inference runs off the
  request thread (see `docker-compose.yml`'s commented-out `worker` service).

This directory intentionally has no Python code yet in Phase 1 — the goal of
this phase is project scaffolding and auth, not the ML integration.
