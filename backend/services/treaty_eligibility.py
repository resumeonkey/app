"""
Trade-treaty eligibility matrix.

Maps a candidate's country of citizenship + education level to the set of
Canadian free-trade agreements they can use for LMIA-exempt temporary entry
as a professional/technician.

Currently fully populated for Chile (the primary use case). Adding a new
country is just a new entry in _MATRIX — no other code changes needed.

Education levels:
  - "university"  → 4-year degree (qualifies as a "professional")
  - "technical"   → 2-year diploma (qualifies as a "technician", CPTPP only)
  - "none"        → no treaty professional pathway

Treaty codes returned: "CPTPP", "CCFTA" (Canada-Chile), "CUSMA" (Mexico),
"PERU", "COLOMBIA", "PANAMA", "COSTARICA".
"""
from __future__ import annotations

# country (lowercase) → {education_level → [treaty codes]}
# Bilateral FTAs (CCFTA/CUSMA/PERU/…) cover *professionals* (university only).
# CPTPP additionally covers *technicians* (2-yr), but only for CPTPP members
# (Chile, Mexico, Peru in Latin America).
_MATRIX: dict[str, dict[str, list[str]]] = {
    "chile": {
        "university": ["CCFTA", "CPTPP"],
        "technical":  ["CPTPP"],
    },
    "mexico": {
        "university": ["CUSMA", "CPTPP"],
        "technical":  ["CPTPP"],
    },
    "peru": {
        "university": ["PERU", "CPTPP"],
        "technical":  ["CPTPP"],
    },
    "colombia": {
        "university": ["COLOMBIA"],
    },
    "panama": {
        "university": ["PANAMA"],
    },
    "costa rica": {
        "university": ["COSTARICA"],
    },
}

# Countries exposed in the profile UI (order matters for display).
SUPPORTED_COUNTRIES = ["Chile", "Mexico", "Peru", "Colombia", "Panama", "Costa Rica"]


def eligible_treaties(citizenship: str | None, education_level: str | None) -> set[str]:
    """Return the set of treaty codes the candidate qualifies for. Empty if none."""
    if not citizenship or not education_level or education_level == "none":
        return set()
    by_education = _MATRIX.get(citizenship.strip().lower())
    if not by_education:
        return set()
    return set(by_education.get(education_level, []))
