"""The scope gate and publishing: who can see which version, and how versions become visible."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from mypal.auth.principal import Principal
from mypal.db.models import AuditEvent, PolicyVersionStatus
from mypal.policies import lifecycle
from mypal.policies.lifecycle import LifecycleError
from mypal.retrieval.index import VectorIndex
from mypal.retrieval.scope import allowed_version_ids
from tests.factories import REVIEWER, UPLOADER
from tests.fakes import fake_retriever
from tests.rag_helpers import TODAY, add_version, published, seed_reference

Status = PolicyVersionStatus
TEXT = [("1. Rules", "Employees get ten days of leave.")]


def person(
    company: str = "CO-A", location: str | None = "NORTH", category: str | None = "PERMANENT"
):  # noqa: ANN201
    return Principal("someone", company, location, category)


@pytest.fixture
def session(db_session: Session) -> Session:
    seed_reference(db_session)
    return db_session


# --- Scope gate -------------------------------------------------------------------------------


def test_only_active_versions_are_visible(session: Session, vector_index: VectorIndex) -> None:
    active = published(session, vector_index, "active-policy", TEXT)
    draft = add_version(session, "draft-policy", TEXT, status=Status.DRAFT)
    approved = add_version(session, "approved-policy", TEXT, status=Status.APPROVED)

    visible = allowed_version_ids(session, person(), TODAY)

    assert active.id in visible
    assert draft.id not in visible
    assert approved.id not in visible


def test_superseded_version_disappears_when_replacement_is_published(
    session: Session, vector_index: VectorIndex
) -> None:
    v1 = published(session, vector_index, "leave", TEXT, label="v1")
    v2 = published(session, vector_index, "leave", TEXT, label="v2")

    assert allowed_version_ids(session, person(), TODAY) == [v2.id]
    assert v1.status is Status.SUPERSEDED


def test_other_company_sees_nothing(session: Session, vector_index: VectorIndex) -> None:
    published(session, vector_index, "co-a-policy", TEXT, company="CO-A")

    assert allowed_version_ids(session, person(company="CO-B"), TODAY) == []


def test_location_and_category_scopes(session: Session, vector_index: VectorIndex) -> None:
    north = published(session, vector_index, "north-only", TEXT, location="NORTH")
    trainee = published(session, vector_index, "trainee-only", TEXT, category="TRAINEE")
    everyone = published(session, vector_index, "everyone", TEXT)

    assert set(allowed_version_ids(session, person("CO-A", "NORTH", "PERMANENT"), TODAY)) == {
        north.id,
        everyone.id,
    }
    assert set(allowed_version_ids(session, person("CO-A", "SOUTH", "TRAINEE"), TODAY)) == {
        trainee.id,
        everyone.id,
    }


def test_unknown_location_only_unlocks_all_location_policies(
    session: Session, vector_index: VectorIndex
) -> None:
    published(session, vector_index, "north-only", TEXT, location="NORTH")
    everyone = published(session, vector_index, "everyone", TEXT)

    assert allowed_version_ids(session, person(location=None), TODAY) == [everyone.id]


def test_version_not_yet_in_effect_is_not_visible(
    session: Session, vector_index: VectorIndex
) -> None:
    version = published(session, vector_index, "policy", TEXT)

    assert allowed_version_ids(session, person(), date(2025, 12, 31)) == []
    assert allowed_version_ids(session, person(), TODAY) == [version.id]


# --- Lifecycle --------------------------------------------------------------------------------


def test_full_lifecycle_writes_an_audit_trail(session: Session, vector_index: VectorIndex) -> None:
    version = add_version(session, "policy", TEXT, status=Status.DRAFT)

    lifecycle.submit_for_review(session, version.id, UPLOADER)
    lifecycle.approve(session, version.id, REVIEWER)
    lifecycle.publish(session, version.id, REVIEWER, fake_retriever(vector_index), TODAY)

    assert version.status is Status.ACTIVE
    actions = session.scalars(
        select(AuditEvent.action)
        .where(AuditEvent.entity_id == str(version.id))
        .order_by(AuditEvent.id)
    ).all()
    assert actions == [
        "policy_version.submit",
        "policy_version.approve",
        "policy_version.publish",
    ]
    assert vector_index.count() == 1


def test_uploader_cannot_approve_their_own_version(session: Session) -> None:
    version = add_version(session, "policy", TEXT, status=Status.IN_REVIEW)

    with pytest.raises(LifecycleError) as excinfo:
        lifecycle.approve(session, version.id, UPLOADER)
    assert excinfo.value.code == "four_eyes_violation"


def test_draft_cannot_be_published(session: Session, vector_index: VectorIndex) -> None:
    version = add_version(session, "policy", TEXT, status=Status.DRAFT)

    with pytest.raises(LifecycleError, match="only a approved version"):
        lifecycle.publish(session, version.id, REVIEWER, fake_retriever(vector_index), TODAY)
    assert vector_index._client.collection_exists(vector_index.collection) is False


def test_future_version_cannot_be_published_yet(
    session: Session, vector_index: VectorIndex
) -> None:
    version = add_version(session, "policy", TEXT, effective_from=date(2026, 12, 1))

    with pytest.raises(LifecycleError, match="already in effect"):
        lifecycle.publish(session, version.id, REVIEWER, fake_retriever(vector_index), TODAY)


def test_replacement_links_to_and_supersedes_previous_version(
    session: Session, vector_index: VectorIndex
) -> None:
    v1 = published(session, vector_index, "leave", TEXT, label="v1")
    v2 = published(session, vector_index, "leave", [("1. Rules", "Now twelve days.")], label="v2")

    assert (v1.status, v2.status) == (Status.SUPERSEDED, Status.ACTIVE)
    assert v2.supersedes_version_id == v1.id
    # Superseded points stay indexed (ready for rollback) but the scope gate excludes them.
    assert vector_index.count() == 2
