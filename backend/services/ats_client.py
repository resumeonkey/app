"""
Direct ATS board clients for Greenhouse and Ashby.
These boards expose free public JSON APIs — no auth required.
Only verified companies with known board slugs are queried.
"""
import logging
from pathlib import Path
from typing import Any

import httpx
import yaml

log = logging.getLogger(__name__)

_TIMEOUT = 20
_DATA_DIR = Path(__file__).parent.parent / "data"


def _load_companies() -> list[dict]:
    path = _DATA_DIR / "companies.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("companies", [])


def _load_applied_companies() -> set[str]:
    """Return lowercase company names the user has already applied to."""
    path = _DATA_DIR / "applied.csv"
    if not path.exists():
        return set()
    applied: set[str] = set()
    with open(path) as f:
        for i, line in enumerate(f):
            if i == 0:
                continue  # header
            parts = line.strip().split(",")
            if parts:
                applied.add(parts[1].strip().lower())
    return applied


async def _get_json(url: str) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Accept": "application/json"})
        resp.raise_for_status()
        return resp.json()


def _normalize_greenhouse(job: dict, company_name: str) -> dict | None:
    title = (job.get("title") or "").strip()
    url   = job.get("absolute_url") or ""
    location = ""
    loc = job.get("location")
    if loc:
        location = loc.get("name", "")
    if not title or not url:
        return None
    return {
        "id":       job.get("id", ""),
        "title":    title,
        "company":  company_name,
        "location": location,
        "url":      url,
        "source":   "greenhouse",
        "snippet":  (job.get("content") or "")[:800],
    }


def _normalize_ashby(job: dict, company_name: str) -> dict | None:
    title = (job.get("title") or "").strip()
    url   = job.get("jobUrl") or ""
    location = job.get("locationName") or job.get("location") or ""
    if not title or not url:
        return None
    return {
        "id":       job.get("id", ""),
        "title":    title,
        "company":  company_name,
        "location": location,
        "url":      url,
        "source":   "ashby",
        "snippet":  (job.get("descriptionPlain") or "")[:800],
    }


async def fetch_ats_jobs() -> list[dict]:
    """Fetch jobs from all verified ATS-accessible companies in companies.yaml."""
    companies  = _load_companies()
    all_jobs: list[dict] = []

    for co in companies:
        ats   = co.get("ats", "").lower()
        board = co.get("board", "")
        name  = co.get("name", "")
        if not board or not name:
            continue
        # Only hit APIs we know are public and don't require scraping
        try:
            if ats == "greenhouse":
                data = await _get_json(
                    f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
                )
                for j in (data.get("jobs") or []):
                    n = _normalize_greenhouse(j, name)
                    if n:
                        all_jobs.append(n)
            elif ats == "ashby":
                data = await _get_json(
                    f"https://api.ashbyhq.com/posting-api/job-board/{board}"
                )
                for j in (data.get("jobPostings") or []):
                    n = _normalize_ashby(j, name)
                    if n:
                        all_jobs.append(n)
            # Lever public API: https://api.lever.co/v0/postings/{slug}
            elif ats == "lever":
                jobs = await _get_json(
                    f"https://api.lever.co/v0/postings/{board}?mode=json"
                )
                for j in (jobs or []):
                    title = (j.get("text") or "").strip()
                    url   = j.get("hostedUrl") or j.get("applyUrl") or ""
                    loc   = (j.get("categories") or {}).get("location", "")
                    if title and url:
                        all_jobs.append({
                            "id": j.get("id", ""),
                            "title": title, "company": name,
                            "location": loc, "url": url,
                            "source": "lever",
                            "snippet": (j.get("descriptionPlain") or "")[:800],
                        })
        except Exception as exc:
            log.warning("ats_client: %s (%s/%s): %s", name, ats, board, exc)

    return all_jobs
