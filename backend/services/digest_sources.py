"""
Job sources for the three digest lists. Every fetcher is fail-soft: an error or a changed
response format yields [] and is reported in the per-source stats, never an exception.

Normalised job dict: title, company, location, url, source, snippet, posted (raw), days_posted.
"""
import asyncio
import html
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import httpx

from backend.config import get_settings
from backend.services.ats_client import fetch_ats_jobs
from backend.services.digest_rubrics import CANADA, CHILE, REMOTE, parse_days
from backend.services.job_search import _jina_get, search_jobs_via_jina

log = logging.getLogger(__name__)

JINA_SEM = asyncio.Semaphore(4 if get_settings().jina_api_key else 2)   # Jina free tier throttles bursts; shared by every list
_UA = {"User-Agent": "Mozilla/5.0 (compatible; ResumonkeyDigest/1.0)", "Accept": "application/json, */*"}
_TIMEOUT = 25

CANADA_QUERIES = [
    "Implementation Specialist", "Implementation Analyst", "Implementation Consultant",
    "Onboarding Specialist", "Solutions Consultant", "Implementation Specialist Spanish",
    "QA Analyst UAT", "Application Support Analyst", "Technical Support Specialist Spanish",
]
CHILE_QUERIES = [
    "Product Owner", "Product Manager", "Analista QA", "Analista funcional",
    "Consultor implementación", "Analista de sistemas", "Business Analyst",
]
REMOTE_QUERIES = [
    "Implementation Specialist remote", "Onboarding Specialist remote", "QA Analyst remote",
    "Technical Support bilingual Spanish", "Technical Customer Success Manager", "Product Owner remote",
]
_REMOTE_TITLE_RE = re.compile(
    r"(implement|onboard|solutions? (consultant|engineer|analyst)|\bqa\b|quality|tester|uat|support|customer success|"
    r"product owner|product manager|technical account|integration|business analyst|systems analyst|spanish|bilingual)", re.I)


def _clean(htm: str, limit: int = 1800) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", htm or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:limit]


def _norm(title, company, location, url, source, snippet="", posted=None) -> dict | None:
    title, url = (title or "").strip(), (url or "").strip()
    if not title or not url.startswith("http"):
        return None
    return {
        "title": title, "company": (company or "").strip(), "location": (location or "").strip(),
        "url": url, "source": source, "snippet": (snippet or "").strip(), "posted": posted,
        "days_posted": parse_days(posted),
    }


async def _get_json(url: str, params: dict | None = None, method: str = "GET", json_body: dict | None = None):
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True, headers=_UA) as client:
        resp = await client.request(method, url, params=params, json=json_body)
        resp.raise_for_status()
        return resp


# ── LinkedIn (via Jina) ───────────────────────────────────────────────────────

async def _linkedin(queries: list[str], location: str, remote: str, source: str) -> list[dict]:
    async def one(q: str) -> list[dict]:
        async with JINA_SEM:
            try:
                rows = await search_jobs_via_jina(q, num_results=10, location=location, remote=remote, date_posted="30d")
            except Exception as exc:
                log.warning("digest linkedin '%s' (%s) failed: %s", q, location, exc)
                return []
        return [j for j in (_norm(r.get("title"), r.get("company"), r.get("location"), r.get("url"), source,
                                   r.get("snippet") or r.get("content"), r.get("date")) for r in rows) if j]

    return [j for batch in await asyncio.gather(*(one(q) for q in queries)) for j in batch]


# ── Canada: company ATS boards ────────────────────────────────────────────────

async def _canada_ats() -> list[dict]:
    try:
        rows = await fetch_ats_jobs()
    except Exception as exc:
        log.warning("digest ats failed: %s", exc)
        return []
    return [j for j in (_norm(r.get("title"), r.get("company"), r.get("location"), r.get("url"), r.get("source", "ats"),
                               r.get("snippet"), r.get("posted")) for r in rows) if j]


# ── Get on Board (Chile / LATAM) ──────────────────────────────────────────────

