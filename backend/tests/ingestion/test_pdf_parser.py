import pytest

from mypal.ingestion.errors import DocumentRejected
from mypal.ingestion.pdf_parser import parse_pdf
from tests.ingestion.builders import blank_pdf_bytes, image_only_pdf_bytes, pdf_bytes

LONG = (
    "Employees are entitled to eight days of casual leave in each calendar year, which may "
    "not be carried forward and may not exceed three consecutive working days at a time."
)


def _kinds(document) -> list[tuple[str, str]]:  # noqa: ANN001
    return [(b.kind, b.text) for b in document.blocks]


def test_headings_get_levels_from_section_numbers() -> None:
    document = parse_pdf(
        pdf_bytes([("h1", "3. Types of leave"), ("h2", "3.1 Casual leave"), ("p", "Body.")])
    )

    headings = [(b.text, b.level) for b in document.blocks if b.kind == "heading"]
    assert headings == [("3. Types of leave", 1), ("3.1 Casual leave", 2)]


def test_unnumbered_headings_get_levels_from_font_size() -> None:
    document = parse_pdf(pdf_bytes([("h1", "Purpose"), ("h2", "Background"), ("p", "Body.")]))

    headings = [(b.text, b.level) for b in document.blocks if b.kind == "heading"]
    assert headings == [("Purpose", 1), ("Background", 2)]


def test_wrapped_lines_are_joined_into_one_paragraph() -> None:
    document = parse_pdf(pdf_bytes([("h1", "1. Leave"), ("p", LONG), ("p", "Second para.")]))

    paragraphs = [b.text for b in document.blocks if b.kind == "paragraph"]
    assert paragraphs == [LONG, "Second para."]


def test_bullets_become_list_items_without_the_glyph() -> None:
    document = parse_pdf(pdf_bytes([("h1", "1. Steps"), ("li", ["Apply in the portal.", LONG])]))

    items = [b.text for b in document.blocks if b.kind == "list_item"]
    assert items == ["Apply in the portal.", LONG]
    assert not any("cid:" in b.text for b in document.blocks)


def test_tables_are_extracted_once_and_not_repeated_as_paragraphs() -> None:
    rows = [["Grade", "Metro"], ["Grade A", "INR 4,000"], ["Grade B", "INR 3,000"]]
    document = parse_pdf(pdf_bytes([("h1", "2. Allowance"), ("table", rows), ("p", "After.")]))

    tables = [b for b in document.blocks if b.kind == "table"]
    assert len(tables) == 1
    assert tables[0].rows == (
        ("Grade", "Metro"),
        ("Grade A", "INR 4,000"),
        ("Grade B", "INR 3,000"),
    )
    assert not any("INR 4,000" in b.text for b in document.blocks if b.kind != "table")
    assert [b.kind for b in document.blocks] == ["heading", "table", "paragraph"]


def test_page_numbers_follow_the_content() -> None:
    document = parse_pdf(
        pdf_bytes(
            [
                ("h1", "1. First"),
                ("p", "On page one."),
                ("pagebreak", None),
                ("h1", "2. Second"),
                ("p", "On page two."),
            ]
        )
    )

    assert document.page_count == 2
    assert {b.text: b.page for b in document.blocks} == {
        "1. First": 1,
        "On page one.": 1,
        "2. Second": 2,
        "On page two.": 2,
    }


def test_running_footer_is_removed() -> None:
    document = parse_pdf(
        pdf_bytes(
            [("h1", "1. A"), ("p", "One."), ("pagebreak", None), ("h1", "2. B"), ("p", "Two.")],
            footer="Company confidential",
        )
    )

    assert not any("confidential" in b.text.lower() for b in document.blocks)


def test_scanned_page_is_flagged_for_manual_review() -> None:
    document = parse_pdf(image_only_pdf_bytes())

    assert document.blocks == []
    assert [(i.severity, i.code, i.page) for i in document.issues] == [
        ("warning", "page_without_text_layer", 1)
    ]


def test_blank_page_is_only_informational() -> None:
    document = parse_pdf(blank_pdf_bytes())

    assert [(i.severity, i.code) for i in document.issues] == [("info", "empty_page")]


def test_password_protected_pdf_is_rejected() -> None:
    with pytest.raises(DocumentRejected, match="password-protected"):
        parse_pdf(pdf_bytes([("p", "Secret")], encrypt="secret"))
