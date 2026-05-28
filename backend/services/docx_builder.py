"""
DOCX adaptation: XML-level text replacement.

Approach (inspired by cv_editor.py pattern):
  1. Build a {normalized_original_line: adapted_line} replacement map from all
     blocks_changed (we have both block["original"] and block["adapted"]).
  2. Open the DOCX as a zip, parse word/document.xml with lxml.
  3. Iterate EVERY <w:p> element in the document — body AND table cells.
     For each paragraph, normalize its text; if it matches an original line,
     replace the runs with the adapted text while preserving formatting.
  4. Remove paragraphs whose original line has no corresponding adapted line
     (LLM output shorter than original section).
  5. Repack the zip.

Advantages over para_indices:
  - No cascade: text matching is independent for each paragraph.
  - No index tracking: insertions/deletions in one section don't affect others.
  - Covers table cells: skills table entries can now be updated.
  - Format-safe: we only touch run text, never section headings or layout.
"""
import os
import re
import shutil
import zipfile
from copy import deepcopy
from typing import Any

from lxml import etree

# Canonical section keywords — used to detect when the LLM accidentally echoes
# a section heading as the first line of its adapted output.
_SECTION_HEADING_WORDS: frozenset[str] = frozenset({
    "summary", "profile", "professional summary", "professional profile",
    "career summary", "career profile", "about me", "objective",
    "skills", "technical skills", "core competencies", "key skills",
    "core capabilities", "areas of expertise", "expertise",
    "experience", "work experience", "professional experience",
    "work history", "employment", "employment history", "career history",
    "education", "academic", "academic background",
    "projects", "key projects", "selected projects", "notable projects",
    "certifications", "certification", "licenses", "license", "credentials",
    "professional development", "training",
    "languages", "language skills",
    "volunteer", "volunteering", "community",
})

# Word namespace
_WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_NS = "http://www.w3.org/XML/1998/namespace"

def _w(tag: str) -> str:
    return f"{{{_WNS}}}{tag}"


# Pattern: "| May 2020 – Apr 2021" — marks a job-title line.
# Requires a MONTH NAME so "CertiProf | 2025" does NOT match.
_JOB_TITLE_RE = re.compile(
    r'\|\s*(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
    r'jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)',
    re.IGNORECASE,
)

# Sections whose bullet items are intentionally bold (preserve bold).
_BOLD_PRESERVE_SECTIONS = frozenset({"certifications"})


# ── Public API ─────────────────────────────────────────────────────────────────

def build_adapted_docx(
    master_path: str,
    master_sections: dict[str, Any],
    blocks_changed: list[dict],
    output_path: str,
) -> str:
    """
    Creates output_path as an adapted copy of master_path.
    Uses XML-level text replacement: finds each original paragraph by its
    text content and replaces it with the adapted version in-place.
    Returns output_path.
    """
    shutil.copy2(master_path, output_path)

    # ── Build replacement + removal maps ──────────────────────────────────────
    replacements: dict[str, tuple[str, str]] = {}   # norm_orig → (adapted, section)
    removals:     set[str]                   = set() # norm_orig → remove paragraph

    for block in blocks_changed:
        section_name = block.get("section", "")
        orig_lines = [l.strip() for l in block.get("original", "").split("\n") if l.strip()]
        adpt_lines = [l.strip() for l in block.get("adapted",  "").split("\n") if l.strip()]

        for i, orig in enumerate(orig_lines):
            key = _norm(orig)
            if not key:
                continue
            if i < len(adpt_lines):
                adpt = adpt_lines[i].lstrip("•-– ").strip()
                # Guard: if the LLM echoed back a bare section heading as the
                # first (or any) adapted line, skip it.  This prevents the
                # heading paragraph in the document from being written twice.
                if adpt.lower() in _SECTION_HEADING_WORDS:
                    continue
                # Skip identity replacements: if the adapted text is the same
                # as the original (after normalisation), leave the paragraph
                # untouched so its original multi-run formatting (e.g. partial
                # bold on cert name vs. non-bold "| Org | Year") is preserved.
                if _norm(adpt) == key:
                    continue
                replacements[key] = (adpt, section_name)
            else:
                # LLM produced fewer lines — mark original paragraph for removal
                removals.add(key)

    # ── Open DOCX zip, parse XML ──────────────────────────────────────────────
    with zipfile.ZipFile(output_path, "r") as zin:
        all_files = {name: zin.read(name) for name in zin.namelist()}

    doc_xml = all_files.get("word/document.xml")
    if not doc_xml:
        return output_path

    root = etree.fromstring(doc_xml)

    # ── Apply replacements & collect removals ─────────────────────────────────
    paras_to_remove: list = []

    for p_elem in root.iter(_w("p")):
        para_text = _para_text(p_elem)
        if not para_text:
            continue

        if para_text in replacements:
            adpt, sname = replacements[para_text]
            _set_para_text(p_elem, adpt, section_name=sname)

        elif para_text in removals:
            paras_to_remove.append(p_elem)

    for p in paras_to_remove:
        parent = p.getparent()
        if parent is not None:
            parent.remove(p)

    # ── Repack ────────────────────────────────────────────────────────────────
    all_files["word/document.xml"] = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )

    tmp = output_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in all_files.items():
            zout.writestr(name, data)
    os.replace(tmp, output_path)

    return output_path


# ── XML helpers ────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Normalize whitespace for matching (collapses soft-break spaces, etc.)."""
    return " ".join(text.replace("\n", " ").split()).strip()


def _para_text(p_elem) -> str:
    """
    Concatenate all <w:t> text in a paragraph, replacing <w:br> with space.
    Then normalize whitespace so soft-break paragraphs match their DB raw_text.
    """
    parts: list[str] = []
    for elem in p_elem.iter():
        if elem.tag == _w("t") and elem.text:
            parts.append(elem.text)
        elif elem.tag == _w("br"):
            parts.append(" ")
    return _norm("".join(parts))


def _set_para_text(p_elem, new_text: str, section_name: str = "") -> None:
    """
    Replace the text of a paragraph in-place.

    Job-title lines (matched by _JOB_TITLE_RE):
      → Force bold run, remove w:numPr (strip bullet).

    All other lines:
      → Copy first-run rPr, apply bold-stripping rules:
        • Non-bullet slots (no numPr): always preserve bold (heading/title slots).
        • Bullet slots in certifications: preserve bold (intentional).
        • Bullet slots elsewhere: strip bold (safety net against overflow).
    """
    clean = new_text.lstrip("•-– ").strip()
    if not clean:
        return

    is_job_title = bool(_JOB_TITLE_RE.search(clean))

    # ── Collect first-run formatting ──────────────────────────────────────────
    # Only look at DIRECT-child <w:r> elements.
    # The recursive f".//{_w('r')}" search also finds runs nested inside
    # <w:pPr><w:rPr> (paragraph-property runs), which carry different and
    # incorrect formatting — using them corrupts the visible text style.
    first_rpr = None
    all_runs = [c for c in p_elem if c.tag == _w("r")]
    if all_runs:
        rpr = all_runs[0].find(_w("rPr"))
        if rpr is not None:
            first_rpr = deepcopy(rpr)

    # ── Paragraph properties ──────────────────────────────────────────────────
    pPr = p_elem.find(_w("pPr"))
    orig_has_numpr = (
        pPr is not None and pPr.find(_w("numPr")) is not None
    )

    # ── Remove existing runs (direct children of p_elem) ─────────────────────
    for child in list(p_elem):
        if child.tag == _w("r"):
            p_elem.remove(child)

    # ── Build replacement run ─────────────────────────────────────────────────
    if is_job_title:
        # Strip bullet, force bold heading
        if pPr is not None:
            numPr = pPr.find(_w("numPr"))
            if numPr is not None:
                pPr.remove(numPr)

        r = etree.SubElement(p_elem, _w("r"))
        rpr_new = etree.SubElement(r, _w("rPr"))
        etree.SubElement(rpr_new, _w("b"))

    else:
        r = etree.SubElement(p_elem, _w("r"))

        if first_rpr is not None:
            # Bold-stripping logic:
            #   Non-bullet slot → always preserve bold (title/heading slot).
            #   Cert section bullet → preserve bold (intentional).
            #   Other bullet slots → strip bold (safety net).
            should_strip = (
                orig_has_numpr
                and section_name not in _BOLD_PRESERVE_SECTIONS
            )
            if should_strip:
                for bold_tag in (_w("b"), _w("bCs")):
                    el = first_rpr.find(bold_tag)
                    if el is not None:
                        first_rpr.remove(el)
            r.append(deepcopy(first_rpr))

    t = etree.SubElement(r, _w("t"))
    t.text = clean
    t.set(f"{{{_XML_NS}}}space", "preserve")
