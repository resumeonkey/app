"""
Job search service — uses Jina Reader (r.jina.ai, free, no API key) on
LinkedIn's public job search pages, which allows extracting real job listings
without any authentication.

Public API:
  generate_search_queries(master_sections, params, provider, model) → list[str]
  search_jobs_via_jina(query, num_results, location, remote, date_posted) → list[dict]
  extract_job_via_jina(url) → str
  score_job(job_text, master_sections, provider, model) → dict
"""
import asyncio
import json
import logging
import re
import uuid
from urllib.parse import quote, quote_plus

import httpx

from backend.services.llm_client import call_llm

log = logging.getLogger(__name__)

# ── CCFTA eligible job title keywords (Canada-Chile Free Trade Agreement) ─────
# Appendix L-1: Chilean nationals can get work permits WITHOUT LMIA in these roles.
_CCFTA_ELIGIBLE_TITLES = [
    "computer systems analyst", "systems analyst", "it analyst", "business analyst",
    "engineer", "software engineer", "data engineer", "cloud engineer",
    "management consultant", "business consultant", "implementation consultant",
    "operations consultant", "it consultant", "erp consultant", "crm consultant",
    "accountant", "cpa", "auditor", "financial analyst",
    "mathematician", "statistician", "data scientist", "data analyst",
    "actuary", "economist", "scientist",
    "architect", "urban planner",
    "land surveyor", "geologist", "meteorologist",
]


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text.strip())

_HTTP_TIMEOUT = 30          # seconds per Jina request
_MAX_JOB_CHARS = 8_000      # cap on extracted job text forwarded to LLM
_PROFILE_CHARS = 500        # profile excerpt sent to LLM for query generation
_SCORE_JOB_CHARS = 700      # job text sent per job in single-job scoring (reduced)
_BATCH_PROFILE_CHARS = 220  # profile excerpt in batch scoring (very compact)
_BATCH_SNIPPET_CHARS = 130  # snippet chars per job in batch mode

# Lighter models for scoring (vs generation). Saves tokens on rate-limited tiers.
_SCORE_MODEL_MAP: dict[str, str] = {
    # Groq: llama-3.1-8b has 500K TPD vs 100K for llama-3.3-70b (5× more headroom)
    "groq": "llama-3.1-8b-instant",
    # anthropic: claude-haiku is already the lightest — keep as-is
    # gemini: gemini-2.0-flash is already cheap — keep as-is
}


def _scoring_model(provider: str, model: str) -> str:
    """Return lightest model for the provider when doing compatibility scoring."""
    return _SCORE_MODEL_MAP.get(provider, model)

# ── LinkedIn filter constants ─────────────────────────────────────────────────
_REMOTE_FILTER = {
    "remote":  "2",
    "onsite":  "1",
    "hybrid":  "3",
}
_DATE_FILTER = {
    "24h": "r86400",
    "3d":  "r259200",
    "7d":  "r604800",
    "30d": "r2592000",
}

# ── Job Bank province codes ───────────────────────────────────────────────────
_JOBBANK_PROVINCE_CODES = {
    "british columbia": "BC", "bc": "BC",
    "alberta": "AB", "ab": "AB",
    "ontario": "ON", "on": "ON",
    "quebec": "QC", "qc": "QC",
    "manitoba": "MB", "mb": "MB",
    "saskatchewan": "SK", "sk": "SK",
    "nova scotia": "NS", "ns": "NS",
    "new brunswick": "NB", "nb": "NB",
    "newfoundland": "NL", "nl": "NL",
    "prince edward island": "PE", "pei": "PE",
    "northwest territories": "NT", "nt": "NT",
    "yukon": "YT", "yt": "YT",
    "nunavut": "NU", "nu": "NU",
}


# ── Query generation ──────────────────────────────────────────────────────────

