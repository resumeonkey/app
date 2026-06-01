"""
MasterResume — the single source of truth.
Only one active master exists at a time; older ones are archived.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Boolean, JSON

from backend.database import Base


class MasterResume(Base):
    __tablename__ = "master_resumes"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))

    # File info
    original_filename = Column(String, nullable=False)
    file_path         = Column(String, nullable=False)   # path to original docx/pdf
    file_type         = Column(String, nullable=False)   # "docx" | "pdf"

    # Parsed content (structured representation of the resume)
    full_text         = Column(Text, nullable=True)      # plain text version
    sections          = Column(JSON, nullable=True)      # {section_name: {text, paragraph_indices}}
    candidate_name    = Column(String, nullable=True)

    # State
    is_active         = Column(Boolean, default=True)    # only one active at a time
    notes             = Column(Text, nullable=True)      # optional user notes about this master

    # Candidate profile preferences (persist across searches)
    english_level     = Column(String, default="any", nullable=True)
    # "any" | "basic" | "conversational" | "professional" | "fluent"

    # Comma-separated expertise tags set by the candidate.
    # Used as explicit primary-skill signals in query generation and scoring.
    # Example: "QA, Testing, SQL, Product Owner, Implementation, Telecom, APIs"
    profile_tags      = Column(Text, nullable=True)
