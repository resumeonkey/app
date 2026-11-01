"""
Digest pipeline for the three lists: pre-filter -> cap -> enrich -> LLM fact extraction ->
post-filter -> deterministic scoring -> top N. The LLM never assigns the final score.
"""
import asyncio
import html
import json
import logging
import re

import httpx
import time
from collections import Counter

from backend.config import get_settings
from backend.services.digest_rubrics import (
    CANADA, CHILE, POSTFILTERS, PREFILTERS, REMOTE, SCORERS, _chile_salary_net_clp,
    _remote_pay_monthly_usd, _s, apply_fit_floor, title_keyword_hits,
)
from backend.services.llm_client import call_llm

log = logging.getLogger(__name__)

PROFILE = """CANDIDATE PROFILE (applies to every list)
- 16 years in systems: QA and testing (ISTQB CTFL), platform configuration (Nokia BSCS, Salesforce, Dynamics 365, SmartBackOffice), advanced SQL.
- 4 years as Product Owner at Entel (contact centre; implemented a service-management system with routing and SLAs; led two Scrum teams in Chile and Peru).
- Current experience in maintenance operations and field service (certified Thermoplan technician, Vixxo platform).
- Builds agents and tools with LLMs (Anthropic certifications, Claude Code).
- Native Spanish, professional English. Does NOT speak French.
- Has NO experience in the financial industry (banking, fintech, credit, insurance)."""

_COMMON = """You extract FACTS about job postings. Base every fact ONLY on the text provided; when the text does not say, use the neutral default.
Never infer a language requirement from the company name or country. Return ONLY JSON: {"results":[{"i":0, ...}, ...]} with EXACTLY one object per job, in order.
Never skip, merge or drop a job: an irrelevant, duplicated or non-job posting still gets its own object (set "is_job" to false and use neutral defaults).
Common keys: "i" (int), "is_job" (bool; false if the text is not a real single job posting), "modality" ("remote"|"hybrid"|"onsite"|"unknown"),
"city_country" (string), "salary_text" (string or null; copy the published salary as written).
IMPORTANT for every fit score: the candidate works in SOFTWARE / IT systems. Quality, QA or "calidad" roles in manufacturing, food processing, meat/fish plants, mining, construction,
laboratories, healthcare, retail stores, or ISO/inspection/food-safety quality control are NOT software QA: give them fit 0. Sales, recruiting, accounting and field-technician roles are also fit 0."""

