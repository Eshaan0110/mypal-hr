from mypal.db.models import ChunkKind
from mypal.ingestion.chunker import chunk_document
from mypal.ingestion.document import Block, ParsedDocument


def _doc(*blocks: Block) -> ParsedDocument:
    return ParsedDocument(format="pdf", page_count=3, blocks=list(blocks))


def h(text: str, level: int, page: int = 1) -> Block:
    return Block("heading", text, page, level=level)


def p(text: str, page: int = 1) -> Block:
    return Block("paragraph", text, page)


def test_each_section_becomes_its_own_chunk_with_heading_path() -> None:
    chunks = chunk_document(
        _doc(
            h("3. Types of leave", 1),
            h("3.1 Casual leave", 2),
            p("Eight days."),
            h("3.2 Sick leave", 2),
            p("Ten days."),
            h("4. Applying", 1),
            p("Use the portal."),
        )
    )

    assert [(c.heading_path, c.section_ref, c.text) for c in chunks] == [
        (["3. Types of leave", "3.1 Casual leave"], "3.1", "Eight days."),
        (["3. Types of leave", "3.2 Sick leave"], "3.2", "Ten days."),
        (["4. Applying"], "4", "Use the portal."),
    ]
    assert [c.ordinal for c in chunks] == [0, 1, 2]


def test_text_before_first_heading_has_an_empty_path() -> None:
    chunks = chunk_document(_doc(p("Preamble."), h("1. Purpose", 1), p("Body.")))

    assert chunks[0].heading_path == []
    assert chunks[0].section_ref is None


def test_unnumbered_subheading_inherits_parent_section_number() -> None:
    chunks = chunk_document(_doc(h("5. Exceptions", 1), h("Approval", 2), p("HR Head.")))

    assert chunks[0].section_ref == "5"


def test_list_items_are_kept_together_with_markers() -> None:
    chunks = chunk_document(
        _doc(h("4. Steps", 1), Block("list_item", "Apply.", 1), Block("list_item", "Wait.", 1))
    )

    assert chunks[0].text == "- Apply.\n- Wait."


def test_long_section_is_split_at_sentence_boundaries_within_budget() -> None:
    sentence = "Employees must follow this rule carefully every single time. "
    long_text = sentence * 30  # about 270 words

    chunks = chunk_document(_doc(h("2. Rules", 1), p(long_text.strip())), max_words=100)

    assert len(chunks) >= 3
    assert all(c.word_count <= 100 for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)  # never cut mid-sentence
    assert all(c.heading_path == ["2. Rules"] for c in chunks)


def test_page_range_covers_all_merged_paragraphs() -> None:
    chunks = chunk_document(_doc(h("1. A", 1), p("Start.", page=1), p("End.", page=2)))

    assert (chunks[0].page_start, chunks[0].page_end) == (1, 2)


def test_tables_are_separate_chunks_and_split_with_repeated_header() -> None:
    rows = (("Grade", "Amount"), *((f"Grade {i}", f"INR {i}000") for i in range(30)))
    chunks = chunk_document(
        _doc(h("2. Allowance", 1), p("See table."), Block("table", "", 2, rows=rows)),
        max_words=40,
    )

    tables = [c for c in chunks if c.kind is ChunkKind.TABLE]
    assert chunks[0].kind is ChunkKind.TEXT
    assert len(tables) > 1
    assert all(t.text.startswith("Grade | Amount\n--- | ---") for t in tables)
    assert sum(t.text.count("INR") for t in tables) == 30  # no row lost or duplicated
    assert all(t.section_ref == "2" and t.page_start == 2 for t in tables)


def test_content_hash_is_deterministic() -> None:
    first = chunk_document(_doc(h("1. A", 1), p("Same text.")))
    second = chunk_document(_doc(h("1. A", 1), p("Same text.")))

    assert first[0].content_hash == second[0].content_hash
    assert len(first[0].content_hash) == 64
