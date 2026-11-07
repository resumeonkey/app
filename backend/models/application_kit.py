"""
ApplicationKit — the "Kit de Postulación" (Phase 1) for one job offer.

Groups the tailored CV (via a linked Adaptation), a cover letter, and the
form-answer document built from the approved answer bank. The kit PREPARES the
application; it never submits it.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey

from backend.database import Base


class ApplicationKit(Base):
    __tablename__ = "application_kits"

    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    # Job info (copied from the digest offer)
    job_url      = Column(String, nullable=False, index=True)
    company      = Column(String, nullable=True)
    title        = Column(String, nullable=True)
    list_key     = Column(String, nullable=True)   # canada | chile | remote

    # The tailored CV lives in a linked Adaptation (reuses the existing pipeline)
    adaptation_id = Column(String, ForeignKey("adaptations.id"), nullable=True)

    # Kit content
    cover_letter = Column(Text, nullable=True)
    answers      = Column(JSON, nullable=True)   # {"standard": {...}, "posting_questions": [{question, answer}]}

    # State of the kit's OWN content (cover letter + answers); the CV status is read from the adaptation.
    status       = Column(String, default="pending")   # pending | ready | error
    error_msg    = Column(Text, nullable=True)

    # Application tracking
    applied_at   = Column(DateTime, nullable=True)   # set when the user confirms they applied