_SCHEMAS = {
    CANADA: """LIST: CANADA. Priority titles, best first: Implementation Specialist/Analyst/Consultant, Onboarding Specialist, Solutions Consultant (junior to mid);
technical roles that ask for Spanish; manual QA Analyst / UAT; Application Support / Technical Support Tier 2.
Keys:
"fit" (int 0-4): 4 = a priority implementation/onboarding/solutions title at junior-mid level; 3 = technical role that asks for Spanish, or manual QA/UAT that matches the profile;
 2 = application/technical support Tier 2 or an adjacent IT role; 1 = loosely related; 0 = unrelated. Subtract 1-2 if clearly senior or needs skills the profile lacks.
"remote_canada" (bool; fully remote role open to people in Canada), "french_required" (bool; French required or listed as bilingual French, or the posting is written in French),
"posting_language" ("en"|"fr"|"es"|"other"), "spanish" ("required"|"asset"|"none"; Spanish named as required/asset),
"domain_match" (bool; contact centre, ITSM, field service/maintenance, telecom or AI domain),
"bachelor_no_equiv" (bool; requires a Bachelor's degree and the text does NOT say "or equivalent" experience).""",
    CHILE: """LIST: CHILE. Target titles: Product Owner, Product Manager (only if it does not require experience the candidate lacks, e.g. financial industry), Analista QA,
Analista funcional, Consultor/Especialista de implementación, Analista de sistemas, Business Analyst. Senior roles ARE fine here.
Keys:
"fit_base" (int 0-4): 4 = Product Owner, QA or implementation title that matches the profile; 3 = Product Manager, functional analyst, business analyst, systems analyst; 2 = adjacent; 1 = loose; 0 = unrelated.
"domain_bonus" (bool; telecom, contact centre, banking or HR tech domain), "requires_unmet_experience" (bool; the posting REQUIRES domain experience the candidate lacks, especially financial-industry experience),
"english_signal" ("strong"|"mild"|"none"; strong = English adds value, or role is regional / with foreign clients; mild = English desirable),
"in_metropolitan_region" (true|false|null; Región Metropolitana de Santiago), "salary_monthly" (number or null; monthly amount in the posted currency; null if UF or unclear),
"salary_currency" ("CLP"|"USD"|"other"), "salary_basis" ("net"|"gross"|"unknown"; líquido=net, bruto=gross),
"agency" (bool; posted by a recruitment agency / selection consultancy rather than the end employer).""",
    REMOTE: """LIST: REMOTE INTERNATIONAL (English as an advantage). Roles: implementation, onboarding, QA, bilingual technical support, technical customer success, product owner.
The candidate can work from Canada OR from Chile. Keys:
"fit" (int 0-4): 4 = exact target role for the profile; 3 = close; 2 = adjacent; 1 = loose; 0 = unrelated.
"eligibility" ("explicit"|"ambiguous"|"restricted"): explicit = text names LATAM / Latin America / Chile / Canada / North America / Americas / worldwide / anywhere;
 restricted = requires living in the US or in any country that is neither Canada nor Chile (e.g. "US only", "EU only"); ambiguous = unclear.
"eligible_for" (list): include "canada" if residents of Canada are accepted (Canada, North America, Americas, worldwide, anywhere); include "chile" if residents of Chile are accepted
 (Chile, LATAM, Latin America, South America, Americas, worldwide, anywhere); [] if neither or unclear. "not_tech_role" (bool; voice recording, per-task data labeling, surveys, micro-tasks),
"scam_signals" (bool; asks for payment, bank data, or to apply through Telegram/WhatsApp), "company_verifiable" (true|false|null; false only if there is no identifiable real company; null if unsure),
"pay_min" and "pay_max" (numbers or null; the published pay exactly as written, NO conversion; a single figure goes in both; null if unpublished),
"pay_currency" ("USD"|"CAD"|"EUR"|"GBP"|"CLP"|"other"|null), "pay_period" ("hour"|"day"|"week"|"month"|"year"|null), "employment_type" ("employee_eor"|"employee"|"contractor"|"unknown"; EOR/Deel/Remote.com = employee_eor),
"timezone" (string or null), "languages_required" ("en_es"|"en"|"es"|"other"|"unknown"; en_es = BOTH English and Spanish required),
"french_required" (bool; French is required, or the role is bilingual English-French, or the posting is written in French), "posting_language" (string, e.g. "en"),
"domain_match" (bool; contact centre, ITSM, AI or telecom domain).""",
}

_BATCH = 6   # smaller batches: with 10 offers the model often returned valid JSON but skipped several
_LLM_SEM = asyncio.Semaphore(2)   # free-tier LLM quotas are per minute: few concurrent calls across the three lists
# Each model has its own rate-limit bucket (Groq free tier: 8,000 tokens/min per model), so batches are spread round-robin.
_MODEL_POOL = [("groq", "openai/gpt-oss-20b"), ("groq", "openai/gpt-oss-120b"), ("gemini", "gemini-3.1-flash-lite")]
_RETRY_WAITS = (0, 25, 50)     # seconds before each attempt; waits out per-minute quota errors


def _system_prompt(list_key: str) -> str:
    return f"{PROFILE}\n\n{_COMMON}\n\n{_SCHEMAS[list_key]}"


def _job_block(i: int, j: dict) -> str:
    days = j.get("days_posted")
    return (f"### {i}\nTitle: {j.get('title')}\nCompany: {j.get('company')}\nLocation: {j.get('location')}\n"
            f"Source: {j.get('source')}\nPosted: {'unknown' if days is None else f'{days} days ago'}\n"
            f"Text: {(j.get('snippet') or '')[:700]}")


def _parse(raw: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.M).strip()
    data = json.loads(text)
    rows = data.get("results", data) if isinstance(data, dict) else data
    return rows if isinstance(rows, list) else []


