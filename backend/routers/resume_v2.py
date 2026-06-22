"""
Data-driven resume endpoints (Nivel 2).

  GET  /api/resume/profiles            → list built-in structured profiles
  POST /api/resume/generate            → (optionally adapt to a job) and return a clean DOCX
"""
import json
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.master import MasterResume
from backend.models.context import UserContext
from backend.services.resume_generator import generate_resume_docx
from backend.services.resume_adapter_v2 import adapt_resume_data

router = APIRouter()

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_personal_background(db: Session) -> str:
    """Collect the user's REAL info: active master's full text + active context
    items. Used to fill a chosen template with the candidate's real data."""
    parts: list[str] = []
    master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
    if master:
        if master.candidate_name:
            parts.append(f"CANDIDATE NAME: {master.candidate_name}")
        if master.full_text:
            parts.append("RESUME:\n" + master.full_text)
    ctx = db.query(UserContext).filter(UserContext.is_active == True).all()
    for c in ctx:
        if c.content:
            parts.append(f"[{c.title}]\n{c.content}")
    return "\n\n".join(parts).strip()


def _load_profile(profile_id: str) -> dict:
    # Career-area templates (template_*) and personal masters (master_*) are both
    # loadable by id.
    for prefix in ("template_", "master_"):
        path = _DATA_DIR / f"{prefix}{profile_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise HTTPException(404, f"Profile '{profile_id}' not found.")


@router.get("/profiles")
def list_profiles() -> dict:
    """List the career-area resume types (template_*) available to choose from."""
    profiles = []
    for p in sorted(_DATA_DIR.glob("template_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            profiles.append({
                "profile_id": d.get("profile_id", p.stem.replace("template_", "")),
                "name": d.get("name", ""),
                "title": d.get("title", ""),
                "area": d.get("area", ""),
                "format_type": d.get("format_type", ""),
                "description": d.get("description", ""),
            })
        except Exception:
            continue
    return {"profiles": profiles}


class GenerateRequest(BaseModel):
    profile_id: str = "hr_technology"
    template: str = "classic"            # "classic" | "iris"
    job_description: str = ""            # empty → generate the master as-is
    user_instructions: str = ""
    use_personal_data: bool = True       # fill the template with the user's REAL info
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"


@router.post("/generate")
async def generate(body: GenerateRequest, db: Session = Depends(get_db)) -> FileResponse:
    data = _load_profile(body.profile_id)

    # Cross the chosen template (area/format) with the candidate's REAL data so the
    # output has the user's actual name, experience, education — not placeholders.
    background = _load_personal_background(db) if body.use_personal_data else ""

    if body.job_description.strip() or background:
        data = await adapt_resume_data(
            data=data,
            job_description=body.job_description,
            provider=body.llm_provider,
            model=body.llm_model,
            user_instructions=body.user_instructions,
            personal_background=background,
        )

    out_path = os.path.join(tempfile.gettempdir(), f"resume_{uuid.uuid4().hex}.docx")
    generate_resume_docx(data, out_path, template=body.template)

    safe_name = (data.get("name") or "resume").replace(" ", "_")
    filename = f"{safe_name}_{body.profile_id}.docx"
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )
