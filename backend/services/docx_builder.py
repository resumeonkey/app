"""
Reconstruct the adapted .docx by modifying ONLY the changed sections
in the original document, preserving all formatting, styles, and layout.

Strategy:
1. Copy the original docx to a new file.
2. For each changed section, find its paragraphs by index and update them in-place.
3. When adapted text has more/fewer lines than original, expand/contract carefully.
4. Never touch paragraphs outside changed sections.
"""
import os
import re
import shutil
from docx import Document
from docx.oxml.ns import qn
from lxml import etree
from copy import deepcopy
from typing import Any

# Pattern: "| May 2020 – Apr 2021" — marks a job-title line.
# IMPORTANT: must require a MONTH NAME so that certification lines like
# "CertiProf | 2025" or "Udemy | 2024" are NOT mistakenly treated as job titles.
_JOB_TITLE_RE = re.compile(
    r'\|\s*(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
    r'jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)',
    re.IGNORECASE,
)


def build_adapted_docx(
    master_path: str,
    master_sections: dict[str, Any],
    blocks_changed: list[dict],
    output_path: str,
) -> str:
    """
    Creates output_path as an adapted copy of master_path.
    Returns the output_path.
    """
    # Work on a copy — never mutate the master
    shutil.copy2(master_path, output_path)
    doc = Document(output_path)

    for block in blocks_changed:
        section_name = block["section"]
        adapted_text = block["adapted"]

        # Look up by exact key first; fall back to case-insensitive partial match.
        # This makes the builder robust whether blocks_changed uses canonical names
        # ("experience") or actual document heading text ("Work Experience").
        section_info = master_sections.get(section_name)
        if section_info is None:
            for key, info in master_sections.items():
                if section_name.lower() in key.lower() or key.lower() in section_name.lower():
                    section_info = info
                    break

        if not section_info:
            continue

        para_indices = section_info.get("para_indices", [])
        if not para_indices:
            continue

        _replace_section_content(doc, para_indices, adapted_text)

    doc.save(output_path)
    return output_path