async def extract_facts(list_key: str, jobs: list[dict], provider: str, model: str) -> list[dict | None]:
    system = _system_prompt(list_key)
    facts: list[dict | None] = [None] * len(jobs)
    pool = [(provider, model)] + [m for m in _MODEL_POOL if m != (provider, model)]

    async def run(start: int) -> None:
        chunk = jobs[start:start + _BATCH]
        prov, mod = pool[(start // _BATCH) % len(pool)]
        pending = list(range(len(chunk)))          # offers of this batch still without facts
        async with _LLM_SEM:
            for attempt, wait in enumerate(_RETRY_WAITS, start=1):
                if not pending:
                    return
                if wait:
                    await asyncio.sleep(wait)
                user = "\n\n".join(_job_block(k, chunk[p]) for k, p in enumerate(pending))
                try:
                    raw = await call_llm(prov, mod, system, user, json_mode=True, temperature=0.0)
                    for row in _parse(raw):
                        k = int(row.get("i", -1))
                        if 0 <= k < len(pending):
                            facts[start + pending[k]] = row
                    pending = [p for p in pending if facts[start + p] is None]
                    if pending:   # a valid JSON that skips offers is not a success: ask again for the skipped ones only
                        log.warning("digest facts batch %s@%d attempt %d: model skipped %d of %d offers",
                                    list_key, start, attempt, len(pending), len(chunk))
                except Exception as exc:
                    log.warning("digest facts batch %s@%d attempt %d failed: %s", list_key, start, attempt, str(exc)[:200])

    await asyncio.gather(*(run(s) for s in range(0, len(jobs), _BATCH)))
    return facts


FULL_TEXT_LIMIT = 15000   # applied after cleaning

_BLOCKED_MARKERS = (
    "just a moment", "performing security verification", "captcha", "enable javascript", "access denied",
    "attention required", "sign in to view", "join now to see", "authwall", "expand search", "skip to main content",
    "verify you are human", "unusual traffic",
)


def looks_blocked(text: str) -> bool:
    """True when the fetched page is a login wall / bot check / site chrome instead of the posting."""
    t = (text or "").lower()
    if len(t) < 200:
        return True
    head = t[:1500]
    return any(m in head for m in _BLOCKED_MARKERS)


def _linkedin_guest_url(url: str) -> str | None:
    """Public (no-login) endpoint of a LinkedIn posting, built from the numeric id at the end of the job URL."""
    m = re.search(r"linkedin\.com/jobs/view/(?:[^?#]*?-)?(\d{6,})", url or "")
    return f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}" if m else None


# ── text cleaning ─────────────────────────────────────────────────────────────

_IMG_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_NOISE = [
    re.compile(r"Join or sign in to (?:save this job|find your next job).*?Report this job", re.I),  # LinkedIn login box
    re.compile(r"Get AI-powered advice on this job.*?tailor your resume", re.I),
    re.compile(r"Email or phone Password Show Forgot password.*?Cookie Policy\s*\.?", re.I),
    re.compile(r"New to LinkedIn\?\s*Join now.*?Cookie Policy\s*\.?", re.I),
    re.compile(r"See who .{1,60}? has hired for this role", re.I),
    re.compile(r"Referrals increase your chances of interviewing at .{1,80}? by 2x\s*See who you know", re.I),
    re.compile(r"Direct message the job poster from", re.I),
    re.compile(r"\b(Show more Show less|Show more|Show less)\b", re.I),
    re.compile(r"^Title:.{0,400}?Markdown Content:\s*", re.I),                                  # Jina header
    re.compile(r"\b(Final URL|Published Time|Warning):[^ ]*( [^ ]+){0,12}?(?= [A-Z])", re.I),
    # runs of phone country codes ("Afghanistan +93 Albania +355 ...")
    re.compile(r"(?:[A-Z][\w.'’()-]*(?: [A-Za-z][\w.'’()-]*){0,3} \+\d{1,4}(?:\s+|$)){4,}"),
    re.compile(r"\bApply Save\b"),
]


def clean_markdown(md: str) -> str:
    """Markdown -> single-line text with images and link targets removed (no site-specific noise rules yet)."""
    text = _IMG_MD.sub(" ", md or "")
    text = re.sub(r"\]\(https?://[^)]*\)", "]", text)
    text = re.sub(r"[#*_>\[\]`]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_posting(text: str) -> str:
    """Strip login notices, applicant counters, phone-code lists and Jina headers from posting text."""
    for rx in _NOISE:
        text = rx.sub(" ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _html_to_text(h: str) -> str:
    h = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|/div|/ul|/ol)[^>]*>", "\n", h or "")
    h = re.sub(r"(?i)<li[^>]*>", "• ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t]+", " ", h)
    return re.sub(r"\n\s*\n+", "\n\n", h).strip()


# ── per-source fetchers ───────────────────────────────────────────────────────

_UA = {"User-Agent": "Mozilla/5.0 (compatible; ResumonkeyDigest/1.0)", "Accept": "application/json, */*"}
_GH_URL = re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)")


async def fetch_greenhouse(url: str) -> tuple[str, list]:
    """Greenhouse public boards API: clean description + application form questions."""
    m = _GH_URL.search(url or "")
    if not m:
        return "", []
    board, job_id = m.group(1), m.group(2)
    try:
        async with httpx.AsyncClient(timeout=25, headers=_UA, follow_redirects=True) as client:
            r = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}", params={"questions": "true"})
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        log.warning("greenhouse api %s/%s failed: %s", board, job_id, str(exc)[:150])
        return "", []
    description = _html_to_text(html.unescape(data.get("content") or ""))[:FULL_TEXT_LIMIT]
    questions = []
    for q in (data.get("questions") or []) + (data.get("location_questions") or []):
        fields = []
        for f in q.get("fields") or []:
            values = [v.get("label") for v in (f.get("values") or []) if v.get("label")]
            entry = {"name": f.get("name"), "type": f.get("type")}
            if values:
                entry["options"] = values if len(values) <= 15 else f"{len(values)} opciones"
            fields.append(entry)
        questions.append({"label": q.get("label") or q.get("description"), "required": bool(q.get("required")), "fields": fields})
    return description, questions


