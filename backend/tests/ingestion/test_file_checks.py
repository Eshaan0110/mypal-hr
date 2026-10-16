import io
import zipfile

import pytest

from mypal.ingestion import file_checks
from mypal.ingestion.errors import DocumentRejected
from mypal.ingestion.file_checks import detect_format
from tests.ingestion.builders import docx_bytes, pdf_bytes


def test_pdf_and_docx_are_recognised_by_content() -> None:
    assert detect_format(pdf_bytes([("p", "Hello")]), "policy.pdf") == "pdf"
    assert detect_format(docx_bytes([("p", "Hello")]), "policy.docx") == "docx"


def test_format_comes_from_content_not_file_name() -> None:
    # A real PDF with a misleading name is still a PDF ...
    assert detect_format(pdf_bytes([("p", "Hello")]), "policy.docx") == "pdf"
    # ... and a text file named .pdf is rejected.
    with pytest.raises(DocumentRejected) as excinfo:
        detect_format(b"just some text", "policy.pdf")
    assert excinfo.value.code == "unsupported_format"


def test_legacy_doc_gets_a_specific_message() -> None:
    with pytest.raises(DocumentRejected, match=r"\.doc files are not supported"):
        detect_format(b"\xd0\xcf\x11\xe0 old word format", "policy.doc")


def test_zip_that_is_not_a_word_document_is_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "not a policy")

    with pytest.raises(DocumentRejected):
        detect_format(buffer.getvalue(), "policy.docx")


def test_empty_file_is_rejected() -> None:
    with pytest.raises(DocumentRejected, match="empty"):
        detect_format(b"", "policy.pdf")


def test_oversized_file_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(file_checks, "MAX_FILE_BYTES", 10)

    with pytest.raises(DocumentRejected) as excinfo:
        detect_format(b"%PDF-" + b"x" * 20, "policy.pdf")
    assert excinfo.value.code == "file_too_large"
