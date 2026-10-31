"""PDF parsing: text by page, section detection from numbered headings, whole tables.

Scanned pages (no extractable text) are flagged `needs_ocr`; on GCP they route to the
Document AI OCR processor. Diagrams -> Gemini multimodal is a later step (see README).
"""
import io
import re
import pdfplumber

HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Za-z0-9 ,/&()\-]{2,80})$")

class ParseError(Exception):
    """Permanent: the file itself is bad. Retrying will not help."""

def parse_pdf(content: bytes):
    """Returns (elements, n_pages). Each element: page, section, element_type, text."""
    try:
        pdf = pdfplumber.open(io.BytesIO(content))
    except Exception as e:
        raise ParseError(f"unreadable PDF: {type(e).__name__}: {e}") from e
    elements, section = [], "Front matter"
    with pdf:
        n_pages = len(pdf.pages)
        if not n_pages:
            raise ParseError("PDF has zero pages")
        for pno, page in enumerate(pdf.pages, start=1):
            tables = page.find_tables()
            bboxes = [t.bbox for t in tables]
            # text outside table regions, so table cells aren't duplicated into prose
            def outside(obj, bboxes=bboxes):
                return not any(b[0] <= obj["x0"] and obj["x1"] <= b[2] and
                               b[1] <= obj["top"] and obj["bottom"] <= b[3] for b in bboxes)
            text = (page.filter(outside).extract_text() or "").strip()
            if not text and not tables:
                elements.append(dict(page=pno, section=section, element_type="needs_ocr", text=""))
                continue
            buf = []
            for line in text.splitlines():
                m = HEADING.match(line.strip())
                if m:
                    if buf:
                        elements.append(dict(page=pno, section=section, element_type="text",
                                             text=" ".join(buf)))
                        buf = []
                    section = f"{m.group(1)} {m.group(2).strip()}"
                else:
                    buf.append(line.strip())
            if buf:
                elements.append(dict(page=pno, section=section, element_type="text", text=" ".join(buf)))
            for t in tables:
                rows = [[(c or "").strip() for c in r] for r in t.extract() if r]
                if rows:
                    elements.append(dict(page=pno, section=section, element_type="table",
                                         text=table_to_text(rows), rows=rows))
    return elements, n_pages

def table_to_text(rows):
    header, body = rows[0], rows[1:]
    lines = [f"Table with columns: {', '.join(header)}."]
    for r in body:
        lines.append("; ".join(f"{h}: {v}" for h, v in zip(header, r)) + ".")
    return " ".join(lines)