async def _getonboard(queries: list[str], remote_only: bool = False) -> list[dict]:
    out: list[dict] = []

    async def one(q: str) -> None:
        try:
            resp = await _get_json("https://www.getonbrd.com/api/v0/search/jobs",
                                   params={"query": q, "per_page": 25, "page": 1, "expand": '["company"]'})
            data = resp.json().get("data", [])
        except Exception as exc:
            log.warning("digest getonbrd '%s' failed: %s", q, exc)
            return
        for d in data:
            a = d.get("attributes", {}) or {}
            mod = str(a.get("remote_modality") or ("fully_remote" if a.get("remote") else "no_remote")).lower()
            if remote_only and "fully" not in mod and mod != "remote":
                continue
            comp = a.get("company") or {}
            comp = (comp.get("data", comp) or {}).get("attributes", comp) if isinstance(comp, dict) else {}
            countries = a.get("countries") or []
            sal = ""
            if a.get("min_salary") or a.get("max_salary"):
                sal = f"Salary published: USD {a.get('min_salary') or '?'}-{a.get('max_salary') or '?'} per month. "
            snippet = f"Modality: {mod}. Countries: {', '.join(map(str, countries))}. {sal}" + _clean(
                " ".join(str(a.get(k) or "") for k in ("description_headline", "description", "functions", "desirable")))
            j = _norm(a.get("title"), comp.get("name") if isinstance(comp, dict) else "", ", ".join(map(str, countries)),
                      (d.get("links") or {}).get("public_url"), "getonboard", snippet, a.get("published_at"))
            if j:
                out.append(j)

    await asyncio.gather(*(one(q) for q in queries))
    return out


# ── Remote boards ─────────────────────────────────────────────────────────────

async def _remoteok() -> list[dict]:
    try:
        data = (await _get_json("https://remoteok.com/api")).json()
    except Exception as exc:
        log.warning("digest remoteok failed: %s", exc)
        return []
    out = []
    for r in data:
        if not isinstance(r, dict) or not r.get("position"):
            continue
        if not _REMOTE_TITLE_RE.search(f"{r.get('position', '')} {' '.join(r.get('tags') or [])}"):
            continue
        sal = f"Salary published: USD {r.get('salary_min')}-{r.get('salary_max')} per year. " if r.get("salary_min") else ""
        snippet = f"Remote region: {r.get('location') or 'unspecified'}. {sal}" + _clean(r.get("description", ""))
        j = _norm(r.get("position"), r.get("company"), r.get("location") or "Remote", r.get("url") or r.get("apply_url"),
                  "remoteok", snippet, r.get("epoch") or r.get("date"))
        if j:
            out.append(j)
    return out


async def _himalayas(queries: list[str]) -> list[dict]:
    out: list[dict] = []

    async def one(q: str) -> None:
        try:
            resp = await _get_json("https://himalayas.app/jobs/api/search", params={"q": q, "sort": "recent"})
            rows = resp.json().get("jobs", [])
        except Exception as exc:
            log.warning("digest himalayas '%s' failed: %s", q, exc)
            return
        for r in rows:
            loc = ", ".join(r.get("locationRestrictions") or []) or "Worldwide"
            tz = ", ".join(map(str, r.get("timezoneRestrictions") or []))
            sal = ""
            if r.get("minSalary") or r.get("maxSalary"):
                sal = f"Salary published: {r.get('currency') or 'USD'} {r.get('minSalary')}-{r.get('maxSalary')} per year. "
            snippet = (f"Location restrictions: {loc}. Timezones: {tz or 'not stated'}. Employment type: {r.get('employmentType')}. "
                       f"{sal}") + _clean(r.get("description") or r.get("excerpt") or "", limit=15000)
            j = _norm(r.get("title"), r.get("companyName"), loc, r.get("applicationLink") or r.get("guid"), "himalayas",
                      snippet, r.get("pubDate"))
            if j:
                out.append(j)

    await asyncio.gather(*(one(q) for q in queries))
    return out


