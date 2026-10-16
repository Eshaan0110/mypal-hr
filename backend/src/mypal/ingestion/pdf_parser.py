"""PDF parsing with pdfplumber.

A PDF does not store "headings" or "paragraphs" - only characters at positions, with a font and a
size. So structure is reconstructed with heuristics:

- Headings: lines noticeably larger than body text, or bold and short. Their level comes from
  section numbering ("3.1" = level 2) when present, otherwise from font size.
- Paragraphs: consecutive lines with a normal line gap are joined.
- Lists: lines starting with a bullet glyph.
- Tables: detected from ruling lines; their text is removed from the surrounding paragraphs.
- Running headers/footers (same text near the top/bottom of most pages) are dropped.

Pages with no extractable text are reported, since they are usually scans that need OCR.
"""

import io
import math
import re
from collections import Counter
from dataclasses import dataclass

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

from mypal.ingestion.document import Block, Issue, ParsedDocument, normalise_text, numbering_depth
from mypal.ingestion.errors import DocumentRejected

MAX_PAGES = 300
MIN_PAGE_CHARS = 20  # fewer extractable characters than this = effectively no text layer
GARBAGE_RATIO_WARNING = 0.05
EDGE_FRACTION = 0.08  # top/bottom 8% of the page is where running headers/footers live

# Bullet glyphs, including "(cid:N)": a glyph the PDF font does not map to a character, which is
# how many PDF generators' bullet symbols come out.
_BULLET = re.compile(r"^(?:\(cid:\d+\)|[•▪●◦■□‣∙·*–-])\s+")
_UNMAPPED_GLYPH = re.compile(r"\(cid:\d+\)")


@dataclass
class _Line:
    page: int
    top: float
    bottom: float
    text: str
    size: float
    bold: bool
    at_edge: bool


@dataclass
class _Table:
    page: int
    top: float
    rows: tuple[tuple[str, ...], ...]


def parse_pdf(content: bytes) -> ParsedDocument:
    try:
        pdf = pdfplumber.open(io.BytesIO(content))
    except (PDFPasswordIncorrect, PdfminerException) as exc:
        raise DocumentRejected(
            "The PDF could not be opened. It may be password-protected or damaged."
        ) from exc

    with pdf:
        page_count = len(pdf.pages)
        if page_count > MAX_PAGES:
            raise DocumentRejected(f"The PDF has more than {MAX_PAGES} pages.")
        document = ParsedDocument(format="pdf", page_count=page_count)
        lines: list[_Line] = []
        tables: list[_Table] = []
        for page in pdf.pages:
            page_lines, page_tables = _read_page(page, document)
            lines.extend(page_lines)
            tables.extend(page_tables)

    lines = _drop_running_headers_and_footers(lines, page_count)
    document.blocks = _build_blocks(lines, tables)
    return document


def _read_page(page, document: ParsedDocument) -> tuple[list[_Line], list[_Table]]:  # noqa: ANN001
    number = page.page_number
    found_tables = page.find_tables()
    table_boxes = [t.bbox for t in found_tables]
    tables = [
        _Table(
            page=number,
            top=t.bbox[1],
            rows=tuple(
                tuple(normalise_text(cell or "") for cell in row) for row in t.extract() if row
            ),
        )
        for t in found_tables
    ]

    lines: list[_Line] = []
    total_chars = 0
    garbage_chars = 0
    for raw in page.extract_text_lines(return_chars=True):
        if _inside_any(raw, table_boxes):
            continue
        visible = [c for c in raw["chars"] if c["text"].strip()]
        if not visible:
            continue
        text = normalise_text(raw["text"])
        total_chars += len(text)
        # Unmapped glyphs that are not a leading bullet mean text was lost in extraction.
        body = _BULLET.sub("", text, count=1)
        garbage_chars += sum(len(m) for m in _UNMAPPED_GLYPH.findall(body)) + body.count("�")
        sizes = Counter(round(c["size"], 1) for c in visible)
        bold = sum("bold" in c["fontname"].lower() for c in visible) > len(visible) / 2
        lines.append(
            _Line(
                page=number,
                top=raw["top"],
                bottom=raw["bottom"],
                text=text,
                size=sizes.most_common(1)[0][0],
                bold=bold,
                at_edge=(
                    raw["top"] < page.height * EDGE_FRACTION
                    or raw["bottom"] > page.height * (1 - EDGE_FRACTION)
                ),
            )
        )

    table_chars = sum(len(" ".join(row)) for t in tables for row in t.rows)
    if total_chars + table_chars < MIN_PAGE_CHARS:
        if page.images:
            document.issues.append(
                Issue(
                    "warning",
                    "page_without_text_layer",
                    "This page contains an image but no extractable text - it is probably a "
                    "scan. It needs OCR or manual transcription before its content can be used.",
                    page=number,
                )
            )
        else:
            document.issues.append(Issue("info", "empty_page", "This page has no text.", number))
    elif total_chars and garbage_chars / total_chars > GARBAGE_RATIO_WARNING:
        document.issues.append(
            Issue(
                "warning",
                "poor_text_extraction",
                f"About {garbage_chars * 100 // total_chars}% of the characters on this page "
                "could not be decoded. Compare the extracted text with the original.",
                page=number,
            )
        )
    for table in tables:
        document.issues.append(
            Issue(
                "info",
                "table_extracted",
                f"A table with {len(table.rows)} rows was extracted. Check its values against "
                "the original before approval.",
                page=number,
            )
        )
    return lines, tables


