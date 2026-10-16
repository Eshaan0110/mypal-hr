"""The format-independent result of parsing a policy file.

Both parsers (PDF and DOCX) produce the same ParsedDocument, so everything after parsing -
quality checks, chunking, storage - does not care which format the policy arrived in.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["heading", "paragraph", "list_item", "table"]
Severity = Literal["info", "warning", "blocking"]


@dataclass(frozen=True)
class Block:
    """One structural element of the document, in reading order."""

    kind: BlockKind
    text: str
    page: int | None  # 1-based; None for formats without fixed pages (DOCX)
    level: int | None = None  # headings only: 1 = top-level section
    rows: tuple[tuple[str, ...], ...] | None = None  # tables only; first row is the header


@dataclass(frozen=True)
class Issue:
    """Something a reviewer should know about the extraction.

    info     - worth knowing, no action needed
    warning  - the document needs manual review before approval
    blocking - the document cannot be ingested as-is
    """

    severity: Severity
    code: str
    message: str
    page: int | None = None


@dataclass
class ParsedDocument:
    format: Literal["pdf", "docx"]
    page_count: int | None
    blocks: list[Block] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


_WHITESPACE = re.compile(r"\s+")
# Numbered headings such as "3", "3.", "3.1" or "4.2.1" followed by text.
_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")


def normalise_text(text: str) -> str:
    """NFKC turns ligatures and full-width characters into plain equivalents (e.g. "ﬁ" -> "fi");
    then collapse runs of whitespace."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def section_number(heading: str) -> str | None:
    """'3.1 Casual leave' -> '3.1';  'Purpose' -> None."""
    match = _SECTION_NUMBER.match(heading)
    return match.group(1) if match else None


def numbering_depth(heading: str) -> int | None:
    """'3' -> 1, '3.1' -> 2, '4.2.1' -> 3; None when the heading is not numbered."""
    number = section_number(heading)
    return number.count(".") + 1 if number else None
