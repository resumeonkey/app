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


class DigestJob(Base):
    """Full text of every offer that was emailed, so it can be read later without scraping the source again."""
    __tablename__ = "digest_jobs"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_url     = Column(Text, nullable=False, unique=True, index=True)
    list_key    = Column(String, nullable=True)       # canada | chile | remote
    title       = Column(String, nullable=True)
    company     = Column(String, nullable=True)
    location    = Column(String, nullable=True)
    source      = Column(String, nullable=True)
    score       = Column(Integer, nullable=True)
    reason      = Column(Text, nullable=True)
    description = Column(Text, nullable=True)         # full posting text (empty if the source blocked it)
    first_sent  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