async def generate_search_queries(
    master_sections: dict,
    params: dict,
    provider: str,
    model: str,
    bilingual_spanish: bool = False,
) -> list[str]:
    """
    Use LLM to generate 2–4 keyword search queries from the candidate profile
    and user-specified parameters. The location/remote filters are handled
    separately via LinkedIn URL parameters, so queries here are keywords only.
    """
    profile_text = _build_profile_text(master_sections)
    job_title    = params.get("job_title", "").strip()

    bilingual_hint = (
        '\n- El candidato es hispanohablante nativo. Incluir una query con "bilingual Spanish" '
        'o "bilingüe" si aplica al puesto.'
    ) if bilingual_spanish else ""

    prompt = f"""Eres un experto en búsqueda de empleo.

## Perfil del candidato (extracto)
{profile_text}

## Puesto que busca el usuario
{job_title or '(no especificado, infiere del perfil)'}

## Parámetros adicionales
- Industrias: {', '.join(params.get('industries', [])) or 'cualquiera'}
- Nivel: {', '.join(params.get('experience_level', [])) or 'cualquiera'}
- Keywords adicionales: {', '.join(params.get('include_keywords', [])) or 'ninguno'}
- Excluir: {', '.join(params.get('exclude_keywords', [])) or 'ninguno'}{bilingual_hint}

## Tu tarea
Genera 2–4 variaciones de búsqueda de keywords para LinkedIn Jobs.
Las queries deben ser SOLO palabras clave del puesto/skills (sin ciudad ni país, eso se filtra aparte).

Ejemplos correctos: "QA Engineer Automation", "Software Developer Python React", "Data Analyst SQL"
Ejemplos INCORRECTOS: "QA Engineer Vancouver Canada" (no incluir ubicación)

Responde ÚNICAMENTE con JSON válido:
{{"queries": ["keyword query 1", "keyword query 2"]}}"""

    try:
        raw = await call_llm(
            provider=provider,
            model=model,
            system="Eres un especialista en reclutamiento y búsqueda de empleo.",
            user=prompt,
            json_mode=True,
            temperature=0.3,
        )
        data   = _parse_json_response(raw)
        result = data.get("queries", [])
        if isinstance(result, list) and result:
            return [str(q).strip() for q in result[:4] if str(q).strip()]
    except Exception as e:
        log.warning("generate_search_queries failed: %s", e)

    # Fallback: use job_title directly
    if job_title:
        return [job_title]
    return ["software developer"]


def _build_profile_text(master_sections: dict) -> str:
    """Short profile excerpt (summary + skills) for LLM context."""
    parts = []
    for section in ("summary", "skills", "experience"):
        text = master_sections.get(section, {}).get("raw_text", "").strip()
        if text:
            parts.append(text[:200])
    return "\n\n".join(parts)[:_PROFILE_CHARS]


# ── LinkedIn search via Jina Reader ──────────────────────────────────────────

def _build_linkedin_url(
    query: str,
    location: str = "Canada",
    remote: str = "any",
    date_posted: str = "any",
) -> str:
    """Build a LinkedIn public job search URL with filters."""
    base = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={quote_plus(query)}"
        f"&location={quote_plus(location)}"
    )
    wt = _REMOTE_FILTER.get(remote)
    if wt:
        base += f"&f_WT={wt}"
    tpr = _DATE_FILTER.get(date_posted)
    if tpr:
        base += f"&f_TPR={tpr}"
    return base


_JOB_BLOCK_RE = re.compile(
    # Each listing on LinkedIn's Jina-rendered markdown looks like:
    # * [title-or-something](https://ca.linkedin.com/jobs/view/SLUG?...)
    #   ### Actual Job Title
    #   #### [Company Name](https://...)
    #   Location text  status text
    r'\*\s+\[.*?\]\((https://(?:ca\.|www\.)?linkedin\.com/jobs/view/[^\)]+)\)'
    r'.*?###\s+(.+?)\n'          # ### Job Title
    r'.*?####\s+\[(.+?)\]'      # #### [Company]
    r'.+?\n\s*(.+?)(?:\s{2,})', # location (two spaces separate fields)
    re.DOTALL,
)

_DATE_RE = re.compile(r'(\d+\s+(?:hour|day|week|month)s?\s+ago|Just now|Today)', re.IGNORECASE)


def _parse_linkedin_results(content: str, num_results: int) -> list[dict]:
    """Extract job listings from LinkedIn page markdown rendered by Jina."""
    results = []
    seen: set[str] = set()

    for m in _JOB_BLOCK_RE.finditer(content):
        url     = m.group(1).split("?")[0]   # strip tracking params
        title   = m.group(2).strip()
        company = m.group(3).strip()
        loc_raw = m.group(4).strip()

        if url in seen:
            continue
        seen.add(url)

        # Extract date from surrounding text (30-char window after match)
        context   = content[m.start():m.end() + 100]
        date_m    = _DATE_RE.search(context)
        date_text = date_m.group(0) if date_m else ""

        # Location can include trailing noise — take up to first  2+ spaces or newline
        location = re.split(r'\s{2,}|\n', loc_raw)[0].strip()

        results.append({
            "id":      str(uuid.uuid4()),
            "title":   title,
            "company": company,
            "location": location,
            "url":     url,
            "snippet": f"{title} at {company} — {location}",
            "content": "",   # full content fetched on-demand via extract_job
            "date":    date_text,
        })

        if len(results) >= num_results:
            break

    return results


