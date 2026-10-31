"""
Daily job digest — search + score + email.

POST /api/digest/run
  Fetches fresh jobs from ATS boards + Jina search, scores them against
  the active master profile, filters already-applied/sent ones, and emails
  the top results via Resend.

Protected by X-Digest-Key header (set DIGEST_API_KEY in environment).
"""
import csv
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.models.digest import DigestSent
from backend.models.master import MasterResume
from backend.services.ats_client import fetch_ats_jobs
from backend.services.email_service import send_digest_email
from backend.services.job_search import batch_score_jobs, search_jobs_via_jina

log = logging.getLogger(__name__)
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data"

# ── Auth helper ───────────────────────────────────────────────────────────────

def _require_digest_key(x_digest_key: str = Header(default="")):
    settings = get_settings()
    expected = settings.digest_api_key
    if expected and x_digest_key != expected:
        raise HTTPException(status_code=401, detail="Invalid digest key")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_applied_companies() -> set[str]:
    """Load company names from applied.csv (lowercase, for dedup)."""
    path = _DATA_DIR / "applied.csv"
    if not path.exists():
        return set()
    applied: set[str] = set()
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                company = (row.get("company") or "").strip().lower()
                if company:
                    applied.add(company)
    except Exception as exc:
        log.warning("digest: could not read applied.csv: %s", exc)
    return applied


def _already_sent_urls(db: Session) -> set[str]:
    rows = db.query(DigestSent.job_url).all()
    return {r.job_url for r in rows}


def _record_sent(db: Session, jobs: list[dict]) -> None:
    for j in jobs:
        url = j.get("url", "")
        if not url:
            continue
        if db.query(DigestSent).filter(DigestSent.job_url == url).first():
            continue
        db.add(DigestSent(
            job_url=url,
            title=j.get("title"),
            company=j.get("company"),
            score=j.get("score"),
        ))
    db.commit()


def _build_profile_text_simple(master: MasterResume) -> str:
    """Minimal profile text from master fields (for query building)."""
    parts = []
    if master.target_roles:
        parts.append(master.target_roles)
    if master.profile_tags:
        parts.append(master.profile_tags)
    if master.industry_experience:
        parts.append(master.industry_experience)
    return " ".join(parts)


