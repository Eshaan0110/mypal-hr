"""Ingestion use cases: preview a file without storing it, and store it as a draft version.

store_draft() writes the version, its scopes, its chunks and an audit event in the caller's
transaction - either all of it is saved or none of it. The caller commits.
"""

import hashlib
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mypal.db.models import (
    AuditEvent,
    Chunk,
    Company,
    EmployeeCategory,
    Location,
    Policy,
    PolicyVersion,
    PolicyVersionScope,
    PolicyVersionStatus,
)
from mypal.errors import AppError
from mypal.ingestion.chunker import ChunkDraft, chunk_document
from mypal.ingestion.document import Issue, ParsedDocument
from mypal.ingestion.docx_parser import parse_docx
from mypal.ingestion.errors import DocumentRejected, IngestionConflict
from mypal.ingestion.file_checks import detect_format
from mypal.ingestion.pdf_parser import parse_pdf
from mypal.ingestion.quality import assess, build_report
from mypal.ingestion.schemas import DraftMetadata, ScopeInput


@dataclass
class ParseResult:
    document: ParsedDocument
    chunks: list[ChunkDraft]
    issues: list[Issue]
    report: dict[str, Any]


def parse_file(content: bytes, filename: str) -> ParseResult:
    """Parse, chunk and assess a file. Pure function: touches no database."""
    file_format = detect_format(content, filename)
    document = parse_pdf(content) if file_format == "pdf" else parse_docx(content)
    chunks = chunk_document(document)
    issues = assess(document, chunks)
    return ParseResult(document, chunks, issues, build_report(document, chunks, issues))


def store_draft(
    session: Session,
    metadata: DraftMetadata,
    filename: str,
    content: bytes,
    request_id: str | None = None,
) -> tuple[PolicyVersion, ParseResult]:
    result = parse_file(content, filename)
    if result.report["blocking"]:
        reasons = "; ".join(i.message for i in result.issues if i.severity == "blocking")
        raise DocumentRejected(f"The document cannot be ingested: {reasons}")

    _check_scope_codes_exist(session, metadata.scopes)
    policy = _get_or_create_policy(session, metadata)
    sha256 = hashlib.sha256(content).hexdigest()
    _check_not_duplicate(session, policy, metadata.version_label, sha256)

    version = PolicyVersion(
        policy_id=policy.id,
        version_label=metadata.version_label,
        status=PolicyVersionStatus.DRAFT,
        effective_from=metadata.effective_from,
        source_link=str(metadata.source_link) if metadata.source_link else None,
        # Only the base name: never store a client's local directory structure.
        source_filename=PurePath(filename).name,
        source_sha256=sha256,
        parse_report=result.report,
        created_by=metadata.uploaded_by,
    )
    session.add(version)
    session.flush()  # assigns version.id

    session.add_all(
        PolicyVersionScope(
            version_id=version.id,
            company_code=scope.company_code,
            location_code=scope.location_code,
            category_code=scope.category_code,
        )
        for scope in metadata.scopes
    )
    session.add_all(
        Chunk(
            version_id=version.id,
            ordinal=draft.ordinal,
            kind=draft.kind,
            text=draft.text,
            heading_path=draft.heading_path,
            section_ref=draft.section_ref,
            page_start=draft.page_start,
            page_end=draft.page_end,
            content_hash=draft.content_hash,
        )
        for draft in result.chunks
    )
    session.add(
        AuditEvent(
            actor_id=metadata.uploaded_by,
            action="policy_version.upload",
            entity_type="policy_version",
            entity_id=str(version.id),
            after={
                "policy_key": policy.policy_key,
                "version_label": version.version_label,
                "status": version.status.value,
                "source_filename": version.source_filename,
                "source_sha256": sha256,
                "chunk_count": len(result.chunks),
                "needs_manual_review": result.report["needs_manual_review"],
            },
            request_id=request_id,
        )
    )
    session.flush()
    return version, result


def _get_or_create_policy(session: Session, metadata: DraftMetadata) -> Policy:
    policy = session.scalar(select(Policy).where(Policy.policy_key == metadata.policy_key))
    if policy is None:
        policy = Policy(policy_key=metadata.policy_key, title=metadata.title, owner=metadata.owner)
        session.add(policy)
        session.flush()
    elif policy.title != metadata.title:
        raise IngestionConflict(
            f"Policy '{policy.policy_key}' already exists with the title '{policy.title}'. "
            "Use the same title, or a different policy key for a different policy."
        )
    return policy


def _check_not_duplicate(session: Session, policy: Policy, label: str, sha256: str) -> None:
    existing = session.scalars(
        select(PolicyVersion).where(PolicyVersion.policy_id == policy.id)
    ).all()
    if any(v.version_label == label for v in existing):
        raise IngestionConflict(f"Version '{label}' of '{policy.policy_key}' already exists.")
    same_file = next((v for v in existing if v.source_sha256 == sha256), None)
    if same_file is not None:
        raise IngestionConflict(
            f"This exact file was already uploaded as version '{same_file.version_label}'."
        )


def _check_scope_codes_exist(session: Session, scopes: list[ScopeInput]) -> None:
    """Friendly error before the database's foreign keys would reject the codes anyway."""
    wanted = {
        Company: {s.company_code for s in scopes},
        Location: {s.location_code for s in scopes if s.location_code},
        EmployeeCategory: {s.category_code for s in scopes if s.category_code},
    }
    missing: list[str] = []
    for model, codes in wanted.items():
        if not codes:
            continue
        found = set(session.scalars(select(model.code).where(model.code.in_(codes))))
        missing += [f"{model.__tablename__}:{code}" for code in sorted(codes - found)]
    if missing:
        raise AppError(
            f"Unknown scope code(s): {', '.join(missing)}.",
            code="unknown_scope_code",
            status_code=422,
        )