async def fetch_himalayas(url: str, title: str, company: str) -> str:
    """Himalayas pages sit behind Cloudflare; its public search API carries the description instead."""
    slug = (url or "").split("?")[0].rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=25, headers=_UA, follow_redirects=True) as client:
            r = await client.get("https://himalayas.app/jobs/api/search", params={"q": title or slug.rsplit("/", 1)[-1], "sort": "recent"})
        r.raise_for_status()
        rows = r.json().get("jobs", [])
    except Exception as exc:
        log.warning("himalayas api '%s' failed: %s", title, str(exc)[:150])
        return ""
    for row in rows:
        link = (row.get("guid") or row.get("applicationLink") or "").split("?")[0].rstrip("/")
        same_job = link == slug or (title and row.get("title") == title and company and row.get("companyName") == company)
        if same_job:
            text = _html_to_text(row.get("description") or row.get("excerpt") or "")
            return text[:FULL_TEXT_LIMIT]
    return ""


async def fetch_getonboard(url: str, title: str) -> str:
    """Get on Board public API (search by title, match by URL): clean description + published salary."""
    target = (url or "").split("?")[0].rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=25, headers=_UA, follow_redirects=True) as client:
            r = await client.get("https://www.getonbrd.com/api/v0/search/jobs",
                                 params={"query": title or target.rsplit("/", 1)[-1], "per_page": 25, "page": 1, "expand": '["company"]'})
        r.raise_for_status()
        rows = r.json().get("data", [])
    except Exception as exc:
        log.warning("getonboard api '%s' failed: %s", title, str(exc)[:150])
        return ""
    for d in rows:
        if ((d.get("links") or {}).get("public_url") or "").split("?")[0].rstrip("/") != target:
            continue
        a = d.get("attributes") or {}
        parts = [_html_to_text(str(a.get(k) or "")) for k in ("description_headline", "description", "functions", "desirable", "benefits")]
        sal = f"Salary published: USD {a.get('min_salary') or '?'}-{a.get('max_salary') or '?'} per month." if (a.get("min_salary") or a.get("max_salary")) else ""
        return "\n\n".join(x for x in [sal, *parts] if x)[:FULL_TEXT_LIMIT]
    return ""


