"""
Email delivery via Resend (resend.com).
Free tier: 3 000 emails/month, 100/day.
"""
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


def _job_card(job: dict) -> str:
    score   = job.get("score", 0)
    title   = job.get("title", "")
    company = job.get("company", "")
    loc     = job.get("location", "") or ""
    why     = job.get("why_fit", "") or ""
    gap     = job.get("main_gap", "") or ""
    url     = job.get("url", "#")

    loc_html = f'<p class="card-loc">📍 {loc}</p>' if loc else ""
    why_html = f'<p class="card-why">✅ {why}</p>' if why else ""
    gap_html = f'<p class="card-gap">⚠️ {gap}</p>' if gap else ""

    return f"""
<div class="card">
  <div class="card-top">
    <div>
      <p class="card-title">{title}</p>
      <p class="card-company">{company}</p>
    </div>
    {_score_badge(score)}
  </div>
  {loc_html}
  {why_html}
  {gap_html}
  <a class="btn" href="{url}" target="_blank">Ver oferta →</a>
</div>"""


def build_digest_html(jobs: list[dict]) -> str:
    today   = date.today().strftime("%d %b %Y")
    count   = len(jobs)
    subject_line = f"{count} oferta{'s' if count != 1 else ''} nuevas para ti hoy"
    cards   = "\n".join(_job_card(j) for j in jobs)

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
    <p class="intro">Hola — encontré <strong>{count} oferta{'s' if count != 1 else ''} nueva{'s' if count != 1 else ''}</strong>
      que encajan con tu perfil. Ordenadas por puntaje.</p>
    {cards}
  </div>
  <div class="footer">
    Resumonkey · <a href="https://resumonkey.dev">resumonkey.dev</a> ·
    Generado automáticamente. No respondas a este correo.
  </div>
</div>
</body>
</html>"""


# ── Resend sender ─────────────────────────────────────────────────────────────

async def send_digest_email(jobs: list[dict]) -> bool:
    """Send digest email via Resend. Returns True on success."""
    settings = get_settings()
    if not settings.resend_api_key:
        log.warning("email_service: RESEND_API_KEY not set — skipping send")
        return False

    count = len(jobs)
    today = date.today().strftime("%d %b %Y")
    subject = f"🐵 {count} oferta{'s' if count != 1 else ''} para ti — {today}"

    payload = {
        "from": settings.digest_from_email,
        "to":   [settings.digest_recipient_email],
        "subject": subject,
        "html": build_digest_html(jobs),
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
