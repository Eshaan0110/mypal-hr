"""Storing drafts: everything is written together, nothing is published, bad uploads leave no
trace."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mypal.db.models import AuditEvent, Chunk, PolicyVersion, PolicyVersionStatus
from mypal.errors import AppError
from mypal.ingestion.demo_reference import seed_demo_reference_data
from mypal.ingestion.errors import DocumentRejected, IngestionConflict
from mypal.ingestion.schemas import DraftMetadata, ScopeInput
from mypal.ingestion.service import store_draft
from tests.ingestion.builders import image_only_pdf_bytes, pdf_bytes

POLICY = pdf_bytes(
    [("h1", "1. Purpose"), ("p", "Why."), ("h1", "2. Rules"), ("p", "Eight days of leave.")]
)


def _metadata(**overrides: object) -> DraftMetadata:
    values: dict[str, object] = {
        "policy_key": "leave-policy",
        "title": "Leave Policy",
        "owner": "HR Ops (fictional)",
        "version_label": "v1",
        "uploaded_by": "uploader@example.test",
        "scopes": [
            ScopeInput(company_code="DEMO-HEALTH"),
            ScopeInput(company_code="DEMO-HEALTH", location_code="DEMO-NORTH"),
        ],
    }
    values.update(overrides)
    return DraftMetadata(**values)


@pytest.fixture
def session(db_session: Session) -> Session:
    seed_demo_reference_data(db_session)
    return db_session


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_stores_draft_with_scopes_chunks_report_and_audit(session: Session) -> None:
    version, result = store_draft(session, _metadata(), "C:\\Users\\hr\\leave.pdf", POLICY)

    assert version.status is PolicyVersionStatus.DRAFT
    assert version.approved_by is None and version.published_at is None
    assert version.source_filename == "leave.pdf"  # client directory stripped
    assert version.parse_report == result.report
    assert {(s.company_code, s.location_code) for s in version.scopes} == {
        ("DEMO-HEALTH", None),
        ("DEMO-HEALTH", "DEMO-NORTH"),
    }
    session.refresh(version)
    assert [c.section_ref for c in version.chunks] == ["1", "2"]

    audit = session.scalars(select(AuditEvent)).one()
    assert audit.action == "policy_version.upload"
    assert audit.entity_id == str(version.id)
    assert audit.actor_id == "uploader@example.test"


def test_same_file_cannot_be_uploaded_twice(session: Session) -> None:
    store_draft(session, _metadata(), "leave.pdf", POLICY)

    with pytest.raises(IngestionConflict, match="already uploaded as version 'v1'"):
        store_draft(session, _metadata(version_label="v2"), "copy.pdf", POLICY)


def test_version_label_must_be_new(session: Session) -> None:
    store_draft(session, _metadata(), "leave.pdf", POLICY)
    other_file = pdf_bytes([("h1", "1. Purpose"), ("p", "Changed.")])

    with pytest.raises(IngestionConflict, match="Version 'v1'"):
        store_draft(session, _metadata(), "leave-new.pdf", other_file)


def test_policy_key_cannot_be_reused_for_a_different_title(session: Session) -> None:
    store_draft(session, _metadata(), "leave.pdf", POLICY)
    other_file = pdf_bytes([("h1", "1. Purpose"), ("p", "Other.")])

    with pytest.raises(IngestionConflict, match="already exists with the title"):
        store_draft(
            session, _metadata(title="Travel Policy", version_label="v2"), "t.pdf", other_file
        )


def test_unknown_scope_code_is_rejected_before_anything_is_written(session: Session) -> None:
    with pytest.raises(AppError) as excinfo:
        store_draft(
            session,
            _metadata(scopes=[ScopeInput(company_code="DEMO-HEALTH", location_code="NOWHERE")]),
            "leave.pdf",
            POLICY,
        )

    assert excinfo.value.code == "unknown_scope_code"
    assert _count(session, PolicyVersion) == 0


def test_scanned_document_is_rejected_and_nothing_is_stored(session: Session) -> None:
    with pytest.raises(DocumentRejected, match="No readable text"):
        store_draft(session, _metadata(), "scan.pdf", image_only_pdf_bytes())

    assert _count(session, PolicyVersion) == 0
    assert _count(session, Chunk) == 0
    assert _count(session, AuditEvent) == 0
