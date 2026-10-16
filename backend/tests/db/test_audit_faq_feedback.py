import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import InternalError, ProgrammingError
from sqlalchemy.orm import Session

from mypal.db.models import (
    AnswerOutcome,
    AuditEvent,
    Faq,
    FaqStatus,
    Feedback,
    FeedbackRating,
)
from tests.factories import REVIEWER, UPLOADER, assert_violates, make_policy, make_version

# --- Audit trail ------------------------------------------------------------------------------


def _audit_event(db_session: Session) -> AuditEvent:
    event = AuditEvent(
        actor_id=UPLOADER,
        action="policy_version.upload",
        entity_type="policy_version",
        entity_id=str(uuid.uuid4()),
        after={"status": "draft"},
    )
    db_session.add(event)
    db_session.flush()
    return event


def test_audit_events_can_be_appended(db_session: Session) -> None:
    event = _audit_event(db_session)

    assert event.id is not None
    assert event.occurred_at is not None


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET actor_id = 'someone-else'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
)
def test_audit_events_cannot_be_changed_or_removed(db_session: Session, statement: str) -> None:
    _audit_event(db_session)

    with pytest.raises((InternalError, ProgrammingError), match="append-only"):
        db_session.execute(text(statement))


# --- FAQs -------------------------------------------------------------------------------------


def _faq(db_session: Session, **fields: object) -> Faq:
    version = make_version(db_session, make_policy(db_session))
    values: dict[str, object] = {
        "question": "Test question?",
        "answer": "Test answer.",
        "source_version_id": version.id,
        "created_by": UPLOADER,
    }
    values.update(fields)
    return Faq(**values)


def test_faq_author_cannot_approve_it(db_session: Session) -> None:
    faq = _faq(db_session, approved_by=UPLOADER, approved_at=text("now()"))

    assert_violates(db_session, "ck_faqs_four_eyes", faq)


def test_active_faq_requires_approval(db_session: Session) -> None:
    faq = _faq(db_session, status=FaqStatus.ACTIVE)

    assert_violates(db_session, "ck_faqs_active_has_approver", faq)


def test_approved_faq_can_be_active(db_session: Session) -> None:
    faq = _faq(db_session, status=FaqStatus.ACTIVE, approved_by=REVIEWER, approved_at=text("now()"))
    db_session.add(faq)
    db_session.flush()


# --- Feedback privacy -------------------------------------------------------------------------


def test_feedback_table_stores_no_text_or_identity(db_session: Session) -> None:
    """Privacy decision: feedback never stores question/answer text or who gave it. If someone
    adds such a column, this test fails and forces a deliberate review."""
    columns = {c["name"] for c in inspect(db_session.connection()).get_columns("feedback")}

    assert columns == {
        "id",
        "answer_id",
        "rating",
        "reason_code",
        "outcome",
        "cited_version_ids",
        "created_at",
    }


def test_feedback_records_rating_and_cited_versions(db_session: Session) -> None:
    version_id = uuid.uuid4()
    feedback = Feedback(
        answer_id=uuid.uuid4(),
        rating=FeedbackRating.NOT_HELPFUL,
        reason_code="outdated",
        outcome=AnswerOutcome.ANSWERED,
        cited_version_ids=[version_id],
    )
    db_session.add(feedback)
    db_session.flush()
    db_session.refresh(feedback)

    assert feedback.cited_version_ids == [version_id]
