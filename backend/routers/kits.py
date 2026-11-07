"""
Application Kit (Phase 1): from a digest offer, prepare a tailored CV + cover letter
+ form answers. It PREPARES the application; it never submits it.

Flow:
- POST /api/kits {job_url}  -> looks up the offer in digest_jobs, creates a linked
  Adaptation (tailored CV, reuses the existing pipeline) and an ApplicationKit, and
  kicks off background generation of the cover letter + answers.
- GET  /api/kits/{id}       -> JSON status + content + CV download link.
- GET  /api/kits/{id}/view  -> a self-contained HTML page (polls until ready).
- GET  /api/kits/new?job_url=... -> create-or-reuse by URL, then redirect to the view page.
- PATCH /api/kits/{id}/applied -> mark as applied (also records it as already-applied).
"""
import html
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.models.adaptation import Adaptation
from backend.models.application_kit import ApplicationKit
from backend.models.digest import DigestJob
from backend.models.master import MasterResume
from backend.routers.adaptations import _run_adaptation_task
from backend.services.cover_letter import generate_cover_letter
from backend.services.form_answers import build_form_answers

log = logging.getLogger(__name__)
router = APIRouter()


class CreateKitRequest(BaseModel):
    job_url: str


def _questions(job: DigestJob) -> list:
    raw = job.application_questions
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except Exception:
        return []


async def _run_kit_task(kit_id: str):
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        kit = db.query(ApplicationKit).filter(ApplicationKit.id == kit_id).first()
        if not kit:
            return
        job = db.query(DigestJob).filter(DigestJob.job_url == kit.job_url).first()
        master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
        resume_text = (master.full_text if master else "") or ""
        desc = (job.description if job else "") or ""
        try:
            kit.cover_letter = await generate_cover_letter(
                resume_text, desc, kit.company or "", kit.title or "", kit.list_key)
        except Exception as exc:
            kit.cover_letter = f"(No se pudo generar la carta: {str(exc)[:160]})"
        kit.answers = await build_form_answers(resume_text, _questions(job) if job else [], kit.list_key)
        kit.status = "ready"
        db.commit()
    except Exception as exc:
        try:
            kit = db.query(ApplicationKit).filter(ApplicationKit.id == kit_id).first()
            if kit:
                kit.status = "error"
                kit.error_msg = str(exc)[:500]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _create_kit(db: Session, job_url: str, background_tasks: BackgroundTasks) -> ApplicationKit:
    existing = db.query(ApplicationKit).filter(ApplicationKit.job_url == job_url).order_by(ApplicationKit.created_at.desc()).first()
    if existing:
        return existing
    job = db.query(DigestJob).filter(DigestJob.job_url == job_url).first()
    if not job:
        raise HTTPException(404, "Esa oferta no está en digest_jobs (no se guardó su texto).")
    master = db.query(MasterResume).filter(MasterResume.is_active == True).first()
    if not master:
        raise HTTPException(400, "No hay master resume activo. Activa uno primero.")
    s = get_settings()

    adaptation = Adaptation(
        master_id=master.id,
        job_description=job.description or f"{job.title or ''} at {job.company or ''}",
        job_url=job_url,
        job_title=job.title,
        company_name=job.company,
        llm_provider=s.kit_llm_provider,
        llm_model=s.kit_llm_model,
        status="pending",
    )
    db.add(adaptation)
    db.flush()

    kit = ApplicationKit(
        job_url=job_url, company=job.company, title=job.title, list_key=job.list_key,
        adaptation_id=adaptation.id, status="pending",
    )
    db.add(kit)
    db.commit()
    db.refresh(kit)

    background_tasks.add_task(_run_adaptation_task, adaptation.id)
    background_tasks.add_task(_run_kit_task, kit.id)
    return kit


