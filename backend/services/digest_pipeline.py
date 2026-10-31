"""
Digest pipeline for the three lists: pre-filter -> cap -> enrich -> LLM fact extraction ->
post-filter -> deterministic scoring -> top N. The LLM never assigns the final score.
"""
import asyncio
import json
import logging
import re
import time
from collections import Counter

from backend.config import get_settings
from backend.services.digest_rubrics import (
    CANADA, CHILE, POSTFILTERS, PREFILTERS, REMOTE, SCORERS, _chile_salary_net_clp,
    _remote_pay_monthly_usd, _s, title_keyword_hits,
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
Never infer a language requirement from the company name or country. Return ONLY JSON: {"results":[{"i":0, ...}, ...]} with one object per job, in order.
Common keys: "i" (int), "is_job" (bool; false if the text is not a real single job posting), "modality" ("remote"|"hybrid"|"onsite"|"unknown"),
"city_country" (string), "salary_text" (string or null; copy the published salary as written)."""

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
"pay_usd_monthly" (number or null; convert hourly x160 and annual /12; null if unpublished or not convertible), "employment_type" ("employee_eor"|"employee"|"contractor"|"unknown"; EOR/Deel/Remote.com = employee_eor),
"timezone" (string or null), "languages_required" ("en_es"|"en"|"es"|"other"|"unknown"; en_es = BOTH English and Spanish required),
"domain_match" (bool; contact centre, ITSM, AI or telecom domain).""",
}

_BATCH = 10
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
        user = "\n\n".join(_job_block(k, j) for k, j in enumerate(chunk))
        async with _LLM_SEM:
            for attempt, wait in enumerate(_RETRY_WAITS, start=1):
                if wait:
                    await asyncio.sleep(wait)
                try:
                    raw = await call_llm(prov, mod, system, user, json_mode=True, temperature=0.0)
                    for row in _parse(raw):
                        idx = int(row.get("i", -1))
                        if 0 <= idx < len(chunk):
                            facts[start + idx] = row
                    return
                except Exception as exc:
                    log.warning("digest facts batch %s@%d attempt %d failed: %s", list_key, start, attempt, str(exc)[:200])

    await asyncio.gather(*(run(s) for s in range(0, len(jobs), _BATCH)))
    return facts


async def _enrich(jobs: list[dict], limit: int = 25) -> int:
    """Fetch full text for postings that came without a description (mostly LinkedIn)."""
    from backend.services.job_search import _jina_get
    from backend.services.digest_sources import JINA_SEM
    todo = [j for j in jobs if len(j.get("snippet") or "") < 250][:limit]
    async def one(j: dict) -> None:
        async with JINA_SEM:
            try:
                md = await _jina_get(j["url"], retries=1)
            except Exception:
                return
        j["snippet"] = clean_markdown(md)[:FULL_TEXT_LIMIT]

    await asyncio.gather(*(one(j) for j in todo))
    return len(todo)


FULL_TEXT_LIMIT = 8000


def clean_markdown(md: str) -> str:
    text = re.sub(r"\]\(https?://[^)]*\)", "]", md or "")
    text = re.sub(r"[#*_>\[\]`]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def complete_descriptions(items: list[dict], min_chars: int = 900) -> int:
    """Make sure every offer that will be emailed carries its full posting text (fetched through Jina if it is short)."""
    from backend.services.job_search import _jina_get
    from backend.services.digest_sources import JINA_SEM

    async def one(it: dict) -> None:
        if len(it.get("description") or "") >= min_chars:
            return
        async with JINA_SEM:
            try:
                md = await _jina_get(it["url"], retries=1)
            except Exception:
                return
        text = clean_markdown(md)[:FULL_TEXT_LIMIT]
        if len(text) > len(it.get("description") or ""):
            it["description"] = text

    todo = [i for i in items if len(i.get("description") or "") < min_chars]
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
