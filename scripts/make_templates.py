import json, os, sys, tempfile
sys.path.insert(0, r"D:\resume-adapter")
D = r"D:\resume-adapter\backend\data"

for f in ("master_qa_software.json", "master_operations_process.json"):
    p = os.path.join(D, f)
    if os.path.exists(p):
        os.remove(p); print("removed", f)

CONTACT = {"location": "City, Province, Canada", "phone": "(000) 000-0000",
           "email": "you@email.com", "linkedin": "linkedin.com/in/you", "website": ""}

templates = {
"hospitality": dict(
  area="Hospitality & Tourism", format_type="Combinado",
  description="Servicio al cliente, F&B, operaciones de hotel/restaurante.",
  title="Hospitality & Guest Services Professional",
  tagline=["Guest Service", "Food & Beverage", "Front Desk", "Team Coordination", "Bilingual"],
  summary=["Hospitality professional with experience delivering exceptional guest experiences in fast-paced hotel and restaurant environments.",
           "Skilled in front-of-house operations, food and beverage service, and team coordination, with a focus on service quality and customer satisfaction."],
  competencies={
   "Guest Service": ["Customer Service", "Guest Relations", "Complaint Resolution", "Reservations", "Upselling"],
   "Food & Beverage": ["Table Service", "Bartending Basics", "POS Systems", "Food Safety", "Inventory Support"],
   "Operations & Team": ["Shift Coordination", "Cash Handling", "Scheduling Support", "Cleanliness Standards", "Teamwork"]},
  experience=[
   {"title": "Front Desk Agent", "company": "Example Hotel", "location": "City, Province", "dates": "2022 - Present", "domain": "hospitality",
    "bullets": ["Welcomed and checked in guests, handling reservations and inquiries with a friendly, professional manner.",
                "Resolved guest concerns promptly, contributing to improved guest satisfaction scores.",
                "Coordinated with housekeeping and management to ensure smooth daily operations."]},
   {"title": "Server", "company": "Example Restaurant", "location": "City, Province", "dates": "2020 - 2022", "domain": "hospitality",
    "bullets": ["Provided attentive table service in a high-volume restaurant, managing multiple tables efficiently.",
                "Operated POS system for orders and payments with accuracy.",
                "Upsold menu items and specials, supporting revenue targets."]}],
  education=[{"degree": "Diploma in Hospitality Management", "institution": "Your College", "dates": "Year"}],
  certifications=[{"name": "Food Safe / Food Handler Certificate", "issuer": "Provincial", "year": ""},
                  {"name": "Smart Serve / Responsible Beverage Service", "issuer": "Provincial", "year": ""}]),

"information_technology": dict(
  area="Information Technology", format_type="Hibrido",
  description="Skills tecnicas arriba, proyectos y certificaciones.",
  title="IT Professional",
  tagline=["Software", "Troubleshooting", "Cloud", "Databases", "Support"],
  summary=["IT professional with experience supporting systems, applications, and end users across enterprise environments.",
           "Strong technical foundation in troubleshooting, scripting, and system administration, with a focus on reliability and security."],
  competencies={
   "Technical Skills": ["SQL", "Python", "PowerShell", "Networking", "System Administration", "Troubleshooting"],
   "Tools & Platforms": ["Windows / Linux", "Azure / AWS", "Active Directory", "Git", "Ticketing Systems"],
   "Practices": ["Agile / Scrum", "Documentation", "Incident Management", "Data Backup", "Security Basics"]},
  experience=[
   {"title": "IT Support Specialist", "company": "Example Corp", "location": "City, Province", "dates": "2021 - Present", "domain": "IT support",
    "bullets": ["Provided technical support to end users, resolving hardware, software, and network issues.",
                "Administered user accounts and access in Active Directory.",
                "Documented procedures and maintained the knowledge base to improve resolution times."]},
   {"title": "Junior Systems Administrator", "company": "Example Inc", "location": "City, Province", "dates": "2019 - 2021", "domain": "IT",
    "bullets": ["Supported server maintenance, backups, and monitoring across Windows and Linux systems.",
                "Automated routine tasks with PowerShell scripts.",
                "Assisted with cloud migration and configuration projects."]}],
  education=[{"degree": "Diploma in Computer Systems Technology", "institution": "Your College", "dates": "Year"}],
  certifications=[{"name": "CompTIA A+", "issuer": "CompTIA", "year": ""},
                  {"name": "Microsoft / AWS Cloud Fundamentals", "issuer": "Vendor", "year": ""}]),

"healthcare": dict(
  area="Healthcare & Nursing", format_type="Cronologico",
  description="Licencias y certificaciones primero, skills clinicas.",
  title="Healthcare Professional",
  tagline=["Patient Care", "Clinical Skills", "Documentation", "Team Care", "Bilingual"],
  summary=["Compassionate healthcare professional with experience providing patient-centered care in clinical settings.",
           "Skilled in clinical procedures, patient assessment, and accurate documentation, committed to safety and quality of care."],
  competencies={
   "Clinical Skills": ["Patient Assessment", "Vital Signs", "Medication Administration", "Wound Care", "Infection Control"],
   "Patient Care": ["Patient Education", "Care Planning", "Mobility Assistance", "Compassionate Care", "Family Communication"],
   "Professional": ["Charting / EMR", "Privacy / Confidentiality", "Team Collaboration", "Time Management", "CPR / First Aid"]},
  experience=[
   {"title": "Registered Nurse / Care Aide", "company": "Example Health Centre", "location": "City, Province", "dates": "2021 - Present", "domain": "healthcare",
    "bullets": ["Provided direct patient care including assessment, monitoring, and medication administration.",
                "Maintained accurate patient records in the electronic medical record system.",
                "Collaborated with the interdisciplinary team to develop and update care plans."]}],
  education=[{"degree": "Bachelor of Science in Nursing (BScN)", "institution": "Your University", "dates": "Year"}],
  certifications=[{"name": "Provincial Nursing License / Registration", "issuer": "College of Nurses", "year": ""},
                  {"name": "CPR / BLS", "issuer": "Heart & Stroke", "year": ""}]),

"skilled_trades": dict(
  area="Skilled Trades", format_type="Combinado",
  description="Tickets/certificaciones, seguridad y manejo de equipos.",
  title="Skilled Tradesperson",
  tagline=["Installation", "Maintenance", "Safety", "Blueprints", "Hand & Power Tools"],
  summary=["Skilled tradesperson with hands-on experience in installation, maintenance, and repair across residential and commercial sites.",
           "Strong focus on safety, code compliance, and quality workmanship."],
  competencies={
   "Trade Skills": ["Installation", "Maintenance & Repair", "Blueprint Reading", "Measurements", "Troubleshooting"],
   "Safety & Compliance": ["WHMIS", "Site Safety", "Code Compliance", "PPE", "Hazard Assessment"],
   "Equipment": ["Hand Tools", "Power Tools", "Diagnostic Tools", "Equipment Operation", "Material Handling"]},
  experience=[
   {"title": "Tradesperson / Apprentice", "company": "Example Contracting", "location": "City, Province", "dates": "2020 - Present", "domain": "skilled trades",
    "bullets": ["Performed installation, maintenance, and repairs on residential and commercial projects.",
                "Read blueprints and followed building codes and safety regulations.",
                "Operated hand and power tools safely, maintaining a clean and organized work site."]}],
  education=[{"degree": "Trade Certification / Apprenticeship", "institution": "Your Trade School", "dates": "Year"}],
  certifications=[{"name": "Red Seal / Trade Ticket", "issuer": "Provincial", "year": ""},
                  {"name": "WHMIS / Working at Heights", "issuer": "Provincial", "year": ""}]),

"administrative": dict(
  area="Administrative & Office", format_type="Cronologico",
  description="Organizacion, software de oficina y comunicacion.",
  title="Administrative Professional",
  tagline=["Office Administration", "Scheduling", "MS Office", "Communication", "Data Entry"],
  summary=["Organized administrative professional with experience supporting office operations and management teams.",
           "Skilled in scheduling, correspondence, record keeping, and office software, with strong attention to detail."],
  competencies={
   "Administration": ["Scheduling", "Calendar Management", "Correspondence", "Filing & Records", "Reception"],
   "Software": ["MS Office (Word, Excel, Outlook)", "Data Entry", "Google Workspace", "CRM Basics", "Bookkeeping Basics"],
   "Professional": ["Communication", "Time Management", "Confidentiality", "Customer Service", "Problem Solving"]},
  experience=[
   {"title": "Administrative Assistant", "company": "Example Organization", "location": "City, Province", "dates": "2021 - Present", "domain": "administrative",
    "bullets": ["Managed calendars, scheduling, and correspondence for the management team.",
                "Maintained accurate records and filing systems, ensuring confidentiality.",
                "Prepared documents and reports using MS Office and supported office operations."]}],
  education=[{"degree": "Diploma in Office Administration", "institution": "Your College", "dates": "Year"}],
  certifications=[{"name": "MS Office / Bookkeeping Certificate", "issuer": "Provider", "year": ""}]),

"sales_customer_service": dict(
  area="Sales & Customer Service", format_type="Combinado",
  description="Metricas/targets, CRM y comunicacion.",
  title="Sales & Customer Service Professional",
  tagline=["Sales", "Customer Service", "CRM", "Targets", "Relationship Building"],
  summary=["Results-driven sales and customer service professional with experience meeting targets and building customer relationships.",
           "Skilled in needs assessment, product knowledge, and CRM tools, with a focus on customer satisfaction and retention."],
  competencies={
   "Sales": ["Lead Generation", "Needs Assessment", "Closing", "Upselling / Cross-selling", "Target Achievement"],
   "Customer Service": ["Relationship Building", "Complaint Resolution", "Product Knowledge", "Follow-up", "Retention"],
   "Tools & Skills": ["CRM (Salesforce/HubSpot)", "POS Systems", "Reporting", "Communication", "Negotiation"]},
  experience=[
   {"title": "Sales Associate", "company": "Example Retailer", "location": "City, Province", "dates": "2021 - Present", "domain": "sales / retail",
    "bullets": ["Met and exceeded monthly sales targets through attentive customer service and product knowledge.",
                "Built lasting customer relationships, driving repeat business and referrals.",
                "Processed transactions and managed CRM records accurately."]}],
  education=[{"degree": "Diploma in Business / Sales", "institution": "Your College", "dates": "Year"}],
  certifications=[{"name": "Customer Service / Sales Certificate", "issuer": "Provider", "year": ""}]),
}

for pid, body in templates.items():
    out = {"profile_id": pid, "name": "Your Name", **body, "contact": dict(CONTACT)}
    json.dump(out, open(os.path.join(D, f"template_{pid}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
print("created", len(templates), "templates")

from backend.services.resume_generator import generate_resume_docx
for pid in templates:
    d = json.load(open(os.path.join(D, f"template_{pid}.json"), encoding="utf-8"))
    generate_resume_docx(d, os.path.join(tempfile.gettempdir(), f"t_{pid}.docx"))
print("all generate OK")
