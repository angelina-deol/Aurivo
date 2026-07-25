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

logger = logging.getLogger(__name__)


def _generate_spectrogram(storage, investigation) -> None:
    """Best-effort — spectrogram generation failing should never block the
    investigation from completing with a real fraud prediction. Any
    failure here is swallowed and logged, not re-raised."""
    try:
        from ml.preprocessing.spectrogram import generate_spectrogram_png
        from backend.services.storage import build_storage_key

        with storage.local_path(investigation.audio_metadata.storage_key) as path:
            png_bytes = generate_spectrogram_png(path)

        spectrogram_key = build_storage_key(f"{investigation.id}-spectrogram.png")
        storage.save(io.BytesIO(png_bytes), spectrogram_key)
        investigation.audio_metadata.spectrogram_storage_key = spectrogram_key
    except Exception:
        logger.warning(
            "Spectrogram generation failed for investigation %s — continuing without it",
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
        # different individual step (the ml import, then
        # get_storage_backend() called separately for the spectrogram step)
        # OUTSIDE any try/except, meaning a failure in just that one step
        # left the investigation stuck at "processing" forever with no way
        # for the frontend to ever learn something had gone wrong, since it
        # only ever polls this row's status. Consolidating everything here,
        # rather than trusting each step individually to remember its own
        # try/except, is deliberate after getting bitten by that twice.
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
                result = predict(path)
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
        db.commit()
    finally:
        db.close()
