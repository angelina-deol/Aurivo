"""
Tests for backend/workers/tasks.py's DB-update logic.

These call the task function directly (bypassing Redis/the broker entirely
— Celery tasks are plain callables) and mock only `ml.inference.
aasist_wrapper.predict`, since torch isn't installed in this test
environment. Spectrogram generation (Phase 4) uses real scipy/matplotlib
computation against a real generated WAV file — not mocked — since neither
of those needs torch and both are already proven dependencies elsewhere in
this suite.

Uses its own isolated in-memory SQLite engine, patched directly into
backend.workers.tasks's SessionLocal — deliberately NOT the real
backend.database.session engine (which is tied to settings.DATABASE_URL,
and therefore to wherever .env happens to be found relative to cwd). Tests
should never depend on an app's real configured database or on which
directory pytest was invoked from; the other test files already follow this
same isolation pattern via FastAPI's dependency_overrides; this file does
the equivalent for a Celery task, which doesn't go through FastAPI's DI.
"""
import io
import shutil
import uuid
import wave
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.models.audio_metadata import AudioMetadata
from backend.database.models.investigation import STATUS_COMPLETE, STATUS_FAILED, Investigation
from backend.database.models.user import User
from backend.database.session import Base
from backend.services.storage import LocalDiskStorage
from backend.workers.tasks import analyze_investigation

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

TEST_STORAGE_DIR = "./test_worker_uploads"


@pytest.fixture(autouse=True)
def _setup_db(monkeypatch):
    Base.metadata.create_all(bind=test_engine)
    # backend.workers.tasks imported `SessionLocal` by name at module load
    # time, so the task calls the name bound in ITS OWN module namespace —
    # patch it there, not on backend.database.session.
    monkeypatch.setattr("backend.workers.tasks.SessionLocal", TestSessionLocal)
    yield
    Base.metadata.drop_all(bind=test_engine)
    shutil.rmtree(TEST_STORAGE_DIR, ignore_errors=True)


def _make_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    num_frames = int(duration_seconds * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        # A silent clip is enough for scipy.signal.spectrogram to run on —
        # this test is about the pipeline wiring, not the visual content.
        wav_file.writeframes(b"\x00\x00" * num_frames)
    buf.seek(0)
    return buf.read()


def _make_investigation_with_audio(real_file: bool = False, storage_key: str = "fake-key.wav") -> str:
    """By default uses a storage_key that doesn't point to a real file —
    fine for tests that mock predict() entirely and don't care whether
    spectrogram generation succeeds (it's a soft failure either way). Pass
    real_file=True to actually write a real WAV so spectrogram generation
    can be tested for real."""
    if real_file:
        storage = LocalDiskStorage(TEST_STORAGE_DIR)
        storage.save(io.BytesIO(_make_wav_bytes()), storage_key)

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


@pytest.fixture(autouse=True)
def _use_test_storage_dir():
    with patch("backend.services.storage.settings.LOCAL_STORAGE_DIR", TEST_STORAGE_DIR):
        yield


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


def test_analyze_investigation_marks_failed_if_ml_import_itself_fails():
    """Regression test for a real bug: an earlier version imported
    ml.inference.aasist_wrapper at the top of the task function, outside
    any try/except. If that import failed (e.g. ml/ not mounted correctly,
    exactly what happened when the ml/ volume wasn't visible in a worker
    container), the investigation was never marked failed — it stayed at
    "processing" forever, and the frontend polled indefinitely with no way
    to ever learn something had gone wrong. The import must happen inside
    the try block so this case is caught the same as any other failure."""
    investigation_id = _make_investigation_with_audio()

    with patch(
        "backend.services.storage.get_storage_backend",
        side_effect=ModuleNotFoundError("No module named 'ml'"),
    ):
        with pytest.raises(ModuleNotFoundError):
            analyze_investigation(investigation_id)

    db = TestSessionLocal()
    try:
        investigation = db.query(Investigation).filter(Investigation.id == uuid.UUID(investigation_id)).first()
        assert investigation.status == STATUS_FAILED, (
            "investigation must be marked failed, not left stuck at "
            "'processing' forever, when something fails before inference "
            "even starts"
        )
    finally:
        db.close()


def test_analyze_investigation_generates_real_spectrogram():
    """Phase 4: a real WAV goes in, a real spectrogram PNG should come out
    — not mocked, since spectrogram generation only needs scipy/matplotlib
    (already proven dependencies), not torch."""
    investigation_id = _make_investigation_with_audio(real_file=True, storage_key="spec-test.wav")

    fake_result = type(
        "PredictionResult", (), {"prediction": "real", "confidence": 0.7, "fraud_score": 30.0}
    )()

    with patch("ml.inference.aasist_wrapper.predict", return_value=fake_result):
        analyze_investigation(investigation_id)

    db = TestSessionLocal()
    try:
        investigation = db.query(Investigation).filter(Investigation.id == uuid.UUID(investigation_id)).first()
        assert investigation.status == STATUS_COMPLETE
        key = investigation.audio_metadata.spectrogram_storage_key
        assert key is not None, "spectrogram should have been generated for a real audio file"
        assert investigation.audio_metadata.has_spectrogram is True

        storage = LocalDiskStorage(TEST_STORAGE_DIR)
        with storage.local_path(key) as path:
            with open(path, "rb") as f:
                png_bytes = f.read()
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n", "stored file should be a real PNG"
    finally:
        db.close()


def test_analyze_investigation_completes_even_if_spectrogram_generation_fails():
    """Spectrogram generation is a soft failure by design — if it fails
    (e.g. a corrupt/unreadable file), the investigation should still be
    able to complete with a real fraud prediction, just without an
    attached spectrogram."""
    investigation_id = _make_investigation_with_audio()  # fake_key.wav — no real file on disk

    fake_result = type(
        "PredictionResult", (), {"prediction": "real", "confidence": 0.6, "fraud_score": 40.0}
    )()

    with patch("ml.inference.aasist_wrapper.predict", return_value=fake_result):
        analyze_investigation(investigation_id)

    db = TestSessionLocal()
    try:
        investigation = db.query(Investigation).filter(Investigation.id == uuid.UUID(investigation_id)).first()
        assert investigation.status == STATUS_COMPLETE
        assert investigation.audio_metadata.spectrogram_storage_key is None
    finally:
        db.close()
