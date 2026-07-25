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
