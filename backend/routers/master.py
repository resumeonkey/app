"""
Master resume endpoints: upload, get, list versions.
Only one master is 'active' at a time.
"""
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.models.master import MasterResume
from backend.services.resume_parser import parse_docx, parse_pdf

router   = APIRouter()
settings = get_settings()

MAX_BYTES = settings.max_upload_mb * 1024 * 1024

ALLOWED_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "docx",
    "application/pdf": "pdf",
}


class MasterSummary(BaseModel):
    id: str
    original_filename: str
    candidate_name: Optional[str]
    is_active: bool
    created_at: datetime
    notes: Optional[str]
    sections_detected: list[str]

    class Config:
        from_attributes = True


class MasterDetail(MasterSummary):
    full_text: Optional[str]
    sections: Optional[dict]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/active", response_model=MasterDetail)
def get_active_master(db: Session = Depends(get_db)):
    master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
    if not master:
        raise HTTPException(404, "No active master resume. Upload one first.")
    return _to_detail(master)


@router.get("/", response_model=list[MasterSummary])
def list_masters(db: Session = Depends(get_db)):
    masters = db.query(MasterResume).order_by(MasterResume.created_at.desc()).all()
    return [_to_summary(m) for m in masters]


@router.post("/upload", response_model=MasterDetail, status_code=201)
async def upload_master(
    file: UploadFile = File(...),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    # Validate
    content_type = file.content_type or ""
    file_type = ALLOWED_TYPES.get(content_type)
    if not file_type:
        # Try by extension
        fname = file.filename or ""
        if fname.endswith(".docx"): file_type = "docx"
        elif fname.endswith(".pdf"): file_type = "pdf"
        else:
            raise HTTPException(400, "Solo se aceptan archivos DOCX o PDF.")

    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(413, f"Archivo demasiado grande (máx {settings.max_upload_mb} MB)")

    # Save file
    os.makedirs(settings.upload_dir, exist_ok=True)
    master_id = __import__("uuid").uuid4().hex
    safe_name = f"master_{master_id}.{file_type}"
    file_path = os.path.join(settings.upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(contents)

    # Parse resume
    try:
        if file_type == "docx":
            parsed = parse_docx(file_path)
        else:
            parsed = parse_pdf(file_path)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(422, f"No se pudo leer el archivo: {e}")

    # Deactivate previous masters
    db.query(MasterResume).filter(MasterResume.is_active == True).update({"is_active": False})

    master = MasterResume(
        id=master_id,
        original_filename=file.filename or safe_name,
        file_path=file_path,
        file_type=file_type,
        full_text=parsed.get("full_text"),
        sections=parsed.get("sections"),
        candidate_name=parsed.get("candidate_name"),
        notes=notes,
        is_active=True,
    )
    db.add(master)
    db.commit()
    db.refresh(master)
    return _to_detail(master)


@router.patch("/{master_id}/activate", response_model=MasterSummary)
def activate_master(master_id: str, db: Session = Depends(get_db)):
    master = db.query(MasterResume).filter(MasterResume.id == master_id).first()
    if not master:
        raise HTTPException(404, "Master not found")
    db.query(MasterResume).filter(MasterResume.is_active == True).update({"is_active": False})
    master.is_active = True
    db.commit()
    db.refresh(master)
    return _to_summary(master)


@router.delete("/{master_id}", status_code=204)
def delete_master(master_id: str, db: Session = Depends(get_db)):
    master = db.query(MasterResume).filter(MasterResume.id == master_id).first()
    if not master:
        raise HTTPException(404, "Master not found")
    if master.file_path and os.path.exists(master.file_path):
        os.remove(master.file_path)
    db.delete(master)
    db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_summary(m: MasterResume) -> dict:
    return {
        "id": m.id, "original_filename": m.original_filename,
        "candidate_name": m.candidate_name, "is_active": m.is_active,
        "created_at": m.created_at, "notes": m.notes,
        "sections_detected": list((m.sections or {}).keys()),
    }

def _to_detail(m: MasterResume) -> dict:
    return {**_to_summary(m), "full_text": m.full_text, "sections": m.sections}
