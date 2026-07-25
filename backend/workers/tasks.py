"""
Background task: run AASIST inference on an uploaded/recorded investigation.

Runs in a separate Celery worker process, so it opens its own DB session
rather than reusing FastAPI's request-scoped one from database/session.py.
"""
import time
import uuid

from backend.database.models.investigation import (
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    Investigation,
)
from backend.database.session import SessionLocal
from backend.services.storage import get_storage_backend
from backend.workers.celery_app import celery_app


@celery_app.task(name="backend.workers.tasks.analyze_investigation", bind=True, max_retries=1)
def analyze_investigation(self, investigation_id: str) -> None:
    from ml.inference.aasist_wrapper import ModelNotReadyError, predict

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

        storage = get_storage_backend()
        started = time.monotonic()

        try:
            with storage.local_path(investigation.audio_metadata.storage_key) as path:
                result = predict(path)
        except ModelNotReadyError:
            # AASIST/checkpoint not in place on this worker — fail the
            # investigation clearly rather than leaving it stuck at
            # "processing" forever with no explanation.
            investigation.status = STATUS_FAILED
            db.commit()
            raise
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
