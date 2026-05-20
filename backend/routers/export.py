"""
Export: download the adapted .docx file.
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.adaptation import Adaptation

router = APIRouter()


@router.get("/{adaptation_id}/docx")
def download_docx(adaptation_id: str, db: Session = Depends(get_db)):
    a = db.query(Adaptation).filter(Adaptation.id == adaptation_id).first()
    if not a:
        raise HTTPException(404, "Adaptation not found")
    if a.status != "done":
        raise HTTPException(409, f"Adaptation is not ready (status: {a.status})")
    if not a.output_path or not os.path.exists(a.output_path):
        raise HTTPException(404, "Output file not found. The master may have been a PDF.")

    filename = os.path.basename(a.output_path)
    return FileResponse(
        path=a.output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )
