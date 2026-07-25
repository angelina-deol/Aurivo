import uuid
from datetime import datetime

from pydantic import BaseModel


class AudioMetadataResponse(BaseModel):
    original_filename: str
    content_type: str
    duration_seconds: float
    sample_rate: int
    channels: int
    file_size_bytes: int
    noise_level: float | None = None
    speech_duration_seconds: float | None = None
    silence_ratio: float | None = None
    has_spectrogram: bool = False

    class Config:
        from_attributes = True


class InvestigationResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    prediction: str | None = None
    confidence: float | None = None
    fraud_score: float | None = None
    processing_time_seconds: float | None = None
    created_at: datetime
    updated_at: datetime
    audio_metadata: AudioMetadataResponse | None = None

    class Config:
        from_attributes = True


class InvestigationListResponse(BaseModel):
    items: list[InvestigationResponse]
    total: int
    limit: int
    offset: int
