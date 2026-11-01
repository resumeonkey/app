"""
Calibration fixtures. The title, company and location come from the real postings the user named;
Real texts: SysAid, MaintainX, Cumplo, TELUS and BNamericas. Still reconstructed by us (not the original text): CGI, Zafin, Quadbridge, WiTi, Datovia.
"""
from backend.services.digest_rubrics import CANADA, CHILE, REMOTE, parse_days


def _job(title, company, location, snippet, posted="3 days ago"):
    slug = (company + "-" + title).lower().replace(" ", "-")[:60]
    return {"title": title, "company": company, "location": location, "url": f"https://calibration.invalid/{slug}",
            "source": "fixture", "snippet": snippet, "posted": posted, "days_posted": parse_days(posted)}


# REAL posting texts (read through the digest fetchers on 2026-11-01; cleaned of page chrome, lightly condensed, wording unchanged).
_MAINTAINX_TEXT = "MaintainX is a leading mobile-first work execution platform for industrial and frontline teams. More than 13,000 customers, including Duracell, McDonald's, Shell, DHL and Volvo, use MaintainX to cut unplanned downtime and run better operations, across 13.9 million managed assets and 79.5 million completed work orders. In August 2026 MaintainX became part of Autodesk, joining Autodesk Operations Solutions. We're looking for a bilingual Implementation Analyst to join our team. In this customer-facing role, you'll support customer implementations by configuring the MaintainX platform, managing data migration, gathering business requirements, and troubleshooting technical issues throughout onboarding. You'll work closely with customers and internal teams to ensure successful deployments, drive platform adoption, and help translate maintenance and operational processes into effective workflows, delivering an exceptional onboarding experience. What You'll Do: Lead mid-market customers through successful implementations. Own implementation tasks such as data structuring, data migration and product training. Assist customers in identifying ways to get the most value out of the product. Lead meetings with client stakeholders. Deliver formal training to end-users. Provide knowledge transfer to internal team members throughout the onboarding process. Track and communicate client issues and proactively troubleshoot and resolve problems. Participate in multiple accounts, deadlines, and milestones. About You: 1+ years of relevant experience in software implementation, customer onboarding or application engineering. Fluent in both English and Spanish, with the ability to confidently communicate and deliver implementation in both languages in a business setting. BEng degree or equivalent. Experience in manufacturing and/or industrial space. Excellent communication, presentation, facilitation, time management, and interpersonal skills. Proficiency in Microsoft Excel, including data cleanup, validation, manipulation, and functions such as XLOOKUP, PivotTables, and formulas used to prepare and migrate customer data. Ability to manage multiple priorities and perform well in a fast-paced environment while maintaining a high level of quality and client satisfaction. Savvy with technology and capacity to become well-versed in our software in a short period of time. Ability to learn the MaintainX product within 30 days to advise customers."
_SYSAID_TEXT = "SysAid is a leading provider of IT Service Management (ITSM) and Asset Management solutions delivered through a SaaS model. Trusted by over 5,000 organisations worldwide, we empower businesses to improve efficiency with automation, analytics, and AI. As we continue to grow, we're looking for an Implementation Specialist to help our clients successfully adopt and maximise SysAid's solutions, gain hands-on experience with ITIL best practices, work with global customers, and shape ITSM transformations. We are seeking a bilingual Implementation Specialist (English/Spanish) to lead and manage end-to-end implementation of SysAid's solutions, ensuring our SMB clients achieve measurable value from day one. Work Location & Schedule: This role is based in our Toronto office, with on-site work Monday-Thursday. Fridays are a remote half-day, providing a balance of collaboration and flexibility. Responsibilities. Project Leadership & Client Engagement: Lead end-to-end implementation projects for SysAid ITSM and ESM solutions. Manage project plans, timelines, and deliverables, ensuring alignment with client goals. Act as the primary point of contact for clients. Conduct client workshops to gather business requirements, align expectations, and showcase SysAid's capabilities. Solution Design & Configuration: Design and configure solutions to meet client needs, including workflows, integrations, and reporting. Collaborate with internal teams on customizations and system integrations. Test and validate configured solutions with clients to ensure quality and functionality. Design, build, and configure SysAid AI agents for customers (Copilot, AI Agents, Dex), from use case definition through testing and go-live. Write, test, and refine agent prompts and instructions. Configure the knowledge sources that agents rely on (KB articles, service catalogue, past tickets). Training & Enablement: Deliver engaging training sessions to end-users and administrators. Provide support during the go-live phase. Requirements: 1-2+ years of experience in ITSM or related software implementation/consulting. Strong organisational and project management skills; ability to manage multiple projects simultaneously. Familiarity with ITSM platforms (SysAid, ServiceNow, Jira Service Management, etc.) and industry best practices. Experience in process design and workflow automation; exposure to APIs or system integrations is a plus. Hands-on experience configuring AI or automation features in an ITSM or SaaS platform. Working knowledge of prompt engineering. Ability to explain AI concepts to non-technical stakeholders and run hands-on training."
_CUMPLO_TEXT = 'En Cumplo, buscamos personas que quieran marcar la diferencia. Sobre nosotros: En Cumplo, conectamos a empresas que buscan liquidez con personas dispuestas a invertir en sus proyectos. Nuestra misión es democratizar el financiamiento y apoyar el crecimiento de las pymes en Latinoamérica. ¿Qué te espera? Liderar y coordinar equipos multifuncionales para garantizar el desarrollo y éxito de los productos digitales. Definir y mantener un roadmap del producto alineado con los objetivos estratégicos, el valor para el cliente y las demandas del mercado. Monitorear el desempeño del producto frente a métricas clave, impulsando mejoras basadas en datos. Diseñar y priorizar características del producto en colaboración con stakeholders clave. Realizar estudios de mercado y analizar datos de usuarios. Gestionar feedback de clientes para iterar sobre las funcionalidades del producto. Desarrollar continuamente casos de negocio para impulsar la implementación de iniciativas. ¿Qué necesitas? Desde 2 años de experiencia en roles como Product Manager, Category Manager o Segment Manager. Experiencia previa en la industria financiera. Titulación o formación en Ingeniería Civil, Ingeniería Industrial o áreas afines. Dominio medio-avanzado de SQL. Manejo de LLMs para la gestión, organización y resolución de tareas de forma eficiente. Experiencia trabajando con metodologías Agile y/o Lean. Deseable: nociones del Riesgo, Cobranza, Rentabilidad e impacto en Provisiones de las colocaciones en el rubro financiero. Semi Senior, jornada completa, Santiago (Chile).'

