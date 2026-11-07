"""
Form answers for the Application Kit, built from the APPROVED answer bank.

Two parts:
- "standard": the standing answers the user approved once (contact, salary, languages, etc.).
- "posting_questions": the posting's own questions mapped to answers using ONLY the bank +
  the resume. If there is no basis, the answer is "FALTA: responder tú" (never invented).

Hard rule: any question about work authorization or sponsorship is NEVER auto-answered — it
is returned with the bank's default plus a "⚠ REVISAR ANTES DE ENVIAR" flag for manual review.
"""
import json
import logging
import re
from pathlib import Path

from backend.config import get_settings
from backend.services.llm_client import call_llm

log = logging.getLogger(__name__)

_BANK_PATH = Path(__file__).resolve().parent.parent / "data" / "answer_bank.json"
_AUTH_RE = re.compile(r"(authoriz|work permit|sponsor|visa|eligib|legally|right to work|autoriz|patrocin|permiso de trabajo)", re.I)
_REVIEW_FLAG = "⚠ REVISAR ANTES DE ENVIAR"


def load_answer_bank() -> dict:
    try:
        return json.loads(_BANK_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("form_answers: could not read answer bank: %s", exc)
        return {}


def _salary_for(bank: dict, list_key: str | None) -> str:
    sal = (bank.get("salary_expectations") or {})
    k = (list_key or "").lower()
    if k == "canada":
        return sal.get("canada_implementation_onboarding_po") or ""
    if k == "chile":
        return sal.get("chile") or ""
    if k == "remote":
        return sal.get("remote_international") or ""
    return ""


def standard_answers(bank: dict, list_key: str | None) -> dict:
    b = bank.get("basics") or {}
    wa = bank.get("work_authorization") or {}
    lang = bank.get("languages") or {}
    si = bank.get("self_identification") or {}
    ca = (wa.get("canada") or {}).get("defaults_while_pending") or {}
    return {
        "full_name": b.get("full_name", ""),
        "email": b.get("email", ""),
        "phone": b.get("phone", ""),
        "location": b.get("location", ""),
        "linkedin": b.get("linkedin", ""),
        "portfolio": b.get("portfolio", ""),
        "salary_expectation": _salary_for(bank, list_key),
        "availability": bank.get("availability", ""),
        "languages": f"Spanish: {lang.get('spanish','')} · English: {lang.get('english','')} · French: {lang.get('french','')}",
        "work_authorization_canada": f"{ca.get('authorized_to_work_in_canada','')}  [{_REVIEW_FLAG}]",
        "requires_sponsorship": f"{ca.get('requires_sponsorship','')}  [{_REVIEW_FLAG}]",
        "work_authorization_free_text": ca.get("free_text", ""),
        "pronouns": si.get("pronouns", ""),
        "voluntary_self_id": si.get("voluntary_gender_ethnicity_disability", ""),
        "veteran": si.get("veteran", ""),
        "references": bank.get("references", ""),
    }


_SYSTEM = (
    "You map a job application's questions to answers for a candidate, using ONLY the provided "
    "answer bank and resume. NEVER invent facts. If the bank/resume give no basis to answer, set "
    "the answer to exactly 'FALTA: responder tú'. For ANY question about work authorization, work "
    "permit, visa, sponsorship or legal right to work, do NOT decide — set the answer to the bank's "
    "default and it will be flagged for manual review. Return strict JSON: "
    '{"items":[{"question":"...","answer":"..."}]}. Keep answers short.'
)


async def _map_questions(bank: dict, resume_text: str, questions: list[str], list_key: str | None) -> list[dict]:
    s = get_settings()
    std = standard_answers(bank, list_key)
    user = (
        f"ANSWER BANK (approved standing answers):\n{json.dumps(std, ensure_ascii=False)}\n\n"
        f"TOOL YEARS:\n{json.dumps(bank.get('tools_years') or {}, ensure_ascii=False)}\n\n"
        f"RESUME:\n{(resume_text or '')[:3000]}\n\n"
        f"QUESTIONS (answer each):\n" + "\n".join(f"- {q}" for q in questions)
    )
    try:
        raw = await call_llm(s.kit_llm_provider, s.kit_llm_model, _SYSTEM, user, json_mode=True, temperature=0.1)
        data = json.loads(raw)
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ValueError("no items")
    except Exception as exc:
        log.warning("form_answers: question mapping failed: %s", str(exc)[:200])
        items = [{"question": q, "answer": "FALTA: responder tú"} for q in questions]
    # Enforce the manual-review rule for authorization/sponsorship questions.
    for it in items:
        if _AUTH_RE.search(str(it.get("question", ""))) and _REVIEW_FLAG not in str(it.get("answer", "")):
            it["answer"] = f"{it.get('answer','')}  [{_REVIEW_FLAG}]".strip()
    return items


async def build_form_answers(resume_text: str, questions: list | None, list_key: str | None) -> dict:
    bank = load_answer_bank()
    out = {"standard": standard_answers(bank, list_key), "posting_questions": []}
    qs = [str(q).strip() for q in (questions or []) if str(q).strip()]
    if qs:
        out["posting_questions"] = await _map_questions(bank, resume_text, qs, list_key)
    return out
