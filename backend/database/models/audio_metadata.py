import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from backend.database.session import Base


class AudioMetadata(Base):
    __tablename__ = "audio_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id = Column(
        UUID(as_uuid=True), ForeignKey("investigations.id"), nullable=False, unique=True
    )

    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    storage_key = Column(String(512), nullable=False)

    duration_seconds = Column(Float, nullable=False)
    sample_rate = Column(Integer, nullable=False)
    channels = Column(Integer, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)

    # Populated in Phase 3+ once ml/preprocessing computes them.
    noise_level = Column(Float, nullable=True)
    speech_duration_seconds = Column(Float, nullable=True)
    silence_ratio = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
