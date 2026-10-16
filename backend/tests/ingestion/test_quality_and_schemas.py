import pytest
from pydantic import ValidationError

from mypal.ingestion.schemas import DraftMetadata, ScopeInput
from mypal.ingestion.service import parse_file
from tests.ingestion.builders import image_only_pdf_bytes, pdf_bytes

# --- Quality report ---------------------------------------------------------------------------


def test_clean_document_needs_no_review() -> None:
    report = parse_file(pdf_bytes([("h1", "1. Purpose"), ("p", "Text.")]), "a.pdf").report

    assert report["needs_manual_review"] is False
    assert report["blocking"] is False
    assert report["chunk_count"] == 1


def test_fully_scanned_document_is_blocked() -> None:
    report = parse_file(image_only_pdf_bytes(pages=2), "scan.pdf").report

    assert report["blocking"] is True
    codes = {i["code"] for i in report["issues"]}
    assert {"no_text", "page_without_text_layer"} <= codes


def test_document_without_headings_needs_review() -> None:
    report = parse_file(pdf_bytes([("p", "Only body text here.")]), "a.pdf").report

    assert report["needs_manual_review"] is True
    assert "no_headings_detected" in {i["code"] for i in report["issues"]}


# --- Metadata validation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("DEMO", ScopeInput(company_code="DEMO")),
        ("DEMO:NORTH", ScopeInput(company_code="DEMO", location_code="NORTH")),
        ("DEMO:*:TRAINEE", ScopeInput(company_code="DEMO", category_code="TRAINEE")),
    ],
)
def test_scope_shorthand_is_parsed(value: str, expected: ScopeInput) -> None:
    assert ScopeInput.parse(value) == expected


def _metadata(**overrides: object) -> DraftMetadata:
    values: dict[str, object] = {
        "policy_key": "leave-policy",
        "title": "Leave Policy",
        "owner": "HR Ops",
        "version_label": "v1",
        "uploaded_by": "uploader@example.test",
        "scopes": [ScopeInput(company_code="DEMO")],
    }
    values.update(overrides)
    return DraftMetadata(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"policy_key": "Leave Policy"},  # not a slug
        {"version_label": "v 1"},
        {"source_link": "javascript:alert(1)"},  # only http(s) links
        {"scopes": []},  # a version must apply to someone
        {"scopes": [ScopeInput(company_code="DEMO")] * 2},
        {"uploaded_by": "   "},
    ],
)
def test_invalid_metadata_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _metadata(**overrides)


def test_valid_metadata_is_accepted() -> None:
    metadata = _metadata(source_link="https://intranet.example.test/policies/leave")

    assert str(metadata.source_link) == "https://intranet.example.test/policies/leave"
