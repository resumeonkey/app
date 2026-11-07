"""
Cover letter generation for the Application Kit.

One LLM call. Uses only facts present in the candidate's resume text — never
invents achievements, employers, dates or credentials.
"""
import logging

from backend.config import get_settings
from backend.services.llm_client import call_llm

log = logging.getLogger(__name__)

_SYSTEM = (
    "You write concise, honest cover letters for a job seeker. "
    "Use ONLY facts that appear in the provided resume. Never invent achievements, "
    "employers, dates, metrics, tools or credentials. Do not mention work authorization, "
    "visas, sponsorship or salary. Keep it to 3-4 short paragraphs. Plain text, no markdown, "
    "no placeholders like [Company] — use the real company and role given."
)


def _lang_for(list_key: str | None) -> str:
    return "Spanish" if (list_key or "").lower() == "chile" else "English"


async def generate_cover_letter(resume_text: str, job_description: str,
                                company: str, title: str, list_key: str | None) -> str:
    s = get_settings()
    lang = _lang_for(list_key)
    user = (
        f"RESUME (the only source of truth about the candidate):\n{(resume_text or '')[:6000]}\n\n"
        f"JOB\nCompany: {company or '(unknown)'}\nRole: {title or '(unknown)'}\n"
        f"Description:\n{(job_description or '')[:4000]}\n\n"
        f"Write the cover letter in {lang}. Address it to the hiring team. "
        f"Open with the role, show 2-3 concrete matches between the resume and the job, "
        f"and close with a brief call to action. Sign as the candidate's name from the resume."
    )
    # gpt-oss-20b occasionally returns an empty completion; retry a couple of times before giving up.
    last = ""
    for attempt in range(3):
        try:
            text = (await call_llm(s.kit_llm_provider, s.kit_llm_model, _SYSTEM, user, temperature=0.4) or "").strip()
        except Exception as exc:
            log.warning("cover_letter: attempt %d failed: %s", attempt + 1, str(exc)[:200])
            text = ""
        if len(text) >= 120:
            return text
        last = text
    raise RuntimeError("La carta volvió vacía del modelo tras varios intentos.")
