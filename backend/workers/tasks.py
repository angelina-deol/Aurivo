"""
Background task: run AASIST inference on an uploaded/recorded investigation.

Runs in a separate Celery worker process, so it opens its own DB session
rather than reusing FastAPI's request-scoped one from database/session.py.
"""
import io
import logging
import time
import uuid

from backend.database.models.investigation import (
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    Investigation,
)
from backend.database.session import SessionLocal
from backend.workers.celery_app import celery_app
from backend.workers.subprocess_runner import run_isolated

logger = logging.getLogger(__name__)

# Both comfortably under Celery's own 300s task_time_limit and the API's
# 360s stale-processing reconciliation window (see
# backend/api/routes/investigations.py), so a legitimate timeout here
# always resolves before either of those higher-level safety nets would
# otherwise have to.
SPECTROGRAM_TIMEOUT_SECONDS = 60
PREDICT_TIMEOUT_SECONDS = 120


def _generate_spectrogram(storage, investigation) -> None:
    """Best-effort — spectrogram generation failing should never block the
    investigation from completing with a real fraud prediction. Any
    failure here (including a subprocess crash, now that this runs
    isolated — see subprocess_runner.py) is swallowed and logged, not
    re-raised."""
    try:
        from ml.preprocessing.spectrogram import generate_spectrogram_png
        from backend.services.storage import build_storage_key

        with storage.local_path(investigation.audio_metadata.storage_key) as path:
            png_bytes = run_isolated(
                generate_spectrogram_png, path, timeout=SPECTROGRAM_TIMEOUT_SECONDS
            )

        spectrogram_key = build_storage_key(f"{investigation.id}-spectrogram.png")
        storage.save(io.BytesIO(png_bytes), spectrogram_key)
        investigation.audio_metadata.spectrogram_storage_key = spectrogram_key
    except Exception:
        logger.warning(
            "Spectrogram generation failed for investigation %s — continuing without it",
            investigation.id,
            exc_info=True,
        )


def _generate_explanation(investigation, result) -> None:
    """Best-effort, same as spectrogram generation — an LLM/API hiccup
    shouldn't block an otherwise-successful investigation from completing.
    generate_explanation() already has its own internal template fallback
    for a missing API key or a failed call, so this basically can't raise,
    but the try/except stays as defense in depth."""
    try:
        from backend.services.llm_explanation import ExplanationInput, generate_explanation

        investigation.ai_explanation = generate_explanation(
            ExplanationInput(
                prediction=result.prediction,
                confidence=result.confidence,
                fraud_score=result.fraud_score,
                duration_seconds=investigation.audio_metadata.duration_seconds,
                sample_rate=investigation.audio_metadata.sample_rate,
                channels=investigation.audio_metadata.channels,
                attention_regions=result.attention_regions,
            )
        )
    except Exception:
        logger.warning(
            "Explanation generation failed for investigation %s — continuing without it",
            investigation.id,
            exc_info=True,
        )


@celery_app.task(name="backend.workers.tasks.analyze_investigation", bind=True, max_retries=1)
def analyze_investigation(self, investigation_id: str) -> None:
    db = SessionLocal()
    try:
        investigation = (
            db.query(Investigation).filter(Investigation.id == uuid.UUID(investigation_id)).first()
        )
        if investigation is None:
            return  # deleted before the worker picked it up

        if investigation.audio_metadata is None:
            investigation.status = STATUS_FAILED
            db.commit()
            return

        investigation.status = STATUS_PROCESSING
        db.commit()

        started = time.monotonic()

        # Everything that can fail between "processing" and "complete" is
        # inside this one try block — including getting a storage backend
        # itself. Two earlier versions of this function each left a
        # different individual step OUTSIDE any try/except, meaning a
        # failure in just that one step left the investigation stuck at
        # "processing" forever with no way for the frontend to ever learn
        # something had gone wrong, since it only ever polls this row's
        # status. Consolidating everything here, rather than trusting each
        # step individually to remember its own try/except, is deliberate
        # after getting bitten by that twice.
        #
        # predict() itself now runs via run_isolated() (see
        # subprocess_runner.py): a real, confirmed bug showed that a
        # malformed audio file can crash the native decode path outright —
        # not a catchable Python exception, an actual process crash. With
        # this worker on --pool=solo (chosen to dodge a separate PyTorch
        # fork deadlock), there's no parent process to catch that, so it
        # used to take the entire worker down. Isolating this in a
        # subprocess means a crash from any cause — that one, or anything
        # not yet seen — can only kill the subprocess, never the worker.
        try:
            from backend.services.storage import get_storage_backend
            from ml.inference.aasist_wrapper import predict

            storage = get_storage_backend()

            # Spectrogram generation (Phase 4) is separately soft-failing
            # inside _generate_spectrogram — a bad spectrogram shouldn't
            # fail an otherwise-successful fraud analysis. But getting a
            # storage backend at all, and running AASIST itself, are hard
            # failures: if either of those breaks, there's no meaningful
            # result to report.
            _generate_spectrogram(storage, investigation)
            db.commit()

            with storage.local_path(investigation.audio_metadata.storage_key) as path:
                result = run_isolated(predict, path, timeout=PREDICT_TIMEOUT_SECONDS)
        except Exception:
            investigation.status = STATUS_FAILED
            db.commit()
            raise

        elapsed = time.monotonic() - started

        investigation.status = STATUS_COMPLETE
        investigation.prediction = result.prediction
        investigation.confidence = result.confidence
        investigation.fraud_score = result.fraud_score
        investigation.processing_time_seconds = round(elapsed, 3)
        investigation.attention_regions = result.attention_regions

        # Explanation generation (Phase 6) needs the prediction/confidence/
        # fraud_score set above, so it runs after — and like spectrogram
        # generation, is soft-failing: a bad explanation shouldn't undo an
        # otherwise-successful, already-committed-worthy analysis.
        _generate_explanation(investigation, result)

        db.commit()
    finally:
        db.close()
