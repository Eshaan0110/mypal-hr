"""Structure-aware chunking.

A chunk is the unit retrieval returns and the answer cites, so it should hold one coherent rule
with enough context to be understood on its own. Rules used here:

1. Never mix sections: a new heading always starts a new chunk, and each chunk records its
   heading path (e.g. ["3. Types of leave", "3.2 Sick leave"]) and section number ("3.2").
2. Within a section, paragraphs and list items are packed together up to a word budget; a
   paragraph that is too long on its own is split at sentence boundaries.
3. Tables become their own chunks. Large tables are split by rows, repeating the header row in
   every piece so each piece still says what its columns mean.
4. Page start/end are kept on every chunk for citations (PDF only).
"""

import hashlib
import re
from dataclasses import dataclass, field

from mypal.db.models import ChunkKind
from mypal.ingestion.document import Block, ParsedDocument, section_number

DEFAULT_MAX_WORDS = 250
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ChunkDraft:
    ordinal: int
    kind: ChunkKind
    text: str
    heading_path: list[str]
    section_ref: str | None
    page_start: int | None
    page_end: int | None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class _Heading:
    level: int
    text: str


@dataclass
class _Builder:
    max_words: int
    chunks: list[ChunkDraft] = field(default_factory=list)
    headings: list[_Heading] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    words: int = 0

    def enter_heading(self, block: Block) -> None:
        self.flush()
        level = block.level or 1
        while self.headings and self.headings[-1].level >= level:
            self.headings.pop()
        self.headings.append(_Heading(level, block.text))

    def add_text(self, text: str, page: int | None) -> None:
        for piece in _split_long_text(text, self.max_words):
            piece_words = len(piece.split())
            if self.parts and self.words + piece_words > self.max_words:
                self.flush()
            self.parts.append(piece)
            self.words += piece_words
            if page is not None:
                self.pages.append(page)

    def add_table(self, block: Block) -> None:
        self.flush()
        rows = list(block.rows or ())
        if not rows:
            return
        header, body = rows[0], rows[1:] or []
        piece: list[tuple[str, ...]] = []
        for row in body:
            candidate = [header, *piece, row]
            if piece and _word_count(_render_table(candidate)) > self.max_words:
                self._emit(ChunkKind.TABLE, _render_table([header, *piece]), [block.page])
                piece = []
            piece.append(row)
        self._emit(ChunkKind.TABLE, _render_table([header, *piece]), [block.page])

    def flush(self) -> None:
        if self.parts:
            self._emit(ChunkKind.TEXT, "\n".join(self.parts), self.pages)
        self.parts, self.pages, self.words = [], [], 0

    def _emit(self, kind: ChunkKind, text: str, pages: list[int | None]) -> None:
        known_pages = [p for p in pages if p is not None]
        self.chunks.append(
            ChunkDraft(
                ordinal=len(self.chunks),
                kind=kind,
                text=text,
                heading_path=[h.text for h in self.headings],
                section_ref=_deepest_section_number(self.headings),
                page_start=min(known_pages) if known_pages else None,
                page_end=max(known_pages) if known_pages else None,
            )
        )


def chunk_document(
    document: ParsedDocument, max_words: int = DEFAULT_MAX_WORDS
) -> list[ChunkDraft]:
    builder = _Builder(max_words=max_words)
    for block in document.blocks:
        if block.kind == "heading":
            builder.enter_heading(block)
        elif block.kind == "table":
            builder.add_table(block)
        elif block.kind == "list_item":
            builder.add_text(f"- {block.text}", block.page)
        else:
            builder.add_text(block.text, block.page)
    builder.flush()
    return builder.chunks


def _deepest_section_number(headings: list[_Heading]) -> str | None:
    for heading in reversed(headings):
        number = section_number(heading.text)
        if number:
            return number
    return None


def _split_long_text(text: str, max_words: int) -> list[str]:
    """Split text longer than the budget at sentence boundaries (never mid-sentence unless a
    single sentence is itself longer than the budget)."""
    if _word_count(text) <= max_words:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        if current and _word_count(" ".join([*current, sentence])) > max_words:
            pieces.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        pieces.append(" ".join(current))
    return pieces


def _render_table(rows: list[tuple[str, ...]]) -> str:
    """Markdown-style rows: readable by people in the preview and by the language model."""
    lines = [" | ".join(rows[0]), " | ".join("---" for _ in rows[0])]
    lines.extend(" | ".join(row) for row in rows[1:])
    return "\n".join(lines)


def _word_count(text: str) -> int:
    return len(text.split())
