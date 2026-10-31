"""
Email delivery via Resend (resend.com).
Free tier: 3 000 emails/month, 100/day.
"""
import html
import logging
from datetime import date

import httpx

from backend.config import get_settings

log = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"

# ── HTML template ─────────────────────────────────────────────────────────────

_BASE_STYLE = """
  body { margin:0; padding:0; background:#f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color:#111827; }
  .wrap  { max-width:600px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden; }
  .hdr   { background:#1e3a5f; padding:28px 32px 20px; }
  .hdr h1 { margin:0; color:#fff; font-size:22px; font-weight:700; letter-spacing:-0.5px; }
  .hdr p  { margin:4px 0 0; color:#93c5fd; font-size:13px; }
  .body  { padding:24px 32px; }
  .intro { font-size:15px; color:#374151; margin:0 0 20px; }
  .card  { border:1px solid #e5e7eb; border-radius:10px; padding:20px; margin-bottom:16px; }
  .card-top  { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
  .card-title { font-size:16px; font-weight:600; margin:0 0 2px; color:#111827; }
  .card-company { font-size:13px; color:#6b7280; margin:0; }
  .badge  { flex-shrink:0; font-size:18px; font-weight:700; border-radius:8px; padding:4px 12px;
            text-align:center; min-width:48px; }
  .card-loc  { font-size:12px; color:#9ca3af; margin:10px 0 10px; }
  .card-why  { font-size:13px; color:#374151; margin:0 0 8px; }
  .card-gap  { font-size:12px; color:#9ca3af; margin:0 0 14px; }
  .btn   { display:inline-block; background:#1e3a5f; color:#fff !important; text-decoration:none;
           font-size:13px; font-weight:600; padding:9px 18px; border-radius:7px; }
  .footer { background:#f9fafb; border-top:1px solid #e5e7eb; padding:18px 32px; font-size:11px; color:#9ca3af; }
  .footer a { color:#6b7280; }
  @media (max-width:480px) {
    .body { padding:18px 16px; }
    .hdr  { padding:20px 16px 16px; }
    .card { padding:14px; }
    .footer { padding:14px 16px; }
  }
"""


def _score_badge(score: int) -> str:
    if score >= 8:
        return f'<span class="badge" style="background:#dcfce7;color:#15803d">{score}/10</span>'
    if score >= 6:
        return f'<span class="badge" style="background:#fef3c7;color:#b45309">{score}/10</span>'
    return f'<span class="badge" style="background:#fee2e2;color:#b91c1c">{score}/10</span>'


_LIST_TITLES = {
    "canada": "🇨🇦 Canadá",
    "chile": "🇨🇱 Chile",
    "remote": "🌎 Remoto internacional",
}
_MODALITY = {"remote": "Remoto", "hybrid": "Híbrido", "onsite": "Presencial", "unknown": "Modalidad no indicada"}


def _job_card(job: dict) -> str:
    e = lambda v: html.escape(str(v)) if v not in (None, "") else ""  # noqa: E731
    days = job.get("days_posted")
    meta = [e(job.get("location")), _MODALITY.get(job.get("modality") or "unknown", ""),
            "fecha desconocida" if days is None else ("hoy" if days == 0 else f"hace {days} día{'s' if days != 1 else ''}")]
    if job.get("salary"):
        meta.append("💰 " + e(job["salary"]))
    tags = []
    if job.get("agency"):
        tags.append("🏢 Agencia de reclutamiento")
    if job.get("employment_type") and job["employment_type"] != "unknown":
        tags.append({"employee_eor": "Empleado (EOR)", "employee": "Empleado", "contractor": "Contractor"}.get(job["employment_type"], ""))
    if job.get("timezone"):
        tags.append("🕒 " + e(job["timezone"]))
    tags_html = f'<p class="card-gap">{" · ".join(t for t in tags if t)}</p>' if tags else ""
    return f"""
<div class="card">
  <div class="card-top">
    <div>
      <p class="card-title">{e(job.get("title"))}</p>
      <p class="card-company">{e(job.get("company"))}</p>
    </div>
    {_score_badge(int(job.get("score") or 0))}
  </div>
  <p class="card-loc">📍 {" · ".join(m for m in meta if m)}</p>
  {tags_html}
  <p class="card-why">{e(job.get("reason"))}</p>
  <a class="btn" href="{html.escape(str(job.get("url") or "#"), quote=True)}" target="_blank">Postular →</a>
</div>"""


def _section(key: str, jobs: list[dict]) -> str:
    body = "\n".join(_job_card(j) for j in jobs) if jobs else \
        '<p class="intro">Sin ofertas hoy que pasen los filtros.</p>'
    return f'<h2 style="font-size:17px;margin:22px 0 8px">{_LIST_TITLES.get(key, key)} ({len(jobs)})</h2>\n{body}'


def build_digest_html(lists: dict[str, list[dict]]) -> str:
    today = date.today().strftime("%d %b %Y")
    count = sum(len(v) for v in lists.values())
    subject_line = f"{count} ofertas en 3 listas"
    sections = "\n".join(_section(k, lists.get(k, [])) for k in ("canada", "chile", "remote"))
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject_line}</title>
<style>{_BASE_STYLE}</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>🐵 Resumonkey</h1>
    <p>Digest diario · {today}</p>
  </div>
  <div class="body">
    <p class="intro">Tres listas, máximo 5 ofertas cada una, ordenadas por puntaje (0 a 10).</p>
    {sections}
  </div>
  <div class="footer">
    Resumonkey · <a href="https://resumonkey.dev">resumonkey.dev</a> ·
    Generado automáticamente. No respondas a este correo.
  </div>
</div>
</body>
</html>"""


# ── Resend sender ─────────────────────────────────────────────────────────────

async def send_digest_email(lists: dict[str, list[dict]]) -> bool:
    """Send digest email via Resend. Returns True on success."""
    settings = get_settings()
    if not settings.resend_api_key:
        log.warning("email_service: RESEND_API_KEY not set — skipping send")
        return False

    c = {k: len(lists.get(k, [])) for k in ("canada", "chile", "remote")}
    today = date.today().strftime("%d %b %Y")
    subject = f"🐵 Digest: Canadá {c['canada']} · Chile {c['chile']} · Remoto {c['remote']} — {today}"

    payload = {
        "from": settings.digest_from_email,
        "to":   [settings.digest_recipient_email],
        "subject": subject,
        "html": build_digest_html(lists),
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            log.info("email_service: sent id=%s to %s", data.get("id"), settings.digest_recipient_email)
            return True
    except Exception as exc:
        log.error("email_service: send failed: %s", exc)
        return False
