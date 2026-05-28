"""
Core adaptation pipeline.

Stage 1: Analyze the job description → extract requirements, keywords, skills.
Stage 2: Compare against the master resume → decide WHICH blocks to adapt.
Stage 3: Rewrite only those blocks — one LLM call per section.
Stage 4: Return a list of changes to apply to the docx.

Rule enforced in every prompt:
"Use the master Canadian resume as the only template.
 Adapt content only. Never alter structure, format, or Canadian style."
"""
import json
import re
from backend.services.llm_client import call_llm
from backend.services.prompt_loader import load_prompt


# ── Section config ─────────────────────────────────────────────────────────────
# Maps canonical_name → (key_substrings_to_match, prompt_template)
# The key_substrings list is used case-insensitively against actual section keys.
SECTION_CONFIG: dict[str, tuple[tuple[str, ...], str]] = {
    "summary":         (("summary", "profile", "about", "objective"),  "adapt_summary"),
    "skills":          (("skill", "technical", "competenc", "tool"),   "adapt_skills"),
    "experience":      (("experience", "work", "employment", "career"), "adapt_experience"),
    "education":       (("education", "degree", "academic", "study"),  "adapt_education"),
    "projects":        (("project",),                                   "adapt_experience"),
    "certifications":  (("certif", "licen", "credential", "award"),    "adapt_certifications"),
    "volunteer":       (("volunteer", "community", "civic"),            "adapt_experience"),
}

SYSTEM_RULE = """REGLA MAESTRA: Usa siempre el resume tipo canadiense ya cargado como plantilla maestra.
Adapta SOLO el contenido necesario para la oferta. Nunca alteres la estructura,
el estilo canadiense, ni el formato del documento base. El output debe verse como
una variante del mismo CV, no como un CV nuevo.

IDIOMA OBLIGATORIO: Escribe SIEMPRE en el mismo idioma que el texto original del resume.
Si el resume original está en inglés → responde en inglés. Si está en español → español.
NUNCA traduzcas el contenido aunque el resto del prompt esté en español."""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_json(raw: str) -> dict | list:
    """Parse JSON after stripping markdown fences — same logic as job_search._parse_json_response."""
    text = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text.strip())


def _resolve_sections(master_sections: dict) -> dict[str, str]:
    """
    Return {canonical_name: actual_key} for every section in master_sections
    that matches one of our SECTION_CONFIG patterns.

    Example: {"summary": "Summary / Profile", "skills": "Technical Skills", ...}
    """
    mapping: dict[str, str] = {}
    for canonical, (keywords, _) in SECTION_CONFIG.items():
        for actual_key in master_sections.keys():
            key_lower = actual_key.lower()
            if any(kw in key_lower for kw in keywords):
                if canonical not in mapping:   # first match per canonical wins
                    mapping[canonical] = actual_key
                    break
    return mapping


# ── Public API ─────────────────────────────────────────────────────────────────

async def run_adaptation(
    master_sections: dict,
    master_full_text: str,
    job_description: str,
    user_instructions: str,
    llm_provider: str,
    llm_model: str,
    user_context: str = "",
) -> dict:
    """
    Returns:
    {
      "job_analysis": {...},
      "blocks_changed": [
        {"section": "summary", "reason": "...", "original": "...", "adapted": "..."},
        ...
      ]
    }
    """

    context_block = (
        f"\n\n--- CONTEXTO ADICIONAL DEL CANDIDATO ---\n{user_context.strip()}\n---"
        if user_context and user_context.strip()
        else ""
    )
    system_base         = SYSTEM_RULE
    system_with_context = SYSTEM_RULE + context_block

    # ── Stage 1: Analyze the job ─────────────────────────────────────────────
    job_analysis = await _analyze_job(job_description, llm_provider, llm_model, system_base)

    # ── Resolve actual section keys ──────────────────────────────────────────
    resolved = _resolve_sections(master_sections)  # {canonical: actual_key}

    # ── Stage 2: Decide which sections to adapt ──────────────────────────────
    blocks_to_adapt = await _select_blocks(
        resolved=resolved,
        master_sections=master_sections,
        job_analysis=job_analysis,
        user_instructions=user_instructions,
        provider=llm_provider,
        model=llm_model,
        system=system_with_context,
    )

    # ── Stage 3: Rewrite each selected section ───────────────────────────────
    blocks_changed = []
    for block in blocks_to_adapt:
        canonical = block["section"]

        # Resolve canonical → actual key in master_sections
        actual_key = resolved.get(canonical)
        if not actual_key:
            continue

        original_text = master_sections[actual_key].get("raw_text", "").strip()
        if not original_text:
            continue

        _, prompt_name = SECTION_CONFIG.get(canonical, (None, "adapt_experience"))

        adapted_text = await _adapt_section(
            section_name=canonical,
            prompt_name=prompt_name,
            original_text=original_text,
            master_full_text=master_full_text,
            job_analysis=job_analysis,
            user_instructions=user_instructions,
            reason=block["reason"],
            provider=llm_provider,
            model=llm_model,
            system=system_with_context,
        )

        blocks_changed.append({
            "section":  canonical,
            "reason":   block["reason"],
            "original": original_text,
            "adapted":  adapted_text,
        })

    return {
        "job_analysis":   job_analysis,
        "blocks_changed": blocks_changed,
    }


