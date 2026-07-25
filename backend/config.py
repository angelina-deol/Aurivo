"""
Central configuration for Aurivo backend.
All values are overridable via environment variables / .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "Aurivo"
    ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Security / Auth ---
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Signs the OAuth state/nonce cookie during the Google login redirect
    # round-trip. Separate from JWT_SECRET_KEY so rotating one doesn't
    # invalidate the other.
    SESSION_SECRET_KEY: str = "change-me-in-production-too"

    # Where to send the browser after a successful OAuth login completes.
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    # --- OAuth (Google) ---
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg2://aurivo:aurivo@postgres:5432/aurivo"

    # --- Redis / Celery (used starting Phase 3 for the inference queue) ---
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # --- Object storage (S3-compatible; used starting Phase 2 for uploads) ---
    # If S3_ACCESS_KEY/S3_SECRET_KEY are unset, storage falls back to local
    # disk under LOCAL_STORAGE_DIR — no AWS/MinIO account needed for local
    # dev. Set them (plus S3_ENDPOINT_URL for MinIO/R2/etc, or leave unset
    # for real AWS) to switch to S3-compatible storage.
    S3_ENDPOINT_URL: str | None = None
    S3_BUCKET: str = "aurivo-audio"
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_REGION: str = "us-east-1"
    LOCAL_STORAGE_DIR: str = "./uploads"

    # --- Upload limits ---
    MAX_UPLOAD_SIZE_MB: int = 100
    ALLOWED_AUDIO_CONTENT_TYPES: list[str] = [
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/flac",
        "audio/x-flac",
        "audio/mpeg",
        "audio/mp3",
    ]
    ALLOWED_AUDIO_EXTENSIONS: list[str] = [".wav", ".flac", ".mp3"]

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
