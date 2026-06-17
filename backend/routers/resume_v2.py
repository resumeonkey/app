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

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.services.resume_generator import generate_resume_docx
from backend.services.resume_adapter_v2 import adapt_resume_data

router = APIRouter()

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_profile(profile_id: str) -> dict:
    path = _DATA_DIR / f"master_{profile_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Profile '{profile_id}' not found.")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/profiles")
def list_profiles() -> dict:
    profiles = []
    for p in sorted(_DATA_DIR.glob("master_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            profiles.append({
                "profile_id": d.get("profile_id", p.stem.replace("master_", "")),
                "name": d.get("name", ""),
                "title": d.get("title", ""),
            })
        except Exception:
            continue
    return {"profiles": profiles}


class GenerateRequest(BaseModel):
    profile_id: str = "hr_technology"
    template: str = "classic"            # "classic" | "iris"
    job_description: str = ""            # empty → generate the master as-is
    user_instructions: str = ""
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"


@router.post("/generate")
async def generate(body: GenerateRequest) -> FileResponse:
    data = _load_profile(body.profile_id)

    if body.job_description.strip():
        data = await adapt_resume_data(
            data=data,
            job_description=body.job_description,
            provider=body.llm_provider,
            model=body.llm_model,
            user_instructions=body.user_instructions,
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
