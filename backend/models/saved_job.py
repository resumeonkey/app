"""
SavedJob — a job listing bookmarked by the user.
Persists across searches. One row per saved job (unique by URL).
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Integer, JSON, Boolean

from backend.database import Base


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Job data from search results
    url        = Column(String, nullable=False, unique=True, index=True)
    title      = Column(String, nullable=True)
    company    = Column(String, nullable=True)
    location   = Column(String, nullable=True)
    snippet    = Column(Text, nullable=True)
    salary     = Column(String, nullable=True)
    date_posted = Column(String, nullable=True)
    source     = Column(String, nullable=True)   # linkedin | jobbank | workopolis | eluta

    # Scoring data (snapshot at time of save)
    compatibility_score = Column(Integer, nullable=True)
    matched_skills      = Column(JSON, nullable=True)
    missing_skills      = Column(JSON, nullable=True)
    score_summary       = Column(Text, nullable=True)
    confidence          = Column(String, nullable=True)
    blockers            = Column(JSON, nullable=True)
    why_relevant        = Column(JSON, nullable=True)

    # Immigration flags
    lmia_approved       = Column(Boolean, default=False)
    ccfta_eligible      = Column(Boolean, default=False)
    immigration_support = Column(String, nullable=True)
    bilingual_advantage = Column(Boolean, default=False)
    english_barrier     = Column(Boolean, default=False)
    english_required    = Column(String, nullable=True)

    # User notes (optional)
    notes = Column(Text, nullable=True)

    # Application tracking
    applied_at = Column(DateTime(timezone=True), nullable=True)
