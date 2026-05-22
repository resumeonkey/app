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
from backend.services.llm_client import call_llm
from backend.services.prompt_loader import load_prompt


ADAPTABLE_SECTIONS = ["summary", "skills", "experience", "projects"]

SYSTEM_RULE = """REGLA MAESTRA: Usa siempre el resume tipo canadiense ya cargado como plantilla maestra.
Adapta SOLO el contenido necesario para la oferta. Nunca alteres la estructura,
el estilo canadiense, ni el formato del documento base. El output debe verse como
una variante del mismo CV, no como un CV nuevo."""


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
        {
          "section": "summary",
          "reason": "...",
          "original": "...",
          "adapted": "..."
        },
        ...
      ]
    }
    """

    # Build the system rule enriched with candidate context
    context_block = (
        f"\n\n--- CONTEXTO ADICIONAL DEL CANDIDATO ---\n{user_context.strip()}\n---"
        if user_context and user_context.strip()
        else ""
    )
    system_with_context = SYSTEM_RULE + context_block

    # ── Stage 1: Analyze the job ──────────────────────────────────────────────
    job_analysis = await _analyze_job(job_description, llm_provider, llm_model, system_with_context)

    # ── Stage 2: Decide which sections to adapt ───────────────────────────────
    blocks_to_adapt = await _select_blocks(
        master_full_text=master_full_text,
        master_sections=master_sections,
        job_analysis=job_analysis,
        user_instructions=user_instructions,
        llm_provider=llm_provider,
        llm_model=llm_model,
        system=system_with_context,
    )

    # ── Stage 3: Rewrite each selected section ─────────────────────────────────
    blocks_changed = []
    for block in blocks_to_adapt:
        section_name = block["section"]
        if section_name not in master_sections:
            continue

        original_text = master_sections[section_name]["raw_text"]
        adapted_text  = await _adapt_section(
            section_name=section_name,
            original_text=original_text,
            master_full_text=master_full_text,
            job_analysis=job_analysis,
            user_instructions=user_instructions,
            reason=block["reason"],
            llm_provider=llm_provider,
            llm_model=llm_model,
            system=system_with_context,
        )

        blocks_changed.append({
            "section":  section_name,
            "reason":   block["reason"],
            "original": original_text,
            "adapted":  adapted_text,
        })

    return {
        "job_analysis":   job_analysis,
        "blocks_changed": blocks_changed,
    }


# ── Internal pipeline stages ──────────────────────────────────────────────────

async def _analyze_job(job_description: str, provider: str, model: str, system: str = SYSTEM_RULE) -> dict:
    prompt = load_prompt("analyze_job").format(job_description=job_description)
    raw = await call_llm(
        provider=provider, model=model,
        system=system + "\n\nEres un especialista en reclutamiento canadiense.",
        user=prompt,
        json_mode=True,
    )
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


async def _select_blocks(
    master_full_text: str,
    master_sections: dict,
    job_analysis: dict,
    user_instructions: str,
    provider: str,
    model: str,
    system: str = SYSTEM_RULE,
) -> list[dict]:
    available_sections = [s for s in master_sections.keys() if s in ADAPTABLE_SECTIONS]
    sections_summary   = "\n".join(
        f"- {s}: {master_sections[s]['raw_text'][:200]}..." for s in available_sections
    )

    prompt = load_prompt("select_blocks").format(
        sections_summary=sections_summary,
        job_analysis=json.dumps(job_analysis, ensure_ascii=False, indent=2),
        user_instructions=user_instructions or "Ninguna instrucción adicional.",
        available_sections=", ".join(available_sections),
    )

    raw = await call_llm(
        provider=provider, model=model,
        system=system + "\n\nDecides qué bloques del resume canadiense adaptar para esta oferta específica.",
        user=prompt,
        json_mode=True,
    )

    try:
        data = json.loads(raw)
        return data.get("blocks_to_adapt", [])
    except Exception:
        # Fallback: always adapt summary and skills
        return [
            {"section": "summary", "reason": "Adaptar al rol específico"},
            {"section": "skills",  "reason": "Destacar habilidades relevantes"},
        ]


async def _adapt_section(
    section_name: str,
    original_text: str,
    master_full_text: str,
    job_analysis: dict,
    user_instructions: str,
    reason: str,
    provider: str,
    model: str,
    system: str = SYSTEM_RULE,
) -> str:
    prompt_name = f"adapt_{section_name}" if section_name in ("summary", "skills") else "adapt_experience"
    prompt_template = load_prompt(prompt_name)

    prompt = prompt_template.format(
        original_text=original_text,
        job_analysis=json.dumps(job_analysis, ensure_ascii=False, indent=2),
        user_instructions=user_instructions or "Ninguna instrucción adicional.",
        reason=reason,
        master_context=master_full_text[:1500],
    )

    adapted = await call_llm(
        provider=provider, model=model,
        system=system + f"\n\nEstás reescribiendo la sección '{section_name}' del resume canadiense.",
        user=prompt,
        temperature=0.3,
    )
    return adapted.strip()