def _replace_section_content(doc: Document, para_indices: list[int], new_text: str):
    """
    Replace the text in the paragraphs at para_indices with new_text lines.
    Preserves the formatting (bold, italic, font) of the first run of each paragraph.
    Uses doc.paragraphs (body-level only) — must match resume_parser.parse_docx ordering.
    """
    new_lines = [line for line in new_text.split("\n") if line.strip()]
    paras     = doc.paragraphs

    # Validate indices
    valid_indices = [i for i in para_indices if i < len(paras)]
    if not valid_indices:
        return

    # Safety cap: LLM sometimes expands content far beyond the original.
    # Allow at most 50% more lines than the original slot count to prevent
    # the adapted section from overrunning into adjacent sections.
    max_lines = len(valid_indices) + max(5, len(valid_indices) // 2)
    if len(new_lines) > max_lines:
        new_lines = new_lines[:max_lines]

    # We'll map new lines onto the existing paragraph slots.
    # If more new lines than slots, insert extra paragraphs after the last slot.
    # If fewer new lines, clear extra paragraphs (set to empty).

    # Paragraphs to remove when adapted text is shorter than original.
    # Collect them first; remove AFTER the loop (modifying the doc mid-loop is unsafe).
    paragraphs_to_remove: list = []

    for slot_num, para_idx in enumerate(valid_indices):
        para = paras[para_idx]
        if slot_num < len(new_lines):
            _set_paragraph_text(para, new_lines[slot_num])
        else:
            # More original slots than new lines — remove excess paragraphs
            # so they don't leave blank lines in the document.
            paragraphs_to_remove.append(para)

    for para in paragraphs_to_remove:
        _remove_paragraph(para)

    # If more new lines than original paragraphs, insert after the last valid index
    if len(new_lines) > len(valid_indices):
        last_para = paras[valid_indices[-1]]
        extra_lines = new_lines[len(valid_indices):]
        for line in reversed(extra_lines):
            new_para = _insert_paragraph_after(last_para, line)
            _copy_style(last_para, new_para)


def _remove_paragraph(para) -> None:
    """
    Physically remove a paragraph from the document XML.
    Used when the adapted text is shorter than the original, so surplus
    original paragraphs don't produce blank lines in the output.
    """
    p = para._p
    parent = p.getparent()
    if parent is not None:
        parent.remove(p)


def _set_paragraph_text(para, text: str):
    """Clear all runs in paragraph and set new text, preserving first-run formatting.

    Special case: if the new text looks like a job-title line (contains | + date),
    the paragraph is re-formatted as a bold non-bullet heading even if the
    original paragraph slot had a list-bullet style.  This fixes master DOCX files
    where some role headers are incorrectly stored as bullet paragraphs.
    """
    from docx.oxml import OxmlElement

    # Handle bullet-like prefix (strip leading "• " or "- ")
    clean_text = text.lstrip("•-– ").strip() if text.startswith(("•", "-", "–")) else text
    if not clean_text:
        # Empty text — just clear the paragraph content
        for run in para.runs:
            run._r.getparent().remove(run._r)
        for r in para._p.findall(qn("w:r")):
            para._p.remove(r)
        return

    is_job_title = bool(_JOB_TITLE_RE.search(clean_text))

    if is_job_title:
        # ── Job-title line: force bold heading, remove bullet properties ──────
        # Clear existing runs
        for run in para.runs:
            run._r.getparent().remove(run._r)
        for r in para._p.findall(qn("w:r")):
            para._p.remove(r)

        # Strip list/bullet properties from pPr so it doesn't render as a bullet
        pPr = para._p.find(qn("w:pPr"))
        if pPr is not None:
            for child_tag in ("w:numPr", "w:pStyle"):
                el = pPr.find(qn(child_tag))
                if el is not None:
                    # Remove numPr entirely; keep pStyle but we'll leave it
                    if child_tag == "w:numPr":
                        pPr.remove(el)

        # Create bold run
        r = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        b = OxmlElement("w:b")
        rPr.append(b)
        r.append(rPr)
        t = OxmlElement("w:t")
        t.text = clean_text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t)
        para._p.append(r)

    else:
        # ── Normal line: preserve original run formatting (minus bold) ────────
        # Strip w:b / w:bCs so bullet/content lines never inherit bold from a
        # master slot that happened to be bold (e.g. a highlighted achievement
        # line in the master).  Job-title bold is handled explicitly above.
        first_run_rpr = None
        if para.runs:
            rpr = para.runs[0]._r.find(qn("w:rPr"))
            if rpr is not None:
                first_run_rpr = deepcopy(rpr)
                for bold_tag in ("w:b", "w:bCs"):
                    el = first_run_rpr.find(qn(bold_tag))
                    if el is not None:
                        first_run_rpr.remove(el)

        for run in para.runs:
            run._r.getparent().remove(run._r)
        for r in para._p.findall(qn("w:r")):
            para._p.remove(r)

        r = OxmlElement("w:r")
        if first_run_rpr is not None:
            r.append(deepcopy(first_run_rpr))
        t = OxmlElement("w:t")
        t.text = clean_text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t)
        para._p.append(r)


def _insert_paragraph_after(ref_para, text: str):
    """Insert a new paragraph after ref_para with the same style."""
    from docx.oxml import OxmlElement
    new_p = OxmlElement("w:p")

    # Copy paragraph properties (pPr) from reference
    ref_ppr = ref_para._p.find(qn("w:pPr"))
    if ref_ppr is not None:
        new_p.append(deepcopy(ref_ppr))

    # Add text run
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    r.append(t)
    new_p.append(r)

    # Insert after reference paragraph in the XML tree
    ref_para._p.addnext(new_p)

    # Return a Paragraph wrapper — find the newly added para
    from docx.text.paragraph import Paragraph
    return Paragraph(new_p, ref_para._p.getparent())


def _copy_style(source_para, target_para):
    """Copy paragraph style name from source to target."""
    try:
        if source_para.style:
            target_para.style = source_para.style
    except Exception:
        pass
