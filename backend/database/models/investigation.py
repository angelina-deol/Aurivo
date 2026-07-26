"""
Investigation model.

Phase 2 creates a real row per uploaded/recorded audio file, with its
metadata attached via the one-to-one AudioMetadata relationship. The
prediction/confidence/fraud-score fields land in Phase 3 once AASIST
inference is wired up — until then, `status` stays "awaiting_analysis" and
those columns stay null.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.database.session import Base

# pending           -> row created, upload in progress (not currently used,
#                      reserved for chunked/resumable uploads later)
# awaiting_analysis -> upload complete, no ML worker exists yet (Phase 2 state)
# processing        -> queued to Celery, AASIST running (Phase 3+)
# complete          -> prediction available (Phase 3+)
# failed            -> upload or analysis failed
STATUS_AWAITING_ANALYSIS = "awaiting_analysis"
STATUS_PROCESSING = "processing"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    filename = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default=STATUS_AWAITING_ANALYSIS)

    # Populated in Phase 3+ by the AASIST inference worker.
    prediction = Column(String(50), nullable=True)  # "real" | "ai_generated"
    confidence = Column(Float, nullable=True)
    fraud_score = Column(Float, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)

    # Populated in Phase 6. ai_explanation is always set on a completed
    # investigation (template fallback if no LLM API key is configured —
    # see services/llm_explanation.py). attention_regions is None when the
    # attention map couldn't be captured for some reason; both are
    # generated as soft-failure steps, same as the spectrogram.
    ai_explanation = Column(String(2000), nullable=True)
    attention_regions = Column(JSON, nullable=True)  # [{"start", "end", "salience"}, ...]

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    audio_metadata = relationship(
        "AudioMetadata",
        uselist=False,
        cascade="all, delete-orphan",
        backref="investigation",
    )
