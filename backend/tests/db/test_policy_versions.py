"""Lifecycle rules for policy versions, enforced by the database itself (not just app code)."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mypal.db.models import PolicyVersionStatus as Status
from tests.factories import (
    REVIEWER,
    UPLOADER,
    assert_violates,
    build_version,
    make_policy,
    make_version,
)


def test_draft_version_needs_only_basic_fields(db_session: Session) -> None:
    version = make_version(db_session, make_policy(db_session))

    assert version.status is Status.DRAFT
    assert version.approved_by is None


def test_second_active_version_of_same_policy_is_rejected(db_session: Session) -> None:
    policy = make_policy(db_session)
    make_version(db_session, policy, label="v1", status=Status.ACTIVE)

    second = build_version(policy, label="v2", status=Status.ACTIVE)

    assert_violates(db_session, "uq_policy_versions_one_active", second)


def test_different_policies_can_each_have_an_active_version(db_session: Session) -> None:
    make_version(db_session, make_policy(db_session, "policy-a"), status=Status.ACTIVE)
    make_version(db_session, make_policy(db_session, "policy-b"), status=Status.ACTIVE)


def test_policy_replacement_supersedes_old_version(db_session: Session) -> None:
    """The worked replacement from the plan: v1 active -> v1 superseded, v2 active."""
    policy = make_policy(db_session)
    v1 = make_version(db_session, policy, label="v1", status=Status.ACTIVE)
    v2 = make_version(db_session, policy, label="v2", status=Status.APPROVED)

    # Order matters: retire v1 first, or the one-active index rejects the change.
    v1.status = Status.SUPERSEDED
    db_session.flush()
    v2.status = Status.ACTIVE
    v2.published_at = datetime.now(UTC)
    v2.supersedes_version_id = v1.id
    db_session.flush()

    db_session.refresh(policy)
    assert {v.version_label: v.status for v in policy.versions} == {
        "v1": Status.SUPERSEDED,
        "v2": Status.ACTIVE,
    }


def test_uploader_cannot_approve_own_version(db_session: Session) -> None:
    version = build_version(make_policy(db_session), status=Status.APPROVED, approved_by=UPLOADER)

    assert_violates(db_session, "ck_policy_versions_four_eyes", version)


def test_approved_status_requires_an_approver(db_session: Session) -> None:
    version = build_version(make_policy(db_session), status=Status.APPROVED)
    version.approved_by = None
    version.approved_at = None

    assert_violates(db_session, "ck_policy_versions_approved_states_have_approver", version)


def test_approver_and_approval_time_go_together(db_session: Session) -> None:
    version = build_version(make_policy(db_session), approved_by=REVIEWER, approved_at=None)

    assert_violates(db_session, "ck_policy_versions_approval_fields_together", version)


def test_version_in_review_needs_an_effective_date(db_session: Session) -> None:
    version = build_version(make_policy(db_session), status=Status.IN_REVIEW, effective_from=None)

    assert_violates(db_session, "ck_policy_versions_reviewed_states_have_effective_date", version)


def test_active_version_needs_a_publish_time(db_session: Session) -> None:
    version = build_version(make_policy(db_session), status=Status.ACTIVE, published_at=None)

    assert_violates(db_session, "ck_policy_versions_published_states_have_published_at", version)


def test_version_cannot_supersede_a_version_of_another_policy(db_session: Session) -> None:
    other = make_version(db_session, make_policy(db_session, "other-policy"))
    version = build_version(make_policy(db_session), supersedes_version_id=other.id)

    assert_violates(db_session, "fk_policy_versions_supersedes_same_policy", version)


def test_unknown_status_value_is_rejected(db_session: Session) -> None:
    # Effective date set, so the unknown status is the only rule this row breaks.
    version = make_version(db_session, make_policy(db_session), effective_from=date(2026, 1, 1))
    # Raw SQL, bypassing the Python enum, to prove the database itself refuses the value.
    statement = text("UPDATE policy_versions SET status = 'published' WHERE id = :id")

    with pytest.raises(IntegrityError, match="ck_policy_versions_status"):
        db_session.execute(statement, {"id": version.id})


def test_duplicate_version_label_is_rejected(db_session: Session) -> None:
    policy = make_policy(db_session)
    make_version(db_session, policy, label="v1")

    assert_violates(db_session, "uq_policy_versions_label", build_version(policy, label="v1"))
