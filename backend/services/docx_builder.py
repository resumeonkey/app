"""
DOCX adaptation: XML-level text replacement (cv_editor pattern).

Core principle (same as cv_editor.py):
  → Only <w:t>.text is ever changed.
  → Runs, rPr, pPr, numPr, bold, font, color — 100% untouched.
  → Format of each paragraph is defined by the original and stays there.

Pipeline:
  1. Build {norm(original_line) → adapted_line} from blocks_changed.
  2. Open DOCX as zip, parse word/document.xml with lxml.
  3. For every <w:p> (body + table cells): normalise text; if it matches
     an original line, call _set_para_text → only <w:t> nodes are mutated.
  4. Remove paragraphs for lines the LLM dropped (shorter output).
  5. Repack zip.
"""
import os
import re
import shutil
import zipfile
from difflib import SequenceMatcher

from lxml import etree

# Canonical section keywords — guard against the LLM echoing a section
# heading as the first adapted line, which would overwrite the real heading.
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
_WNS    = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_NS = "http://www.w3.org/XML/1998/namespace"

def _w(tag: str) -> str:
    return f"{{{_WNS}}}{tag}"

# Unicode space-like characters that can precede "|" in a run.
# U+0020 SPACE · U+00A0 NBSP · U+2002 EN SPACE · U+2003 EM SPACE · U+2009 THIN SPACE
_SPACE_LIKE: frozenset[str] = frozenset({" ", "\xa0", " ", " ", " "})


# ── Public API ─────────────────────────────────────────────────────────────────

