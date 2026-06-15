"""
Job search endpoints.

  GET  /api/search/suggest              → suggested search params from active master
  POST /api/search/run                  → search + score jobs
  POST /api/search/extract              → extract job description from URL
"""
import asyncio
import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.master import MasterResume
from backend.services.job_search import (
    generate_search_queries,
    search_jobs_via_jina,
    search_jobbank_via_jina,
    search_workopolis_via_jina,
    search_eluta_via_jina,
    extract_job_via_jina,
    batch_score_jobs,
    score_job,
    _build_profile_text,
    _parse_json_response,
    _build_jobbank_url,
    _build_workopolis_url,
    _build_eluta_url,
    _parse_jobbank_results,
    _parse_workopolis_results,
    _parse_eluta_results,
    _CCFTA_ELIGIBLE_TITLES,
    _CPTPP_ELIGIBLE_TITLES,
    _is_language_keyword,
    filter_excluded_roles,
)

log = logging.getLogger(__name__)
from backend.services.llm_client import call_llm

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class SearchParams(BaseModel):
    # Which profile (master resume) to search with — if None, uses the active one
    master_id: Optional[str] = None

    # What to search for
    job_title: str = ""
    custom_query: str = ""        # if set, bypass LLM query generation

    # Location
    country: str = "Canada"
    province: str = ""
    city: str = ""
    remote: str = "any"           # "remote" | "hybrid" | "onsite" | "any"

    # Job characteristics
    job_type: list[str] = []      # "full-time" | "part-time" | "contract" | "internship"
    experience_level: list[str] = []  # "entry" | "mid" | "senior" | "lead" | "executive"

    # Compensation
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "CAD"

    # Company
    company_type: list[str] = []  # "startup" | "mid-size" | "enterprise" | "non-profit" | "government"
    company_size: list[str] = []  # "small" | "medium" | "large" | "enterprise"

    # Keywords
    include_keywords: list[str] = []
    exclude_keywords: list[str] = []

    # Other
    languages: list[str] = ["english"]
    date_posted: str = "any"      # "24h" | "3d" | "7d" | "30d" | "any"
    industries: list[str] = []

    # Control
    num_results: int = 8
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5"

    # Filtros para inmigrantes / hispanohablantes
    lmia_only: bool = False         # Job Bank: solo empleos con LMIA aprobado
    bilingual_spanish: bool = False # Boost "bilingüe español" en queries
    ccfta_check: bool = False       # Evaluar elegibilidad bajo Tratado Chile-Canadá

    # Nivel de inglés del candidato — afecta queries Y scoring
    # "any"           → sin filtro (comportamiento actual)
    # "basic"         → A2-B1: puede leer/escribir oraciones simples
    # "conversational"→ B1-B2: puede comunicarse con algo de esfuerzo
    # "professional"  → B2-C1: inglés de negocios completo
    # "fluent"        → C1-C2: nivel nativo o casi nativo
    english_level: str = "any"


class ExtractRequest(BaseModel):
    url: str
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/suggest")
async def suggest_params(
    llm_provider: str = "anthropic",
    llm_model: str = "claude-haiku-4-5",
    db: Session = Depends(get_db),
):
    """
    Return suggested search parameters inferred from the active master resume.
    Used to pre-populate the search form on first load.
    """
    master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
    if not master or not master.sections:
        return {"suggestions": {}, "recommendations": []}

    profile = _build_profile_text(master.sections)
    if not profile:
        log.warning("suggest_params: could not extract profile text; sections=%s",
                    list(master.sections.keys()))
        return {"suggestions": {}, "recommendations": []}

    prompt = f"""Analiza este perfil de resume y genera:
1. Los parámetros de búsqueda más apropiados (campo principal).
2. Entre 4 y 5 roles alternativos que el candidato podría buscar, con motivo específico.

## Perfil
{profile[:1500]}

Responde ÚNICAMENTE con JSON válido:
{{
  "job_title": "título del puesto más apropiado para este candidato",
  "experience_level": ["mid"],
  "industries": ["Technology"],
  "skills_highlight": "3-5 skills principales separadas por coma",
  "recommendations": [
    {{
      "title": "Implementation Consultant",
      "keywords": "software implementation consultant ERP",
      "experience_level": ["mid"],
      "industries": ["Technology", "Consulting"],
      "remote": "any",
      "why": "Tu experiencia en onboarding técnico y QA encaja directamente",
      "icon": "🚀"
    }},
    {{
      "title": "Business Analyst",
      "keywords": "business analyst requirements agile",
      "experience_level": ["mid"],
      "industries": ["Technology"],
      "remote": "any",
      "why": "Mapea con tus habilidades de análisis y documentación de procesos",
      "icon": "📊"
    }}
  ]
}}

Reglas para recommendations:
- Entre 4 y 5 entradas, roles DISTINTOS entre sí
- "why" debe ser específico al perfil (max 80 chars), en español
- "keywords" es la query de búsqueda en inglés para Canada
- "icon" un emoji relevante al rol
- "remote" puede ser "remote", "hybrid", o "any"
- Los roles deben tener alta probabilidad de match con el perfil"""

    try:
        raw = await call_llm(
            provider=llm_provider,
            model=llm_model,
            system="Eres un coach de carrera senior. Analizas perfiles y sugieres búsquedas precisas.",
            user=prompt,
            json_mode=True,
            temperature=0.3,
        )
        data = _parse_json_response(raw)   # strips markdown fences before json.loads
        recs = data.get("recommendations", [])
        log.info("suggest_params: got %d recommendations (profile_chars=%d)",
                 len(recs), len(profile))
        return {
            "suggestions": {k: v for k, v in data.items() if k != "recommendations"},
            "recommendations": recs,
        }
    except Exception as exc:
        log.error("suggest_params: LLM call failed — %s", exc, exc_info=True)
        return {"suggestions": {}, "recommendations": []}