async def search_jobs_via_jina(
    query: str,
    num_results: int = 10,
    location: str = "Canada",
    remote: str = "any",
    date_posted: str = "any",
) -> list[dict]:
    """
    Search LinkedIn jobs via Jina Reader (completely free, no API key).
    Returns a list of job dicts ready for scoring.
    """
    linkedin_url = _build_linkedin_url(query, location, remote, date_posted)

    headers = {
        "X-Return-Format": "markdown",
        "X-Timeout":       "20",
    }

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(
            f"https://r.jina.ai/{linkedin_url}",
            headers=headers,
        )
        response.raise_for_status()

    content = response.content.decode("utf-8", errors="replace")
    return _parse_linkedin_results(content, num_results)


# ── Job Bank (Canada) via Jina Reader ────────────────────────────────────────

def _build_jobbank_url(
    query: str,
    location: str = "Canada",
    province: str = "",
    remote: str = "any",
    lmia_only: bool = False,
) -> str:
    """Build a Job Bank Canada search URL."""
    base = (
        f"https://www.jobbank.gc.ca/jobsearch/jobsearch"
        f"?searchstring={quote_plus(query)}"
        f"&locationstring={quote_plus(location)}"
    )
    # Province filter
    code = _JOBBANK_PROVINCE_CODES.get(province.lower().strip(), "")
    if code:
        base += f"&fprov={code}"
    # Remote/telework filter
    if remote == "remote":
        base += "&fsrc=7"
    # LMIA filter — only show employers with approved LMIA (can hire foreign workers)
    if lmia_only:
        base += "&fwlmia=1"
    return base


# URL-anchored pattern — any link to a Job Bank job posting
_JOBBANK_POSTING_RE = re.compile(
    r'\[([^\]]{1,300})\]\((https://www\.jobbank\.gc\.ca/jobsearch/jobposting/\d+[^)]*)\)',
    re.IGNORECASE | re.DOTALL,
)

# Noise text Jina sometimes injects into Job Bank link text
_JOBBANK_NOISE_RE = re.compile(
    r'This job was posted directly by the employer on Job Bank\.?\s*'
    r'|^\s*Job\s*Bank\s+',
    re.IGNORECASE,
)

_JOBBANK_SALARY_RE = re.compile(
    r'\$[\d,]+(?:\.\d+)?(?:\s*(?:to|-|–)\s*\$[\d,]+(?:\.\d+)?)?(?:\s+(?:per\s+)?(?:hour|year|month))?',
    re.IGNORECASE,
)

# Province abbreviations for location guessing from context
_CA_PROVINCE_RE = re.compile(
    r'\b(British Columbia|Alberta|Ontario|Quebec|Manitoba|Saskatchewan|'
    r'Nova Scotia|New Brunswick|Newfoundland|Prince Edward Island|'
    r'BC|AB|ON|QC|MB|SK|NS|NB|NL|PE|NT|YT|NU)\b',
)


def _extract_jobbank_context(content: str, m_start: int, m_end: int) -> tuple[str, str, str, str | None]:
    """Extract company, location, date, salary from context around a Job Bank match."""
    before = content[max(0, m_start - 400):m_start]
    after  = content[m_end:min(len(content), m_end + 600)]
    ctx    = before + after

    # Company: look for "Business name:" or "Employer:" label
    company = ""
    for pat in (r'Business\s+name[:\s]+([^\n]{3,60})', r'Employer[:\s]+([^\n]{3,60})'):
        cm = re.search(pat, ctx, re.IGNORECASE)
        if cm:
            company = cm.group(1).strip()
            break

    # Location: look for "Location:" label or Canadian province mention
    location = "Canada"
    lm = re.search(r'Location[:\s]+([^\n]{3,60})', ctx, re.IGNORECASE)
    if lm:
        location = lm.group(1).strip()
    else:
        pm = _CA_PROVINCE_RE.search(after[:300])
        if pm:
            location = pm.group(0)

    # Date
    date = ""
    dm = re.search(r'(\d{4}-\d{2}-\d{2}|\d+\s+days?\s+ago|Today|yesterday)', ctx, re.IGNORECASE)
    if dm:
        date = dm.group(0)

    # Salary
    salary = None
    sm = _JOBBANK_SALARY_RE.search(after[:400])
    if sm:
        salary = sm.group(0).strip()

    return company, location, date, salary


