"""
Context: personal/professional context repository.
Users paste text or upload files; the LLM uses this context in every adaptation.
"""
import tempfile
import os
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.context import UserContext
from backend.services.resume_parser import parse_resume

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ContextOut(BaseModel):
    id: str
    title: str
    content: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ContextOut])
def list_contexts(db: Session = Depends(get_db)):
    return db.query(UserContext).order_by(UserContext.created_at.desc()).all()


@router.post("/text", response_model=ContextOut, status_code=201)
def add_text_context(
    title:   str = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    if not content.strip():
        raise HTTPException(400, "El contenido no puede estar vacío.")
    ctx = UserContext(title=title.strip(), content=content.strip())
    db.add(ctx)
    db.commit()
    db.refresh(ctx)
    return ctx


@router.post("/file", response_model=ContextOut, status_code=201)
async def add_file_context(
    title: str = Form(...),
    file:  UploadFile = File(...),
    db:    Session = Depends(get_db),
):
    contents = await file.read()
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in (".pdf", ".docx", ".txt"):
        raise HTTPException(400, "Solo se aceptan .pdf, .docx o .txt")

    # Write to temp file and parse
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        parsed = parse_resume(tmp_path)
        text = parsed.get("full_text", "").strip()
    finally:
        os.remove(tmp_path)

    if not text:
        raise HTTPException(422, "No se pudo extraer texto del archivo.")

    ctx = UserContext(title=title.strip() or filename, content=text)
    db.add(ctx)
    db.commit()
    db.refresh(ctx)
    return ctx


@router.patch("/{ctx_id}/toggle", response_model=ContextOut)
def toggle_context(ctx_id: str, db: Session = Depends(get_db)):
    ctx = db.query(UserContext).filter(UserContext.id == ctx_id).first()
    if not ctx:
        raise HTTPException(404, "Contexto no encontrado")
    ctx.is_active = not ctx.is_active
    db.commit()
    db.refresh(ctx)
    return ctx


@router.delete("/{ctx_id}", status_code=204)
def delete_context(ctx_id: str, db: Session = Depends(get_db)):
    ctx = db.query(UserContext).filter(UserContext.id == ctx_id).first()
    if not ctx:
        raise HTTPException(404, "Contexto no encontrado")
    db.delete(ctx)
    db.commit()
