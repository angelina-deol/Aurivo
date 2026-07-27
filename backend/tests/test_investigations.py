import io
import shutil
import wave
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import get_settings
from backend.database.session import Base, get_db
from backend.main import app

TEST_UPLOAD_DIR = "./test_uploads"

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Route local storage to a throwaway test directory instead of the real
# LOCAL_STORAGE_DIR, and clean it up after the module runs.
get_settings().LOCAL_STORAGE_DIR = TEST_UPLOAD_DIR

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mock_celery_dispatch():
    """Every test in this file exercises the upload endpoint, not the
    inference pipeline itself — patch out the actual Celery enqueue so
    these don't need Redis running (and don't hang for ~60s retrying a
    connection that isn't there)."""
    with patch("backend.api.routes.investigations.analyze_investigation.delay") as mock_delay:
        yield mock_delay


def _make_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generates silent 16-bit mono PCM WAV bytes using only the stdlib."""
    num_frames = int(duration_seconds * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * num_frames)
    buf.seek(0)
    return buf.read()


def _auth_headers() -> dict:
    email = "investigator@aurivo.ai"
    password = "supersecret123"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def teardown_module():
    shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)


def test_upload_valid_wav_creates_investigation():
    headers = _auth_headers()
    wav_bytes = _make_wav_bytes(duration_seconds=2.0, sample_rate=16000)

    response = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("sample.wav", wav_bytes, "audio/wav")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "processing"
    assert body["prediction"] is None
    assert body["audio_metadata"]["sample_rate"] == 16000
    assert body["audio_metadata"]["channels"] == 1
    assert abs(body["audio_metadata"]["duration_seconds"] - 2.0) < 0.05


def test_upload_rejects_unsupported_extension():
    headers = _auth_headers()
    response = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("sample.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 415


def test_upload_rejects_empty_file():
    headers = _auth_headers()
    response = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("empty.wav", b"", "audio/wav")},
    )
    assert response.status_code == 400


def test_upload_rejects_corrupt_wav():
    headers = _auth_headers()
    response = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("bad.wav", b"this is not a real wav file", "audio/wav")},
    )
    assert response.status_code == 422


def test_upload_requires_auth():
    wav_bytes = _make_wav_bytes()
    response = client.post(
        "/api/v1/investigations/analyze",
        files={"file": ("sample.wav", wav_bytes, "audio/wav")},
    )
    assert response.status_code == 401


def test_upload_succeeds_even_if_broker_dispatch_fails():
    """If enqueueing to Celery fails (e.g. Redis is unreachable), the
    upload — which already succeeded and was committed — should still
    return 202 with an honest 'failed' status, not a 500. The investigation
    was already created by the time we dispatch; a broker outage shouldn't
    turn a successful upload into a server error for the client."""
    headers = _auth_headers()
    wav_bytes = _make_wav_bytes()

    with patch(
        "backend.api.routes.investigations.analyze_investigation.delay",
        side_effect=ConnectionError("broker unreachable"),
    ):
        response = client.post(
            "/api/v1/investigations/analyze",
            headers=headers,
            files={"file": ("broker-down.wav", wav_bytes, "audio/wav")},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "failed"


def test_list_get_delete_investigation():
    headers = _auth_headers()
    wav_bytes = _make_wav_bytes()

    upload_resp = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("list-test.wav", wav_bytes, "audio/wav")},
    )
    investigation_id = upload_resp.json()["id"]

    list_resp = client.get("/api/v1/investigations", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    get_resp = client.get(f"/api/v1/investigations/{investigation_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["filename"] == "list-test.wav"

    delete_resp = client.delete(f"/api/v1/investigations/{investigation_id}", headers=headers)
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/api/v1/investigations/{investigation_id}", headers=headers)
    assert missing_resp.status_code == 404


def test_get_investigation_not_owned_by_user_is_404():
    # A second user should never be able to fetch the first user's investigation.
    headers_a = _auth_headers()
    wav_bytes = _make_wav_bytes()
    upload_resp = client.post(
        "/api/v1/investigations/analyze",
        headers=headers_a,
        files={"file": ("private.wav", wav_bytes, "audio/wav")},
    )
    investigation_id = upload_resp.json()["id"]

    client.post(
        "/api/v1/auth/register",
        json={"email": "other-user@aurivo.ai", "password": "supersecret123"},
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": "other-user@aurivo.ai", "password": "supersecret123"},
    )
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    response = client.get(f"/api/v1/investigations/{investigation_id}", headers=headers_b)
    assert response.status_code == 404


def _mark_complete(investigation_id: str, prediction: str, confidence: float, processing_time_seconds: float):
    """Directly sets an investigation to 'complete' with known values,
    bypassing the real Celery task/AASIST model — these tests are about
    the search/filter/stats endpoints, not inference itself."""
    import uuid as uuid_module

    from backend.database.models.investigation import STATUS_COMPLETE, Investigation

    db = TestingSessionLocal()
    try:
        inv = db.query(Investigation).filter(Investigation.id == uuid_module.UUID(investigation_id)).first()
        inv.status = STATUS_COMPLETE
        inv.prediction = prediction
        inv.confidence = confidence
        inv.processing_time_seconds = processing_time_seconds
        inv.fraud_score = round(confidence * 100 if prediction == "ai_generated" else (1 - confidence) * 100, 2)
        db.commit()
    finally:
        db.close()


def test_list_investigations_search_by_filename():
    headers = _auth_headers()
    client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("quarterly-earnings-call.wav", _make_wav_bytes(), "audio/wav")},
    )
    client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("voicemail-from-mom.wav", _make_wav_bytes(), "audio/wav")},
    )

    response = client.get("/api/v1/investigations?search=earnings", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["filename"] == "quarterly-earnings-call.wav"


def test_list_investigations_filter_by_status():
    headers = _auth_headers()
    upload_resp = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("to-complete.wav", _make_wav_bytes(), "audio/wav")},
    )
    _mark_complete(upload_resp.json()["id"], "real", 0.8, 1.5)

    client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("still-processing.wav", _make_wav_bytes(), "audio/wav")},
    )

    response = client.get("/api/v1/investigations?status=complete", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert all(item["status"] == "complete" for item in body["items"])
    assert any(item["filename"] == "to-complete.wav" for item in body["items"])
    assert not any(item["filename"] == "still-processing.wav" for item in body["items"])


def test_list_investigations_filter_by_prediction():
    headers = _auth_headers()
    real_resp = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("real-one.wav", _make_wav_bytes(), "audio/wav")},
    )
    fake_resp = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("fake-one.wav", _make_wav_bytes(), "audio/wav")},
    )
    _mark_complete(real_resp.json()["id"], "real", 0.9, 1.0)
    _mark_complete(fake_resp.json()["id"], "ai_generated", 0.95, 1.2)

    response = client.get("/api/v1/investigations?prediction=ai_generated", headers=headers)
    body = response.json()
    filenames = [item["filename"] for item in body["items"]]
    assert "fake-one.wav" in filenames
    assert "real-one.wav" not in filenames


def test_stats_endpoint_aggregates_correctly():
    email = "stats-test-user@aurivo.ai"
    client.post("/api/v1/auth/register", json={"email": email, "password": "supersecret123"})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    real1 = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("stats-real-1.wav", _make_wav_bytes(), "audio/wav")},
    ).json()["id"]
    real2 = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("stats-real-2.wav", _make_wav_bytes(), "audio/wav")},
    ).json()["id"]
    fake1 = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("stats-fake-1.wav", _make_wav_bytes(), "audio/wav")},
    ).json()["id"]

    _mark_complete(real1, "real", 0.8, 1.0)
    _mark_complete(real2, "real", 0.6, 2.0)
    _mark_complete(fake1, "ai_generated", 0.9, 3.0)

    response = client.get("/api/v1/investigations/stats", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert body["total_analyses"] == 3
    assert body["today_analyses_count"] == 3
    assert body["fraud_detected_count"] == 1
    assert body["real_count"] == 2
    assert abs(body["average_confidence"] - ((0.8 + 0.6 + 0.9) / 3)) < 1e-3
    assert abs(body["average_processing_time_seconds"] - 2.0) < 1e-3
    assert len(body["daily_uploads"]) == 14
    assert len(body["daily_fraud_rate"]) == 14
    assert len(body["confidence_histogram"]) == 10
    # today's bucket (last entry, since the window is oldest -> newest) should show all 3 uploads
    assert body["daily_uploads"][-1]["count"] == 3


def test_stats_endpoint_requires_auth():
    response = client.get("/api/v1/investigations/stats")
    assert response.status_code == 401


def _age_investigation(investigation_id: str, seconds_ago: float):
    """Backdates updated_at to simulate an investigation that's been
    'processing' for a while — standing in for a worker that crashed
    mid-task (e.g. OOM-killed) and never got the chance to mark it failed
    itself, since a SIGKILL bypasses every try/except in the task."""
    import uuid as uuid_module
    from datetime import datetime, timedelta, timezone

    from backend.database.models.investigation import Investigation

    db = TestingSessionLocal()
    try:
        inv = db.query(Investigation).filter(Investigation.id == uuid_module.UUID(investigation_id)).first()
        inv.updated_at = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        db.commit()
    finally:
        db.close()


def test_stale_processing_investigation_gets_marked_failed_on_fetch():
    headers = _auth_headers()
    upload_resp = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("stuck.wav", _make_wav_bytes(), "audio/wav")},
    )
    investigation_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "processing"

    _age_investigation(investigation_id, seconds_ago=400)  # older than the 360s threshold

    response = client.get(f"/api/v1/investigations/{investigation_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_recently_processing_investigation_is_not_marked_failed():
    """A genuinely in-flight investigation (well within the time limit)
    must not get swept up as 'stale' just for still being in progress."""
    headers = _auth_headers()
    upload_resp = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("still-going.wav", _make_wav_bytes(), "audio/wav")},
    )
    investigation_id = upload_resp.json()["id"]

    _age_investigation(investigation_id, seconds_ago=30)  # well under the 360s threshold

    response = client.get(f"/api/v1/investigations/{investigation_id}", headers=headers)
    assert response.json()["status"] == "processing"


def test_stale_reconciliation_also_applies_in_list_endpoint():
    headers = _auth_headers()
    upload_resp = client.post(
        "/api/v1/investigations/analyze",
        headers=headers,
        files={"file": ("stuck-in-list.wav", _make_wav_bytes(), "audio/wav")},
    )
    investigation_id = upload_resp.json()["id"]
    _age_investigation(investigation_id, seconds_ago=400)

    response = client.get("/api/v1/investigations?search=stuck-in-list", headers=headers)
    body = response.json()
    assert body["items"][0]["status"] == "failed"