def _parse_jobbank_results(content: str, num_results: int) -> list[dict]:
    """
    Extract job listings from Job Bank page markdown rendered by Jina.
    URL-first approach: find jobposting URLs, then extract context around them.
    """
    results = []
    seen: set[str] = set()

    for m in _JOBBANK_POSTING_RE.finditer(content):
        raw_link_text = m.group(1).strip()
        raw_url       = m.group(2)

        # Clean URL (strip session params)
        url = re.sub(r';jsessionid=[^?&]*', '', raw_url)
        base_url = url.split("?")[0]

        if base_url in seen:
            continue

        # Clean title from link text (remove Job Bank boilerplate)
        title = _JOBBANK_NOISE_RE.sub('', raw_link_text).strip()
        # Collapse internal whitespace/newlines from multi-line link text
        title = re.sub(r'\s+', ' ', title).strip()

        if len(title) < 3:
            continue

        seen.add(base_url)

        company, location, date, salary = _extract_jobbank_context(content, m.start(), m.end())

        # LMIA: check nearby text
        after_ctx = content[m.end():m.end() + 300]
        lmia = bool(re.search(r'\blmia\b|labour\s+market\s+impact', after_ctx, re.IGNORECASE))

        results.append({
            "id":             str(uuid.uuid4()),
            "title":          title,
            "company":        company,
            "location":       location,
            "url":            base_url + "?source=searchresults",
            "snippet":        f"{title} at {company} — {location}" if company else title,
            "content":        "",
            "date":           date,
            "salary_display": salary,
            "source":         "jobbank",
            "lmia_approved":  lmia,
        })

        if len(results) >= num_results:
            break

    return results


async def search_jobbank_via_jina(
    query: str,
    num_results: int = 10,
    location: str = "Canada",
    province: str = "",
    remote: str = "any",
    lmia_only: bool = False,
) -> list[dict]:
    """
    Search Job Bank Canada via Jina Reader (free, government portal, no blocking).
    Especially useful for jobs not posted on LinkedIn (SMEs, government, nonprofits).
    """
    jobbank_url = _build_jobbank_url(query, location, province, remote, lmia_only)

    headers = {
        "X-Return-Format": "markdown",
        "X-Timeout":       "20",
    }

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(
            f"https://r.jina.ai/{jobbank_url}",
            headers=headers,
        )
        response.raise_for_status()

    content = response.content.decode("utf-8", errors="replace")
    return _parse_jobbank_results(content, num_results)


# ── Workopolis via Jina Reader ───────────────────────────────────────────────

_WORKOPOLIS_DATE_FILTER = {
    "24h": "1", "3d": "3", "7d": "7", "30d": "30",
}


def _build_workopolis_url(
    query: str,
    location: str = "Canada",
    remote: str = "any",
    date_posted: str = "any",
) -> str:
    """Build a Workopolis job search URL."""
    base = (
        f"https://www.workopolis.com/jobsearch/find-jobs"
        f"?ak={quote_plus(query)}"
        f"&l={quote_plus(location)}"
    )
    if remote == "remote":
        base += "&ftr=Remote"
    elif remote == "hybrid":
        base += "&ftr=Hybrid"
    age = _WORKOPOLIS_DATE_FILTER.get(date_posted)
    if age:
        base += f"&age={age}"
    return base


# URL-anchored pattern — any link containing a Workopolis viewjob URL
_WORKOPOLIS_POSTING_RE = re.compile(
    r'\[([^\]]{3,200})\]\((https://www\.workopolis\.com/jobsearch/viewjob/[^\)\s]+)\)',
    re.IGNORECASE,
)

_WORKOPOLIS_SALARY_RE = re.compile(
    r'\$[\d,]+(?:\.\d+)?(?:\s*[–—-]\s*\$[\d,]+(?:\.\d+)?)?(?:\s+a\s+\w+)?',
    re.IGNORECASE,
)

_WORKOPOLIS_DATE_RE = re.compile(
    r'(\d+[dhw]|\d+\s+days?\s+ago|Just now|Today)',
    re.IGNORECASE,
)

