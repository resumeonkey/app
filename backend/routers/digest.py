"""
Daily job digest — three separate lists (Canada, Chile, international remote).

POST /api/digest/run        full pipeline; emails the top offers of each list
POST /api/digest/calibrate  scores the calibration fixtures and compares them with expectations
Protected by the X-Digest-Key header (DIGEST_API_KEY in the environment).
"""
import asyncio
import csv
import logging
import json
import re
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.models.digest import DigestJob, DigestSent
from backend.services.digest_fixtures import FIXTURES, check
from backend.services.digest_pipeline import complete_descriptions, looks_blocked, extract_facts, process_list  # noqa: F401
from backend.services.digest_rubrics import LIST_KEYS, normalize
from backend.services.digest_sources import fetch_list_jobs
from backend.services.email_service import get_email_status, send_digest_email, send_test_email

log = logging.getLogger(__name__)
router = APIRouter()

_DATA_DIR = Path(__file__).parent.parent / "data"


def _require_digest_key(x_digest_key: str = Header(default="")):
    """Every /api/digest endpoint needs the X-Digest-Key header. With no key configured the endpoints stay closed."""
    expected = get_settings().digest_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="DIGEST_API_KEY is not configured on the server")
    if not secrets.compare_digest(x_digest_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid digest key")


def _load_applied() -> list[tuple[str, str]]:
    """(company, title) pairs from applied.csv, normalised. A blank title excludes the whole company."""
    path = _DATA_DIR / "applied.csv"
    if not path.exists():
        return []
    rows: list[tuple[str, str]] = []
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                company = normalize(re.sub(r"\(.*?\)", "", row.get("company") or ""))
                if company:
                    rows.append((company, normalize(row.get("title") or "")))
    except Exception as exc:
        log.warning("digest: could not read applied.csv: %s", exc)
    return rows


def _is_applied(job: dict, applied: list[tuple[str, str]]) -> bool:
    company, title = normalize(job.get("company") or ""), normalize(job.get("title") or "")
    if not company:
        return False
    for a_company, a_title in applied:
        if a_company in company or company in a_company:
            if not a_title or a_title in title or title in a_title:
                return True
    return False


def _already_sent_urls(db: Session) -> set[str]:
    return {r.job_url for r in db.query(DigestSent.job_url).all()}


def _record_sent(db: Session, jobs: list[dict]) -> None:
    for j in jobs:
        url = j.get("url", "")
        if not url or db.query(DigestSent).filter(DigestSent.job_url == url).first():
            continue
        db.add(DigestSent(job_url=url, title=j.get("title"), company=j.get("company"), score=j.get("score")))
    db.commit()


_SOURCE_BY_HOST = [
    ("linkedin.com", "linkedin"), ("greenhouse.io", "greenhouse"), ("ashbyhq.com", "ashby"), ("lever.co", "lever"),
    ("getonbrd.com", "getonboard"), ("himalayas.app", "himalayas"), ("weworkremotely.com", "weworkremotely"),
    ("remoteok", "remoteok"), ("computrabajo", "computrabajo"), ("laborum", "laborum"), ("trabajando", "trabajando"),
]


def _source_from_url(url: str) -> str | None:
    u = (url or "").lower()
    return next((name for host, name in _SOURCE_BY_HOST if host in u), None)


def _save_jobs(db: Session, items: list[dict]) -> None:
    """Upsert the clean posting text, list, source and application questions of every emailed offer (by URL)."""
    for j in items:
        url = j.get("url")
        if not url:
            continue
        row = db.query(DigestJob).filter(DigestJob.job_url == url).first()
        if row is None:
            row = DigestJob(job_url=url)
            db.add(row)
        for field, value in (("list_key", j.get("list")), ("title", j.get("title")), ("company", j.get("company")),
                             ("location", j.get("location")), ("score", j.get("score")), ("reason", j.get("reason"))):
            if value not in (None, ""):
                setattr(row, field, value)                       # never overwrite a known value with an empty one
        row.source = j.get("source") or row.source or _source_from_url(url)
        if j.get("description") is not None and (j["description"] or not row.description):
            row.description = j["description"]
        if j.get("application_questions") is not None:
            row.application_questions = json.dumps(j["application_questions"], ensure_ascii=False)
    db.commit()


def _without_text(lists: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """The HTTP response (and the workflow log) stays small: the full text lives in the database."""
    heavy = {"description", "application_questions"}
    return {k: [{f: v for f, v in i.items() if f not in heavy} for i in items] for k, items in lists.items()}


class DigestResult(BaseModel):
    jobs_found: int
    jobs_scored: int
    jobs_emailed: int
    email_sent: bool
    lists: dict[str, list[dict]]
    stats: dict
    email_id: str | None = None
    email_error: str | None = None
    email_delivery: str | None = None


@router.post("/run", response_model=DigestResult, dependencies=[Depends(_require_digest_key)])
async def run_digest(
    llm_provider: str = "groq",
    llm_model: str = "openai/gpt-oss-20b",
    min_score: int = 0,
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """
    For each list: fetch -> drop applied/already-sent -> hard filters -> LLM fact extraction ->
    rubric score (0-10) -> top N. dry_run=true skips the email and the sent-history write.
    """
    s = get_settings()
    applied = _load_applied()
    sent_urls = _already_sent_urls(db)

    lists: dict[str, list[dict]] = {}
    stats: dict = {"limits": {"max_per_list": s.digest_max_per_list, "max_llm_jobs_per_list": s.digest_max_llm_jobs_per_list,
                              "max_age_days": s.digest_max_age_days}}
    found = scored = unscored = 0

    async def one_list(key: str):
        t0 = time.monotonic()
        jobs, source_counts = await fetch_list_jobs(key)
        log.warning("digest %s: fetched %d jobs in %.0fs %s", key, len(jobs), time.monotonic() - t0, source_counts)
        fresh = [j for j in jobs if j["url"] not in sent_urls and not _is_applied(j, applied)]
        items, list_stats, _ = await process_list(key, fresh, llm_provider, llm_model)
        list_stats["sources"] = source_counts
        list_stats["excluded_applied_or_sent"] = len(jobs) - len(fresh)
        list_stats["seconds"] = round(time.monotonic() - t0)
        return key, len(jobs), items, list_stats

    for key, n_jobs, items, list_stats in await asyncio.gather(*(one_list(k) for k in LIST_KEYS)):
        stats[key] = list_stats
        lists[key] = [i for i in items if i["score"] >= min_score][: s.digest_max_per_list]
        found += n_jobs
        scored += list_stats["scored"]
        unscored += list_stats.get("unscored_llm_failed", 0)

    stats["unscored_llm_failed_total"] = unscored
    emailed = [i for v in lists.values() for i in v]
    await complete_descriptions(emailed)
    if emailed and not dry_run:
        _save_jobs(db, emailed)
    email_sent, email_id, email_error, delivery = False, None, None, None
    if emailed and not dry_run:
        result = await send_digest_email(lists, unscored)
        email_sent, email_id, email_error = result["sent"], result["id"], result["error"]
        if email_sent:
            _record_sent(db, emailed)
            # Resend usually reports "delivered" within seconds; check it so the caller sees the real state.
            for _ in range(6):
                await asyncio.sleep(5)
                delivery = (await get_email_status(email_id)).get("last_event")
                if delivery in ("delivered", "bounced", "complained", "failed"):
                    break

    return DigestResult(jobs_found=found, jobs_scored=scored, jobs_emailed=len(emailed) if email_sent else 0,
                        email_sent=email_sent, lists=_without_text(lists), stats=stats,
                        email_id=email_id, email_error=email_error, email_delivery=delivery)


@router.post("/test-email", dependencies=[Depends(_require_digest_key)])
async def test_email():
    """Send a tiny test message and report Resend's answer (and the delivery state a few seconds later)."""
    result = await send_test_email()
    if result["sent"]:
        for _ in range(6):
            await asyncio.sleep(5)
            status = await get_email_status(result["id"])
            if status.get("last_event") in ("delivered", "bounced", "complained", "failed"):
                break
        result["delivery"] = status.get("last_event")
        result["status_error"] = status.get("error")   # e.g. a send-only Resend key cannot read email status
    return result


@router.get("/email-status/{email_id}", dependencies=[Depends(_require_digest_key)])
async def email_status(email_id: str):
    return await get_email_status(email_id)


@router.post("/calibrate", dependencies=[Depends(_require_digest_key)])
async def calibrate(llm_provider: str = "groq", llm_model: str = "openai/gpt-oss-20b"):
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


@router.get("/models", dependencies=[Depends(_require_digest_key)])
async def list_models():
    """Model ids each configured provider key can actually call (ids only, never keys)."""
    import httpx
    s = get_settings()
    targets = {
        "groq": ("https://api.groq.com/openai/v1/models", s.groq_api_key),
        "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/models", s.gemini_api_key),
    }
    out: dict = {}
    async with httpx.AsyncClient(timeout=20) as client:
        for name, (url, key) in targets.items():
            if not key:
                out[name] = "no key configured"
                continue
            try:
                r = await client.get(url, headers={"Authorization": f"Bearer {key}"})
                r.raise_for_status()
                out[name] = sorted(m.get("id", "") for m in r.json().get("data", []))
            except Exception as exc:
                out[name] = f"error: {str(exc)[:200]}"
    return out


@router.get("/jobs", dependencies=[Depends(_require_digest_key)])
def list_jobs(limit: int = 30, db: Session = Depends(get_db)):
    """Offers that were emailed, newest first, without the long text."""
    rows = db.query(DigestJob).order_by(DigestJob.first_sent.desc()).limit(limit).all()
    return [{"url": r.job_url, "list": r.list_key, "source": r.source, "title": r.title, "company": r.company,
             "location": r.location, "score": r.score, "has_description": bool(r.description),
             "has_questions": bool(r.application_questions), "first_sent": r.first_sent} for r in rows]


@router.get("/job", dependencies=[Depends(_require_digest_key)])
def get_job(url: str, db: Session = Depends(get_db)):
    """Stored clean posting text and application questions for one emailed offer."""
    r = db.query(DigestJob).filter(DigestJob.job_url == url).first()
    if r is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    try:
        questions = json.loads(r.application_questions) if r.application_questions else None
    except ValueError:
        questions = None
    return {"url": r.job_url, "list": r.list_key, "title": r.title, "company": r.company, "location": r.location,
            "source": r.source, "score": r.score, "reason": r.reason, "description": r.description,
            "application_questions": questions, "first_sent": r.first_sent}


@router.post("/backfill-jobs", dependencies=[Depends(_require_digest_key)])
async def backfill_jobs(limit: int = 40, refresh: bool = False, db: Session = Depends(get_db)):
    """
    Fetch and store the clean posting text of offers that were already emailed.
    Default: only offers never stored or stored with a blocked page. refresh=true refetches and re-cleans all of them.
    """
    stored = {r.job_url: r for r in db.query(DigestJob).all()}
    bad = {u for u, r in stored.items() if looks_blocked(r.description or "")}
    sent = [r for r in db.query(DigestSent).order_by(DigestSent.sent_at.desc()).limit(limit * 3).all()
            if refresh or r.job_url not in stored or r.job_url in bad][:limit]
    items = []
    for r in sent:
        old = stored.get(r.job_url)
        items.append({"url": r.job_url, "title": r.title, "company": r.company, "score": r.score,
                      "description": (old.description if old else "") or "",
                      "list": old.list_key if old else None, "source": (old.source if old else None) or _source_from_url(r.job_url)})
    await complete_descriptions(items, refresh=refresh)
    _save_jobs(db, items)
    return {"processed": len(items), "with_text": sum(1 for i in items if i.get("description")),
            "with_questions": sum(1 for i in items if i.get("application_questions")),
            "still_empty": [f"{i['company']} - {i['title']}" for i in items if not i.get("description")]}


@router.get("/sent", dependencies=[Depends(_require_digest_key)])
def list_sent(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(DigestSent).order_by(DigestSent.sent_at.desc()).limit(limit).all()
    return [{"url": r.job_url, "title": r.title, "company": r.company, "score": r.score, "sent_at": r.sent_at} for r in rows]


@router.delete("/sent/reset", dependencies=[Depends(_require_digest_key)])
def reset_sent(db: Session = Depends(get_db)):
    deleted = db.query(DigestSent).delete()
    db.commit()
    return {"deleted": deleted}
