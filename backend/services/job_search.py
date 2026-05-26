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


_JOBBANK_LINK_RE = re.compile(
    # Job Bank markdown: [...Job Bank TITLE * DATE * COMPANY * Location LOC * ...](url)
    r'\[(?:[^\]]*?)Job\s*Bank\s+([^\*\]]+?)'   # title after "Job Bank"
    r'\s*\*\s*([^\*]+?)'                         # date
    r'\s*\*\s*([^\*]+?)'                         # company
    r'\s*\*\s*Location\s+([^\*\]]+?)'            # location
    r'(?:\s*\*[^\]]*)?'                          # optional salary/other
    r'\]\((https://www\.jobbank\.gc\.ca/jobsearch/jobposting/\d+[^)]*)\)',
    re.DOTALL | re.IGNORECASE,
)

_JOBBANK_SALARY_RE = re.compile(
    r'Salary\s+(\$[\d,]+(?:\.\d+)?(?:\s+to\s+\$[\d,]+(?:\.\d+)?)?[^*\]]*)',
    re.IGNORECASE,
)


def _parse_jobbank_results(content: str, num_results: int) -> list[dict]:
    """Extract job listings from Job Bank page markdown rendered by Jina."""
    results = []
    seen: set[str] = set()

    for m in _JOBBANK_LINK_RE.finditer(content):
        title   = m.group(1).strip()
        date    = m.group(2).strip()
        company = m.group(3).strip()
        loc_raw = m.group(4).strip()
        raw_url = m.group(5)

        # Strip jsessionid tracking params
        url = re.sub(r';jsessionid=[^?]*', '', raw_url).split("?")[0]
        url += "?source=searchresults"

        if url in seen:
            continue
        seen.add(url)

        # Extract salary from surrounding context
        context   = content[m.start():m.end() + 50]
        salary_m  = _JOBBANK_SALARY_RE.search(context)
        salary    = salary_m.group(1).strip() if salary_m else None

        location = loc_raw.split("*")[0].strip()

        results.append({
            "id":       str(uuid.uuid4()),
            "title":    title,
            "company":  company,
            "location": location,
            "url":      url,
            "snippet":  f"{title} at {company} — {location}",
            "content":  "",
            "date":     date,
            "salary_display": salary,
            "source":   "jobbank",
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


_WORKOPOLIS_JOB_RE = re.compile(
    # ## [Job Title](https://www.workopolis.com/jobsearch/viewjob/HASH)
    # Company—Location [optional rating]
    r'##\s+\[(.+?)\]\((https://www\.workopolis\.com/jobsearch/viewjob/[^\)\s]+)\)\s*\n'
    r'([^\n—–-]+?)\s*[—–-]+\s*([^\n\[\d]+)',
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


def _parse_workopolis_results(content: str, num_results: int) -> list[dict]:
    """Extract job listings from Workopolis page markdown rendered by Jina."""
    results = []
    seen: set[str] = set()

    for m in _WORKOPOLIS_JOB_RE.finditer(content):
        title   = m.group(1).strip()
        url     = m.group(2).strip()
        company = m.group(3).strip()
        loc_raw = m.group(4).strip()

        if url in seen:
            continue
        seen.add(url)

        # Strip trailing rating like "[4.2]" from location
        location = re.split(r'\s*\[|\s{2,}|\n', loc_raw)[0].strip()

        # Look for salary in 250 chars following the match
        context  = content[m.start():m.end() + 250]
        salary_m = _WORKOPOLIS_SALARY_RE.search(context[m.end() - m.start():])
        salary   = salary_m.group(0).strip() if salary_m else None

        date_m = _WORKOPOLIS_DATE_RE.search(context[m.end() - m.start():])
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


_ELUTA_JOB_RE = re.compile(
    # ## [Job Title](https://www.eluta.ca/...) [$salary optional]
    # (blank line)
    # [Company Name](company_url)
    r'##\s+\[(.+?)\]\((https?://(?:www\.)?eluta\.ca/[^\)\s]+)\)'
    r'(?:\s+\[?\$([^\]\n\[]+?)\]?)?\s*\n'   # optional inline salary
    r'(?:\n|\s)*'
    r'\[([^\]]+)\]\([^\)]+\)',               # [Company](url)
    re.IGNORECASE,
)

_ELUTA_LOCATION_RE = re.compile(
    r'\n\s*([A-Z][A-Za-z\s\.\-]+(?:,\s*[A-Z]{2})?)\s*\n',
)

_ELUTA_DATE_RE = re.compile(
    r'(\d+\s+days?\s+ago|\d+[dh]\s+ago|Today|Posted\s+\w+)',
    re.IGNORECASE,
)


def _parse_eluta_results(content: str, num_results: int) -> list[dict]:
    """Extract job listings from Eluta.ca page markdown rendered by Jina."""
    results = []
    seen: set[str] = set()

    for m in _ELUTA_JOB_RE.finditer(content):
        title   = m.group(1).strip()
        url     = m.group(2).strip()
        salary  = m.group(3).strip() if m.group(3) else None
        company = m.group(4).strip()

        if url in seen:
            continue
        seen.add(url)

        # Location is typically on the line right after the company link
        after = content[m.end():m.end() + 300]
        loc_m = _ELUTA_LOCATION_RE.search(after)
        location = loc_m.group(1).strip() if loc_m else "Canada"

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
    return _clean_extracted_text(raw)


def _clean_extracted_text(text: str) -> str:
    """Strip markdown images, convert links to text, cap length."""
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)           # images
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # links → text
    text = re.sub(r'\n{4,}', '\n\n\n', text)               # excessive blank lines
    return text.strip()[:_MAX_JOB_CHARS]


# ── LLM scoring ───────────────────────────────────────────────────────────────

async def score_job(
    job_text: str,
    master_sections: dict,
    provider: str,
    model: str,
    ccfta_check: bool = False,
    bilingual_spanish: bool = False,
) -> dict:
    """
    Score job–candidate compatibility using LLM.
    Only the first 2000 chars of job_text are sent to keep token cost low.
    """
    profile_text = _build_profile_text(master_sections)
    job_excerpt  = job_text[:2000]

    ccfta_block = """
## Evaluación CCFTA (Tratado Libre Comercio Chile-Canadá)
El candidato es chileno. El CCFTA permite trabajar en Canadá SIN LMIA para estas categorías:
Computer Systems Analyst, Engineer, Management Consultant, Accountant, Mathematician/Statistician,
Data Scientist, Scientist, Architect, Land Surveyor.
"ccfta_eligible": true si el puesto encaja en alguna categoría anterior.
""" if ccfta_check else ""

    bilingual_block = """
## Evaluación bilingüe
"bilingual_advantage": true si el puesto valora o requiere español/bilingüe.
""" if bilingual_spanish else ""

    prompt = f"""Evalúa la compatibilidad entre este candidato y esta oferta laboral.

## Perfil del candidato
{profile_text}

## Oferta laboral
{job_excerpt}
{ccfta_block}{bilingual_block}
## Tu tarea
Extrae datos clave y calcula el score. Responde ÚNICAMENTE con JSON válido:

{{
  "compatibility_score": 85,
  "job_title": "título exacto del puesto",
  "company": "nombre de la empresa o cadena vacía",
  "location": "ciudad, provincia o 'Remote'",
  "salary": "rango salarial si disponible, sino null",
  "date_posted": "fecha si disponible, sino null",
  "matched_skills": ["skill1", "skill2"],
  "missing_skills": ["skill3"],
  "score_summary": "Una oración (máx 90 chars) explicando el score",
  "ccfta_eligible": false,
  "immigration_support": "no",
  "bilingual_advantage": false
}}

Valores para "immigration_support": "yes" (menciona sponsorship/LMIA/work permit), "mentioned" (referencia vaga), "no".

## Guía de scoring
90-100: Candidato cumple todos los requisitos + extras
70-89:  Cumple mayoría, pequeñas brechas
50-69:  Cumple básico, brechas moderadas
30-49:  Parcialmente compatible, brechas significativas
0-29:   Poca compatibilidad"""

    try:
        raw = await call_llm(
            provider=provider,
            model=model,
            system="Eres un reclutador senior. Evalúas candidatos con precisión y brevedad.",
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
            # Immigration fields
            "ccfta_eligible":      bool(data.get("ccfta_eligible", False)),
            "immigration_support": str(data.get("immigration_support", "no")),
            "bilingual_advantage": bool(data.get("bilingual_advantage", False)),
        }
    except Exception as e:
        log.warning("score_job failed (provider=%s model=%s): %s", provider, model, e)
        return _fallback_score()


def _fallback_score() -> dict:
    return {
        "compatibility_score": 50,
        "job_title": "", "company": "", "location": "",
        "salary": None, "date_posted": None,
        "matched_skills": [], "missing_skills": [],
        "score_summary": "No se pudo calcular la compatibilidad.",
    }
