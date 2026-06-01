"""
Master resume endpoints: upload, get, list versions.
Only one master is 'active' at a time.
"""
import uuid
import tempfile
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
from backend.services import storage

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
    profile_name: Optional[str]
    english_level: Optional[str]
    profile_tags: Optional[str]
    target_roles: Optional[str]
    excluded_roles: Optional[str]
    industry_experience: Optional[str]
    target_industries: Optional[str]

    class Config:
        from_attributes = True


class MasterDetail(MasterSummary):
    full_text: Optional[str]
    sections: Optional[dict]


class MasterPreferencesUpdate(BaseModel):
    profile_name:         Optional[str] = None  # display name, e.g. "Tech / Implementation"
    english_level:        Optional[str] = None  # "any"|"basic"|"conversational"|"professional"|"fluent"
    profile_tags:         Optional[str] = None  # comma-separated technical keywords
    target_roles:         Optional[str] = None  # comma-separated target job titles
    excluded_roles:       Optional[str] = None  # comma-separated exclusion terms
    industry_experience:  Optional[str] = None  # industries where candidate has experience
    target_industries:    Optional[str] = None  # industries candidate wants to target


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

    master_id = uuid.uuid4().hex
    safe_name = f"master_{master_id}.{file_type}"
    storage_path = f"uploads/{safe_name}"

    # Parse requires a real file path — write to temp, then persist to storage
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_type}") as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        if file_type == "docx":
            parsed = parse_docx(tmp_path)
        else:
            parsed = parse_pdf(tmp_path)
    except Exception as e:
        raise HTTPException(422, f"No se pudo leer el archivo: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if file_type == "docx" else "application/pdf"
    )
    file_path = storage.upload_file(contents, storage_path, content_type)

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


@router.patch("/{master_id}/preferences", response_model=MasterSummary)
def update_preferences(
    master_id: str,
    body: MasterPreferencesUpdate,
    db: Session = Depends(get_db),
):
    """Update candidate profile preferences (english_level, etc.)."""
    master = db.query(MasterResume).filter(MasterResume.id == master_id).first()
    if not master:
        raise HTTPException(404, "Master not found")
    def _normalize_tags(raw: str | None, max_chars: int = 300,
                        max_items: int = 30, max_item_len: int = 50) -> str | None:
        """Trim, dedupe-empty, and cap a comma-separated tag string."""
        if raw is None:
            return None
        items = [t.strip()[:max_item_len] for t in raw[:max_chars * 2].split(",") if t.strip()]
        joined = ", ".join(items[:max_items])
        return joined[:max_chars] or None

    if body.profile_name is not None:
        master.profile_name = body.profile_name.strip()[:60] or None
    if body.english_level is not None:
        valid = {"any", "basic", "conversational", "professional", "fluent"}
        if body.english_level not in valid:
            raise HTTPException(400, f"english_level must be one of: {', '.join(sorted(valid))}")
        master.english_level = body.english_level
    if body.profile_tags is not None:
        master.profile_tags = _normalize_tags(body.profile_tags, max_chars=250)
    if body.target_roles is not None:
        master.target_roles = _normalize_tags(body.target_roles, max_chars=400)
    if body.excluded_roles is not None:
        master.excluded_roles = _normalize_tags(body.excluded_roles, max_chars=400)
    if body.industry_experience is not None:
        master.industry_experience = _normalize_tags(body.industry_experience, max_chars=200)
    if body.target_industries is not None:
        master.target_industries = _normalize_tags(body.target_industries, max_chars=200)
    db.commit()
    db.refresh(master)
    return _to_summary(master)


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
    # Delete from storage — wrapped so a missing/failed file doesn't block the DB delete.
    # An unhandled exception here would cause FastAPI to return a 500 without CORS headers,
    # which the browser sees as "Network Error" rather than a proper error response.
    if master.file_path:
        try:
            storage.delete_file(master.file_path)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "delete_master: could not delete file %s — %s", master.file_path, exc
            )
    db.delete(master)
    db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_summary(m: MasterResume) -> dict:
    return {
        "id": m.id, "original_filename": m.original_filename,
        "candidate_name": m.candidate_name, "is_active": m.is_active,
        "created_at": m.created_at, "notes": m.notes,
        "sections_detected":  list((m.sections or {}).keys()),
        "profile_name":       m.profile_name or "",
        "english_level":      m.english_level or "any",
        "profile_tags":       m.profile_tags or "",
        "target_roles":       m.target_roles or "",
        "excluded_roles":     m.excluded_roles or "",
        "industry_experience":m.industry_experience or "",
        "target_industries":  m.target_industries or "",
    }

def _to_detail(m: MasterResume) -> dict:
    return {**_to_summary(m), "full_text": m.full_text, "sections": m.sections}
