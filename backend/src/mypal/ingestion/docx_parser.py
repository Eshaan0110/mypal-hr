"""Word (.docx) parsing with python-docx.

DOCX files carry real structure (heading styles, list styles, tables), so less guessing is needed
than for PDF. Two limitations are reported rather than hidden:
- Word decides page breaks only when rendering, so there are no page numbers. Citations use
  section numbers instead.
- Headers, footers and text boxes are not read (they rarely hold policy rules).
"""

import io

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from mypal.ingestion.document import Block, Issue, ParsedDocument, normalise_text, numbering_depth
from mypal.ingestion.errors import DocumentRejected


def parse_docx(content: bytes) -> ParsedDocument:
    try:
        word = Document(io.BytesIO(content))
    except Exception as exc:  # python-docx raises several unrelated exception types
        raise DocumentRejected("The Word document could not be opened.") from exc

    document = ParsedDocument(format="docx", page_count=None)
    document.issues.append(
        Issue(
            "info",
            "no_page_numbers",
            "Word documents have no fixed pages, so citations will use section numbers only.",
        )
    )

    inferred_headings = 0
    for element in word.element.body.iterchildren():
        if element.tag == qn("w:p"):
            block, inferred = _paragraph_block(Paragraph(element, word))
            inferred_headings += inferred
            if block:
                document.blocks.append(block)
        elif element.tag == qn("w:tbl"):
            block = _table_block(Table(element, word))
            if block:
                document.blocks.append(block)
                document.issues.append(
                    Issue(
                        "info",
                        "table_extracted",
                        f"A table with {len(block.rows or ())} rows was extracted. Check its "
                        "values against the original before approval.",
                    )
                )

    if inferred_headings:
        document.issues.append(
            Issue(
                "info",
                "headings_inferred",
                f"{inferred_headings} heading(s) were inferred from bold text because they do "
                "not use Word heading styles. Check the section structure in the preview.",
            )
        )
    return document


def _join_tab_columns(text: str) -> str:
    """Policies often lay out definitions as "Term<TAB>Meaning". Plain whitespace collapsing
    turns that into one run-on phrase ("Immediate Family Spouse, Children ..."), so the term
    boundary is kept as "Term: Meaning". A leading number or marker ("3.1<TAB>Casual leave",
    "a)<TAB>...") is only a label and joins with a space."""
    parts = [part.strip() for part in text.split("\t") if part.strip()]
    if len(parts) < 2:
        return text
    head = parts[0]
    separator = " " if not any(c.isalpha() for c in head) or len(head) <= 2 else ": "
    if head.endswith((":", "-", "–")):
        separator = " "
    return head + separator + " ".join(parts[1:])


def _paragraph_block(paragraph: Paragraph) -> tuple[Block | None, int]:
    text = normalise_text(_join_tab_columns(paragraph.text))
    if not text:
        return None, 0
    style = (paragraph.style.name if paragraph.style is not None else "") or ""

    if style == "Title":
        return Block("heading", text, None, level=numbering_depth(text) or 1), 0
    if style.startswith("Heading "):
        style_level = int(style.removeprefix("Heading ") or 1)
        return Block("heading", text, None, level=numbering_depth(text) or style_level), 0
    numbered = paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None
    if style.startswith("List") or numbered:
        return Block("list_item", text, None), 0
    if _is_bold_heading(paragraph, text):
        return Block("heading", text, None, level=numbering_depth(text) or 2), 1
    return Block("paragraph", text, None), 0


def _is_bold_heading(paragraph: Paragraph, text: str) -> bool:
    """Many real policies fake headings with bold body text instead of heading styles."""
    runs = [run for run in paragraph.runs if run.text.strip()]
    return (
        bool(runs)
        and all(run.bold for run in runs)
        and len(text) <= 100
        and not text.endswith((".", ",", ";", ":"))
    )


def _table_block(table: Table) -> Block | None:
    rows: list[tuple[str, ...]] = []
    for row in table.rows:
        cells = tuple(normalise_text(cell.text) for cell in row.cells)
        if any(cells):
            rows.append(cells)
    if not rows:
        return None
    text = "\n".join(" | ".join(row) for row in rows)
    return Block("table", text, None, rows=tuple(rows))