def _dedupe_by_url(jobs: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result = []
    for j in jobs:
        url = j.get("url", "")
        if url and url not in seen:
            seen.add(url)
            result.append(j)
    return result


_MAX_SCORE_CANDIDATES = 40
_ATS_SOURCES = {"greenhouse", "ashby", "lever"}
_STOPWORDS = {"canada", "senior", "junior", "remote", "with", "and", "the"}


def _prefilter_jobs(jobs: list[dict], roles: list[str]) -> list[dict]:
    """Keep ATS jobs whose title shares a keyword with the target roles, capped for LLM scoring."""
    words = {w for r in roles for w in re.findall(r"[a-z]{4,}", r.lower())} - _STOPWORDS
    ranked = []
    for j in jobs:
        title = (j.get("title") or "").lower()
        hits = sum(1 for w in words if w in title)
        if hits or j.get("source") not in _ATS_SOURCES:
            ranked.append((hits, j))
    ranked.sort(key=lambda t: t[0], reverse=True)
    return [j for _, j in ranked[:_MAX_SCORE_CANDIDATES]]


# ── Response models ───────────────────────────────────────────────────────────

class DigestResult(BaseModel):
    jobs_found: int
    jobs_scored: int
    jobs_emailed: int
    email_sent: bool
    top_jobs: list[dict]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/run", response_model=DigestResult, dependencies=[Depends(_require_digest_key)])
async def run_digest(
    llm_provider: str = "groq",
    llm_model: str = "llama-3.1-8b-instant",
    min_score: int = 5,
    max_jobs: int = 8,
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """
    Run the full daily digest pipeline:
    1. Fetch jobs from ATS boards (Greenhouse/Ashby/Lever)
    2. Jina LinkedIn search using target_roles from active master
    3. Filter applied + already-sent
    4. Score with LLM
    5. Email top results
    6. Record sent job URLs

    dry_run=true: skips email send and database recording.
    """
    # 1. Active master profile
    master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
    if not master or not master.sections:
        raise HTTPException(status_code=422, detail="No active master resume found. Upload a resume first.")

    applied_co   = _load_applied_companies()
    sent_urls    = _already_sent_urls(db)

    # 2. ATS jobs (Greenhouse/Ashby/Lever from companies.yaml)
    log.info("digest: fetching ATS board jobs")
    try:
        ats_jobs = await fetch_ats_jobs()
        log.info("digest: ATS returned %d jobs", len(ats_jobs))
    except Exception as exc:
        log.warning("digest: ATS fetch error: %s", exc)
        ats_jobs = []

    # 3. Jina search — one query per target role (max 3 to stay within rate limits)
    jina_jobs: list[dict] = []
    target_roles = master.target_roles or ""
    roles = [r.strip() for r in target_roles.split(",") if r.strip()][:3]
    if not roles:
        roles = ["Implementation Consultant Canada", "QA Analyst Canada"]

    for role in roles:
        log.info("digest: jina search for '%s'", role)
        try:
            results = await search_jobs_via_jina(
                query=role,
                num_results=6,
                location="Canada",
                remote="any",
                date_posted="7d",
            )
            jina_jobs.extend(results)
        except Exception as exc:
            log.warning("digest: jina search '%s' failed: %s", role, exc)

    log.info("digest: jina returned %d jobs", len(jina_jobs))

    # 4. Combine + deduplicate
    all_jobs = _dedupe_by_url(ats_jobs + jina_jobs)
    log.info("digest: combined %d unique jobs", len(all_jobs))

    # 5. Filter: already applied to this company AND already emailed this URL
    def _is_excluded(job: dict) -> bool:
        company_norm = (job.get("company") or "").strip().lower()
        url = job.get("url", "")
        if any(applied in company_norm or company_norm in applied for applied in applied_co):
            return True
        if url in sent_urls:
            return True
        return False

    fresh_jobs = [j for j in all_jobs if not _is_excluded(j)]
    log.info("digest: %d fresh jobs after dedup filter", len(fresh_jobs))

    fresh_jobs = _prefilter_jobs(fresh_jobs, roles)
    log.info("digest: %d candidates after role prefilter", len(fresh_jobs))

    if not fresh_jobs:
        log.info("digest: nothing new to email")
        return DigestResult(
            jobs_found=len(all_jobs),
            jobs_scored=0,
            jobs_emailed=0,
            email_sent=False,
            top_jobs=[],
        )

    # 6. Score with LLM
    log.info("digest: scoring %d jobs with %s/%s", len(fresh_jobs), llm_provider, llm_model)
    scored = await batch_score_jobs(
        raw_jobs=fresh_jobs,
        master_sections=master.sections,
        provider=llm_provider,
        model=llm_model,
        profile_tags=master.profile_tags or "",
        industry_experience=master.industry_experience or "",
        target_industries=master.target_industries or "",
    )

    # 7. Sort by score and take top N above threshold
    top = sorted(
        [j for j in scored if (j.get("score") or 0) >= min_score],
        key=lambda j: j.get("score", 0),
        reverse=True,
    )[:max_jobs]

    log.info("digest: %d jobs above min_score=%d", len(top), min_score)

    if not top:
        return DigestResult(
            jobs_found=len(all_jobs),
            jobs_scored=len(scored),
            jobs_emailed=0,
            email_sent=False,
            top_jobs=[],
        )

    # 8. Send email
    email_sent = False
    if not dry_run:
        email_sent = await send_digest_email(top)
        if email_sent:
            _record_sent(db, top)

    return DigestResult(
        jobs_found=len(all_jobs),
        jobs_scored=len(scored),
        jobs_emailed=len(top) if email_sent else 0,
        email_sent=email_sent,
        top_jobs=top,
    )


@router.get("/sent", dependencies=[Depends(_require_digest_key)])
def list_sent(limit: int = 50, db: Session = Depends(get_db)):
    """List the last N job URLs that were included in a digest."""
    rows = (
        db.query(DigestSent)
        .order_by(DigestSent.sent_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {"url": r.job_url, "title": r.title, "company": r.company,
         "score": r.score, "sent_at": r.sent_at}
        for r in rows
    ]


@router.delete("/sent/reset", dependencies=[Depends(_require_digest_key)])
def reset_sent(db: Session = Depends(get_db)):
    """Clear the sent-jobs history so all jobs are eligible again."""
    deleted = db.query(DigestSent).delete()
    db.commit()
    return {"deleted": deleted}