_WWR_FEEDS = ["remote-customer-support-jobs", "remote-product-jobs", "remote-devops-sysadmin-jobs", "remote-programming-jobs"]


async def fetch_weworkremotely(url: str) -> str:
    """We Work Remotely RSS items carry the full description; match by link."""
    import xml.etree.ElementTree as ET
    target = (url or "").split("?")[0].rstrip("/")
    async with httpx.AsyncClient(timeout=25, headers=_UA, follow_redirects=True) as client:
        for feed in _WWR_FEEDS:
            try:
                r = await client.get(f"https://weworkremotely.com/categories/{feed}.rss")
                r.raise_for_status()
                root = ET.fromstring(r.text)
            except Exception as exc:
                log.warning("wwr feed %s failed: %s", feed, str(exc)[:120])
                continue
            for it in root.iter("item"):
                if (it.findtext("link") or "").split("?")[0].rstrip("/") == target:
                    return _html_to_text(it.findtext("description") or "")[:FULL_TEXT_LIMIT]
    return ""


async def fetch_posting_text(url: str) -> str:
    """Posting text through Jina. Returns "" when every attempt only gives a login wall or bot check."""
    from backend.services.job_search import _jina_get
    from backend.services.digest_sources import JINA_SEM
    candidates = [c for c in (_linkedin_guest_url(url), url) if c]
    for c in candidates:
        async with JINA_SEM:
            try:
                md = await _jina_get(c, retries=1)
            except Exception:
                continue
        text = clean_markdown(md)
        if not looks_blocked(text):
            return clean_posting(text)[:FULL_TEXT_LIMIT]
    return ""


async def fetch_posting(url: str, title: str = "", company: str = "") -> dict:
    """{"description": clean text or "", "questions": list|None} using the best source for this URL."""
    out: dict = {"description": "", "questions": None}
    if "greenhouse.io" in (url or ""):
        desc, questions = await fetch_greenhouse(url)
        if desc:
            return {"description": desc, "questions": questions}
    elif "himalayas.app" in (url or ""):
        desc = await fetch_himalayas(url, title, company)
        if desc:
            return {"description": desc, "questions": None}
    elif "getonbrd.com" in (url or ""):
        desc = await fetch_getonboard(url, title)
        if desc:
            return {"description": desc, "questions": None}
    elif "weworkremotely.com" in (url or ""):
        desc = await fetch_weworkremotely(url)
        if desc:
            return {"description": desc, "questions": None}
    out["description"] = await fetch_posting_text(url)
    return out


async def _enrich(jobs: list[dict], limit: int = 25) -> int:
    """Fetch full text for postings that came without a description (mostly LinkedIn). Blocked pages are ignored."""
    todo = [j for j in jobs if len(j.get("snippet") or "") < 250][:limit]

    async def one(j: dict) -> None:
        got = await fetch_posting(j["url"], j.get("title", ""), j.get("company", ""))
        if got["description"]:
            j["snippet"] = got["description"]

    await asyncio.gather(*(one(j) for j in todo))
    return len(todo)


async def complete_descriptions(items: list[dict], min_chars: int = 900, refresh: bool = False) -> int:
    """
    Make sure every offer that will be emailed carries its real, clean posting text (never a login wall or bot check).
    Greenhouse offers are always fetched so their application questions are kept; refresh=True refetches everything.
    """
    async def one(it: dict) -> None:
        current = clean_posting(it.get("description") or "")
        if looks_blocked(current):
            current = ""
        it["description"] = current
        is_gh = "greenhouse.io" in (it.get("url") or "")
        if len(current) >= min_chars and not refresh and not is_gh:
            return
        got = await fetch_posting(it["url"], it.get("title", ""), it.get("company", ""))
        if got["description"] and (refresh or len(got["description"]) > len(current)):
            it["description"] = got["description"]
        if got["questions"] is not None:
            it["application_questions"] = got["questions"]

    todo = [i for i in items if refresh or "greenhouse.io" in (i.get("url") or "") or len(i.get("description") or "") < min_chars]
    await asyncio.gather(*(one(i) for i in todo))
    return len(todo)