# Real posting text taken from digest_jobs (TELUS, Himalayas). Verbatim, with the long company boilerplate left out.
_TELUS_TEXT = (
    "Bilingual Systems Quality Analyst II (100% Remote) As Systems Quality Analyst, you will be responsible for analyzing business and "
    "technical requirements, developing test scenarios and test cases, and executing tests to ensure the quality and reliability of our "
    "solutions. This is a remote position with the option for in-person attendance at a TELUS Health office, if available in your area. "
    "Responsibilities: analyze business and technical documentation to identify testing requirements, scenarios, and test cases; develop and "
    "document test scenarios and test cases using established testing tools; execute tests within integrated solutions; identify, document, "
    "and report defects. Qualifications and Skills: Degree in Quality Assurance, Business Administration, or equivalent work experience. "
    "Strong attention to detail, analytical thinking. Excellent verbal and written communication skills in both French and English. "
    "Annual salary range $50,000 to $65,000. Intermediate knowledge of English is required because you will on a regular basis interact in "
    "English with external parties. Note for Quebec candidates: if knowledge of English is required for this position, it is because the team "
    "member will be asked, on a regular basis, to interact in English with external or internal parties."
)

# Real posting text from digest_jobs (BNamericas, Get on Board): a pure sales role that once scored 7/10 only for being remote and well paid.
_BNAMERICAS_TEXT = (
    "Salary published: USD 4000-5000 per month. Requisitos / Requirements: Más de 4 años de éxito demostrado en ventas B2B SaaS, con un "
    "historial de cumplimiento o superación de cuotas. / 4+ years of proven success in B2B SaaS sales, with a track record of meeting or "
    "exceeding quotas. Idiomas: español fluido e inglés nivel avanzado. Experiencia en tecnología de ventas: conocimientos avanzados de "
    "Salesforce, HubSpot, Outreach, Gong o Salesloft. Fuertes habilidades de negociación, comunicación y presentación. Conocimientos de IA: "
    "capacidad para comprender, posicionar y vender soluciones SaaS basadas en IA. Altamente proactivo, ambicioso y orientado a los "
    "resultados. Capacidad para prosperar en un entorno de ventas consultivo y gestionar acuerdos complejos. Impulsar ciclos de ventas "
    "integrales, desde la prospección hasta la negociación y el cierre, dentro del espacio B2B SaaS."
)

FIXTURES = [
    {"label": "SysAid Implementation Specialist (English/Spanish), Toronto", "list": CANADA, "expect": {"min": 8},
     "job": _job("Implementation Specialist (English/Spanish)", "SysAid", "Toronto, Ontario, Canada", _SYSAID_TEXT)},
    {"label": "MaintainX Implementation Analyst Bilingual (English & Spanish), Toronto", "list": CANADA, "expect": {"min": 8},
     "job": _job("Implementation Analyst - Bilingual (English & Spanish)", "MaintainX", "Toronto, Ontario, Canada", _MAINTAINX_TEXT)},
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
     "job": _job("Product Manager – Chile", "Cumplo", "Santiago, Chile", _CUMPLO_TEXT, "4 días")},
    {"label": "TELUS Bilingual Systems Quality Analyst (texto real: exige francés e inglés; descartada)", "list": REMOTE, "expect": {"discard": True},
     "job": _job("Bilingual Systems Quality Analyst I (100% Remote)", "TELUS", "Canada", _TELUS_TEXT, "6 days ago")},
    {"label": "BNamericas Account Executive (texto real: ventas puras, remoto USD 4000-5000; debe descartarse por encaje bajo)", "list": CHILE, "expect": {"discard": True},
     "job": _job("Ejecutivo/a de Cuentas / Account Executive – SaaS Solutions", "BNamericas", "Remote", _BNAMERICAS_TEXT, "4 días")},
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
