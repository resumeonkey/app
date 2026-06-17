"""
Data-driven resume adaptation (Nivel 2).

Instead of editing an uploaded DOCX, the LLM rewrites the STRUCTURED fields of the
resume (tagline, summary, competencies, experience bullets) for a given job and
returns JSON. Because the output is data — not document text — it cannot corrupt
formatting, leak debug lines, or scramble sections. The clean DOCX is then built
by resume_generator from the adapted data.

Public API:
    async adapt_resume_data(data, job_description, provider, model, user_instructions="") -> dict
"""
from __future__ import annotations

import json
import logging

from backend.services.llm_client import call_llm

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert Canadian resume writer. You adapt a candidate's EXISTING "
    "resume data to a specific job, honestly. You never invent experience, tools, "
    "platforms, employers, dates, or domains. You return ONLY valid JSON."
)


def _build_prompt(data: dict, job_description: str, user_instructions: str) -> str:
    adaptable = {
        "tagline": data.get("tagline", []),
        "summary": data.get("summary", []),
        "competencies": data.get("competencies", {}),
        "experience": [
            {
                "company": e.get("company", ""),
                "domain": e.get("domain", ""),
                "bullets": e.get("bullets", []),
            }
            for e in data.get("experience", [])
        ],
    }
    return f"""Adapt this candidate's resume DATA for the target job. Return JSON with the
SAME shape (tagline, summary, competencies, experience). Keep array lengths and
the experience order/count identical to the input.

## Candidate resume data (only the adaptable parts)
{json.dumps(adaptable, ensure_ascii=False, indent=2)}

## Target job description
{job_description[:4000]}

## User instructions (optional)
{user_instructions or "None."}

## HARD RULES (credibility — a recruiter will read this)
1. NEVER invent platforms, tools, certifications, employers, dates, metrics, or
   responsibilities that are not already in the candidate's data.
2. Keep EACH experience entry in its ORIGINAL domain (see "domain"). Do NOT inject
   the target job's domain into an unrelated role. Example: if a role's domain is
   "core banking" or "telecom QA", do NOT add HR/HRIS wording to it.
3. Do NOT convert broad experience into deep domain expertise. If the candidate
   only touched a domain briefly, say "exposure to / supported", never "10+ years
   X specialist" or "administration/ownership" of a platform they only reported on.
   "SuccessFactors reporting" never becomes "SuccessFactors administration".
4. You MAY reorder and reword to surface the most job-relevant content first, and
   use the job's terminology WHEN it honestly matches existing experience.
5. competencies: keep the same 3 category keys and a similar count per category;
   reorder/reword to match the job, but every skill must be real (present in the
   data). Do not add named platforms not already listed.
6. experience: keep the same number of entries and roughly the same bullet count
   per entry. Each bullet ≤ 28 words.
7. tagline: 4-5 short items, all real skills, reordered for the job.
8. Write in English (same language as the input data).

Return ONLY this JSON shape (no markdown, no comments):
{{"tagline":["..."],"summary":["...","...","..."],"competencies":{{"<cat>":["..."]}},"experience":[{{"bullets":["..."]}}]}}
The experience array MUST be in the same order as the input (one object per role)."""


async def adapt_resume_data(
    data: dict,
    job_description: str,
    provider: str,
    model: str,
    user_instructions: str = "",
) -> dict:
    """
    Return a NEW data dict with adapted tagline/summary/competencies/experience
    bullets. Non-adaptable fields (name, title, contact, education, certifications,
    and each experience entry's title/company/location/dates) are preserved exactly.
    On any failure, returns the original data unchanged (safe).
    """
    prompt = _build_prompt(data, job_description, user_instructions)
    try:
        raw = await call_llm(
            provider=provider, model=model, system=_SYSTEM,
            user=prompt, json_mode=True, temperature=0.3,
        )
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            text = text[4:] if text.lower().startswith("json") else text
        parsed = json.loads(text.strip())
    except Exception as e:
        log.warning("adapt_resume_data failed (%s) — returning original data", str(e)[:120])
        return data

    out = json.loads(json.dumps(data))  # deep copy

    if isinstance(parsed.get("tagline"), list) and parsed["tagline"]:
        out["tagline"] = [str(x) for x in parsed["tagline"]][:6]
    if isinstance(parsed.get("summary"), list) and parsed["summary"]:
        out["summary"] = [str(x) for x in parsed["summary"]]
    if isinstance(parsed.get("competencies"), dict) and parsed["competencies"]:
        # Only keep categories that exist in the original (no invented sections)
        merged = {}
        for cat in out.get("competencies", {}):
            new_list = parsed["competencies"].get(cat)
            merged[cat] = [str(s) for s in new_list] if isinstance(new_list, list) and new_list \
                else out["competencies"][cat]
        out["competencies"] = merged

    # Experience: map adapted bullets back by position, preserving all metadata.
    p_exp = parsed.get("experience")
    if isinstance(p_exp, list) and len(p_exp) == len(out.get("experience", [])):
        for i, entry in enumerate(out["experience"]):
            b = p_exp[i].get("bullets") if isinstance(p_exp[i], dict) else None
            if isinstance(b, list) and b:
                entry["bullets"] = [str(x) for x in b]

    return out
