"""Read-only views of the policy register for HR administrators.

Unlike chat retrieval, these views include every status (drafts, rejected, superseded): HR needs
to see and review content that employees must not see. Access is restricted by the API layer.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mypal.db.models import (
    AuditEvent,
    Company,
    EmployeeCategory,
    Location,
    Policy,
    PolicyVersion,
)
from mypal.errors import AppError
from mypal.schemas.admin import (
    AuditEntry,
    ChunkPreview,
    PolicySummary,
    ReferenceCode,
    ReferenceData,
    ScopeOut,
    VersionDetail,
    VersionSummary,
)


def list_policies(session: Session) -> list[PolicySummary]:
    policies = session.scalars(
        select(Policy).options(selectinload(Policy.versions)).order_by(Policy.title)
    ).all()
    return [
        PolicySummary(
            policy_key=p.policy_key,
            title=p.title,
            owner=p.owner,
            versions=[
                _summary(v) for v in sorted(p.versions, key=lambda v: v.created_at, reverse=True)
            ],
        )
        for p in policies
    ]


def version_detail(session: Session, version_id: uuid.UUID) -> VersionDetail:
    version = session.scalar(
        select(PolicyVersion)
        .where(PolicyVersion.id == version_id)
        .options(
            selectinload(PolicyVersion.policy),
            selectinload(PolicyVersion.scopes),
            selectinload(PolicyVersion.chunks),
        )
    )
    if version is None:
        raise AppError(f"Policy version {version_id} not found.", code="not_found", status_code=404)
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_type == "policy_version", AuditEvent.entity_id == str(version.id))
        .order_by(AuditEvent.occurred_at, AuditEvent.id)
    ).all()
    return VersionDetail(
        **_summary(version).model_dump(),
        policy_key=version.policy.policy_key,
        policy_title=version.policy.title,
        policy_owner=version.policy.owner,
        source_link=version.source_link,
        supersedes_version_id=version.supersedes_version_id,
        scopes=[
            ScopeOut(
                company_code=s.company_code,
                location_code=s.location_code,
                category_code=s.category_code,
            )
            for s in version.scopes
        ],
        parse_report=version.parse_report,
        chunks=[
            ChunkPreview(
                ordinal=c.ordinal,
                kind=c.kind,
                heading_path=list(c.heading_path),
                section_ref=c.section_ref,
                page_start=c.page_start,
                page_end=c.page_end,
                text=c.text,
            )
            for c in version.chunks
        ],
        history=[
            AuditEntry(
                occurred_at=e.occurred_at,
                actor_id=e.actor_id,
                action=e.action,
                before=e.before,
                after=e.after,
            )
            for e in events
        ],
    )


def reference_data(session: Session) -> ReferenceData:
    def codes(model) -> list[ReferenceCode]:  # noqa: ANN001
        rows = session.scalars(select(model).order_by(model.code)).all()
        return [ReferenceCode(code=r.code, name=r.name) for r in rows]

    return ReferenceData(
        companies=codes(Company), locations=codes(Location), categories=codes(EmployeeCategory)
    )


def _summary(version: PolicyVersion) -> VersionSummary:
    return VersionSummary(
        id=version.id,
        version_label=version.version_label,
        status=version.status,
        effective_from=version.effective_from,
        source_filename=version.source_filename,
        created_by=version.created_by,
        created_at=version.created_at,
        approved_by=version.approved_by,
        published_at=version.published_at,
    )
