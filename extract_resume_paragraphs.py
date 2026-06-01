from docx import Document
from docx.oxml.ns import qn

doc_path = r'C:\Users\faleu\Mi unidad\NEW WORK\Masha HEADHUNTER\Alimenta IA\Resume Master.docx'
doc = Document(doc_path)

rows = []
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    style = para.style.name if para.style else 'None'

    # Check for numPr (bullet/list)
    pPr = para._p.find(qn('w:pPr'))
    has_numPr = False
    if pPr is not None:
        has_numPr = pPr.find(qn('w:numPr')) is not None

    # Check if any run has w:b (bold), respecting w:val
    has_bold = False
    for run in para.runs:
        rPr = run._r.find(qn('w:rPr'))
        if rPr is not None:
            b_elem = rPr.find(qn('w:b'))
            if b_elem is not None:
                val = b_elem.get(qn('w:val'))
                if val is None or val not in ('false', '0'):
                    has_bold = True
                    break

    display_text = '[EMPTY]' if not text else text
    rows.append((i, display_text, style, has_numPr, has_bold))

# Print full table
header = f"{'Idx':<5} {'Style':<38} {'numPr':<6} {'Bold':<5} Text"
print(header)
print('-' * 140)
for idx, txt, style, numpr, bold in rows:
    preview = txt[:95].replace('\n', ' ')
    print(f"{idx:<5} {style:<38} {str(numpr):<6} {str(bold):<5} {preview}")
