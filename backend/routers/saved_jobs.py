"""
Saved jobs endpoints.

  GET    /api/jobs/saved          → list all saved jobs
  GET    /api/jobs/saved/urls     → just the saved URLs (fast "is saved?" check)
  POST   /api/jobs/saved          → save a job
  DELETE /api/jobs/saved/{id}     → unsave by id
  DELETE /api/jobs/saved/url      → unsave by URL
  PATCH  /api/jobs/saved/{id}     → update notes / applied_at
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.saved_job import SavedJob

router = APIRouter()


# ── Pydantic ──────────────────────────────────────────────────────────────────

class SaveJobRequest(BaseModel):
    url:                 str
    title:               Optional[str] = None
    company:             Optional[str] = None
    location:            Optional[str] = None
    snippet:             Optional[str] = None
    salary:              Optional[str] = None
    date_posted:         Optional[str] = None
    source:              Optional[str] = None
    compatibility_score: Optional[int] = None
    matched_skills:      Optional[list] = None
    missing_skills:      Optional[list] = None
    score_summary:       Optional[str]  = None
    confidence:          Optional[str]  = None
    blockers:            Optional[list] = None
    why_relevant:        Optional[list] = None
    lmia_approved:       bool = False
    ccfta_eligible:      bool = False
    immigration_support: Optional[str]  = None
    bilingual_advantage: bool = False
    english_barrier:     bool = False
    english_required:    Optional[str]  = None
    notes:               Optional[str]  = None


class PatchSavedJobRequest(BaseModel):
    notes:    Optional[str]  = None
    applied:  Optional[bool] = None   # True = mark applied, False = unmark


class UnsaveByUrlRequest(BaseModel):
    url: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(job: SavedJob) -> dict:
    return {
        "id":                  job.id,
        "created_at":          job.created_at.isoformat() if job.created_at else None,
        "url":                 job.url,
        "title":               job.title,
        "company":             job.company,
        "location":            job.location,
        "snippet":             job.snippet,
        "salary":              job.salary,
        "date_posted":         job.date_posted,
        "source":              job.source,
        "compatibility_score": job.compatibility_score,
        "matched_skills":      job.matched_skills or [],
        "missing_skills":      job.missing_skills or [],
        "score_summary":       job.score_summary,
        "confidence":          job.confidence,
        "blockers":            job.blockers or [],
        "why_relevant":        job.why_relevant or [],
        "lmia_approved":       job.lmia_approved,
        "ccfta_eligible":      job.ccfta_eligible,
        "immigration_support": job.immigration_support,
        "bilingual_advantage": job.bilingual_advantage,
        "english_barrier":     job.english_barrier,
        "english_required":    job.english_required,
        "notes":               job.notes,
        "applied_at":          job.applied_at.isoformat() if job.applied_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def list_saved_jobs(db: Session = Depends(get_db)):
    jobs = db.query(SavedJob).order_by(SavedJob.created_at.desc()).all()
    return {"saved_jobs": [_serialize(j) for j in jobs]}


@router.get("/urls")
def list_saved_urls(db: Session = Depends(get_db)):
    """Return just the set of saved URLs — used by the frontend to mark cards."""
    rows = db.query(SavedJob.url, SavedJob.id).all()
    return {"urls": {url: id for url, id in rows}}


@router.post("")
def save_job(req: SaveJobRequest, db: Session = Depends(get_db)):
    # If already saved, return the existing record
    existing = db.query(SavedJob).filter(SavedJob.url == req.url).first()
    if existing:
        return _serialize(existing)

    job = SavedJob(
        url=req.url,
        title=req.title,
        company=req.company,
        location=req.location,
        snippet=req.snippet,
        salary=req.salary,
        date_posted=req.date_posted,
        source=req.source,
        compatibility_score=req.compatibility_score,
        matched_skills=req.matched_skills,
        missing_skills=req.missing_skills,
        score_summary=req.score_summary,
        confidence=req.confidence,
        blockers=req.blockers,
        why_relevant=req.why_relevant,
        lmia_approved=req.lmia_approved,
        ccfta_eligible=req.ccfta_eligible,
        immigration_support=req.immigration_support,
        bilingual_advantage=req.bilingual_advantage,
        english_barrier=req.english_barrier,
        english_required=req.english_required,
        notes=req.notes,
    )
    try:
        db.add(job)
        db.commit()
        db.refresh(job)
    except IntegrityError:
        db.rollback()
        existing = db.query(SavedJob).filter(SavedJob.url == req.url).first()
        return _serialize(existing)
    return _serialize(job)


@router.delete("/by-url")
def unsave_by_url(req: UnsaveByUrlRequest, db: Session = Depends(get_db)):
    job = db.query(SavedJob).filter(SavedJob.url == req.url).first()
    if not job:
        raise HTTPException(status_code=404, detail="No guardado.")
    db.delete(job)
    db.commit()
    return {"ok": True}


@router.delete("/{job_id}")
def unsave_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(SavedJob).filter(SavedJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="No encontrado.")
    db.delete(job)
    db.commit()
    return {"ok": True}


@router.patch("/{job_id}")
def patch_saved_job(job_id: str, req: PatchSavedJobRequest, db: Session = Depends(get_db)):
    job = db.query(SavedJob).filter(SavedJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="No encontrado.")
    if req.notes is not None:
        job.notes = req.notes
    if req.applied is not None:
        job.applied_at = datetime.now(timezone.utc) if req.applied else None
    db.commit()
    db.refresh(job)
    return _serialize(job)
