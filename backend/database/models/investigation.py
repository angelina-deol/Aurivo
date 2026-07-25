"""
Investigation model — placeholder for Phase 3+.

Once the AASIST inference pipeline is wired up, this table will store one row
per submitted audio analysis (filename, prediction, confidence, fraud score,
processing time, links to the generated report/spectrogram, etc).

Left minimal in Phase 1 so `alembic revision --autogenerate` has something to
track without getting ahead of the ML integration.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from backend.database.session import Base


class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    filename = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="pending")  # pending | processing | complete | failed

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
