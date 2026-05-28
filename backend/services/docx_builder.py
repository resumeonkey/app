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


def _extract_run_structure(p_elem) -> list[tuple[str, Any]]:
    """
    Extract the text and rPr of every direct-child <w:r> in paragraph order.

    Returns [(run_text, rPr_deep_copy_or_None), ...]

    Only direct children are examined — runs nested inside <w:hyperlink> or
    other wrappers are excluded because their rPr belongs to a different scope.
    <w:br> within a run is normalised to a space.

    This is the authoritative per-run format profile used by _set_para_text to
    reconstruct multi-run paragraphs without collapsing their formatting.
    """
    result: list[tuple[str, Any]] = []
    for child in p_elem:
        if child.tag != _w("r"):
            continue
        # Collect run text: <w:t> content + space for every <w:br>
        parts: list[str] = []
        for el in child:
            if el.tag == _w("t") and el.text:
                parts.append(el.text)
            elif el.tag == _w("br"):
                parts.append(" ")
        run_text = "".join(parts)
        rpr_el = child.find(_w("rPr"))
        result.append((run_text, deepcopy(rpr_el) if rpr_el is not None else None))
    return result


def _apply_bold_strip(rpr: Any, orig_has_numpr: bool, section_name: str) -> None:
    """
    Mutate rpr in-place: remove <w:b> and <w:bCs> when the slot is a bullet
    outside of bold-preserve sections.  No-op for non-bullet or cert slots.
    """
    if not orig_has_numpr or section_name in _BOLD_PRESERVE_SECTIONS:
        return
    for bold_tag in (_w("b"), _w("bCs")):
        el = rpr.find(bold_tag)
        if el is not None:
            rpr.remove(el)


def _append_run(p_elem, text: str, rpr: Any,
                orig_has_numpr: bool, section_name: str) -> None:
    """
    Append a single <w:r> child to p_elem with the given text and formatting.

    The rpr argument is deep-copied so the caller's copy is not mutated.
    Bold is stripped when the slot is a regular bullet (not cert).
    Empty text is silently skipped.
    """
    if not text:
        return
    r = etree.SubElement(p_elem, _w("r"))
    if rpr is not None:
        rpr_copy = deepcopy(rpr)
        _apply_bold_strip(rpr_copy, orig_has_numpr, section_name)
        r.append(rpr_copy)
    t = etree.SubElement(r, _w("t"))
    t.text = text
    t.set(f"{{{_XML_NS}}}space", "preserve")


def _set_para_text(p_elem, new_text: str, section_name: str = "") -> None:
    """
    Replace the text of a paragraph in-place, preserving its original
    run-level formatting as faithfully as possible.

    Strategy
    ────────
    1.  Extract the full original run structure via _extract_run_structure
        BEFORE any XML is modified.
    2.  Job-title lines (contain "| <month>"): force a single bold run and
        strip numPr — same as before.
    3.  Multi-run paragraphs whose text contains "|" (cert entries, title lines
        that somehow reach here): split the new text at the first "|" and map
        each segment onto the corresponding original run's rPr.  This preserves
        the canonical Canadian pattern: bold left-of-pipe, non-bold right-of-pipe.
    4.  Single-run or fallback: create one run with the first run's rPr
        (current behaviour, but now via _append_run for consistency).

    Bold-stripping rules (unchanged):
    • Bullet slots outside certifications → strip bold (safety net).
    • Non-bullet slots, or cert bullets   → preserve bold.
    """
    clean = new_text.lstrip("•-– ").strip()
    if not clean:
        return

    is_job_title = bool(_JOB_TITLE_RE.search(clean))

    # ── 1. Extract original run structure BEFORE touching the XML ────────────
    run_struct = _extract_run_structure(p_elem)   # [(text, rPr|None), ...]

    # ── Paragraph properties ──────────────────────────────────────────────────
    pPr = p_elem.find(_w("pPr"))
    orig_has_numpr = pPr is not None and pPr.find(_w("numPr")) is not None

    # ── Remove existing direct-child runs ─────────────────────────────────────
    for child in list(p_elem):
        if child.tag == _w("r"):
            p_elem.remove(child)

    # ── 2. Job-title path: single bold run, strip bullet ─────────────────────
    if is_job_title:
        if pPr is not None:
            numPr = pPr.find(_w("numPr"))
            if numPr is not None:
                pPr.remove(numPr)
        r = etree.SubElement(p_elem, _w("r"))
        rpr_new = etree.SubElement(r, _w("rPr"))
        etree.SubElement(rpr_new, _w("b"))
        t = etree.SubElement(r, _w("t"))
        t.text = clean
        t.set(f"{{{_XML_NS}}}space", "preserve")
        return

    # ── 3. Multi-run path: reconstruct the original run split at "|" ─────────
    # Condition: original had ≥2 substantive runs AND both original and new text
    # contain "|" (the structural separator used in Canadian resume formatting).
    subst_runs = [(txt, rpr) for txt, rpr in run_struct if txt.strip() or rpr is not None]
    orig_joined = "".join(txt for txt, _ in run_struct)
    if len(subst_runs) >= 2 and "|" in clean and "|" in orig_joined:
        pipe_pos   = clean.index("|")
        seg_before = clean[:pipe_pos].rstrip()   # text left of "|" → first run's style (usually bold)
        seg_pipe   = clean[pipe_pos:]             # "|…" text        → second run's style (usually non-bold)

        # Preserve the Unicode spacing character that precedes "|" in the original
        # (Canadian resumes use U+00A0 NO-BREAK SPACE before the pipe, e.g. " | Date").
        # We read it from the original second run so it survives the replacement.
        orig_r2_text = subst_runs[1][0] if len(subst_runs) > 1 else ""
        spacer = ""
        # _SPACE_LIKE: U+0020 SPACE, U+00A0 NBSP, U+2002 EN SPACE, U+2003 EM SPACE, U+2009 THIN SPACE
        _SPACE_LIKE = {" ", " ", " ", " ", " "}
        if orig_r2_text and orig_r2_text[0] in _SPACE_LIKE:
            spacer = orig_r2_text[0]

        rpr_first  = subst_runs[0][1]
        rpr_second = subst_runs[1][1] if len(subst_runs) > 1 else None

        _append_run(p_elem, seg_before,          rpr_first,  orig_has_numpr, section_name)
        _append_run(p_elem, spacer + seg_pipe,   rpr_second, orig_has_numpr, section_name)
        return

    # ── 4. Single-run / fallback path ─────────────────────────────────────────
    first_rpr = subst_runs[0][1] if subst_runs else None
    _append_run(p_elem, clean, first_rpr, orig_has_numpr, section_name)