def _salary_display(list_key: str, job: dict, f: dict) -> str | None:
    if f.get("salary_text") and re.search(r"\d", str(f["salary_text"])):
        return str(f["salary_text"])
    if list_key == CHILE:
        net = _chile_salary_net_clp(f)
        return f"${net:,.0f} líquido (estimado)".replace(",", ".") if net else None
    if list_key == REMOTE:
        pay = _remote_pay_monthly_usd(f)
        return f"USD {pay:,.0f}/mes" if pay else None
    return None


def build_item(list_key: str, job: dict, f: dict, scored: dict) -> dict:
    item = {
        "list": list_key, "score": scored["score"], "title": job.get("title"), "company": job.get("company"),
        "location": f.get("city_country") or job.get("location"), "modality": _s(f.get("modality")) or "unknown",
        "days_posted": job.get("days_posted"), "salary": _salary_display(list_key, job, f),
        "url": job.get("url"), "reason": scored["reason"], "components": scored["components"], "source": job.get("source"),
        "description": (job.get("snippet") or "")[:FULL_TEXT_LIMIT],
    }
    if list_key == CHILE:
        item["agency"] = bool(scored.get("agency"))
    if list_key == REMOTE:
        item["applies_to"] = scored.get("applies_to")
        item["employment_type"] = _s(f.get("employment_type")) or "unknown"
        item["timezone"] = f.get("timezone")
    return item


async def process_list(list_key: str, jobs: list[dict], provider: str, model: str, *, enrich: bool = True) -> tuple[list[dict], dict, dict]:
    """Run one list end to end. Returns (all scored items sorted desc, stats, per-url outcomes)."""
    s = get_settings()
    drops: Counter = Counter()
    outcomes: dict = {}
    stats: dict = {"fetched": len(jobs)}

    def pre(rows: list[dict]) -> list[dict]:
        kept = []
        for j in rows:
            reason = PREFILTERS[list_key](j)
            if reason:
                drops[reason] += 1
                outcomes[j["url"]] = ("discard", reason, None)
            else:
                kept.append(j)
        return kept

    t0 = time.monotonic()
    cands = pre(jobs)
    cands.sort(key=lambda j: (-title_keyword_hits(j.get("title", "")), j.get("days_posted") if j.get("days_posted") is not None else 999))
    if len(cands) > s.digest_max_llm_jobs_per_list:
        stats["capped_out"] = len(cands) - s.digest_max_llm_jobs_per_list
        for j in cands[s.digest_max_llm_jobs_per_list:]:
            outcomes[j["url"]] = ("discard", "fuera_del_tope_de_candidatos", None)
        cands = cands[:s.digest_max_llm_jobs_per_list]
    if enrich:
        stats["enriched"] = await _enrich(cands)
        cands = pre(cands)
    stats["sent_to_llm"] = len(cands)
    t1 = time.monotonic()

    facts = await extract_facts(list_key, cands, provider, model)
    log.warning("digest %s: enrich %.0fs, llm extraction %.0fs for %d jobs", list_key, t1 - t0, time.monotonic() - t1, len(cands))
    scored_items: list[dict] = []
    for job, f in zip(cands, facts):
        if f is None:
            drops["llm_sin_respuesta"] += 1
            outcomes[job["url"]] = ("discard", "llm_sin_respuesta", None)
            continue
        apply_fit_floor(job, f)
        reason = POSTFILTERS[list_key](job, f)
        if reason:
            drops[reason] += 1
            outcomes[job["url"]] = ("discard", reason, f)
            continue
        item = build_item(list_key, job, f, SCORERS[list_key](job, f))
        outcomes[job["url"]] = ("score", item, f)
        scored_items.append(item)
    scored_items.sort(key=lambda x: x["score"], reverse=True)
    stats["scored"] = len(scored_items)
    stats["dropped"] = dict(drops)
    stats["unscored_llm_failed"] = drops.get("llm_sin_respuesta", 0)
    return scored_items, stats, outcomes
