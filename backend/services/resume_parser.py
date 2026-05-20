"""
Parse a DOCX or PDF resume into a structured section map.

Output format:
{
  "full_text": "...",
  "candidate_name": "...",
  "sections": {
    "summary":    {"raw_text": "...", "para_indices": [2, 3]},
    "skills":     {"raw_text": "...", "para_indices": [5, 6, 7]},
    "experience": {"raw_text": "...", "para_indices": [9..25]},
    "education":  {"raw_text": "...", "para_indices": [26..30]},
    ...
  }
}
"""
import re
from typing import Any


# ── Section heading patterns (case-insensitive) ────────────────────────────────
SECTION_PATTERNS = {
    "summary": r"(summary|profile|professional profile|about me|objective|sobre m[ií]|perfil)",
    "skills":  r"(skills|technical skills|core competencies|key skills|competencias|habilidades)",
    "experience": r"(experience|work experience|professional experience|employment|experiencia)",
    "education":  r"(education|academic|educaci[oó]n|formaci[oó]n)",
    "projects":   r"(projects|key projects|selected projects|proyectos)",
    "certifications": r"(certifications?|licenses?|credentials|cursos|certificaciones?)",
    "languages":  r"(languages?|idiomas?)",
    "volunteer":  r"(volunteer|volunteering|voluntariado)",
}


def parse_docx(file_path: str) -> dict[str, Any]:
    from docx import Document
    doc = Document(file_path)

    paragraphs = []
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        style = para.style.name if para.style else ""
        paragraphs.append({"index": i, "text": text, "style": style, "empty": not text})

    return _build_section_map(paragraphs)


def parse_pdf(file_path: str) -> dict[str, Any]:
    try:
        import pdfplumber
        lines = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines.extend(text.split("\n"))
    except ImportError:
        # fallback: pypdf
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        lines = []
        for page in reader.pages:
            lines.extend((page.extract_text() or "").split("\n"))

    # Convert to paragraph-like objects
    paragraphs = []
    for i, line in enumerate(lines):
        text = line.strip()
        # Detect likely headings: ALL CAPS or short bold-ish lines
        style = "Heading 1" if _looks_like_heading(text) else "Normal"
        paragraphs.append({"index": i, "text": text, "style": style, "empty": not text})

    return _build_section_map(paragraphs)


def _looks_like_heading(text: str) -> bool:
    if not text:
        return False
    if text.isupper() and 2 < len(text) < 40:
        return True
    if re.match(r"^[A-Z][A-Z\s&/]+$", text) and len(text) < 40:
        return True
    return False


def _build_section_map(paragraphs: list[dict]) -> dict[str, Any]:
    full_lines = [p["text"] for p in paragraphs if p["text"]]
    full_text  = "\n".join(full_lines)

    # Detect candidate name: usually one of the first 3 non-empty lines
    candidate_name = _detect_name(paragraphs)

    # Find section boundaries by matching headings
    section_starts: list[tuple[str, int]] = []
    for p in paragraphs:
        if not p["text"]:
            continue
        matched = _match_section(p["text"])
        if matched:
            section_starts.append((matched, p["index"]))

    # Build sections: from one heading to the next
    sections: dict[str, dict] = {}
    for i, (section_name, start_idx) in enumerate(section_starts):
        end_idx = section_starts[i + 1][1] if i + 1 < len(section_starts) else len(paragraphs)
        section_paras = [
            p for p in paragraphs
            if start_idx <= p["index"] < end_idx and p["text"]
        ]
        # Skip the heading line itself (first paragraph)
        content_paras = section_paras[1:] if section_paras else []
        sections[section_name] = {
            "raw_text":     "\n".join(p["text"] for p in content_paras),
            "para_indices": [p["index"] for p in content_paras],
            "heading_index": start_idx,
        }

    return {
        "full_text":      full_text,
        "candidate_name": candidate_name,
        "sections":       sections,
    }


def _match_section(text: str) -> str | None:
    clean = text.strip().lower()
    for name, pattern in SECTION_PATTERNS.items():
        if re.search(pattern, clean):
            return name
    return None


def _detect_name(paragraphs: list[dict]) -> str:
    for p in paragraphs[:5]:
        text = p["text"].strip()
        if not text:
            continue
        # Skip lines that look like contact info or headings
        if "@" in text or "http" in text or text.isupper():
            continue
        words = text.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
            return text
    return ""
