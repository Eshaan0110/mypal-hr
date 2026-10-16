"""Checks applied to the raw file before any parser touches it.

The format is decided from the file's content (its "magic bytes"), not its name: a file renamed
from .exe to .pdf is still rejected.
"""

import io
import zipfile
from typing import Literal

from mypal.ingestion.errors import DocumentRejected

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB is far above any normal policy document
MAX_DOCX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # guards against "zip bomb" DOCX files

DocumentFormat = Literal["pdf", "docx"]


def detect_format(content: bytes, filename: str) -> DocumentFormat:
    if not content:
        raise DocumentRejected("The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise DocumentRejected(
            f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.", code="file_too_large"
        )

    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"PK\x03\x04") and _is_docx(content):
        return "docx"

    name = filename.lower()
    if name.endswith(".doc"):
        raise DocumentRejected(
            "Legacy .doc files are not supported. Save the policy as .docx or PDF.",
            code="unsupported_format",
        )
    raise DocumentRejected(
        "Only PDF and Word (.docx) policy documents are supported.", code="unsupported_format"
    )


def _is_docx(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                return False
            uncompressed = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile:
        return False
    if uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
        raise DocumentRejected(
            "The Word document expands to an unexpectedly large size.", code="file_too_large"
        )
    return True