# Various dash chars Workopolis might use between company and location
_DASH_SPLIT_RE = re.compile(r'\s*[—–\-]\s*')


def _parse_workopolis_results(content: str, num_results: int) -> list[dict]:
    """
    Extract job listings from Workopolis page markdown rendered by Jina.
    URL-first: find viewjob URLs then extract company/location from surrounding context.
    """
    results = []
    seen: set[str] = set()

    for m in _WORKOPOLIS_POSTING_RE.finditer(content):
        title = m.group(1).strip()
        url   = m.group(2).strip()

        if url in seen:
            continue
        seen.add(url)

        # The line immediately after the job link often has "Company — Location [rating]"
        after = content[m.end():m.end() + 400]
        lines = [ln.strip() for ln in after.split('\n') if ln.strip()]

        company  = ""
        location = "Canada"
        if lines:
            # First non-empty line should be "Company — Location"
            first_line = lines[0]
            # Strip markdown link syntax if present
            first_line = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', first_line)
            parts = _DASH_SPLIT_RE.split(first_line, maxsplit=1)
            if len(parts) == 2:
                company  = parts[0].strip()
                # Strip trailing rating like "[4.2]"
                location = re.sub(r'\s*\[[\d.]+\]\s*$', '', parts[1]).strip()
            else:
                company = first_line[:60]

        # Province fallback
        if location == "Canada":
            pm = _CA_PROVINCE_RE.search(after[:300])
            if pm:
                location = pm.group(0)

        salary_m = _WORKOPOLIS_SALARY_RE.search(after[:400])
        salary   = salary_m.group(0).strip() if salary_m else None

        date_m = _WORKOPOLIS_DATE_RE.search(after[:400])
        date   = date_m.group(0) if date_m else ""

        results.append({
            "id":             str(uuid.uuid4()),
            "title":          title,
            "company":        company,
            "location":       location,
            "url":            url,
            "snippet":        f"{title} at {company} — {location}" if company else title,
            "content":        "",
            "date":           date,
            "salary_display": salary,
            "source":         "workopolis",
        })

        if len(results) >= num_results:
            break

    return results