@router.post("/run")
async def run_search(params: SearchParams, db: Session = Depends(get_db)):
    """
    Search for jobs matching the candidate profile + user parameters.
    Steps:
      1. Generate search queries (via LLM or custom_query override)
      2. Run Jina Search for each query (parallel, deduplicate by URL)
      3. Score each result against the active master resume (parallel)
      4. Sort by compatibility score and return
    """
    # ── Select profile (master) for this search ───────────────────────────────
    # Per-search profile selection: the user can search with any master without
    # changing the globally "active" one. Falls back to active master if no id.
    master = None
    if params.master_id:
        master = db.query(MasterResume).filter(MasterResume.id == params.master_id).first()
    if not master:
        master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
    if not master:
        raise HTTPException(status_code=400, detail="No hay un resume maestro activo.")

    master_sections = master.sections or {}

    # ── Resolve english_level: param > master profile > "any" ─────────────────
    resolved_english_level = params.english_level
    if resolved_english_level == "any" and master.english_level and master.english_level != "any":
        resolved_english_level = master.english_level

    # ── Resolve search-profile fields from the selected master ────────────────
    resolved_profile_tags       = (master.profile_tags or "").strip()
    resolved_target_roles       = (master.target_roles or "").strip()
    resolved_excluded_roles     = (master.excluded_roles or "").strip()
    resolved_industry_experience = (master.industry_experience or "").strip()
    resolved_target_industries  = (master.target_industries or "").strip()

    # ── Step 1: Queries ───────────────────────────────────────────────────────
    # Auto-detect language keywords typed in the job_title field.
    # e.g. user typed "Spanish" → they want jobs requiring Spanish, not jobs
    # whose title contains the word "Spanish".  Auto-enable bilingual_spanish.
    effective_bilingual = params.bilingual_spanish
    if params.job_title and _is_language_keyword(params.job_title):
        title_lower = params.job_title.strip().lower()
        if title_lower in ("spanish", "español", "espanol", "bilingue", "bilingüe"):
            effective_bilingual = True
        # In all language-keyword cases, the job_title field routes to language hints
        # inside generate_search_queries — no need to override params here.

    # Also auto-enable when "spanish" is in the languages list
    if any(l.strip().lower() in ("spanish", "español", "espanol")
           for l in params.languages):
        effective_bilingual = True

    if params.custom_query.strip():
        queries = [params.custom_query.strip()]
    else:
        queries = await generate_search_queries(
            master_sections=master_sections,
            params=params.model_dump(),
            provider=params.llm_provider,
            model=params.llm_model,
            bilingual_spanish=effective_bilingual,
            english_level=resolved_english_level,
            profile_tags=resolved_profile_tags,
            target_roles=resolved_target_roles,
            excluded_roles=resolved_excluded_roles,
            target_industries=resolved_target_industries,
        )

    if not queries:
        raise HTTPException(status_code=422, detail="No se pudieron generar consultas de búsqueda.")

    # ── Step 2: Search LinkedIn + Job Bank via Jina Reader (parallel) ───────────
    # Build location strings
    location_parts = [p for p in [params.city, params.province, params.country] if p.strip()]
    location_str   = ", ".join(location_parts) if location_parts else "Canada"

    # Each source fetches results_per_source jobs; dedup + score happens after.
    # 5 sources in parallel: LinkedIn x2, Job Bank, Workopolis, Eluta.
    results_per_source = max(4, params.num_results // 2)

    search_tasks = [
        # LinkedIn — up to 2 keyword queries
        *[
            search_jobs_via_jina(
                query=q,
                num_results=results_per_source,
                location=location_str,
                remote=params.remote,
                date_posted=params.date_posted,
            )
            for q in queries[:2]
        ],
        # Job Bank Canada — government portal, strong LMIA data
        search_jobbank_via_jina(
            query=queries[0],
            num_results=results_per_source,
            location=location_str,
            province=params.province,
            remote=params.remote,
            lmia_only=params.lmia_only,
        ),
        # Workopolis — major Canadian aggregator (SMEs, office, retail)
        search_workopolis_via_jina(
            query=queries[0],
            num_results=results_per_source,
            location=location_str,
            remote=params.remote,
            date_posted=params.date_posted,
        ),
        # Eluta.ca — aggregates directly from company career pages
        search_eluta_via_jina(
            query=queries[0],
            num_results=results_per_source,
            location=location_str,
        ),
    ]
    results_per_query = await asyncio.gather(*search_tasks, return_exceptions=True)

    seen_urls: set[str] = set()
    raw_results: list[dict] = []
    for batch in results_per_query:
        if isinstance(batch, Exception):
            continue
        for r in batch:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                raw_results.append(r)

    # ── Hard filter: drop jobs whose title matches an excluded role ───────────
    # This runs BEFORE scoring — deterministic and cheap. Excluded jobs never
    # reach the LLM and never appear in results.
    excluded_jobs: list[dict] = []
    if resolved_excluded_roles:
        raw_results, excluded_jobs = filter_excluded_roles(raw_results, resolved_excluded_roles)

    raw_results = raw_results[: params.num_results]

    if not raw_results:
        return {
            "results": [],
            "queries_used": queries,
            "excluded_count": len(excluded_jobs),
        }

    # ── Step 3: Batch score — ALL jobs in ONE LLM call (~88% token savings) ─────
    scores = await batch_score_jobs(
        raw_jobs=raw_results,
        master_sections=master_sections,
        provider=params.llm_provider,
        model=params.llm_model,
        ccfta_check=params.ccfta_check,
        bilingual_spanish=effective_bilingual,
        english_level=resolved_english_level,
        profile_tags=resolved_profile_tags,
        industry_experience=resolved_industry_experience,
        target_industries=resolved_target_industries,
    )

    # ── Step 4: Merge + sort ─────────────────────────────────────────────────
    final: list[dict] = []
    for raw, score in zip(raw_results, scores):
        if not isinstance(score, dict):
            score = {}
        # Fast treaty-eligibility pre-check from title keywords (no LLM needed)
        title_lower = (raw.get("title") or "").lower()
        fast_ccfta = any(kw in title_lower for kw in _CCFTA_ELIGIBLE_TITLES)
        fast_cptpp = any(kw in title_lower for kw in _CPTPP_ELIGIBLE_TITLES)

        final.append({
            "id":                  raw.get("id", ""),
            "title":               raw.get("title") or score.get("job_title", ""),
            "company":             raw.get("company") or score.get("company", ""),
            "location":            raw.get("location") or score.get("location", ""),
            "url":                 raw.get("url", ""),
            "snippet":             raw.get("snippet", ""),
            "salary":              score.get("salary") or raw.get("salary_display"),
            "date_posted":         raw.get("date") or score.get("date_posted", ""),
            "compatibility_score": score.get("compatibility_score", 50),
            "matched_skills":      score.get("matched_skills", []),
            "missing_skills":      score.get("missing_skills", []),
            "score_summary":       score.get("score_summary", ""),
            # Immigration fields
            "source":              raw.get("source", "linkedin"),
            "lmia_approved":       raw.get("lmia_approved", False),
            "ccfta_eligible":      score.get("ccfta_eligible", False) or fast_ccfta,
            "cptpp_eligible":      fast_cptpp,
            "immigration_support": score.get("immigration_support", "no"),
            "bilingual_advantage": score.get("bilingual_advantage", False),
            # English level fields
            "english_barrier":     score.get("english_barrier", False),
            "english_required":    score.get("english_required", "unknown"),
            # Structured assessment
            "confidence":          score.get("confidence", "low"),
            "blockers":            score.get("blockers", []),
            "why_relevant":        score.get("why_relevant", []),
        })

    # Sort: non-barrier jobs first, then by score descending within each group.
    # This guarantees english_barrier=True jobs always appear below non-barrier
    # ones regardless of whether the LLM applied the point deduction consistently.
    final.sort(
        key=lambda x: (
            1 if (x.get("english_barrier") and params.english_level not in ("any", "fluent", "professional")) else 0,
            -x["compatibility_score"],
        )
    )
    return {
        "results":      final,
        "queries_used": queries,
        "english_level_used": resolved_english_level,
        "excluded_count": len(excluded_jobs),
        "profile_used": master.profile_name or master.original_filename,
    }


@router.post("/extract")
async def extract_job_description(req: ExtractRequest, db: Session = Depends(get_db)):
    """
    Extract full job description from a URL via Jina Reader, then score it
    against the active master resume.
    """
    try:
        job_text = await extract_job_via_jina(req.url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"No se pudo extraer la oferta: {e}")

    if not job_text.strip():
        raise HTTPException(status_code=422, detail="La URL no contiene texto de oferta laboral.")

    score_data: dict = {}
    master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
    if master and master.sections:
        try:
            score_data = await score_job(
                job_text=job_text,
                master_sections=master.sections,
                provider=req.llm_provider,
                model=req.llm_model,
                profile_tags=(master.profile_tags or ""),
            )
        except Exception:
            pass

    return {
        "url":             req.url,
        "job_description": job_text,
        **score_data,
    }


@router.get("/debug-profile")
async def debug_profile(db: Session = Depends(get_db)):
    """
    Debug endpoint: show what _build_profile_text() extracts from the active master.
    GET /api/search/debug-profile
    """
    master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
    if not master:
        return {"error": "No active master found"}
    sections = master.sections or {}
    profile = _build_profile_text(sections)
    return {
        "section_keys": list(sections.keys()),
        "profile_chars": len(profile),
        "profile_text": profile[:500],
    }


@router.get("/debug-source")
async def debug_source(
    source: str = "jobbank",
    query: str = "implementation consultant",
    location: str = "Canada",
    province: str = "",
):
    """
    Debug endpoint: fetch raw Jina markdown for a given source + query and
    show how many results the parser finds. Useful for fixing regex patterns.

    Usage: GET /api/search/debug-source?source=jobbank&query=software+developer
    Sources: jobbank | workopolis | eluta
    """
    headers = {"X-Return-Format": "markdown", "X-Timeout": "20"}

    if source == "jobbank":
        target_url = _build_jobbank_url(query, location, province)
    elif source == "workopolis":
        target_url = _build_workopolis_url(query, location)
    elif source == "eluta":
        target_url = _build_eluta_url(query, location)
    else:
        raise HTTPException(status_code=400, detail="source must be jobbank | workopolis | eluta")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(f"https://r.jina.ai/{target_url}", headers=headers)
            resp.raise_for_status()
        content = resp.content.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Jina fetch failed: {e}")

    # Count parser hits
    if source == "jobbank":
        parsed = _parse_jobbank_results(content, 20)
    elif source == "workopolis":
        parsed = _parse_workopolis_results(content, 20)
    else:
        parsed = _parse_eluta_results(content, 20)

    log.warning(
        "debug-source %s: %d chars, %d parsed results",
        source, len(content), len(parsed),
    )

    # Find lines that contain posting URLs (to help diagnose parser issues)
    import re as _re
    url_patterns = {
        "jobbank":   r'jobbank\.gc\.ca/jobsearch/jobposting/\d+',
        "workopolis": r'workopolis\.com/jobsearch/viewjob/',
        "eluta":     r'eluta\.ca/',
    }
    pat = url_patterns.get(source, "")
    url_lines = []
    if pat:
        for i, line in enumerate(content.splitlines()):
            if _re.search(pat, line, _re.IGNORECASE):
                url_lines.append({"line": i, "text": line[:200]})
        url_lines = url_lines[:20]

    return {
        "source": source,
        "target_url": target_url,
        "jina_url": f"https://r.jina.ai/{target_url}",
        "content_length": len(content),
        "parsed_count": len(parsed),
        "parsed_titles": [r["title"] for r in parsed],
        # Lines containing job posting URLs (key for diagnosing parser)
        "url_lines_found": len(url_lines),
        "url_lines_sample": url_lines[:5],
        # First 3000 chars (nav) + chars 3000-7000 (actual listings)
        "raw_nav": content[:3000],
        "raw_listings": content[3000:7500],
    }
