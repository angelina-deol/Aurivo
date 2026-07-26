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


class AttentionRegion(BaseModel):
    start: float
    end: float
    salience: float


class InvestigationResponse(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    prediction: str | None = None
    confidence: float | None = None
    fraud_score: float | None = None
    processing_time_seconds: float | None = None
    ai_explanation: str | None = None
    attention_regions: list[AttentionRegion] | None = None
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


class DailyCountPoint(BaseModel):
    date: str  # YYYY-MM-DD
    count: int


class DailyRatePoint(BaseModel):
    date: str
    value: float  # 0..100


class HistogramBucket(BaseModel):
    label: str
    count: int


class InvestigationStatsResponse(BaseModel):
    total_analyses: int
    today_analyses_count: int
    fraud_detected_count: int
    real_count: int
    average_confidence: float | None  # 0..1
    average_processing_time_seconds: float | None
    daily_uploads: list[DailyCountPoint]
    daily_fraud_rate: list[DailyRatePoint]  # "detection trend"
    daily_avg_latency: list[DailyRatePoint]  # value = avg processing_time_seconds that day
    confidence_histogram: list[HistogramBucket]
