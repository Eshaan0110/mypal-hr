"""Turn parser findings into a review report that HR sees before approving a draft.

The report is stored with the draft (policy_versions.parse_report), so the reviewer and the audit
trail can always see what the system was unsure about.
"""

from collections import Counter
from dataclasses import asdict
from typing import Any

from mypal.ingestion.chunker import ChunkDraft
from mypal.ingestion.document import Issue, ParsedDocument

REPORT_VERSION = 1


def assess(document: ParsedDocument, chunks: list[ChunkDraft]) -> list[Issue]:
    """Whole-document checks, added to the per-page issues the parser already found."""
    issues = list(document.issues)
    if not chunks:
        issues.append(
            Issue(
                "blocking",
                "no_text",
                "No readable text was found. If this is a scanned document it needs OCR or a "
                "text-based version before it can be ingested.",
            )
        )
        return issues

    if not any(block.kind == "heading" for block in document.blocks):
        issues.append(
            Issue(
                "warning",
                "no_headings_detected",
                "No section headings were detected, so citations cannot point to sections. "
                "Check the chunk preview; the document may need heading styles.",
            )
        )
    scanned_pages = [i.page for i in issues if i.code == "page_without_text_layer"]
    if scanned_pages:
        issues.append(
            Issue(
                "warning",
                "partially_scanned",
                f"{len(scanned_pages)} page(s) have no text layer. Their content is missing "
                "from the chunks below.",
            )
        )
    return issues


def build_report(
    document: ParsedDocument, chunks: list[ChunkDraft], issues: list[Issue]
) -> dict[str, Any]:
    """JSON-serialisable summary stored on the policy version."""
    severities = {issue.severity for issue in issues}
    return {
        "report_version": REPORT_VERSION,
        "format": document.format,
        "page_count": document.page_count,
        "block_counts": dict(Counter(block.kind for block in document.blocks)),
        "chunk_count": len(chunks),
        "table_chunk_count": sum(chunk.kind == "table" for chunk in chunks),
        "issues": [asdict(issue) for issue in issues],
        "needs_manual_review": bool(severities & {"warning", "blocking"}),
        "blocking": "blocking" in severities,
    }
