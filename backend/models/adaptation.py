"""
Adaptation — one tailored version for a specific job offer.
Always references the master resume it was created from.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey

from backend.database import Base


class Adaptation(Base):
    __tablename__ = "adaptations"

    id             = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    master_id      = Column(String, ForeignKey("master_resumes.id"), nullable=False)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))

    # Job info
    job_title       = Column(String, nullable=True)     # inferred from JD
    company_name    = Column(String, nullable=True)     # inferred from JD
    job_description = Column(Text, nullable=False)
    user_instructions = Column(Text, nullable=True)     # additional user notes

    # Analysis
    job_analysis    = Column(JSON, nullable=True)   # extracted requirements, keywords
    blocks_changed  = Column(JSON, nullable=True)   # list of {section, reason, original, adapted}

    # Output
    output_path     = Column(String, nullable=True)  # path to generated .docx
    status          = Column(String, default="pending")  # pending | processing | done | error
    error_msg       = Column(Text, nullable=True)

    # LLM config used
    llm_provider    = Column(String, default="openai")
    llm_model       = Column(String, default="gpt-4o")

    # Application tracking
    job_url         = Column(String, nullable=True)   # URL of the job in job search results
    applied_at      = Column(DateTime, nullable=True) # set when user marks "I applied"
