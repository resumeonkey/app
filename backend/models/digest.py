import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Integer

from backend.database import Base


class DigestSent(Base):
    """Track job URLs already emailed to avoid repeats across digest runs."""
    __tablename__ = "digest_sent"

    id       = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_url  = Column(Text, nullable=False, unique=True, index=True)
    title    = Column(String, nullable=True)
    company  = Column(String, nullable=True)
    score    = Column(Integer, nullable=True)
    sent_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
