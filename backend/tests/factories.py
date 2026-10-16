"""Small helpers that build valid rows, so each test only spells out what it is checking.
All values are obviously fictional test data - not real companies or policies."""

import hashlib
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from mypal.db.models import (
    Chunk,
    Company,
    Policy,
    PolicyVersion,
    PolicyVersionStatus,
)

UPLOADER = "test-uploader@example.test"
REVIEWER = "test-reviewer@example.test"


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def make_company(session: Session, code: str = "TESTCO") -> Company:
    company = Company(code=code, name=f"Test company {code}")
    session.add(company)
    session.flush()
    return company


def make_policy(session: Session, key: str = "test-leave-policy") -> Policy:
    policy = Policy(policy_key=key, title=f"Test policy {key}", owner="Test HR owner")
    session.add(policy)
    session.flush()
    return policy


def build_version(
    policy: Policy,
    *,
    label: str = "v1",
    status: PolicyVersionStatus = PolicyVersionStatus.DRAFT,
    approved_by: str | None = None,
    **fields: object,
) -> PolicyVersion:
    """An unsaved version in any status, with exactly the fields that status requires."""
    reviewed = status not in (PolicyVersionStatus.DRAFT, PolicyVersionStatus.REJECTED)
    approved = status in (
        PolicyVersionStatus.APPROVED,
        PolicyVersionStatus.ACTIVE,
        PolicyVersionStatus.SUPERSEDED,
    )
    published = status in (PolicyVersionStatus.ACTIVE, PolicyVersionStatus.SUPERSEDED)
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "policy_id": policy.id,
        "version_label": label,
        "status": status,
        "source_filename": f"{policy.policy_key}-{label}.pdf",
        "source_sha256": sha256(f"{policy.policy_key}-{label}"),
        "created_by": UPLOADER,
        "effective_from": date(2026, 1, 1) if reviewed else None,
        "approved_by": approved_by or (REVIEWER if approved else None),
        "approved_at": now if (approved_by or approved) else None,
        "published_at": now if published else None,
    }
    values.update(fields)
    return PolicyVersion(**values)


def make_version(session: Session, policy: Policy, **kwargs: object) -> PolicyVersion:
    version = build_version(policy, **kwargs)  # type: ignore[arg-type]
    session.add(version)
    session.flush()
    return version


def build_chunk(version: PolicyVersion, ordinal: int = 0, **fields: object) -> Chunk:
    text = str(fields.pop("text", f"Test passage {ordinal}"))
    return Chunk(
        version_id=version.id,
        ordinal=ordinal,
        text=text,
        content_hash=sha256(text),
        **fields,
    )


def make_chunk(session: Session, version: PolicyVersion, **kwargs: object) -> Chunk:
    chunk = build_chunk(version, **kwargs)  # type: ignore[arg-type]
    session.add(chunk)
    session.flush()
    return chunk


def assert_violates(session: Session, constraint: str, row: object | None = None) -> None:
    """Assert that flushing pending changes is rejected by the named database constraint."""
    if row is not None:
        session.add(row)
    with pytest.raises((IntegrityError, ProgrammingError)) as excinfo:
        session.flush()
    session.rollback()
    assert constraint in str(excinfo.value.orig), excinfo.value.orig
