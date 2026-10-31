"""
Deterministic hard filters and rubrics for the three digest lists.

The LLM only extracts *facts* about a posting (see digest_pipeline); every point
awarded and every discard decision is computed here so results are reproducible
and the rubric can be tuned without touching prompts.
"""
import re
from datetime import datetime, timezone
from typing import Any

from backend.config import get_settings

CANADA = "canada"
CHILE = "chile"
REMOTE = "remote"
LIST_KEYS = (CANADA, CHILE, REMOTE)


# ── small coercion helpers ────────────────────────────────────────────────────

def _b(x: Any) -> bool:
    if isinstance(x, str):
        return x.strip().lower() in ("true", "yes", "si", "sí", "1")
    return bool(x)


def _i(x: Any, lo: int, hi: int, default: int = 0) -> int:
    try:
        return max(lo, min(hi, int(round(float(x)))))
    except (TypeError, ValueError):
        return default


def _s(x: Any) -> str:
    return str(x).strip().lower() if x is not None else ""


# ── posting age ───────────────────────────────────────────────────────────────

_UNIT_DAYS = {"second": 0, "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365,
              "segundo": 0, "minuto": 0, "hora": 0, "dia": 1, "día": 1, "semana": 7, "mes": 30, "año": 365}
_AGE_RE = re.compile(r"(\d+)\s*\+?\s*(second|minute|hour|day|week|month|year|segundo|minuto|hora|d[ií]a|semana|mes|a[ñn]o)s?", re.I)


