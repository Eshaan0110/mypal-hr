"""Lifecycle transitions: draft -> in_review -> approved -> active (-> superseded).

Each transition checks its preconditions, changes the status, and writes an audit event, all in
the caller's transaction. The database constraints (one active version per policy, four-eyes,
required fields per status) remain the final safety net if a check here were ever missed.

Publishing order matters for safety:
1. index the new version's chunks in Qdrant (harmless on its own: retrieval only searches
   versions Postgres says are active, and this one is not active yet);
2. in one database transaction, mark the old active version superseded and the new one active.
If step 2 fails, employees keep getting the old version. Superseded points stay in the index so a
rollback (Phase 7) does not need re-embedding; the scope filter already excludes them.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mypal.db.models import AuditEvent, Chunk, PolicyVersion, PolicyVersionStatus
from mypal.errors import AppError
from mypal.retrieval.embeddings import passage_text
from mypal.retrieval.retriever import Retriever

Status = PolicyVersionStatus


class LifecycleError(AppError):
    status_code = 409
    code = "invalid_lifecycle_transition"


def submit_for_review(
    session: Session, version_id: uuid.UUID, actor: str, request_id: str | None = None
) -> PolicyVersion:
    version = _load(session, version_id)
    _require_status(version, Status.DRAFT, "submitted for review")
    if version.effective_from is None:
        raise LifecycleError("Set an effective date before submitting the version for review.")
    if (version.parse_report or {}).get("blocking"):
        raise LifecycleError("The document has blocking quality issues and cannot be reviewed.")
    return _transition(session, version, Status.IN_REVIEW, actor, "submit", request_id)


def approve(
    session: Session, version_id: uuid.UUID, actor: str, request_id: str | None = None
) -> PolicyVersion:
    version = _load(session, version_id)
    _require_status(version, Status.IN_REVIEW, "approved")
    if actor == version.created_by:
        raise LifecycleError(
            "The person who uploaded a version cannot approve it (four-eyes rule).",
            code="four_eyes_violation",
        )
    version.approved_by = actor
    version.approved_at = datetime.now(UTC)
    return _transition(session, version, Status.APPROVED, actor, "approve", request_id)


def publish(
    session: Session,
    version_id: uuid.UUID,
    actor: str,
    retriever: Retriever,
    today: date,
    request_id: str | None = None,
) -> PolicyVersion:
    version = _load(session, version_id)
    _require_status(version, Status.APPROVED, "published")
    if version.effective_from is None or version.effective_from > today:
        raise LifecycleError(
            "Only versions already in effect can be published. Scheduling future versions is "
            "not supported in the prototype."
        )

    # Step 1: index (outside the database transaction's critical section).
    chunks = list(
        session.scalars(select(Chunk).where(Chunk.version_id == version.id).order_by(Chunk.ordinal))
    )
    if not chunks:
        raise LifecycleError("The version has no chunks to publish.")
    retriever.index_version(
        version.id, [c.id for c in chunks], [passage_text(c.heading_path, c.text) for c in chunks]
    )

    # Step 2: switch which version is active.
    previous = session.scalar(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == version.policy_id,
            PolicyVersion.status == Status.ACTIVE,
        )
    )
    if previous is not None:
        _transition(session, previous, Status.SUPERSEDED, actor, "supersede", request_id)
        session.flush()  # free the "one active version" slot before activating the new one
        version.supersedes_version_id = previous.id
    version.published_at = datetime.now(UTC)
    return _transition(session, version, Status.ACTIVE, actor, "publish", request_id)


def _load(session: Session, version_id: uuid.UUID) -> PolicyVersion:
    version = session.get(PolicyVersion, version_id, with_for_update=True)
    if version is None:
        raise AppError(f"Policy version {version_id} not found.", code="not_found", status_code=404)
    return version


def _require_status(version: PolicyVersion, expected: Status, action: str) -> None:
    if version.status is not expected:
        raise LifecycleError(
            f"Version {version.version_label} is {version.status.value}; only a "
            f"{expected.value} version can be {action}."
        )


def _transition(
    session: Session,
    version: PolicyVersion,
    new_status: Status,
    actor: str,
    action: str,
    request_id: str | None,
) -> PolicyVersion:
    old_status = version.status
    version.status = new_status
    session.add(
        AuditEvent(
            actor_id=actor,
            action=f"policy_version.{action}",
            entity_type="policy_version",
            entity_id=str(version.id),
            before={"status": old_status.value},
            after={"status": new_status.value},
            request_id=request_id,
        )
    )
    session.flush()
    return version
