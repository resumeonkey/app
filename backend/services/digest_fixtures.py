"""
Calibration fixtures. The title, company and location come from the real postings the user named;
the descriptions are short reconstructions written to be typical of each posting, NOT the original text.
Replace `snippet` with the real posting text to calibrate on the real thing.
"""
from backend.services.digest_rubrics import CANADA, CHILE, REMOTE, parse_days


def _job(title, company, location, snippet, posted="3 days ago"):
    slug = (company + "-" + title).lower().replace(" ", "-")[:60]
    return {"title": title, "company": company, "location": location, "url": f"https://calibration.invalid/{slug}",
            "source": "fixture", "snippet": snippet, "posted": posted, "days_posted": parse_days(posted)}


FIXTURES = [
    {"label": "SysAid Implementation Specialist (English/Spanish), Toronto", "list": CANADA, "expect": {"min": 8},
     "job": _job("Implementation Specialist (English/Spanish)", "SysAid", "Toronto, Ontario, Canada",
                 "SysAid is an ITSM and service-management software company with 100+ employees. You will own customer onboarding and "
                 "implementation: configure workflows, SLAs and automations, run UAT and train customer admins. Fluent English and "
                 "Spanish are required to support our Latin American customers. 2+ years in implementation, support or QA. Hybrid, Toronto.")},
    {"label": "MaintainX Implementation Analyst Bilingual (English & Spanish), Toronto", "list": CANADA, "expect": {"min": 8},
     "job": _job("Implementation Analyst - Bilingual (English & Spanish)", "MaintainX", "Toronto, Ontario, Canada",
                 "MaintainX builds maintenance and field-service management software used by 10,000+ organizations. As an Implementation Analyst "
                 "you configure the platform for new customers, migrate data, document requirements and train teams. Spanish is required to support "
                 "our LATAM accounts. Experience with CMMS, ITSM or SQL is an asset. Toronto office or hybrid.")},
    {"label": "CGI Analyste QA, Montreal (descartada por francés)", "list": CANADA, "expect": {"discard": True},
     "job": _job("Analyste QA - Tests manuels et automatisés", "CGI", "Montreal, Quebec, Canada",
                 "Vous serez responsable de la planification et de l'exécution des tests manuels et automatisés pour nos clients. "
                 "Une excellente maîtrise du français et de l'anglais est exigée.")},
    {"label": "Zafin Senior Analyst FinOps, India (descartada por ubicación)", "list": CANADA, "expect": {"discard": True},
     "job": _job("Senior Analyst, FinOps (Cloud, Azure)", "Zafin", "India - Trivandrum",
                 "Own cloud cost governance across Azure subscriptions, build FinOps reports and drive optimisation with engineering teams.")},
    {"label": "Quadbridge Systems Administrator, Montreal (5 o menos)", "list": CANADA, "expect": {"max": 5},
     "job": _job("Systems Administrator, Internal IT", "Quadbridge", "Montreal, QC",
                 "Manage Active Directory, Windows and Linux servers, networking and the internal ticketing system for a 500-person IT consultancy. "
                 "3-5 years of experience in systems administration required.")},
    {"label": "WiTi Product Owner híbrido, Las Condes (7 o más)", "list": CHILE, "expect": {"min": 7},
     "job": _job("Product Owner", "WiTi", "Las Condes, Santiago",
                 "Para importante cliente buscamos Product Owner para liderar el backlog de un producto digital en un equipo Scrum. "
                 "Modalidad híbrida en Las Condes. Levantamiento de requisitos, historias de usuario y priorización. Inglés deseable. "
                 "Renta a convenir.", "5 días")},
    {"label": "Cumplo Product Manager presencial, Santiago, exige industria financiera (4 a 6)", "list": CHILE, "expect": {"range": [4, 6]},
     "job": _job("Product Manager", "Cumplo", "Santiago, Chile",
                 "Buscamos Product Manager para nuestra plataforma de financiamiento. Requisitos: mínimo 4 años de experiencia como Product Manager "
                 "en la industria financiera o fintech (crédito, factoring o pagos). Trabajo presencial en Santiago centro. Renta a convenir.", "4 días")},
    {"label": "DatoviaPlayhouse grabación de voz en español, USD 20 (descartada)", "list": REMOTE, "expect": {"discard": True},
     "job": _job("Spanish voice recording contributor (remote)", "DatoviaPlayhouse", "Remote",
                 "Record your voice in Spanish for an AI dataset. Paid USD 20 per recording session. Work from home, flexible hours. "
                 "Contact us on Telegram to start.", "2 days ago")},
]


def check(expect: dict, outcome: tuple) -> bool:
    kind = outcome[0]
    if expect.get("discard"):
        return kind == "discard"
    if kind == "discard" and "max" in expect:
        return True   # an offer that never reaches the lists is at or below any maximum
    if kind != "score":
        return False
    score = outcome[1]["score"]
    if "min" in expect:
        return score >= expect["min"]
    if "max" in expect:
        return score <= expect["max"]
    if "range" in expect:
        return expect["range"][0] <= score <= expect["range"][1]
    return False
