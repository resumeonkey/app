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

from backend.config import get_settings
from backend.services.llm_client import call_llm


def _jina_headers(extra: dict | None = None) -> dict:
    """Standard Jina Reader headers + optional Bearer auth (raises rate limits)."""
    h = {"X-Return-Format": "markdown", "X-Timeout": "20"}
    if extra:
        h.update(extra)
    key = get_settings().jina_api_key
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


async def _jina_get(target_url: str, extra_headers: dict | None = None, retries: int = 3) -> str:
    """
    GET a page through the Jina Reader with retry+backoff on rate-limit/timeout.
    The free Jina tier throttles bursts (5 parallel scrapes per search), causing
    intermittent failures; retrying with a short backoff recovers most of them.
    """
    import asyncio as _asyncio
    headers = _jina_headers(extra_headers)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(f"https://r.jina.ai/{target_url}", headers=headers)
            # A configured API key with no balance/invalid returns 401/402/403.
            # The free no-key reader works fine, so drop the auth header and retry
            # immediately — a bad key must never break scraping.
            if resp.status_code in (401, 402, 403) and "Authorization" in headers:
                log.warning("jina: key rejected (%s) — falling back to keyless", resp.status_code)
                headers = {k: v for k, v in headers.items() if k != "Authorization"}
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(
                    f"jina {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp.content.decode("utf-8", errors="replace")
        except httpx.HTTPError as e:
            last_exc = e
            if attempt < retries:
                await _asyncio.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_exc  # pragma: no cover

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

# ── CPTPP eligible job title keywords (Comprehensive & Progressive TPP) ────────
# Chile is a CPTPP member. Under Canada's CPTPP "Professionals and Technicians"
# commitments, Chilean nationals can access LMIA-exempt work permits for a BROADER
# set of professional/technical occupations than CCFTA, including many sustainability,
# environmental, agricultural and natural-resource roles relevant to the candidate's
# CPTPP strategy. This list is a fast title-based heuristic (LLM confirms in scoring).
_CPTPP_ELIGIBLE_TITLES = [
    # Professionals shared with CCFTA
    "engineer", "software engineer", "systems analyst", "business analyst",
    "data analyst", "data scientist", "consultant", "scientist", "architect",
    "accountant", "auditor", "economist", "statistician",
    # Environmental / sustainability (CPTPP-strategy focus)
    "environmental", "sustainability", "climate", "esg", "carbon",
    "conservation", "ecology", "ecologist", "renewable", "clean energy",
    "environmental engineer", "environmental scientist", "environmental analyst",
    "sustainability analyst", "sustainability consultant", "sustainability manager",
    # Agriculture / natural resources
    "agronomist", "agricultural", "agriculture", "forestry", "forester",
    "fisheries", "aquaculture", "natural resource",
    # Technical / specialist roles
    "technician", "technologist", "specialist", "coordinator",
    "project manager", "product manager", "implementation specialist",
    "quality", "researcher", "analyst",
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
_PROFILE_CHARS = 1500       # profile excerpt sent to LLM for query generation
_SCORE_JOB_CHARS = 700      # job text sent per job in single-job scoring (reduced)
_BATCH_PROFILE_CHARS = 2200  # profile excerpt in batch scoring — enough to include the full experience timeline (companies+domains+dates) so the LLM can judge DOMAIN-specific years, not just total career years
_BATCH_SNIPPET_CHARS = 600  # snippet chars per job in batch mode — enough to surface hard requirements (tools, years) so the scorer can detect real gaps

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

# Language keywords that should never be treated as job titles.
# When the user types one of these in "Puesto que buscas", we route it to the
# language/bilingual filter instead of using it as a keyword query.
_LANGUAGE_KEYWORDS: frozenset[str] = frozenset({
    "spanish", "español", "espanol", "bilingue", "bilingüe",
    "french", "français", "francais",
    "portuguese", "portugues", "português",
    "mandarin", "cantonese", "arabic", "korean", "japanese",
    "bilingual", "multilingual", "multilinguë",
})


def _is_language_keyword(text: str) -> bool:
    """Return True if text is a language name rather than a job title."""
    return text.strip().lower() in _LANGUAGE_KEYWORDS


async def generate_search_queries(
    master_sections: dict,
    params: dict,
    provider: str,
    model: str,
    bilingual_spanish: bool = False,
    english_level: str = "any",
    profile_tags: str = "",
    target_roles: str = "",
    excluded_roles: str = "",
    target_industries: str = "",
) -> list[str]:
    """
    Use LLM to generate 2–4 keyword search queries from the candidate profile
    and user-specified parameters. The location/remote filters are handled
    separately via LinkedIn URL parameters, so queries here are keywords only.

    Language detection:
    If the user typed a language name (e.g. "Spanish") as the job title, we
    treat it as a language requirement, infer the actual job role from the
    profile, and generate bilingual queries automatically.
    """
    profile_text = _build_profile_text(master_sections, profile_tags=profile_tags)
    raw_job_title = params.get("job_title", "").strip()

    # ── Detect language-as-job-title ─────────────────────────────────────────
    # e.g. user typed "Spanish" meaning "jobs that require Spanish"
    language_from_title = ""
    effective_job_title = raw_job_title
    if raw_job_title and _is_language_keyword(raw_job_title):
        language_from_title = raw_job_title
        effective_job_title = ""   # let the LLM infer the real job role from profile

    # ── Build language context block ──────────────────────────────────────────
    languages = [l.strip() for l in params.get("languages", ["english"]) if l.strip()]
    has_spanish = (
        bilingual_spanish
        or language_from_title.lower() in ("spanish", "español", "espanol")
        or any(l.lower() in ("spanish", "español", "espanol") for l in languages)
    )

    language_hint = ""
    if has_spanish:
        language_hint = (
            '\n- IMPORTANTE: El candidato busca ofertas que requieran o valoren español. '
            'Incluir AL MENOS UNA query que contenga "bilingual Spanish English" o '
            '"bilingue español inglés" según el rol inferido del perfil. '
            'Si el puesto no fue especificado, inferirlo del perfil del candidato.'
        )
    elif language_from_title:
        language_hint = (
            f'\n- El candidato busca ofertas que requieran {language_from_title}. '
            f'Incluir "bilingual {language_from_title}" en al menos una query.'
        )
    elif len(languages) > 1:
        other_langs = [l for l in languages if l.lower() != "english"]
        if other_langs:
            language_hint = (
                f'\n- Idiomas adicionales del candidato: {", ".join(other_langs)}. '
                f'Si aplica al puesto, incluir una query con "bilingual {other_langs[0]}".'
            )

    # ── English level hint ────────────────────────────────────────────────────
    # "basic" / "conversational" → avoid roles that require fluent/native English;
    # steer toward teams where Spanish is used or English demands are lower.
    _ENGLISH_LEVEL_QUERY_HINTS: dict[str, str] = {
        "basic": (
            '\n- NIVEL DE INGLÉS BÁSICO (A2-B1): Evitar roles que requieran redacción '
            'técnica en inglés o "excellent written English". Priorizar: equipos '
            'hispanohablantes, empresas latinoamericanas en Canadá, roles operativos '
            'o técnicos donde el inglés es secundario. Agregar una query con '
            '"no English required" o "Spanish speaking team" si aplica.'
        ),
        "conversational": (
            '\n- NIVEL DE INGLÉS CONVERSACIONAL (B1-B2): Buscar roles donde el inglés '
            'sea funcional pero no el foco principal. Evitar roles de redacción, '
            'comunicación ejecutiva o atención al cliente de alta complejidad. '
            'Incluir "entry level" o "bilingual" cuando sea coherente con el puesto.'
        ),
        "professional": "",   # no restriction — standard queries
        "fluent":        "",   # no restriction — full range
        "any":           "",   # no restriction
    }
    english_hint = _ENGLISH_LEVEL_QUERY_HINTS.get(english_level.lower(), "")

    # ── Generic profile-driven hints (work for ANY career track) ──────────────
    # These come from the user's own search profile, not hardcoded assumptions.
    target_roles_list   = [r.strip() for r in (target_roles or "").split(",") if r.strip()]
    excluded_roles_list = [r.strip() for r in (excluded_roles or "").split(",") if r.strip()]
    target_inds_list    = [i.strip() for i in (target_industries or "").split(",") if i.strip()]

    target_roles_hint = ""
    if target_roles_list and not effective_job_title:
        # No typed title → the profile's target roles DRIVE the queries.
        target_roles_hint = (
            "\n- ROLES OBJETIVO (prioridad alta): el candidato quiere específicamente estos puestos: "
            f"{', '.join(target_roles_list[:12])}. "
            "Genera queries basadas PRINCIPALMENTE en estos títulos y sus variantes cercanas. "
            "NO te desvíes hacia roles genéricos que no estén en esta lista."
        )
    elif target_roles_list:
        # The user TYPED a job title → that intent DOMINATES. Target roles are
        # only soft context; never let them override what the user actually typed.
        target_roles_hint = (
            f"\n- CONTEXTO (roles del perfil, secundario): {', '.join(target_roles_list[:8])}. "
            "PERO el usuario escribió un puesto específico arriba — ESE puesto MANDA. "
            "Genera las queries expandiendo el puesto escrito; usa los roles del perfil solo si "
            "coinciden con ese puesto. NO devuelvas queries de un dominio distinto al que el usuario escribió."
        )

    excluded_hint = ""
    if excluded_roles_list:
        excluded_hint = (
            "\n- ROLES/TÉRMINOS EXCLUIDOS (prohibido): NUNCA generes queries que puedan atraer estos: "
            f"{', '.join(excluded_roles_list[:20])}. "
            "Si un rol objetivo comparte palabra con un término excluido (ej: 'Project Coordinator' vs "
            "'Construction Project Coordinator'), añade un calificador que evite el dominio excluido."
        )

    target_inds_hint = ""
    if target_inds_list:
        target_inds_hint = (
            "\n- INDUSTRIAS OBJETIVO: el candidato prefiere estas industrias: "
            f"{', '.join(target_inds_list[:10])}. "
            "Cuando sea natural, incluye una palabra de industria en alguna query."
        )

    prompt = f"""Eres un experto en búsqueda de empleo en Canadá.

## Perfil del candidato (extracto)
{profile_text}

## Puesto que busca el usuario
{effective_job_title or '(no especificado — usa los ROLES OBJETIVO o infiere del perfil)'}

## Parámetros adicionales
- Industrias: {', '.join(params.get('industries', [])) or 'cualquiera'}
- Nivel: {', '.join(params.get('experience_level', [])) or 'cualquiera'}
- Keywords adicionales: {', '.join(params.get('include_keywords', [])) or 'ninguno'}
- Excluir: {', '.join(params.get('exclude_keywords', [])) or 'ninguno'}{target_roles_hint}{excluded_hint}{target_inds_hint}{language_hint}{english_hint}

## Tu tarea
Genera 2–4 variaciones de búsqueda de keywords para LinkedIn Jobs y Job Bank Canada.
Las queries deben ser SOLO palabras clave del puesto/skills (sin ciudad ni país).

## REGLA #1 — EL TÉRMINO ESCRITO MANDA (la más importante)
Si el "Puesto que busca el usuario" NO está vacío, TODAS las queries deben ser sobre
ESE término: sus sinónimos, expansiones o títulos directamente relacionados. NO uses
los roles del perfil ni la experiencia del resume para decidir QUÉ buscar cuando hay
un término escrito — el perfil es solo trasfondo.
  - "Claude"     → ["Claude", "Claude AI", "Anthropic"]   (producto/empresa: búscalo literal)
  - "QA Analyst" → ["QA Analyst", "Quality Assurance Analyst", "QA Tester"]
  - "HR IT"      → ["HRIS Analyst", "HR Systems Analyst", "HR Technology Analyst"]
PROHIBIDO devolver roles NO relacionados con el término escrito. Si el usuario escribió
"Claude", está TERMINANTEMENTE PROHIBIDO devolver "QA Analyst" u otros roles del resume.
Solo si el "Puesto que busca el usuario" está vacío, usa los ROLES OBJETIVO del perfil.

## CASO ESPECIAL — EMPRESA EN VEZ DE ROL
Si el "Puesto que busca el usuario" es claramente el NOMBRE DE UNA EMPRESA/empleador
(ej. Deloitte, EY, KPMG, Shopify, Google, Telus, RBC) y NO un título de puesto,
trátalo como un FILTRO DE EMPLEADOR: genera queries combinando tus ROLES OBJETIVO
con el nombre de la empresa, para encontrar SUS vacantes en tu rol.
  Ejemplo — usuario escribe "Deloitte":
    ✅ "HRIS Analyst Deloitte"
    ✅ "HR Systems Analyst Deloitte"
    ✅ "Business Systems Analyst Deloitte"
  NO ignores la empresa, y NO la conviertas en un rol.

## REGLA DE COHERENCIA (crítica)
Cada query DEBE ser UN TÍTULO DE PUESTO REAL Y COHERENTE (2–4 palabras que nombren
un solo rol). El "Puesto que busca el usuario" es una INTENCIÓN DE DOMINIO, no
palabras sueltas a buscar por separado.

- PROHIBIDO partir un input de varias palabras en términos independientes y amplios.
  Si el usuario escribe "HR IT" o "HR Technology", NO busques "HR" por un lado e "IT"
  por otro (eso trae HR Advisor, IT Support, GIS Analyst — dominios equivocados).
- En su lugar, EXPANDE la intención a títulos específicos y reales de ESE cruce de dominio.

Ejemplo — usuario escribe "HR IT" / "HR Technology":
  ✅ "HRIS Analyst"
  ✅ "HR Systems Analyst"
  ✅ "People Systems Analyst"
  ✅ "HR Data Analyst"
  ✅ "Workday Analyst"
  ❌ "HR Specialist"  (dominio HR genérico, no sistemas)
  ❌ "IT Support Technician"  (IT genérico)
  ❌ "GIS Analyst"  (dominio totalmente distinto)

Más ejemplos de formato correcto:
  "QA Analyst automation testing"
  "Implementation Specialist software"
  "Hotel Operations Manager hospitality"

Ejemplos INCORRECTOS:
  "Coordinator" (demasiado genérico)
  "Analyst" (genérico — atrae GIS, Financial, etc.)
  "QA Engineer Vancouver Canada" (no incluir ubicación)

## REGLA DE ANCLAJE A ROL (crítica — no inflar seniority ni buscar por plataforma)
- Cada query DEBE estar anclada a un TÍTULO DE ROL de los ROLES OBJETIVO (o muy cercano).
- Los nombres de PLATAFORMA/HERRAMIENTA (ej. "SAP SuccessFactors", "Workday", "SAP")
  NUNCA pueden ser una query por sí solos, ni el término principal. Una herramienta es
  un "plus", no el puesto. Buscar "SAP SuccessFactors" trae Consultants/Managers/Leads
  que NO corresponden al nivel del candidato.
  ❌ "SAP SuccessFactors"  ❌ "SuccessFactors Consultant"  ❌ "Workday"
  ✅ "HRIS Analyst"  ✅ "HR Systems Analyst"  ✅ "HR Reporting Analyst"
- NO subas el nivel: si los ROLES OBJETIVO son Analyst/Specialist/Coordinator, NO generes
  queries de "Consultant", "Manager", "Lead", "Senior Consultant", "Director" — aunque
  el perfil mencione esas herramientas. Mantén el nivel de los ROLES OBJETIVO.

Responde ÚNICAMENTE con JSON válido:
{{"queries": ["keyword query 1", "keyword query 2"]}}"""

    try:
        raw = await call_llm(
            provider=provider,
            model=model,
            system="Eres un especialista en reclutamiento y búsqueda de empleo en Canadá.",
            user=prompt,
            json_mode=True,
            temperature=0.1,   # low variance: stable, role-anchored queries run-to-run
        )
        data   = _parse_json_response(raw)
        result = data.get("queries", [])
        if isinstance(result, list) and result:
            return [str(q).strip() for q in result[:4] if str(q).strip()]
    except Exception as e:
        log.warning("generate_search_queries failed: %s", e)

    # Fallback
    if has_spanish:
        role = effective_job_title or "bilingual"
        return [f"bilingual Spanish English {role}".strip(), f"bilingue español {role}".strip()]
    if effective_job_title:
        return [effective_job_title]
    return ["software developer"]


def _build_profile_text(master_sections: dict, profile_tags: str = "") -> str:
    """
    Build a profile excerpt for LLM consumption.

    Extraction order (skills before summary) ensures tech signals like
    "QA, SQL, APIs, Product Owner" are visible before generic summary text.

    If the candidate set explicit profile_tags (comma-separated expertise),
    those appear as the very first line and override any profile inference.
    Example header:
      CANDIDATE PRIMARY EXPERTISE: QA/Testing | SQL | Product Owner | APIs | Telecom
    """
    # Skills-first order: tech signals before generic summary
    _WANT = [
        ("skill", "technical", "competenc", "tool"),   # skills first
        ("experience", "work", "employment", "history"),
        ("summary", "profile", "about"),               # summary last
    ]

    parts: list[str] = []
    used_keys: set[str] = set()

    for group in _WANT:
        for key, val in master_sections.items():
            key_lower = key.lower()
            if key in used_keys:
                continue
            if any(kw in key_lower for kw in group):
                text = (val or {}).get("raw_text", "").strip()
                if text:
                    parts.append(text[:400])
                    used_keys.add(key)
                    break  # one section per group

    # Fallback: dump first 3 sections if nothing matched above
    if not parts:
        for key, val in list(master_sections.items())[:3]:
            text = (val or {}).get("raw_text", "").strip()
            if text:
                parts.append(text[:400])

    combined = "\n\n".join(parts)

    # Explicit tags override: prepend as a structured header so the LLM
    # immediately knows the candidate's PRIMARY expertise before reading
    # the resume text (which may use generic language like "operations manager").
    if profile_tags and profile_tags.strip():
        tags = [t.strip() for t in profile_tags.split(",") if t.strip()]
        if tags:
            header = "CANDIDATE PRIMARY EXPERTISE: " + " | ".join(tags)
            combined = header + "\n\n" + combined

    return combined[:_PROFILE_CHARS]


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
    content = await _jina_get(linkedin_url)
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
    content = await _jina_get(jobbank_url)
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
    content = await _jina_get(search_url)
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


def _is_junk_job_title(title: str) -> bool:
    """
    True if a parsed 'title' is scraping noise rather than a real job posting:
    markdown images, logos, nav controls, ads, search UI, etc. Prevents entries
    like '![Image: Eluta Logo', 'Search', 'Close menu', 'Advertise your jobs'.
    """
    t = (title or "").strip().lower()
    if not t or len(t) < 3:
        return True
    if t.startswith("!") or t.startswith("![") or t.startswith("image"):
        return True
    # Multi-word phrases are safe as substrings (won't appear inside real titles).
    _JUNK_PHRASES = (
        "close menu", "open menu", "sign in", "sign up", "log in", "view all",
        "see all", "more jobs", "next page", "advertise your", "post a job",
    )
    if any(p in t for p in _JUNK_PHRASES):
        return True
    # Single words must match as WHOLE words, so "Research"/"Menu Engineer" etc.
    # are not wrongly flagged by "search"/"menu".
    _JUNK_WORDS = {
        "logo", "advertise", "cookie", "cookies",
        "newsletter", "subscribe", "filters",
    }
    words = set(re.findall(r"[a-z]+", t))
    return bool(words & _JUNK_WORDS)


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

        # Skip scraping noise (images, logos, nav, ads) and non-job links.
        if _is_junk_job_title(title):
            continue
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
    content = await _jina_get(search_url)
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
    raw = await _jina_get(encoded_url, extra_headers={
        "X-Remove-Selector": (
            "header,footer,nav,.sidebar,#sidebar,"
            ".ads,.advertisement,.cookie-banner,.similar-jobs"
        ),
    })
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


# ── Excluded-role hard filter ───────────────────────────────────────────────

def filter_excluded_roles(
    jobs: list[dict],
    excluded_roles: str,
) -> tuple[list[dict], list[dict]]:
    """
    Split jobs into (kept, excluded) based on the user's excluded_roles list.

    A job is excluded when its TITLE contains an excluded term as a whole
    word/phrase (case-insensitive). This is a cheap deterministic pre-filter
    that runs BEFORE the LLM scoring call — far more reliable than asking the
    model to ignore unwanted roles.

    Matching rules:
    - Multi-word excluded terms (e.g. "Construction Project Coordinator") match
      as a substring of the title.
    - Single-word terms (e.g. "Electrician", "MEP") match as a whole word only,
      so "MEP" does not match "comprehensive" and "civil" does not match "civility".
    """
    terms = [t.strip().lower() for t in (excluded_roles or "").split(",") if t.strip()]
    if not terms:
        return jobs, []

    kept: list[dict] = []
    excluded: list[dict] = []

    for job in jobs:
        title = (job.get("title", "") or "").lower()
        hit = None
        for term in terms:
            if not term:
                continue
            if " " in term:
                # multi-word: substring match
                if term in title:
                    hit = term
                    break
            else:
                # single word: whole-word match
                if re.search(rf'\b{re.escape(term)}\b', title):
                    hit = term
                    break
        if hit:
            job = {**job, "_excluded_by": hit}
            excluded.append(job)
        else:
            kept.append(job)

    return kept, excluded


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
        "english_barrier":     False,
        "english_required":    "unknown",
        # Structured assessment fields
        "confidence":          "low",
        "blockers":            [],
        "why_relevant":        [],
    }


async def batch_score_jobs(
    raw_jobs: list[dict],
    master_sections: dict,
    provider: str,
    model: str,
    ccfta_check: bool = False,
    bilingual_spanish: bool = False,
    english_level: str = "any",
    profile_tags: str = "",
    industry_experience: str = "",
    target_industries: str = "",
    extra_context: str = "",
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

    profile = _build_profile_text(master_sections, profile_tags=profile_tags)[:_BATCH_PROFILE_CHARS]
    # Fold in ALL other saved signals about the candidate (context files: LinkedIn,
    # extra skills, certifications, board roles…) so proximity scoring reflects the
    # full picture, not just the resume.
    if extra_context and extra_context.strip():
        profile += "\n\nADDITIONAL CANDIDATE BACKGROUND (context files):\n" + extra_context.strip()[:1800]

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
        "\nbilingual=true ONLY if the job text EXPLICITLY names a second spoken "
        "language as required or an asset — e.g. 'Spanish', 'French', 'bilingual', "
        "'English and French', 'fluency in Spanish', 'multilingual'. "
        "Do NOT set bilingual=true from generic global/international wording like "
        "'global team', 'international', 'worldwide', 'X countries', 'cross-border'. "
        "If no explicit language other than English is named, bilingual=false."
    ) if bilingual_spanish else ""

    # English level scoring note
    _ENGLISH_SCORE_NOTES: dict[str, str] = {
        "basic": (
            "\nenglish_level=basic (A2-B1). english_required: 'none'|'basic'|'conversational'|'professional'|'fluent'. "
            "english_barrier=true if job clearly requires conversational or higher. "
            "Deduct 25 pts from score if english_barrier=true."
        ),
        "conversational": (
            "\nenglish_level=conversational (B1-B2). english_required: 'none'|'basic'|'conversational'|'professional'|'fluent'. "
            "english_barrier=true if job clearly requires professional or fluent English. "
            "Deduct 15 pts from score if english_barrier=true."
        ),
        "professional": (
            "\nenglish_level=professional (B2-C1). english_required: 'none'|'basic'|'conversational'|'professional'|'fluent'. "
            "english_barrier=false for most roles. "
            "english_barrier=true only if job explicitly demands native-level English writing."
        ),
        "fluent": (
            "\nenglish_level=fluent (C1-C2). english_required: 'none'|'basic'|'conversational'|'professional'|'fluent'. "
            "english_barrier=false for all standard roles."
        ),
        "any": "",
    }
    english_note = _ENGLISH_SCORE_NOTES.get(english_level.lower(), "")

    # Industry context from the user's search profile (generic — any career track)
    industry_note = ""
    exp_list = [i.strip() for i in (industry_experience or "").split(",") if i.strip()]
    tgt_list = [i.strip() for i in (target_industries or "").split(",") if i.strip()]
    if exp_list or tgt_list:
        parts = []
        if exp_list:
            parts.append(
                "Candidate HAS real experience in these industries: "
                + ", ".join(exp_list[:10])
                + ". A job in one of these industries should NOT trigger an industry/domain gap blocker."
            )
        if tgt_list:
            parts.append(
                "Candidate is TARGETING these industries: " + ", ".join(tgt_list[:10]) + "."
            )
        parts.append(
            "If a job is in an industry the candidate has NO experience in AND that industry "
            "requires specialized domain knowledge, add an 'Industry gap' blocker and cap score at 60."
        )
        industry_note = "\n\nINDUSTRY CONTEXT:\n" + " ".join(parts)

    prompt = f"""Score candidate-job compatibility for each job below. Return a JSON object.

Candidate profile:
{profile}{industry_note}

Jobs (index. Title @ Company — Location | snippet):
{jobs_text}

SCORING RULES — read carefully:
- 90-100 = candidate meets nearly ALL hard requirements (years of experience, industry, seniority level, core skills)
- 70-89  = candidate meets MOST hard requirements with minor gaps
- 50-69  = candidate meets SOME requirements but has notable gaps in experience level or industry
- 30-49  = significant gaps: wrong industry, wrong seniority, or missing critical years of experience
- 0-29   = low fit: fundamentally different career track

CRITICAL CALIBRATION — these factors independently cap the score:
- SENIORITY CAP: if the job title/level is "Manager", "Senior Manager", "Consulting Manager",
  "Director", "VP", "Head of", "Lead", "Principal", "Senior Consultant", or "Consultant"
  AND the candidate's profile is analyst/specialist/coordinator/engineer/product-owner level
  → cap at 55 max. A strong tool match (e.g. SAP SuccessFactors) does NOT lift the score
  above this cap: the candidate has the tools but not the consulting/management level.
- Job requires "10+ years" in a specific industry AND candidate lacks that specific industry → cap at 50 max.
- Job requires domain expertise (banking, healthcare, legal) that candidate clearly lacks → cap at 55 max.
- Being bilingual IS a plus, but it CANNOT compensate for missing industry experience, seniority, or years.
  If a bilingual job has all the above caps apply, do NOT raise the score above the cap just for bilingual match.

NAMED-TOOL & SPECIFIC-REQUIREMENT GAPS — count them honestly:
- When the job names SPECIFIC platforms/tools/languages (e.g. Workday, Power BI, SAP SuccessFactors,
  Salesforce, Python, R, Tableau, ServiceNow) that the candidate's profile does NOT contain, each one
  is a real gap. Add it to "missing".
- Adjacent/transferable skills (e.g. "SQL + data validation") do NOT equal a named requirement
  (e.g. "Workday Reporting expertise" or "3-5 years HR Analytics"). Do not treat them as a match.
- If the job lists 3+ specific required tools/skills the candidate lacks, cap the score at 70 max.
- If on top of that the job requires several years in a domain the candidate has not worked in
  (e.g. "7-10 years leading HR SaaS migrations"), cap at 65 max.
- A high count of matched GENERIC skills (SQL, data quality, process improvement) does NOT lift the
  score past these caps when the SPECIFIC hard requirements are missing.

DOMAIN-YEARS HONESTY — the most important calibration rule:
- NEVER convert a candidate's TOTAL career years into DOMAIN-SPECIFIC years. A person with
  10+ years in technology/QA/systems but only a FEW years touching a specific domain (e.g. HR
  systems / HRIS / SuccessFactors) does NOT have "10+ years HRIS experience".
- Estimate domain-specific experience SEPARATELY from total experience. If most of the career
  was in OTHER areas (QA, telecom, product, support) and only a portion was in the job's domain,
  the domain-specific years are SMALL — judge the fit on those.
- A job asking for "Senior" + "N+ years" of the SPECIFIC domain, when the candidate's
  domain-specific experience is clearly less → cap at 65 max and add a blocker
  "Domain-depth gap: limited dedicated <domain> experience".
- In why_relevant, NEVER write "10+ years HRIS", "Senior HRIS professional", "extensive HRIS
  administration", "deep HRIS ownership" for such a candidate. Instead write honestly:
  "HR systems exposure through Product Owner role", "SuccessFactors reporting experience",
  "HR data validation background", "system implementation & UAT experience".
- Their real edge is transferable: technology/QA/validation/process + SOME HR-systems work.
  Frame it that way — do not manufacture a career-long specialist.

PHYSICAL/TRADES DOMAIN CAP — applies when job is in a physical/on-site domain:
- Job title/description shows: construction, civil engineering, MEP, site coordinator, field safety,
  property/facilities management, mining, trades, superintendent, site supervisor, building operations
  AND candidate profile shows: IT, software, QA, telecom, product owner, systems, technical support
  → MANDATORY blocker: "Domain gap: construction/trades expertise required"
  → Cap score at 40 max. Cross-industry "coordination experience" does NOT count for physical domains.
- "10+ years operations coordination" from a tech/telecom background is NOT equivalent to
  10+ years construction coordination. Do NOT list it as why_relevant for these roles.

immigration: "yes"=explicit sponsorship/LMIA/permit, "mentioned"=vague, "no"=none.{ccfta_note}{bilingual_note}{english_note}

confidence field: assess how much job-requirement info you actually had.
  "high"   = snippet included years of experience, mandatory skills, seniority level
  "medium" = snippet had some requirements but was incomplete
  "low"    = you only had the job title and company — no visible requirements

blockers: list up to 3 hard blockers (things that would prevent advancing in the hiring process).
  Examples: "Seniority gap: Senior Manager vs analyst profile",
            "Industry gap: 10+ years banking required",
            "Domain gap: mandatory retail banking operations expertise"
  Empty list [] if no major blockers.

why_relevant: list 2-3 genuine reasons the candidate IS worth noting for this role.
  Examples: "Bilingual Spanish/English", "Process improvement experience",
            "Stakeholder coordination background"
  Be honest — only include real strengths, not forced connections.
  DO NOT overstate transferable experience as direct domain expertise. Phrase the
  candidate's level accurately:
    ✅ "HR process-design exposure" / "system validation background applicable to HR systems"
    ❌ "HRIS specialist" / "end-to-end HR systems implementation expert" (unless the
       profile literally shows that role). "Participated in HR process design" is NOT
       the same as "HRIS analyst" — never phrase it as if it were.

Return ONLY this JSON (one entry per job, same index order):
{{"results":[
  {{"i":0,"score":48,"matched":["skill1"],"missing":["skill2","skill3"],"summary":"brief reason max 90 chars","ccfta":false,"immigration":"no","bilingual":true,"english_barrier":false,"english_required":"professional","confidence":"low","blockers":["Seniority gap","Industry gap: banking"],"why_relevant":["Bilingual Spanish/English","Process improvement"]}},
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
                "english_barrier":     bool(entry.get("english_barrier", False)),
                "english_required":    str(entry.get("english_required", "unknown")),
                "confidence":          str(entry.get("confidence", "medium")),
                "blockers":            entry.get("blockers", []) if isinstance(entry.get("blockers"), list) else [],
                "why_relevant":        entry.get("why_relevant", []) if isinstance(entry.get("why_relevant"), list) else [],
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
                english_level=english_level,
                profile_tags=profile_tags,
                industry_experience=industry_experience,
                target_industries=target_industries,
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
    english_level: str = "any",
    profile_tags: str = "",
    industry_experience: str = "",
    target_industries: str = "",
) -> dict:
    """
    Score a SINGLE job–candidate pair using LLM.
    Used for the /extract endpoint (full job description available).
    For search results, use batch_score_jobs() instead to save tokens.
    """
    profile_text = _build_profile_text(master_sections, profile_tags=profile_tags)
    job_excerpt  = job_text[:_SCORE_JOB_CHARS]

    ccfta_block = (
        "\nCCFTA check: ccfta_eligible=true if role matches Engineer/Systems Analyst/"
        "Management Consultant/Accountant/Scientist/Architect (Canada-Chile FTA)."
    ) if ccfta_check else ""

    bilingual_block = (
        "\nbilingual_advantage: true ONLY if the job text EXPLICITLY names a second "
        "spoken language as required or an asset (Spanish, French, bilingual, "
        "'English and French', 'multilingual'). Do NOT infer it from generic "
        "global/international wording ('global team', 'worldwide', 'X countries'). "
        "If no explicit non-English language is named, bilingual_advantage=false."
    ) if bilingual_spanish else ""

    # English level block for single-job scoring
    _ENGLISH_SINGLE_NOTES: dict[str, str] = {
        "basic": (
            "\nCandidate English level: basic (A2-B1). "
            "english_required: which level the job needs ('none'|'basic'|'conversational'|'professional'|'fluent'). "
            "english_barrier=true if job needs conversational or higher. "
            "Deduct 25 pts if english_barrier=true."
        ),
        "conversational": (
            "\nCandidate English level: conversational (B1-B2). "
            "english_required: which level the job needs. "
            "english_barrier=true if job needs professional or fluent English. "
            "Deduct 15 pts if english_barrier=true."
        ),
        "professional": (
            "\nCandidate English level: professional (B2-C1). "
            "english_required: which level the job needs. "
            "english_barrier=true only if job explicitly demands native-level writing."
        ),
        "fluent": (
            "\nCandidate English level: fluent (C1-C2). "
            "english_required: which level the job needs. "
            "english_barrier=false for all standard roles."
        ),
        "any": "",
    }
    english_block = _ENGLISH_SINGLE_NOTES.get(english_level.lower(), "")

    # Industry context from search profile
    industry_block = ""
    _exp = [i.strip() for i in (industry_experience or "").split(",") if i.strip()]
    _tgt = [i.strip() for i in (target_industries or "").split(",") if i.strip()]
    if _exp or _tgt:
        _b = []
        if _exp:
            _b.append(
                "Candidate HAS experience in: " + ", ".join(_exp[:10])
                + " (do NOT flag industry gap for these)."
            )
        if _tgt:
            _b.append("Candidate targets: " + ", ".join(_tgt[:10]) + ".")
        industry_block = "\nINDUSTRY CONTEXT: " + " ".join(_b)

    prompt = f"""Score candidate-job compatibility. Return only JSON.

Candidate:
{profile_text}

Job:
{job_excerpt}
{ccfta_block}{bilingual_block}{english_block}{industry_block}

SCORING RULES:
- 90-100 = candidate meets nearly ALL hard requirements (years, industry, seniority, core skills)
- 70-89  = meets MOST hard requirements with minor gaps
- 50-69  = meets SOME requirements, notable gaps in level or industry
- 30-49  = significant gaps: wrong industry, wrong seniority, or missing critical years
- 0-29   = fundamentally different career track

CAPS (these override the base score):
- Job says "Senior Manager/Director/VP" AND candidate shows analyst/specialist/engineer roles → cap 55
- Job requires 10+ years in a specific domain AND candidate lacks that domain → cap 50
- Core domain expertise required (banking, healthcare, legal) AND candidate lacks it → cap 55
- Bilingual match is a PLUS (max +10 pts) but CANNOT override seniority or domain caps

PHYSICAL/TRADES DOMAIN CAP:
- Job is in construction, civil, MEP, site supervision, field safety, facilities, mining, property management
  AND candidate is from IT/software/telecom/QA/product management background
  → MANDATORY blocker "Domain gap: construction/trades expertise required" → cap score at 40 max.
- Generic coordination experience from tech/telecom background does NOT transfer to physical/trades domains.
  Do NOT list "10+ years operations coordination" as why_relevant for construction roles.

confidence: how much requirement detail was in the job text.
  "high"=seen years/seniority/mandatory skills, "medium"=partial, "low"=only title/company visible

blockers: up to 3 hard blockers preventing hiring (e.g. "Seniority gap: Director vs. analyst profile")
why_relevant: up to 3 genuine strengths the candidate has for this role

immigration: "yes"=explicit sponsor/LMIA/permit, "mentioned"=vague, "no"=none.

JSON:
{{
  "compatibility_score": 48,
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
  "bilingual_advantage": false,
  "english_barrier": false,
  "english_required": "professional",
  "confidence": "high",
  "blockers": ["Seniority gap: Senior Manager vs analyst profile"],
  "why_relevant": ["Bilingual Spanish/English", "Process improvement experience"]
}}"""

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
            "english_barrier":     bool(data.get("english_barrier", False)),
            "english_required":    str(data.get("english_required", "unknown")),
            "confidence":          str(data.get("confidence", "high")),
            "blockers":            data.get("blockers", []) if isinstance(data.get("blockers"), list) else [],
            "why_relevant":        data.get("why_relevant", []) if isinstance(data.get("why_relevant"), list) else [],
        }
    except Exception as e:
        log.warning("score_job failed (provider=%s model=%s): %s", provider, model, e)
        return _fallback_score()