def _inside_any(line: dict, boxes: list[tuple[float, float, float, float]]) -> bool:
    middle_y = (line["top"] + line["bottom"]) / 2
    middle_x = (line["x0"] + line["x1"]) / 2
    return any(x0 <= middle_x <= x1 and top <= middle_y <= bottom for x0, top, x1, bottom in boxes)


def _drop_running_headers_and_footers(lines: list[_Line], page_count: int) -> list[_Line]:
    """Drop text that repeats near the top or bottom of at least half the pages (ignoring digits,
    so "Page 1" and "Page 2" count as the same line)."""
    if page_count < 2:
        return lines

    def key(line: _Line) -> str:
        return re.sub(r"\d+", "#", line.text.lower())

    pages_per_key: dict[str, set[int]] = {}
    for line in lines:
        if line.at_edge:
            pages_per_key.setdefault(key(line), set()).add(line.page)
    threshold = max(2, math.ceil(page_count / 2))
    repeated = {k for k, pages in pages_per_key.items() if len(pages) >= threshold}
    return [line for line in lines if not (line.at_edge and key(line) in repeated)]


def _build_blocks(lines: list[_Line], tables: list[_Table]) -> list[Block]:
    if not lines and not tables:
        return []
    body_size = _body_font_size(lines)
    heading_sizes = sorted(
        {line.size for line in lines if _looks_like_heading(line, body_size)}, reverse=True
    )

    # Interleave lines and tables in reading order (page, then vertical position).
    items: list[_Line | _Table] = [*lines, *tables]
    items.sort(key=lambda item: (item.page, item.top))

    blocks: list[Block] = []
    previous: _Line | None = None
    for item in items:
        if isinstance(item, _Table):
            text = "\n".join(" | ".join(row) for row in item.rows)
            blocks.append(Block("table", text, item.page, rows=item.rows))
            previous = None
            continue

        line = item
        bullet = _BULLET.match(line.text)
        if _looks_like_heading(line, body_size):
            level = numbering_depth(line.text) or heading_sizes.index(line.size) + 1
            blocks.append(Block("heading", line.text, line.page, level=min(level, 6)))
            previous = None
        elif bullet:
            blocks.append(Block("list_item", line.text[bullet.end() :], line.page))
            previous = line
        elif previous is not None and _continues(previous, line) and blocks:
            last = blocks[-1]
            blocks[-1] = Block(last.kind, f"{last.text} {line.text}", last.page)
            previous = line
        else:
            blocks.append(Block("paragraph", line.text, line.page))
            previous = line
    return blocks


def _body_font_size(lines: list[_Line]) -> float:
    """The most common font size, weighted by amount of text, is the body text size.

    Non-bold lines are preferred: in a short document the (bold) headings can contain more
    characters than the body, which would otherwise make a heading size look like body size.
    """
    regular = [line for line in lines if not line.bold] or lines
    weights: Counter[float] = Counter()
    for line in regular:
        weights[line.size] += len(line.text)
    return weights.most_common(1)[0][0] if weights else 0.0


def _looks_like_heading(line: _Line, body_size: float) -> bool:
    if len(line.text) > 120 or line.text.endswith((".", ",", ";")):
        return False
    if _BULLET.match(line.text):
        return False
    return line.size >= body_size + 1.5 or (line.bold and line.size >= body_size)


def _continues(previous: _Line, line: _Line) -> bool:
    """Same page and a normal line gap (not a paragraph break) means the same paragraph."""
    if previous.page != line.page:
        return False
    gap = line.top - previous.bottom
    return gap <= max(previous.bottom - previous.top, 1) * 0.6
