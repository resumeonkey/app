"""
Daily job digest — three separate lists (Canada, Chile, international remote).

POST /api/digest/run        full pipeline; emails the top offers of each list
POST /api/digest/calibrate  scores the calibration fixtures and compares them with expectations
Protected by the X-Digest-Key header (DIGEST_API_KEY in the environment).
"""
import csv
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.models.digest import DigestSent
from backend.services.digest_fixtures import FIXTURES, check
from backend.services.digest_pipeline import extract_facts, process_list  # noqa: F401
from backend.services.digest_rubrics import LIST_KEYS
from backend.services.digest_sources import fetch_list_jobs
from backend.services.email_service import send_digest_email

log = logging.getLogger(__name__)
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data"


def _require_digest_key(x_digest_key: str = Header(default="")):
    expected = get_settings().digest_api_key
    if expected and x_digest_key != expected:
        raise HTTPException(status_code=401, detail="Invalid digest key")


def _load_applied_companies() -> set[str]:
    path = _DATA_DIR / "applied.csv"
    if not path.exists():
        return set()
    applied: set[str] = set()
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                company = (row.get("company") or "").strip().lower()
                if company:
                    applied.add(company)
    except Exception as exc:
        log.warning("digest: could not read applied.csv: %s", exc)
    return applied


def _already_sent_urls(db: Session) -> set[str]:
    return {r.job_url for r in db.query(DigestSent.job_url).all()}


def _record_sent(db: Session, jobs: list[dict]) -> None:
    for j in jobs:
        url = j.get("url", "")
        if not url or db.query(DigestSent).filter(DigestSent.job_url == url).first():
            continue
        db.add(DigestSent(job_url=url, title=j.get("title"), company=j.get("company"), score=j.get("score")))
    db.commit()


class DigestResult(BaseModel):
    jobs_found: int
    jobs_scored: int
    jobs_emailed: int
    email_sent: bool
    lists: dict[str, list[dict]]
    stats: dict


@router.post("/run", response_model=DigestResult, dependencies=[Depends(_require_digest_key)])
async def run_digest(
    llm_provider: str = "gemini",
    llm_model: str = "gemini-3.8-flash",
    min_score: int = 0,
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """
    For each list: fetch -> drop applied/already-sent -> hard filters -> LLM fact extraction ->
    rubric score (0-10) -> top N. dry_run=true skips the email and the sent-history write.
    """
    s = get_settings()
    applied = _load_applied_companies()
    sent_urls = _already_sent_urls(db)

    lists: dict[str, list[dict]] = {}
    stats: dict = {"limits": {"max_per_list": s.digest_max_per_list, "max_llm_jobs_per_list": s.digest_max_llm_jobs_per_list,
                              "max_age_days": s.digest_max_age_days}}
    found = scored = 0

    for key in LIST_KEYS:
        jobs, source_counts = await fetch_list_jobs(key)
        fresh = [
            j for j in jobs
            if j["url"] not in sent_urls
            and not (j["company"] and any(a == j["company"].lower() or a in j["company"].lower() for a in applied))
        ]
        items, list_stats, _ = await process_list(key, fresh, llm_provider, llm_model)
        list_stats["sources"] = source_counts
        list_stats["excluded_applied_or_sent"] = len(jobs) - len(fresh)
        stats[key] = list_stats
        lists[key] = [i for i in items if i["score"] >= min_score][: s.digest_max_per_list]
        found += len(jobs)
        scored += list_stats["scored"]

    emailed = [i for v in lists.values() for i in v]
    email_sent = False
    if emailed and not dry_run:
        email_sent = await send_digest_email(lists)
        if email_sent:
            _record_sent(db, emailed)

    return DigestResult(jobs_found=found, jobs_scored=scored, jobs_emailed=len(emailed) if email_sent else 0,
                        email_sent=email_sent, lists=lists, stats=stats)


@router.post("/calibrate", dependencies=[Depends(_require_digest_key)])
async def calibrate(llm_provider: str = "gemini", llm_model: str = "gemini-3.8-flash"):
    """Run every fixture through the real pipeline (real LLM extraction, no fetching, no email)."""
    outcomes: dict = {}
    for key in LIST_KEYS:
        jobs = [f["job"] for f in FIXTURES if f["list"] == key]
        if jobs:
            _, _, out = await process_list(key, jobs, llm_provider, llm_model, enrich=False)
            outcomes.update(out)
    rows = []
    for fx in FIXTURES:
        out = outcomes.get(fx["job"]["url"], ("discard", "sin_resultado", None))
        row = {"label": fx["label"], "expected": fx["expect"], "passed": check(fx["expect"], out), "outcome": out[0]}
        if out[0] == "score":
            row.update(score=out[1]["score"], reason=out[1]["reason"])
        else:
            row.update(discarded_because=out[1])
        row["facts"] = out[2]
        rows.append(row)
    return {"all_passed": all(r["passed"] for r in rows), "results": rows}


@router.get("/sent", dependencies=[Depends(_require_digest_key)])
def list_sent(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(DigestSent).order_by(DigestSent.sent_at.desc()).limit(limit).all()
    return [{"url": r.job_url, "title": r.title, "company": r.company, "score": r.score, "sent_at": r.sent_at} for r in rows]


@router.delete("/sent/reset", dependencies=[Depends(_require_digest_key)])
def reset_sent(db: Session = Depends(get_db)):
    deleted = db.query(DigestSent).delete()
    db.commit()
    return {"deleted": deleted}
