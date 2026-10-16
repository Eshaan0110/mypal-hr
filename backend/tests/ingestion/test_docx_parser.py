from mypal.ingestion.docx_parser import parse_docx
from tests.ingestion.builders import docx_bytes


def test_heading_styles_and_numbering_give_levels() -> None:
    document = parse_docx(
        docx_bytes(
            [
                ("title", "Travel Policy"),
                ("h1", "1. Purpose"),
                ("h2", "Background"),
                ("h1", "4. Claims"),
                ("h2", "4.1 Deadline"),
            ]
        )
    )

    assert [(b.text, b.level) for b in document.blocks] == [
        ("Travel Policy", 1),
        ("1. Purpose", 1),
        ("Background", 2),
        ("4. Claims", 1),
        ("4.1 Deadline", 2),
    ]


def test_body_order_lists_and_tables_are_preserved() -> None:
    rows = [["Grade", "Metro"], ["Grade A", "INR 4,000"]]
    document = parse_docx(
        docx_bytes(
            [("h1", "2. Allowance"), ("p", "Intro."), ("table", rows), ("li", ["One", "Two"])]
        )
    )

    assert [b.kind for b in document.blocks] == [
        "heading",
        "paragraph",
        "table",
        "list_item",
        "list_item",
    ]
    table = next(b for b in document.blocks if b.kind == "table")
    assert table.rows == (("Grade", "Metro"), ("Grade A", "INR 4,000"))


def test_bold_only_paragraph_is_treated_as_heading_and_reported() -> None:
    document = parse_docx(docx_bytes([("p", "Intro.")], bold_paragraphs=["5. Exceptions"]))

    assert document.blocks[-1].kind == "heading"
    assert document.blocks[-1].level == 1
    assert "headings_inferred" in {i.code for i in document.issues}


def test_footer_text_is_not_extracted_and_missing_pages_are_reported() -> None:
    document = parse_docx(docx_bytes([("p", "Body.")]))

    assert all("footer" not in b.text.lower() for b in document.blocks)
    assert all(b.page is None for b in document.blocks)
    assert "no_page_numbers" in {i.code for i in document.issues}