_WWR_FEEDS = ["remote-customer-support-jobs", "remote-product-jobs", "remote-devops-sysadmin-jobs"]


async def _weworkremotely() -> list[dict]:
    out: list[dict] = []

    async def one(feed: str) -> None:
        try:
            resp = await _get_json(f"https://weworkremotely.com/categories/{feed}.rss")
            root = ET.fromstring(resp.text)
        except Exception as exc:
            log.warning("digest wwr '%s' failed: %s", feed, exc)
            return
        for it in root.iter("item"):
            raw = (it.findtext("title") or "").strip()
            company, _, title = raw.partition(": ")
            region = it.findtext("region") or "Anywhere"
            if not _REMOTE_TITLE_RE.search(title or raw):
                continue
            j = _norm(title or raw, company if title else "", region, it.findtext("link"), "weworkremotely",
                      f"Remote region: {region}. " + _clean(it.findtext("description") or ""), it.findtext("pubDate"))
            if j:
                out.append(j)

    await asyncio.gather(*(one(f) for f in _WWR_FEEDS))
    return out


# ── Chilean portals through Jina listing pages (best effort) ──────────────────

_PORTALS = [
    ("computrabajo", "https://cl.computrabajo.com/trabajo-de-{slug}", r"computrabajo\.com/.*(oferta|ofertas-de-trabajo)"),
    ("laborum", "https://www.laborum.cl/empleos-busqueda-{slug}.html", r"laborum\.cl/empleos/"),
    ("trabajando", "https://www.trabajando.cl/trabajo-empleo/{slug}", r"trabajando\.cl/.*(oferta|trabajo-empleo/.+-\d+|empleo/\d+)"),
]
_MD_LINK = re.compile(r"\[([^\]\n]{8,160})\]\((https?://[^)\s]+)\)")


async def _chile_portals(queries: list[str]) -> list[dict]:
    out: list[dict] = []

    async def one(source: str, tmpl: str, link_re: str, q: str) -> None:
        url = tmpl.format(slug=quote_plus(q.lower()).replace("+", "-"))
        async with JINA_SEM:
            try:
                md = await _jina_get(url, retries=1)
            except Exception as exc:
                log.warning("digest %s '%s' failed: %s", source, q, exc)
                return
        seen = set()
        for title, link in _MD_LINK.findall(md):
            if link in seen or link.rstrip("/") == url.rstrip("/") or not re.search(link_re, link):
                continue
            seen.add(link)
            j = _norm(title.strip("*# "), "", "Chile", link, source)
            if j:
                out.append(j)

    await asyncio.gather(*(one(s, t, r, q) for s, t, r in _PORTALS for q in queries[:3]))
    return out


# ── public entry point ────────────────────────────────────────────────────────

async def fetch_list_jobs(list_key: str) -> tuple[list[dict], dict]:
    """Return (deduplicated jobs, per-source counts) for one list."""
    if list_key == CANADA:
        parts = {"company_boards": _canada_ats(), "linkedin": _linkedin(CANADA_QUERIES, "Canada", "any", "linkedin")}
    elif list_key == CHILE:
        parts = {"linkedin": _linkedin(CHILE_QUERIES, "Chile", "any", "linkedin"),
                 "getonboard": _getonboard(CHILE_QUERIES),
                 "chile_portals": _chile_portals(CHILE_QUERIES)}
    else:
        parts = {"linkedin": _linkedin(REMOTE_QUERIES, "Latin America", "remote", "linkedin"),
                 "getonboard": _getonboard(REMOTE_QUERIES, remote_only=True),
                 "remoteok": _remoteok(), "himalayas": _himalayas(REMOTE_QUERIES), "weworkremotely": _weworkremotely()}
    results = await asyncio.gather(*parts.values())
    stats, seen, jobs = {}, set(), []
    for name, rows in zip(parts.keys(), results):
        stats[name] = len(rows)
        for j in rows:
            if j["url"] not in seen:
                seen.add(j["url"])
                jobs.append(j)
    return jobs, stats