# ── Internal pipeline stages ──────────────────────────────────────────────────

async def _analyze_job(
    job_description: str, provider: str, model: str, system: str = SYSTEM_RULE
) -> dict:
    prompt = load_prompt("analyze_job").format(job_description=job_description)
    raw = await call_llm(
        provider=provider, model=model,
        system=system + "\n\nEres un especialista en reclutamiento canadiense.",
        user=prompt,
        json_mode=True,
    )
    try:
        return _safe_json(raw)
    except Exception:
        return {"raw": raw}


async def _select_blocks(
    resolved: dict[str, str],
    master_sections: dict,
    job_analysis: dict,
    user_instructions: str,
    provider: str,
    model: str,
    system: str = SYSTEM_RULE,
) -> list[dict]:
    """
    Ask the LLM which canonical sections to rewrite, using 100-char previews.
    Returns [{"section": canonical_name, "reason": "..."}, ...]
    """
    if not resolved:
        return []

    # Build preview using actual key but label with canonical name
    sections_summary = "\n".join(
        f"- {canonical} ({actual_key}): "
        f"{master_sections[actual_key]['raw_text'][:120].strip()}…"
        for canonical, actual_key in resolved.items()
    )

    prompt = load_prompt("select_blocks").format(
        sections_summary=sections_summary,
        job_analysis=json.dumps(job_analysis, ensure_ascii=False, indent=2),
        user_instructions=user_instructions or "Ninguna instrucción adicional.",
        available_sections=", ".join(resolved.keys()),
    )

    raw = await call_llm(
        provider=provider, model=model,
        system=system + "\n\nDecides qué bloques del resume canadiense adaptar para esta oferta específica.",
        user=prompt,
        json_mode=True,
    )

    try:
        data = _safe_json(raw)
        blocks = data.get("blocks_to_adapt", [])
        # Validate: only return blocks whose section name is in resolved
        return [b for b in blocks if isinstance(b, dict) and b.get("section") in resolved]
    except Exception:
        # Fallback: adapt whatever canonical sections we have for summary + skills
        fallback = []
        for canonical in ("summary", "skills", "experience"):
            if canonical in resolved:
                fallback.append({
                    "section": canonical,
                    "reason":  "Adaptar al rol específico" if canonical == "summary"
                               else "Destacar habilidades relevantes" if canonical == "skills"
                               else "Alinear experiencia con la oferta",
                })
        return fallback


def _clean_llm_section_output(text: str) -> str:
    """Strip markdown, LLM meta-commentary, and duplicate lines from section output."""
    notes_pattern = re.compile(
        r'\n+(?:#{1,3}\s*)?(?:notas?\s+de\s+adaptaci[oó]n|adaptation\s+notes?|'
        r'cambios?\s+realizados?|key\s+changes?|changes?\s+made|'
        r'\*\*mantenidas?\*\*|\*\*reordenado\*\*|explanation).*',
        re.IGNORECASE | re.DOTALL,
    )
    text = notes_pattern.sub("", text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)

    # Remove exact duplicate lines (LLM sometimes repeats the same bullet twice)
    lines = text.split('\n')
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        key = line.strip().lower()
        if key and key in seen:
            continue   # skip duplicate non-empty line
        if key:
            seen.add(key)
        deduped.append(line)
    text = '\n'.join(deduped)

    return text.strip()


def _trim_job_analysis(job_analysis: dict) -> dict:
    """Keep only actionable fields for section rewriting; drop metadata."""
    KEEP = {
        "job_title", "seniority_level",
        "required_skills", "preferred_skills",
        "key_responsibilities", "keywords_to_include",
        "ats_keywords", "tools_and_technologies", "soft_skills",
    }
    trimmed = {k: v for k, v in job_analysis.items() if k in KEEP}
    return trimmed if trimmed else job_analysis


async def _adapt_section(
    section_name: str,
    prompt_name: str,
    original_text: str,
    master_full_text: str,
    job_analysis: dict,
    user_instructions: str,
    reason: str,
    provider: str,
    model: str,
    system: str = SYSTEM_RULE,
) -> str:
    prompt_template = load_prompt(prompt_name)

    prompt = prompt_template.format(
        original_text=original_text,
        job_analysis=json.dumps(_trim_job_analysis(job_analysis), ensure_ascii=False, indent=2),
        user_instructions=user_instructions or "Ninguna instrucción adicional.",
        reason=reason,
        master_context=master_full_text[:400],
    )

    adapted = await call_llm(
        provider=provider, model=model,
        system=system + f"\n\nEstás reescribiendo la sección '{section_name}' del resume canadiense.",
        user=prompt,
        temperature=0.3,
    )
    return _clean_llm_section_output(adapted)
