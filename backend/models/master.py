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

    # ── Search profile — persists across searches ────────────────────────────
    # A master resume IS a search profile. Users create one master per career
    # track (e.g. "Tech / QA", "Hospitality", "Operations") and switch between
    # them in the search UI. All fields are generic — no assumptions about industry.

    profile_name      = Column(String, nullable=True)   # e.g. "Tech / Implementation"
    english_level     = Column(String, default="any", nullable=True)
    # "any" | "basic" | "conversational" | "professional" | "fluent"

    # Technical / functional keywords (primary expertise signal for LLM)
    # Example: "QA, Testing, SQL, Product Owner, Implementation, APIs"
    profile_tags      = Column(Text, nullable=True)

    # Job titles the candidate WANTS to find (comma-separated)
    # Example: "Implementation Specialist, QA Analyst, Business Systems Analyst"
    target_roles      = Column(Text, nullable=True)

    # Job title terms the candidate does NOT want to see (comma-separated)
    # Filtered out before scoring. Example: "Construction, Civil, MEP, Superintendent"
    excluded_roles    = Column(Text, nullable=True)

    # Industries where the candidate already HAS experience (for domain scoring)
    # Example: "Telecommunications, Banking, Contact Center, Software Testing"
    industry_experience = Column(Text, nullable=True)

    # Industries the candidate WANTS to work in (used in query generation)
    # Example: "Technology, SaaS, Fintech, Healthcare Technology"
    target_industries = Column(Text, nullable=True)

    # ── Trade-treaty visa eligibility — drives proximity weighting ───────────
    # Country of citizenship + education level determine which Canadian FTAs the
    # candidate can use for LMIA-exempt temporary entry (CPTPP, CCFTA, etc.).
    # See backend/services/treaty_eligibility.py for the country→treaty matrix.
    citizenship       = Column(String, nullable=True)        # e.g. "Chile"
    education_level   = Column(String, default="none", nullable=True)
    # "none" | "technical" (2-yr) | "university" (4-yr)
    prioritize_treaty = Column(Boolean, default=False)       # boost treaty-eligible jobs