def _detail(db: Session, kit: ApplicationKit) -> dict:
    adap = db.query(Adaptation).filter(Adaptation.id == kit.adaptation_id).first() if kit.adaptation_id else None
    cv_status = adap.status if adap else "none"
    cv_url = f"/api/export/{adap.id}/docx" if (adap and adap.status == "done") else None
    return {
        "id": kit.id, "job_url": kit.job_url, "company": kit.company, "title": kit.title,
        "list_key": kit.list_key, "status": kit.status, "error_msg": kit.error_msg,
        "cover_letter": kit.cover_letter, "answers": kit.answers,
        "cv_status": cv_status, "cv_download_url": cv_url,
        "applied_at": kit.applied_at.isoformat() if kit.applied_at else None,
        "ready": kit.status == "ready" and cv_status in ("done", "error"),
    }


@router.post("", status_code=201)
def create_kit(body: CreateKitRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    kit = _create_kit(db, body.job_url, background_tasks)
    return _detail(db, kit)


@router.get("/new")
def new_kit(job_url: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    kit = _create_kit(db, job_url, background_tasks)
    return RedirectResponse(url=f"/api/kits/{kit.id}/view", status_code=303)


@router.get("/{kit_id}")
def get_kit(kit_id: str, db: Session = Depends(get_db)):
    kit = db.query(ApplicationKit).filter(ApplicationKit.id == kit_id).first()
    if not kit:
        raise HTTPException(404, "Kit no encontrado")
    return _detail(db, kit)


@router.patch("/{kit_id}/applied")
def mark_applied(kit_id: str, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    kit = db.query(ApplicationKit).filter(ApplicationKit.id == kit_id).first()
    if not kit:
        raise HTTPException(404, "Kit no encontrado")
    kit.applied_at = datetime.now(timezone.utc)
    if kit.adaptation_id:
        adap = db.query(Adaptation).filter(Adaptation.id == kit.adaptation_id).first()
        if adap:
            adap.applied_at = kit.applied_at
    db.commit()
    return {"ok": True, "applied_at": kit.applied_at.isoformat()}


@router.get("/{kit_id}/view", response_class=HTMLResponse)
def view_kit(kit_id: str, db: Session = Depends(get_db)):
    kit = db.query(ApplicationKit).filter(ApplicationKit.id == kit_id).first()
    if not kit:
        raise HTTPException(404, "Kit no encontrado")
    title = html.escape(f"{kit.title or 'Oferta'} — {kit.company or ''}")
    return HTMLResponse(_VIEW_HTML.replace("__KIT_ID__", kit.id).replace("__TITLE__", title))


_VIEW_HTML = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kit · __TITLE__</title>
<style>
 :root{--bg:#f3f4f6;--card:#fff;--ink:#111827;--muted:#6b7280;--accent:#1e3a5f;--warn:#b45309;--warnbg:#fef3c7}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
 .wrap{max-width:760px;margin:0 auto;padding:24px 16px}
 h1{font-size:20px;margin:0 0 2px} .sub{color:var(--muted);font-size:13px;margin:0 0 18px}
 .card{background:var(--card);border:1px solid #e5e7eb;border-radius:12px;padding:18px;margin-bottom:16px}
 .card h2{font-size:15px;margin:0 0 10px} .muted{color:var(--muted)}
 pre{white-space:pre-wrap;word-wrap:break-word;font-family:inherit;font-size:14px;margin:0}
 .btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;font-size:13px;font-weight:600;padding:8px 14px;border-radius:7px;border:0;cursor:pointer}
 .btn.ghost{background:#eef2f7;color:var(--accent)}
 table{border-collapse:collapse;width:100%;font-size:13px} td{padding:6px 8px;vertical-align:top;border-bottom:1px solid #f0f0f0}
 td.k{color:var(--muted);width:40%} .warn{background:var(--warnbg);color:var(--warn);font-weight:600}
 .qa{border-bottom:1px solid #f0f0f0;padding:8px 0} .q{font-weight:600;font-size:13px} .a{font-size:13px;margin-top:3px}
 .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
</style></head><body><div class="wrap">
 <h1>__TITLE__</h1>
 <p class="sub">Kit de postulación · prepara, no envía. Revisa todo antes de postular.</p>
 <div id="status" class="card">Preparando el kit…</div>
 <div id="content" style="display:none">
  <div class="card"><div class="row"><h2 style="margin:0">CV adaptado</h2><span id="cvbox"></span></div></div>
  <div class="card"><div class="row" style="justify-content:space-between"><h2 style="margin:0">Carta de presentación</h2>
    <button class="btn ghost" onclick="cp('cl')">Copiar</button></div><pre id="cl" style="margin-top:10px"></pre></div>
  <div class="card"><h2>Respuestas estándar</h2><table id="std"></table></div>
  <div class="card" id="pqcard" style="display:none"><h2>Preguntas del aviso</h2><div id="pq"></div></div>
  <div class="card"><div class="row"><button class="btn" onclick="applied()">Marcar como postulada</button>
    <span id="appmsg" class="muted"></span></div></div>
 </div>
<script>
const KIT="__KIT_ID__";
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML}
function cp(id){const t=document.getElementById(id).innerText;navigator.clipboard.writeText(t)}
function warnify(v){v=v==null?'':String(v);return v.includes('REVISAR')||v.startsWith('FALTA')?'<span class="warn">'+esc(v)+'</span>':esc(v)}
async function applied(){await fetch('/api/kits/'+KIT+'/applied',{method:'PATCH'});document.getElementById('appmsg').textContent='Marcada como postulada ✓'}
async function poll(){
 const r=await fetch('/api/kits/'+KIT);const d=await r.json();
 const st=document.getElementById('status');
 const cv=document.getElementById('cvbox');
 if(d.cv_status==='done'&&d.cv_download_url){cv.innerHTML='<a class="btn" href="'+d.cv_download_url+'">Descargar CV (DOCX)</a>'}
 else if(d.cv_status==='error'){cv.innerHTML='<span class="warn">El CV falló al generarse</span>'}
 else{cv.innerHTML='<span class="muted">generando…</span>'}
 if(d.cover_letter!=null){document.getElementById('cl').textContent=d.cover_letter}
 if(d.answers&&d.answers.standard){
   const s=d.answers.standard;let h='';
   const labels={full_name:'Nombre',email:'Email',phone:'Teléfono',location:'Ubicación',linkedin:'LinkedIn',portfolio:'Portafolio',salary_expectation:'Expectativa de sueldo',availability:'Disponibilidad',languages:'Idiomas',work_authorization_canada:'¿Autorizado en Canadá?',requires_sponsorship:'¿Requiere patrocinio?',work_authorization_free_text:'Texto de autorización',pronouns:'Pronombres',voluntary_self_id:'Autoidentificación',veteran:'Veterano',references:'Referencias'};
   for(const k in labels){if(s[k]!==undefined){h+='<tr><td class="k">'+esc(labels[k])+'</td><td>'+warnify(s[k])+'</td></tr>'}}
   document.getElementById('std').innerHTML=h;
 }
 if(d.answers&&d.answers.posting_questions&&d.answers.posting_questions.length){
   document.getElementById('pqcard').style.display='block';
   document.getElementById('pq').innerHTML=d.answers.posting_questions.map(x=>'<div class="qa"><div class="q">'+esc(x.question)+'</div><div class="a">'+warnify(x.answer)+'</div></div>').join('');
 }
 if(d.status==='ready'){st.style.display='none';document.getElementById('content').style.display='block'}
 else if(d.status==='error'){st.innerHTML='<span class="warn">Error al preparar el kit: '+esc(d.error_msg||'')+'</span>'}
 if(!(d.status==='ready'&&(d.cv_status==='done'||d.cv_status==='error'))){setTimeout(poll,3000)}
}
poll();
</script>
</div></body></html>"""