def build_adapted_docx(
    master_path: str,
    master_sections: dict,
    blocks_changed: list[dict],
    output_path: str,
) -> str:
    """
    Creates output_path as an adapted copy of master_path.
    Only <w:t> text nodes are modified — every other XML attribute,
    element, and property is left exactly as in the original.
    Returns output_path.
    """
    shutil.copy2(master_path, output_path)

    # ── Build replacement map ─────────────────────────────────────────────────
    # norm(original_line) → adapted_line
    #
    # Pairing strategy: difflib alignment, NOT positional zip.
    # Positional zip (orig[i] → adpt[i]) breaks catastrophically when the LLM
    # inserts, drops, merges, or reorders a single line: every pairing after
    # that point is shifted by one, so bullet text lands in heading paragraphs
    # (inheriting heading format), trailing original lines get deleted, and the
    # document layout degrades. SequenceMatcher gives us true edit regions:
    #   equal   → line unchanged, leave XML untouched
    #   replace → pair orig↔adapted within the region (the actual rewrites)
    #   delete  → line genuinely dropped by the LLM → removal candidate
    #   insert  → LLM invented a new line → IGNORED (we can never add
    #             paragraphs without breaking the template)
    replacements: dict[str, str] = {}
    removals:     set[str]       = set()

    for block in blocks_changed:
        orig_lines = [l.strip() for l in block.get("original", "").split("\n") if l.strip()]
        adpt_lines = [l.strip() for l in block.get("adapted",  "").split("\n") if l.strip()]

        orig_norm = [_norm(l) for l in orig_lines]
        adpt_norm = [_norm(l.lstrip("•-– ").strip()) for l in adpt_lines]

        matcher = SequenceMatcher(a=orig_norm, b=adpt_norm, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue            # unchanged — leave original XML untouched

            if tag == "replace":
                # Pair lines inside the changed region. When the region sizes
                # differ, zip the overlap; extra original lines become removals,
                # extra adapted lines are dropped (no paragraph to host them).
                region_orig = list(range(i1, i2))
                region_adpt = list(range(j1, j2))
                for oi, ai in zip(region_orig, region_adpt):
                    key  = orig_norm[oi]
                    adpt = adpt_lines[ai].lstrip("•-– ").strip()
                    if not key:
                        continue
                    if adpt.lower() in _SECTION_HEADING_WORDS:
                        continue    # LLM echoed a bare section heading
                    if _norm(adpt) == key:
                        continue    # identity — leave original untouched
                    replacements[key] = adpt
                for oi in region_orig[len(region_adpt):]:
                    if orig_norm[oi]:
                        removals.add(orig_norm[oi])

            elif tag == "delete":
                # LLM dropped these lines entirely
                for oi in range(i1, i2):
                    if orig_norm[oi]:
                        removals.add(orig_norm[oi])
            # tag == "insert": adapted-only lines — ignored by design

    # ── Open DOCX zip, parse XML ──────────────────────────────────────────────
    with zipfile.ZipFile(output_path, "r") as zin:
        all_files = {name: zin.read(name) for name in zin.namelist()}

    doc_xml = all_files.get("word/document.xml")
    if not doc_xml:
        return output_path

    root = etree.fromstring(doc_xml)

    # ── Apply replacements ONLY — never delete paragraphs ─────────────────────
    # Deleting paragraphs when the LLM returns fewer lines is too dangerous: a
    # single misalignment removed whole sections (e.g. "HR TECHNOLOGY HIGHLIGHTS")
    # and protected content (an education diploma). A slightly longer section is
    # always safer than a corrupted/incomplete document. We modify content in
    # place and leave structure intact (the `removals` set is intentionally unused).
    _ = removals  # computed above but deliberately not applied
    already_replaced: set[str] = set()  # prevent replacing duplicate paragraphs twice

    for p_elem in root.iter(_w("p")):
        para_text = _para_text(p_elem)
        if not para_text:
            continue

        # Never rewrite an ALL-CAPS sub-heading (e.g. "HR TECHNOLOGY HIGHLIGHTS").
        # These are structural labels that get swept into a section's content but
        # must stay verbatim — turning them into a bullet breaks the layout.
        if para_text.isupper() and 3 < len(para_text) < 45:
            continue

        if para_text in replacements and para_text not in already_replaced:
            _set_para_text(p_elem, replacements[para_text])
            already_replaced.add(para_text)

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
    """Normalize whitespace for matching (collapses NBSP, soft-break spaces, etc.)."""
    return " ".join(text.replace("\n", " ").split()).strip()


def _para_text(p_elem) -> str:
    """
    Concatenate all <w:t> text in a paragraph, replacing <w:br> with a space.
    Result is normalized so soft-break paragraphs match their DB raw_text.
    """
    parts: list[str] = []
    for elem in p_elem.iter():
        if elem.tag == _w("t") and elem.text:
            parts.append(elem.text)
        elif elem.tag == _w("br"):
            parts.append(" ")
    return _norm("".join(parts))


def _set_para_text(p_elem, new_text: str) -> None:
    """
    cv_editor pattern: ONLY change <w:t>.text — nothing else.

    Runs, rPr (bold/italic/font/size/color), pPr (numPr/indent/spacing),
    hyperlinks, bookmarks — all left 100% untouched.

    Distribution strategy
    ─────────────────────
    Collect every <w:t> that currently holds text, in document order.

    • 1 text node  → write the whole adapted line into it.
    • 2+ text nodes AND "|" in new text:
        - Canadian resume pattern: "Bold Name | non-bold metadata"
        - Split at first "|"; write left segment into node 1, right segment
          into node 2 (preserving the Unicode spacer character that precedes
          "|" in the original — typically U+00A0 NO-BREAK SPACE).
        - Any further nodes are cleared (they were empty or trailing fragments).
    • 2+ text nodes WITHOUT "|":
        - Write everything into node 1, clear the rest.
        - This covers unexpected multi-run bullets where the split point is
          not a structural separator we can detect.

    xml:space="preserve" is set on any node whose text has leading or trailing
    whitespace (required by the OOXML spec to prevent whitespace trimming).
    """
    clean = new_text.lstrip("•-–* ").strip()
    if not clean:
        return

    # Collect <w:t> elements that carry text, from direct-child <w:r> only.
    # We exclude runs inside <w:hyperlink> wrappers intentionally — they are
    # structural elements (URLs, bookmarks) that must never be changed.
    t_nodes: list = []
    for child in p_elem:
        if child.tag != _w("r"):
            continue
        t = child.find(_w("t"))
        if t is not None:
            t_nodes.append(t)

    if not t_nodes:
        return

    # Preserve a literal leading bullet/marker from the original first text node
    # (competency tables use literal "•  " text, not Word list numbering). Without
    # this, replacing the text would drop the bullet and break the visual list.
    _bullet_m = re.match(r'^([••\-–\*]\s+)', t_nodes[0].text or "")
    bullet_prefix = _bullet_m.group(1) if _bullet_m else ""
    if bullet_prefix and not clean.startswith(bullet_prefix.strip()):
        clean = bullet_prefix + clean

    def _write(t_elem, text: str) -> None:
        t_elem.text = text
        # xml:space="preserve" is required when text has leading/trailing spaces
        if text != text.strip():
            t_elem.set(f"{{{_XML_NS}}}space", "preserve")

    # ── Single text node: straightforward swap ────────────────────────────────
    if len(t_nodes) == 1:
        _write(t_nodes[0], clean)
        return

    # ── Multi-node: distribute by "|" separator ───────────────────────────────
    if "|" in clean:
        pipe_pos   = clean.index("|")
        seg_before = clean[:pipe_pos].rstrip()
        seg_pipe   = clean[pipe_pos:]               # includes "|"

        # Copy the spacer character that originally preceded "|" in node 2
        # (typically U+00A0 NO-BREAK SPACE — keeps the visual gap intact).
        orig_node2_text = t_nodes[1].text or ""
        spacer = orig_node2_text[0] if orig_node2_text and orig_node2_text[0] in _SPACE_LIKE else ""

        _write(t_nodes[0], seg_before)
        _write(t_nodes[1], spacer + seg_pipe)
        for t in t_nodes[2:]:          # clear any trailing nodes
            t.text = ""
        return

    # ── Multi-node without "|": everything into first node ───────────────────
    _write(t_nodes[0], clean)
    for t in t_nodes[1:]:
        t.text = ""
