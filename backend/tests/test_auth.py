from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.session import Base, get_db
from backend.main import app

# In-memory SQLite for fast, isolated test runs — the real deployment always
# uses Postgres (see docker-compose.yml / config.py).
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
client = TestClient(app)


def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_and_login():
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "analyst@aurivo.ai", "password": "supersecret123"},
    )
    assert register_resp.status_code == 201
    assert register_resp.json()["email"] == "analyst@aurivo.ai"

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "analyst@aurivo.ai", "password": "supersecret123"},
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    assert "access_token" in tokens

    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "analyst@aurivo.ai"


def test_login_wrong_password_rejected():
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "analyst@aurivo.ai", "password": "wrongpassword"},
    )
    assert response.status_code == 401