def parse_days(value: Any, now: datetime | None = None) -> int | None:
    """Days since a posting date. Accepts '3 days ago', 'hace 2 semanas', ISO dates, epoch seconds/ms."""
    if value is None or value == "":
        return None
    now = now or datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e11:
            ts /= 1000.0
        return max(0, int((now.timestamp() - ts) // 86400))
    text = str(value).strip()
    low = text.lower()
    if low in ("today", "just now", "hoy", "now") or "just posted" in low:
        return 0
    if low in ("yesterday", "ayer"):
        return 1
    m = _AGE_RE.search(low)
    if m:
        unit = m.group(2).lower().replace("í", "i").replace("ñ", "n")
        for k, d in _UNIT_DAYS.items():
            if unit.startswith(k.replace("í", "i").replace("ñ", "n")):
                return int(m.group(1)) * d
    if re.fullmatch(r"\d{9,13}", low):
        return parse_days(int(low), now)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            dt = datetime.strptime(text.replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, (now - dt).days)
        except ValueError:
            continue
    return None


# ── location helpers ──────────────────────────────────────────────────────────

_QC_NAMES = re.compile(r"\b(quebec|québec|montreal|montréal|laval|gatineau|sherbrooke|longueuil|brossard|lévis|levis|trois-rivi[eè]res)\b", re.I)
_QC_CODE = re.compile(r"\bQC\b")
_CA_NAMES = re.compile(
    r"\b(canada|ontario|british columbia|alberta|manitoba|saskatchewan|nova scotia|new brunswick|newfoundland|"
    r"toronto|vancouver|calgary|ottawa|edmonton|winnipeg|halifax|mississauga|kitchener|waterloo|burnaby|"
    r"brampton|markham|richmond hill|surrey|hamilton|regina|saskatoon|oakville|vaughan|newmarket|fredericton|moncton)\b", re.I)
_CA_CODES = re.compile(r"\b(ON|BC|AB|MB|SK|NS|NB|NL|PE)\b")
_FOREIGN = re.compile(
    r"\b(india|united states|usa|u\.s\.|united kingdom|uk|mexico|méxico|brazil|brasil|philippines|germany|france|spain|"
    r"españa|poland|romania|portugal|argentina|colombia|australia|singapore|ireland|netherlands|israel|china|japan|"
    r"pakistan|nigeria|kenya|egypt|ukraine)\b", re.I)


def is_canadian_location(loc: str) -> bool:
    return bool(_CA_NAMES.search(loc) or _CA_CODES.search(loc) or _QC_NAMES.search(loc) or _QC_CODE.search(loc))


def is_quebec_only(loc: str) -> bool:
    has_qc = bool(_QC_NAMES.search(loc) or _QC_CODE.search(loc))
    non_qc = _CA_NAMES.sub(lambda m: "" if m.group(0).lower() == "canada" else m.group(0), loc)
    other = bool(_CA_CODES.search(loc) or _CA_NAMES.search(non_qc))
    return has_qc and not other


def _has_foreign_only(loc: str) -> bool:
    return bool(_FOREIGN.search(loc)) and not is_canadian_location(loc)


_RM_TOKENS = re.compile(
    r"\b(santiago|las condes|providencia|ñuñoa|nunoa|vitacura|lo barnechea|maip[uú]|la florida|huechuraba|"
    r"[ñn]u[ñn]oa|san miguel|independencia|recoleta|quilicura|la reina|pe[ñn]alol[eé]n|macul|estaci[oó]n central|"
    r"regi[oó]n metropolitana|rm|el bosque|puente alto|san bernardo|renca|cerrillos|lo prado|pudahuel)\b", re.I)


_CL_OTHER_CITY = re.compile(
    r"\b(valpara[ií]so|vi[ñn]a del mar|concepci[oó]n|antofagasta|temuco|la serena|rancagua|puerto montt|iquique|talca|"
    r"arica|copiap[oó]|osorno|valdivia|punta arenas|chill[aá]n|curic[oó]|calama|coquimbo)\b", re.I)


def in_metropolitan_region(loc: str) -> bool:
    return bool(_RM_TOKENS.search(loc))


# ── title helpers ─────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _keywords() -> list[str]:
    return [normalize(k) for k in get_settings().digest_title_keywords.split(",") if k.strip()]


def title_keyword_hits(title: str) -> int:
    """How many of the configured keywords appear in the title (accent-insensitive)."""
    t = " " + normalize(title) + " "
    hits = 0
    for kw in _keywords():
        pat = r"(?<![a-z0-9])" + re.escape(kw) + (r"(?![a-z0-9])" if len(kw) <= 3 else "")
        if re.search(pat, t):
            hits += 1
    return hits


_SENIOR_TITLE = re.compile(r"(?<![a-z])(senior|sr|lead|staff|principal|manager|director|head)(?![a-z])")
_NOC_22222 = re.compile(r"(?<![a-z])(qa|quality assurance|quality analyst|quality engineer|software quality|tester|testing|test analyst|uat)(?![a-z])")
_NOC_22221 = re.compile(r"(help ?desk|service desk|technical support|tech support|application support|it support|desktop support|"
                        r"support (analyst|engineer|specialist|technician)|soporte (tecnico|de aplicaciones)|tier [123]|l[123] support)")
_NOC_22220 = re.compile(r"(system(s)? administrator|sysadmin|network (administrator|technician|engineer|analyst)|noc (analyst|technician)|"
                        r"web (technician|administrator)|infrastructure technician)")
_IMPLEMENTATION = re.compile(r"(implementation|implementacion|onboarding|solutions? (consultant|engineer|architect|analyst|specialist)|"
                             r"deployment|integration (specialist|consultant|analyst)|business (systems )?analyst|systems analyst|"
                             r"functional (analyst|consultant)|technical consultant)")


def visa_from_title(title: str) -> tuple[int, str]:
    """Visa component 0-2 from fixed title rules (company size is not checked)."""
    t = normalize(title)
    if _SENIOR_TITLE.search(t):
        return 0, "senior"
    if _NOC_22222.search(t):
        return 2, "NOC 22222"
    if _NOC_22221.search(t):
        return 2, "NOC 22221"
    if _NOC_22220.search(t):
        return 2, "NOC 22220"
    if _IMPLEMENTATION.search(t):
        return 1, "implementación TEER 1"
    return 0, "sin vía clara"


def title_prefilter(job: dict) -> str | None:
    return None if title_keyword_hits(job.get("title", "")) else "titulo_sin_palabras_clave"


# ── language / title heuristics ───────────────────────────────────────────────

_FR_TITLE = re.compile(
    r"\b(analyste|développeur|developpeur|conseiller|conseill[eè]re|ingénieur|ingenieur|chargé|chargée|responsable|"
    r"spécialiste|specialiste|gestionnaire|technicien|technicienne|soutien|automatisés|automatises|manuels|"
    r"et|pour|avec|chez|stagiaire|étudiant|poste|offre)\b", re.I)
_FR_WORDS = set("le la les des du de et pour avec vous nous est une un dans sur au aux sont être notre votre nos vos ce cette ces qui que".split())


def looks_french(title: str, text: str = "") -> bool:
    if len(_FR_TITLE.findall(title or "")) >= 2 or re.search(r"\b(analyste|développeur|conseiller|ingénieur)\b", title or "", re.I):
        return True
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", (text or "")[:700].lower())
    if len(words) >= 40:
        return sum(1 for w in words if w in _FR_WORDS) / len(words) > 0.18
    return False


_TOO_SENIOR = re.compile(r"\b(director|head of|head,|vp|vice[- ]president|principal)\b", re.I)
_NOT_TECH = re.compile(
    r"(voice (record|actor|over)|grabaci[oó]n de voz|data label|labell?ing|annotation|annotator|survey|encuesta|"
    r"transcri|micro-?task|paid per task|per task|captcha|mystery shopper|clickworker)", re.I)
_SCAM = re.compile(r"(telegram|whatsapp|western union|wire transfer|registration fee|processing fee|pay (a |the )?fee|"
                   r"bank (account|details)|send (us )?(your )?(bank|ssn|passport)|purchase (your )?(own )?equipment)", re.I)
_AGENCY = re.compile(
    r"(witi|bc tecnolog|randstad|manpower|adecco|hays|michael page|robert half|page personnel|experis|kelly services|"
    r"talent|reclutamiento|selecci[oó]n|headhunter|consultora de rrhh|staffing|recruit|people ?connect|gestión de talento)", re.I)


def is_agency(company: str, flag: Any = False) -> bool:
    return _b(flag) or bool(_AGENCY.search(company or ""))


# ── facts the LLM must return, per list (documented for the prompt) ───────────

def _modality(f: dict) -> str:
    m = _s(f.get("modality"))
    return m if m in ("remote", "hybrid", "onsite") else "unknown"


# ── CANADA ────────────────────────────────────────────────────────────────────

def prefilter_canada(job: dict) -> str | None:
    s = get_settings()
    kw = title_prefilter(job)
    if kw:
        return kw
    if _TOO_SENIOR.search(job.get("title", "")):
        return "titulo_demasiado_senior"
    days = job.get("days_posted")
    if days is not None and days > s.digest_max_age_days:
        return "mas_de_21_dias"
    loc = job.get("location", "")
    if _has_foreign_only(loc):
        return "fuera_de_canada"
    if looks_french(job.get("title", ""), job.get("snippet", "")):
        return "frances_requerido"
    return None


def postfilter_canada(job: dict, f: dict) -> str | None:
    if not _b(f.get("is_job", True)):
        return "no_es_oferta"
    if _b(f.get("french_required")) or _s(f.get("posting_language")) in ("fr", "french", "francés"):
        return "frances_requerido"
    if not is_canadian_location(job.get("location", "")) and not _b(f.get("remote_canada")):
        return "fuera_de_canada"
    return None


def _canada_practicality(job: dict, f: dict) -> tuple[int, str]:
    loc = job.get("location", "")
    if _b(f.get("remote_canada")) or (re.search(r"\bremote\b", loc, re.I) and is_canadian_location(loc)):
        return 2, "remoto Canadá"
    if re.search(r"\b(vancouver|toronto)\b", loc, re.I):
        return 2, "Vancouver/Toronto"
    if is_quebec_only(loc):
        return 0, "Quebec"
    if is_canadian_location(loc):
        return 1, "otra ciudad"
    return 0, "ubicación incierta"


def score_canada(job: dict, f: dict) -> dict:
    fit = _i(f.get("fit"), 0, 4)
    sp = _s(f.get("spanish"))
    domain = _b(f.get("domain_match"))
    diff = 2 if sp in ("required", "asset") else (1 if domain else 0)
    diff_note = {"required": "español requerido", "asset": "español asset"}.get(sp, "dominio afín" if domain else "sin diferenciador")
    visa, visa_note = visa_from_title(job.get("title", ""))
    prac, prac_note = _canada_practicality(job, f)
    pen, pen_notes = 0, []
    if _b(f.get("bachelor_no_equiv")):
        pen -= 3
        pen_notes.append("Bachelor sin 'or equivalent' −3")
    if is_quebec_only(job.get("location", "")):
        pen -= 2
        pen_notes.append("Quebec −2")
    total = max(0, min(10, fit + diff + visa + prac + pen))
    parts = [f"Ajuste {fit}/4", f"Dif {diff}/2 ({diff_note})", f"Visa {visa}/2 ({visa_note})", f"Prac {prac}/2 ({prac_note})"] + pen_notes
    return {"score": total, "components": {"ajuste": fit, "diferenciador": diff, "visa": visa, "practicidad": prac, "penalizacion": pen},
            "reason": " | ".join(parts)}


# ── CHILE ─────────────────────────────────────────────────────────────────────

def _chile_salary_net_clp(f: dict) -> int | None:
    s = get_settings()
    amount = f.get("salary_monthly")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    cur = _s(f.get("salary_currency")) or "clp"
    clp = amount * s.usd_clp_rate if cur in ("usd", "us$", "dolar", "dólar") else amount
    if _s(f.get("salary_basis")) in ("gross", "bruto"):
        clp *= s.gross_to_net_factor
    return int(clp)


def prefilter_chile(job: dict) -> str | None:
    s = get_settings()
    kw = title_prefilter(job)
    if kw:
        return kw
    days = job.get("days_posted")
    if days is not None and days > s.digest_max_age_days:
        return "mas_de_21_dias"
    return None


def postfilter_chile(job: dict, f: dict) -> str | None:
    s = get_settings()
    if not _b(f.get("is_job", True)):
        return "no_es_oferta"
    loc = job.get("location", "")
    rm_fact = f.get("in_metropolitan_region")
    rm_known = in_metropolitan_region(loc) or _b(rm_fact) or "santiago" in (job.get("url") or "").lower()
    outside = (rm_fact is False or _s(rm_fact) == "false" or bool(_CL_OTHER_CITY.search(loc))) and not rm_known
    if _modality(f) == "onsite" and outside:
        return "presencial_fuera_de_RM"
    net = _chile_salary_net_clp(f)
    if net is not None and net < s.chile_min_salary_clp:
        return "sueldo_bajo_minimo"
    return None


def score_chile(job: dict, f: dict) -> dict:
    s = get_settings()
    base = _i(f.get("fit_base"), 0, 4)
    bonus = 1 if _b(f.get("domain_bonus")) else 0
    fit = min(4, base + bonus)
    unmet = _b(f.get("requires_unmet_experience"))
    if unmet:
        fit = min(fit, 2)
    eng = {"strong": 2, "mild": 1}.get(_s(f.get("english_signal")), 0)
    net = _chile_salary_net_clp(f)
    if net is None:
        sal, sal_note = 1, "no publicado"
    elif net >= s.chile_good_salary_clp:
        sal, sal_note = 2, f"${net:,.0f} líquido".replace(",", ".")
    else:
        sal, sal_note = 0, f"${net:,.0f} líquido".replace(",", ".")
    mod = _modality(f)
    loc = job.get("location", "")
    rm = in_metropolitan_region(loc) or _b(f.get("in_metropolitan_region")) or "santiago" in (job.get("url") or "").lower()
    if mod == "remote":
        mp, mn = 2, "remoto"
    elif mod == "hybrid":
        mp, mn = (2, "híbrido Santiago") if (rm or not loc) else (1, "híbrido fuera de Santiago")
    elif mod == "onsite":
        mp, mn = (1, "presencial Santiago") if rm else (0, "presencial")
    else:
        mp, mn = 1, "modalidad no indicada"
    total = max(0, min(10, fit + eng + sal + mp))
    fit_note = "exige experiencia que no tienes" if unmet else ("dominio extra" if bonus else "")
    parts = [f"Ajuste {fit}/4" + (f" ({fit_note})" if fit_note else ""), f"Inglés {eng}/2", f"Sueldo {sal}/2 ({sal_note})", f"Modalidad {mp}/2 ({mn})"]
    return {"score": total, "components": {"ajuste": fit, "ingles": eng, "sueldo": sal, "modalidad": mp},
            "reason": " | ".join(parts), "agency": is_agency(job.get("company", ""), f.get("agency"))}


# ── REMOTE INTERNATIONAL ──────────────────────────────────────────────────────

def prefilter_remote(job: dict) -> str | None:
    s = get_settings()
    kw = title_prefilter(job)
    if kw:
        return kw
    days = job.get("days_posted")
    if days is not None and days > s.digest_max_age_days:
        return "mas_de_21_dias"
    blob = f"{job.get('title', '')} {job.get('snippet', '')}"
    if _NOT_TECH.search(blob):
        return "no_es_rol_tecnologico"
    if _SCAM.search(blob):
        return "posible_estafa"
    return None


def _remote_pay_monthly_usd(f: dict) -> float | None:
    try:
        v = float(f.get("pay_usd_monthly"))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


_COUNTRY_LABEL = {"canada": "Canadá", "chile": "Chile"}


def _eligible_countries(f: dict) -> list[str]:
    raw = f.get("eligible_for") or []
    if isinstance(raw, str):
        raw = [raw]
    return [c for c in dict.fromkeys(_s(x) for x in raw) if c in _COUNTRY_LABEL]


def postfilter_remote(job: dict, f: dict) -> str | None:
    s = get_settings()
    if not _b(f.get("is_job", True)):
        return "no_es_oferta"
    if _modality(f) in ("hybrid", "onsite"):
        return "no_es_100_remoto"
    if _s(f.get("eligibility")) == "restricted" or (_s(f.get("eligibility")) == "explicit" and not _eligible_countries(f)):
        return "exige_residencia_no_elegible"
    if _b(f.get("not_tech_role")):
        return "no_es_rol_tecnologico"
    if _b(f.get("scam_signals")) or f.get("company_verifiable") is False or _s(f.get("company_verifiable")) == "false":
        return "empresa_no_verificable_o_estafa"
    pay = _remote_pay_monthly_usd(f)
    if pay is not None and pay < s.remote_min_usd:
        return "pago_bajo_minimo"
    return None


def score_remote(job: dict, f: dict) -> dict:
    s = get_settings()
    fit = _i(f.get("fit"), 0, 4)
    el = _s(f.get("eligibility"))
    elig, elig_note = (2, "LATAM/Chile/Canadá/worldwide explícito") if el == "explicit" else (1, "ambiguo")
    pay = _remote_pay_monthly_usd(f)
    if pay is None:
        pp, pn = 1, "no publicado"
    elif pay >= s.remote_good_usd:
        pp, pn = 2, f"USD {pay:,.0f}/mes"
    else:
        pp, pn = 0, f"USD {pay:,.0f}/mes"
    langs = _s(f.get("languages_required"))
    domain = _b(f.get("domain_match"))
    diff = 2 if langs == "en_es" else (1 if domain else 0)
    diff_note = "inglés y español requeridos" if langs == "en_es" else ("dominio afín" if domain else "sin diferenciador")
    total = max(0, min(10, fit + elig + pp + diff))
    parts = [f"Ajuste {fit}/4", f"Elegibilidad {elig}/2 ({elig_note})", f"Pago {pp}/2 ({pn})", f"Dif {diff}/2 ({diff_note})"]
    countries = [_COUNTRY_LABEL[c] for c in _eligible_countries(f)]
    applies_to = countries if countries else ["Canadá o Chile (por confirmar)"]
    return {"score": total, "components": {"ajuste": fit, "elegibilidad": elig, "pago": pp, "diferenciador": diff},
            "reason": " | ".join(parts), "applies_to": applies_to}


# ── dispatch ──────────────────────────────────────────────────────────────────

PREFILTERS = {CANADA: prefilter_canada, CHILE: prefilter_chile, REMOTE: prefilter_remote}
POSTFILTERS = {CANADA: postfilter_canada, CHILE: postfilter_chile, REMOTE: postfilter_remote}
SCORERS = {CANADA: score_canada, CHILE: score_chile, REMOTE: score_remote}
