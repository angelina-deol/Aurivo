"""
Tests for backend/workers/tasks.py's DB-update logic.

These call the task function directly (bypassing Redis/the broker entirely
— Celery tasks are plain callables) and mock only `ml.inference.
aasist_wrapper.predict`, since torch isn't installed in this test
environment.

Uses its own isolated in-memory SQLite engine, patched directly into
backend.workers.tasks's SessionLocal — deliberately NOT the real
backend.database.session engine (which is tied to settings.DATABASE_URL,
and therefore to wherever .env happens to be found relative to cwd). Tests
should never depend on an app's real configured database or on which
directory pytest was invoked from; the other test files already follow this
same isolation pattern via FastAPI's dependency_overrides; this file does
the equivalent for a Celery task, which doesn't go through FastAPI's DI.
"""
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.models.audio_metadata import AudioMetadata
from backend.database.models.investigation import STATUS_COMPLETE, STATUS_FAILED, Investigation
from backend.database.models.user import User
from backend.database.session import Base
from backend.workers.tasks import analyze_investigation

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def _setup_db(monkeypatch):
    Base.metadata.create_all(bind=test_engine)
    # backend.workers.tasks imported `SessionLocal` by name at module load
    # time, so the task calls the name bound in ITS OWN module namespace —
    # patch it there, not on backend.database.session.
    monkeypatch.setattr("backend.workers.tasks.SessionLocal", TestSessionLocal)
    yield
    Base.metadata.drop_all(bind=test_engine)


def _make_investigation_with_audio(storage_key="fake-key.wav") -> str:
    db = TestSessionLocal()
    try:
        user = User(email=f"{uuid.uuid4()}@aurivo.ai", hashed_password="x", auth_provider="local")
        db.add(user)
        db.flush()

        investigation = Investigation(user_id=user.id, filename="test.wav", status="processing")
        db.add(investigation)
        db.flush()

        db.add(
            AudioMetadata(
                investigation_id=investigation.id,
                original_filename="test.wav",
                content_type="audio/wav",
                storage_key=storage_key,
                duration_seconds=2.0,
                sample_rate=16000,
                channels=1,
                file_size_bytes=64000,
            )
        )
        db.commit()
        return str(investigation.id)
    finally:
        db.close()


def test_analyze_investigation_success_updates_record():
    investigation_id = _make_investigation_with_audio()

    fake_result = type(
        "PredictionResult", (), {"prediction": "ai_generated", "confidence": 0.94, "fraud_score": 94.2}
    )()

    with patch("ml.inference.aasist_wrapper.predict", return_value=fake_result):
        analyze_investigation(investigation_id)

    db = TestSessionLocal()
    try:
        investigation = db.query(Investigation).filter(Investigation.id == uuid.UUID(investigation_id)).first()
        assert investigation.status == STATUS_COMPLETE
        assert investigation.prediction == "ai_generated"
        assert investigation.confidence == 0.94
        assert investigation.fraud_score == 94.2
        assert investigation.processing_time_seconds is not None
    finally:
        db.close()


def test_analyze_investigation_missing_row_is_a_noop():
    # Investigation deleted before the worker picked up the task — should
    # return quietly, not raise.
    analyze_investigation(str(uuid.uuid4()))


def test_analyze_investigation_marks_failed_on_inference_error():
    investigation_id = _make_investigation_with_audio()

    with patch("ml.inference.aasist_wrapper.predict", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            analyze_investigation(investigation_id)

    db = TestSessionLocal()
    try:
        investigation = db.query(Investigation).filter(Investigation.id == uuid.UUID(investigation_id)).first()
        assert investigation.status == STATUS_FAILED
    finally:
        db.close()