async def search_workopolis_via_jina(
    query: str,
    num_results: int = 10,
    location: str = "Canada",
    remote: str = "any",
    date_posted: str = "any",
) -> list[dict]:
    """
    Search Workopolis via Jina Reader (major Canadian job aggregator).
    Returns jobs not always found on LinkedIn (retail, trades, office, SMEs).
    """
    search_url = _build_workopolis_url(query, location, remote, date_posted)
    headers = {
        "X-Return-Format": "markdown",
        "X-Timeout":       "20",
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(f"https://r.jina.ai/{search_url}", headers=headers)
        response.raise_for_status()

    content = response.content.decode("utf-8", errors="replace")
    results = _parse_workopolis_results(content, num_results)
    log.info("workopolis: found %d results for %r", len(results), query)
    return results


# ── Eluta.ca via Jina Reader ──────────────────────────────────────────────────

def _build_eluta_url(query: str, location: str = "Canada") -> str:
    """Build an Eluta.ca job search URL (aggregates Canadian company career pages)."""
    return (
        f"https://www.eluta.ca/search"
        f"?q={quote_plus(query)}"
        f"&l={quote_plus(location)}"
    )


# URL-anchored pattern — Eluta job posting links (exclude home/search/about pages)
_ELUTA_POSTING_RE = re.compile(
    r'\[([^\]]{3,200})\]\((https?://(?:www\.)?eluta\.ca/(?!search\b|home\b|about\b|browse\b)[^\)\s]{10,})\)',
    re.IGNORECASE,
)

_ELUTA_COMPANY_RE = re.compile(
    r'\[([^\]]{2,60})\]\(https?://(?:www\.)?eluta\.ca/employer/[^\)]+\)',
    re.IGNORECASE,
)

_ELUTA_SALARY_RE = re.compile(
    r'\$[\d,]+(?:\.\d+)?(?:\s*(?:to|-|–)\s*\$[\d,]+(?:\.\d+)?)?(?:\s+(?:per\s+)?(?:hour|year|month))?',
    re.IGNORECASE,
)

_ELUTA_DATE_RE = re.compile(
    r'(\d+\s+days?\s+ago|\d+[dh]\s+ago|Today|Posted\s+\w+)',
    re.IGNORECASE,
)

_ELUTA_LOCATION_LINE_RE = re.compile(
    r'\n([A-Z][A-Za-z\s,\.]{5,50}(?:BC|AB|ON|QC|MB|SK|NS|NB|NL|PE|NT|YT|NU)[A-Za-z\s,\.]{0,20})\n',
)


def _parse_eluta_results(content: str, num_results: int) -> list[dict]:
    """
    Extract job listings from Eluta.ca page markdown rendered by Jina.
    URL-first: find job-page URLs, then extract company/location from surrounding context.
    """
    results = []
    seen: set[str] = set()

    for m in _ELUTA_POSTING_RE.finditer(content):
        title = m.group(1).strip()
        url   = m.group(2).strip()

        # Skip Eluta navigation / non-job links (company pages, apply links, etc.)
        if any(kw in title.lower() for kw in ('view all', 'see all', 'apply', 'more jobs', 'sign up')):
            continue
        if url in seen:
            continue
        seen.add(url)

        after = content[m.end():m.end() + 500]

        # Company: look for an Eluta employer link nearby
        company = ""
        cm = _ELUTA_COMPANY_RE.search(after[:300])
        if cm:
            company = cm.group(1).strip()

        # Location: look for a line containing a province abbreviation
        location = "Canada"
        lm = _ELUTA_LOCATION_LINE_RE.search(after[:400])
        if lm:
            location = lm.group(1).strip()
        else:
            pm = _CA_PROVINCE_RE.search(after[:300])
            if pm:
                location = pm.group(0)

        salary_m = _ELUTA_SALARY_RE.search(after[:400])
        salary   = salary_m.group(0).strip() if salary_m else None

        date_m = _ELUTA_DATE_RE.search(after)
        date   = date_m.group(0) if date_m else ""

        results.append({
            "id":             str(uuid.uuid4()),
            "title":          title,
            "company":        company,
            "location":       location,
            "url":            url,
            "snippet":        f"{title} at {company} — {location}",
            "content":        "",
            "date":           date,
            "salary_display": salary,
            "source":         "eluta",
        })

        if len(results) >= num_results:
            break

    return results


async def search_eluta_via_jina(
    query: str,
    num_results: int = 10,
    location: str = "Canada",
) -> list[dict]:
    """
    Search Eluta.ca via Jina Reader.
    Eluta aggregates directly from Canadian employer career pages — unique listings
    not found on LinkedIn or Job Bank.
    """
    search_url = _build_eluta_url(query, location)
    headers = {
        "X-Return-Format": "markdown",
        "X-Timeout":       "20",
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(f"https://r.jina.ai/{search_url}", headers=headers)
        response.raise_for_status()

    content = response.content.decode("utf-8", errors="replace")
    results = _parse_eluta_results(content, num_results)
    log.info("eluta: found %d results for %r", len(results), query)
    return results


# ── Jina Reader — extract full job description ────────────────────────────────

async def extract_job_via_jina(url: str) -> str:
    """
    Extract full job description from any URL using Jina Reader (r.jina.ai).
    Works with LinkedIn job pages, Indeed, company career pages, etc.
    Returns cleaned text capped at _MAX_JOB_CHARS.
    """
    encoded_url = quote(url, safe="")
    reader_url  = f"https://r.jina.ai/{encoded_url}"

    headers = {
        "X-Return-Format": "markdown",
        "X-Remove-Selector": (
            "header,footer,nav,.sidebar,#sidebar,"
            ".ads,.advertisement,.cookie-banner,.similar-jobs"
        ),
    }

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(reader_url, headers=headers)
        response.raise_for_status()

    raw = response.content.decode("utf-8", errors="replace")
    cleaned = _clean_extracted_text(raw)
    if _is_error_page(cleaned):
        raise ValueError("URL returned a bot-block or error page — cannot extract job description")
    return cleaned


_ERROR_PAGE_MARKERS = (
    # Cloudflare
    "cloudflare", "cf-ray", "error 403", "error 1020", "error 1015",
    "access denied", "403 forbidden", "attention required",
    # Generic bot/scraping blocks
    "please enable cookies", "enable javascript and cookies",
    "your browser", "ddos protection", "checking your browser",
    "security check", "ray id",
    # Workopolis / job board login walls
    "sign in to view", "create an account", "log in to apply",
)

def _is_error_page(text: str) -> bool:
    """Return True when extracted text looks like a bot-block or error page."""
    sample = text[:2000].lower()
    marker_hits = sum(1 for m in _ERROR_PAGE_MARKERS if m in sample)
    # Flag if 2+ markers found OR text is very short (under 300 chars after strip)
    return marker_hits >= 2 or len(text.strip()) < 300


def _clean_extracted_text(text: str) -> str:
    """Strip markdown images, convert links to text, cap length."""
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)           # images
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # links → text
    text = re.sub(r'\n{4,}', '\n\n\n', text)               # excessive blank lines
    return text.strip()[:_MAX_JOB_CHARS]


# ── LLM scoring ───────────────────────────────────────────────────────────────

def _fallback_score(raw: dict | None = None) -> dict:
    """Return a neutral score dict, optionally seeded with raw job metadata."""
    return {
        "compatibility_score": 50,
        "job_title":           (raw or {}).get("title", ""),
        "company":             (raw or {}).get("company", ""),
        "location":            (raw or {}).get("location", ""),
        "salary":              (raw or {}).get("salary_display"),
        "date_posted":         (raw or {}).get("date"),
        "matched_skills":      [],
        "missing_skills":      [],
        "score_summary":       "No se pudo calcular la compatibilidad.",
        "ccfta_eligible":      False,
        "immigration_support": "no",
        "bilingual_advantage": False,
    }


async def batch_score_jobs(
    raw_jobs: list[dict],
    master_sections: dict,
    provider: str,
    model: str,
    ccfta_check: bool = False,
    bilingual_spanish: bool = False,
) -> list[dict]:
    """
    Score ALL jobs in a SINGLE LLM call — ~88% fewer tokens than per-job scoring.
    Token comparison for 8 jobs:
      Old: 8 calls × ~850 tokens = 6,800 tokens
      New: 1 call  × ~750 tokens =   750 tokens

    Falls back to individual score_job() calls if the batch parse fails.
    """
    if not raw_jobs:
        return []

    # Auto-downgrade to lighter model for scoring (Groq 8B has 5× more daily tokens)
    score_model = _scoring_model(provider, model)

    profile = _build_profile_text(master_sections)[:_BATCH_PROFILE_CHARS]

    # Build compact 1-line summary per job (title + company + location + snippet)
    job_lines = []
    for i, job in enumerate(raw_jobs):
        snippet = (job.get("snippet", "") or "")[:_BATCH_SNIPPET_CHARS].replace("\n", " ")
        job_lines.append(
            f'{i}. {job.get("title","?")} @ {job.get("company","?")} — '
            f'{job.get("location","?")} | {snippet}'
        )
    jobs_text = "\n".join(job_lines)

    ccfta_note = (
        "\nCCFTA=true if role matches: Engineer/Analyst/Consultant/Accountant/Scientist/Architect."
    ) if ccfta_check else ""
    bilingual_note = (
        "\nbilingual=true if job values/requires Spanish or bilingual."
    ) if bilingual_spanish else ""

    prompt = f"""Score candidate-job compatibility for each job below. Return a JSON object.

Candidate (brief):
{profile}

Jobs (index. Title @ Company — Location | snippet):
{jobs_text}

Scoring: 90-100=all requirements met, 70-89=most, 50-69=partial, 30-49=significant gaps, 0-29=low fit.
immigration: "yes"=explicit sponsorship/LMIA/permit, "mentioned"=vague, "no"=none.{ccfta_note}{bilingual_note}

Return ONLY this JSON (one entry per job, same index order):
{{"results":[
  {{"i":0,"score":75,"matched":["skill1","skill2"],"missing":["skill3"],"summary":"brief reason max 90 chars","ccfta":false,"immigration":"no","bilingual":false}},
  ...
]}}"""

    try:
        raw = await call_llm(
            provider=provider,
            model=score_model,
            system="Senior recruiter. Score candidate-job fit. Be concise and accurate.",
            user=prompt,
            json_mode=True,
            temperature=0.1,
        )
        parsed = _parse_json_response(raw)

        # Handle both {"results": [...]} and bare [...]
        entries: list[dict] = parsed.get("results", parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(entries, list):
            raise ValueError(f"Unexpected batch response type: {type(parsed)}")

        # Build indexed lookup
        by_index: dict[int, dict] = {int(e.get("i", e.get("index", idx))): e
                                      for idx, e in enumerate(entries)}

        results = []
        for i, raw_job in enumerate(raw_jobs):
            entry = by_index.get(i)
            if not entry:
                results.append(_fallback_score(raw_job))
                continue
            results.append({
                "compatibility_score": max(0, min(100, int(entry.get("score", 50)))),
                "job_title":           raw_job.get("title", ""),
                "company":             raw_job.get("company", ""),
                "location":            raw_job.get("location", ""),
                "salary":              raw_job.get("salary_display"),
                "date_posted":         raw_job.get("date"),
                "matched_skills":      entry.get("matched", []),
                "missing_skills":      entry.get("missing", []),
                "score_summary":       str(entry.get("summary", ""))[:120],
                "ccfta_eligible":      bool(entry.get("ccfta", False)),
                "immigration_support": str(entry.get("immigration", "no")),
                "bilingual_advantage": bool(entry.get("bilingual", False)),
            })

        log.info(
            "batch_score_jobs: %d jobs scored in 1 call (provider=%s model=%s→%s)",
            len(raw_jobs), provider, model, score_model,
        )
        return results

    except Exception as e:
        log.warning(
            "batch_score_jobs failed (provider=%s model=%s): %s — falling back to per-job",
            provider, model, e,
        )
        # Per-job fallback (original behaviour, also uses lighter model)
        tasks = [
            score_job(
                job_text=(
                    f"{r.get('title','')} at {r.get('company','')} — {r.get('location','')}"
                    f"\n\n{r.get('snippet','')}"
                ),
                master_sections=master_sections,
                provider=provider,
                model=model,
                ccfta_check=ccfta_check,
                bilingual_spanish=bilingual_spanish,
            )
            for r in raw_jobs
        ]
        return await asyncio.gather(*tasks)  # type: ignore[return-value]


async def score_job(
    job_text: str,
    master_sections: dict,
    provider: str,
    model: str,
    ccfta_check: bool = False,
    bilingual_spanish: bool = False,
) -> dict:
    """
    Score a SINGLE job–candidate pair using LLM.
    Used for the /extract endpoint (full job description available).
    For search results, use batch_score_jobs() instead to save tokens.
    """
    profile_text = _build_profile_text(master_sections)
    job_excerpt  = job_text[:_SCORE_JOB_CHARS]

    ccfta_block = (
        "\nCCFTA check: ccfta_eligible=true if role matches Engineer/Systems Analyst/"
        "Management Consultant/Accountant/Scientist/Architect (Canada-Chile FTA)."
    ) if ccfta_check else ""

    bilingual_block = (
        "\nbilingual_advantage: true if job values/requires Spanish or bilingual."
    ) if bilingual_spanish else ""

    prompt = f"""Score candidate-job compatibility. Return only JSON.

Candidate:
{profile_text}

Job:
{job_excerpt}
{ccfta_block}{bilingual_block}
JSON:
{{
  "compatibility_score": 75,
  "job_title": "exact title",
  "company": "company or empty",
  "location": "city/province or Remote",
  "salary": "range or null",
  "date_posted": "date or null",
  "matched_skills": ["skill1"],
  "missing_skills": ["skill2"],
  "score_summary": "one sentence max 90 chars",
  "ccfta_eligible": false,
  "immigration_support": "no",
  "bilingual_advantage": false
}}

Scoring: 90-100=all met, 70-89=most, 50-69=partial, 30-49=gaps, 0-29=low fit.
immigration: "yes"=explicit sponsor/LMIA/permit, "mentioned"=vague, "no"=none."""

    try:
        raw = await call_llm(
            provider=provider,
            model=_scoring_model(provider, model),
            system="Senior recruiter. Score candidate-job fit accurately.",
            user=prompt,
            json_mode=True,
            temperature=0.1,
        )
        data = _parse_json_response(raw)
        return {
            "compatibility_score": max(0, min(100, int(data.get("compatibility_score", 50)))),
            "job_title":           str(data.get("job_title", "")).strip(),
            "company":             str(data.get("company", "")).strip(),
            "location":            str(data.get("location", "")).strip(),
            "salary":              data.get("salary"),
            "date_posted":         data.get("date_posted"),
            "matched_skills":      data.get("matched_skills", []),
            "missing_skills":      data.get("missing_skills", []),
            "score_summary":       str(data.get("score_summary", "")).strip()[:120],
            "ccfta_eligible":      bool(data.get("ccfta_eligible", False)),
            "immigration_support": str(data.get("immigration_support", "no")),
            "bilingual_advantage": bool(data.get("bilingual_advantage", False)),
        }
    except Exception as e:
        log.warning("score_job failed (provider=%s model=%s): %s", provider, model, e)
        return _fallback_score()
