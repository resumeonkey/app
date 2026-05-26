"""
Job search endpoints.

  GET  /api/search/suggest              → suggested search params from active master
  POST /api/search/run                  → search + score jobs
  POST /api/search/extract              → extract job description from URL
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.master import MasterResume
from backend.services.job_search import (
    generate_search_queries,
    search_jobs_via_jina,
    search_jobbank_via_jina,
    extract_job_via_jina,
    score_job,
    _build_profile_text,
)
from backend.services.llm_client import call_llm

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class SearchParams(BaseModel):
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
        return {"suggestions": {}}

    profile = _build_profile_text(master.sections)
    if not profile:
        return {"suggestions": {}}

    prompt = f"""Analiza este perfil de resume y sugiere parámetros de búsqueda.

## Perfil
{profile[:600]}

Responde ÚNICAMENTE con JSON:
{{
  "job_title": "título del puesto más apropiado para este candidato",
  "experience_level": ["mid"],
  "industries": ["Technology"],
  "skills_highlight": "3-5 skills principales separadas por coma"
}}"""

    try:
        raw = await call_llm(
            provider=llm_provider,
            model=llm_model,
            system="Eres un coach de carrera. Analizas perfiles y sugieres búsquedas de empleo.",
            user=prompt,
            json_mode=True,
            temperature=0.2,
        )
        return {"suggestions": json.loads(raw)}
    except Exception:
        return {"suggestions": {}}


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
    master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
    if not master:
        raise HTTPException(status_code=400, detail="No hay un resume maestro activo.")

    master_sections = master.sections or {}

    # ── Step 1: Queries ───────────────────────────────────────────────────────
    if params.custom_query.strip():
        queries = [params.custom_query.strip()]
    else:
        queries = await generate_search_queries(
            master_sections=master_sections,
            params=params.model_dump(),
            provider=params.llm_provider,
            model=params.llm_model,
        )

    if not queries:
        raise HTTPException(status_code=422, detail="No se pudieron generar consultas de búsqueda.")

    # ── Step 2: Search LinkedIn + Job Bank via Jina Reader (parallel) ───────────
    # Build location strings
    location_parts = [p for p in [params.city, params.province, params.country] if p.strip()]
    location_str   = ", ".join(location_parts) if location_parts else "Canada"

    # Split results evenly between sources (LinkedIn gets slightly more)
    results_per_source = max(4, params.num_results // 2)

    search_tasks = [
        # LinkedIn — up to 2 queries
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
        # Job Bank Canada — 1 query (government + SME jobs not on LinkedIn)
        search_jobbank_via_jina(
            query=queries[0],
            num_results=results_per_source,
            location=location_str,
            province=params.province,
            remote=params.remote,
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

    raw_results = raw_results[: params.num_results]

    if not raw_results:
        return {"results": [], "queries_used": queries}

    # ── Step 3: Score (parallel) ──────────────────────────────────────────────
    # Use title + company + location as the scoring text (LinkedIn already parsed them).
    # This avoids fetching each job page just for scoring — much faster & cheaper.
    score_tasks = [
        score_job(
            job_text=f"{r.get('title', '')} at {r.get('company', '')} — {r.get('location', '')}\n\n{r.get('snippet', '')}",
            master_sections=master_sections,
            provider=params.llm_provider,
            model=params.llm_model,
        )
        for r in raw_results
    ]
    scores = await asyncio.gather(*score_tasks, return_exceptions=True)

    # ── Step 4: Merge + sort ─────────────────────────────────────────────────
    final: list[dict] = []
    for raw, score in zip(raw_results, scores):
        if isinstance(score, Exception):
            score = {
                "compatibility_score": 50,
                "job_title": raw.get("title", ""), "company": "",
                "location": "", "salary": None, "date_posted": None,
                "matched_skills": [], "missing_skills": [], "score_summary": "",
            }
        # Prefer LinkedIn-parsed title/company/location over LLM extraction
        # (LinkedIn data is accurate; LLM had only a title snippet to work with)
        final.append({
            "id":                  raw.get("id", ""),
            "title":               raw.get("title") or score.get("job_title", ""),
            "company":             raw.get("company") or score.get("company", ""),
            "location":            raw.get("location") or score.get("location", ""),
            "url":                 raw.get("url", ""),
            "snippet":             raw.get("snippet", ""),
            "salary":              score.get("salary"),
            "date_posted":         raw.get("date") or score.get("date_posted", ""),
            "compatibility_score": score.get("compatibility_score", 50),
            "matched_skills":      score.get("matched_skills", []),
            "missing_skills":      score.get("missing_skills", []),
            "score_summary":       score.get("score_summary", ""),
        })

    final.sort(key=lambda x: x["compatibility_score"], reverse=True)
    return {"results": final, "queries_used": queries}


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
            )
        except Exception:
            pass

    return {
        "url":             req.url,
        "job_description": job_text,
        **score_data,
    }
