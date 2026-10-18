"""POST /api/feedback, GET /api/me and GET /api/dev/users."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from mypal.config import Settings
from mypal.db.models import AnswerOutcome, Feedback, FeedbackRating, QueryMetric
from mypal.db.session import get_db_session
from mypal.main import create_app
from tests.factories import assert_violates

HEADERS = {"X-Dev-User": "dev-employee-north"}
CITED = uuid.uuid4()


@pytest.fixture
def api(settings: Settings, db_session: Session) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_db_session] = lambda: db_session
    yield TestClient(app)


@pytest.fixture
def answer_id(db_session: Session) -> uuid.UUID:
    """An answer the server really gave (as recorded by the chat pipeline)."""
    metric = QueryMetric(
        request_id="test",
        answer_id=uuid.uuid4(),
        cited_version_ids=[CITED],
        outcome=AnswerOutcome.ANSWERED,
        total_ms=10,
    )
    db_session.add(metric)
    db_session.flush()
    return metric.answer_id


def post(api: TestClient, body: dict, headers: dict | None = HEADERS):  # noqa: ANN201
    return api.post("/api/feedback", json=body, headers=headers or {})


# --- Feedback ---------------------------------------------------------------------------------


def test_feedback_takes_outcome_and_citations_from_the_server_record(
    api: TestClient, answer_id: uuid.UUID, db_session: Session
) -> None:
    response = post(api, {"answer_id": str(answer_id), "rating": "helpful"})

    assert response.status_code == 200
    feedback = db_session.scalars(select(Feedback)).one()
    assert feedback.rating is FeedbackRating.HELPFUL
    assert feedback.outcome is AnswerOutcome.ANSWERED
    assert feedback.cited_version_ids == [CITED]


def test_feedback_for_an_answer_that_never_happened_is_rejected(api: TestClient) -> None:
    response = post(api, {"answer_id": str(uuid.uuid4()), "rating": "helpful"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_answer"


def test_second_rating_replaces_the_first(
    api: TestClient, answer_id: uuid.UUID, db_session: Session
) -> None:
    post(api, {"answer_id": str(answer_id), "rating": "helpful"})
    post(api, {"answer_id": str(answer_id), "rating": "not_helpful", "reason_code": "outdated"})

    [feedback] = db_session.scalars(select(Feedback)).all()
    assert (feedback.rating, feedback.reason_code) == (FeedbackRating.NOT_HELPFUL, "outdated")


def test_reason_is_dropped_for_helpful_ratings(
    api: TestClient, answer_id: uuid.UUID, db_session: Session
) -> None:
    post(api, {"answer_id": str(answer_id), "rating": "helpful", "reason_code": "unclear"})

    assert db_session.scalars(select(Feedback)).one().reason_code is None


@pytest.mark.parametrize(
    "extra",
    [
        {"reason_code": "my manager is wrong about my case"},  # free text is not a reason code
        {"comment": "I asked about my divorce"},  # unknown fields are rejected, not ignored
        {"question": "How many sick days?"},
    ],
)
def test_feedback_cannot_carry_free_text(
    api: TestClient, answer_id: uuid.UUID, extra: dict
) -> None:
    response = post(api, {"answer_id": str(answer_id), "rating": "not_helpful", **extra})

    assert response.status_code == 422


def test_feedback_requires_login(api: TestClient, answer_id: uuid.UUID) -> None:
    response = post(api, {"answer_id": str(answer_id), "rating": "helpful"}, headers=None)

    assert response.status_code == 401


def test_database_rejects_a_reason_on_a_helpful_rating(db_session: Session) -> None:
    row = Feedback(
        answer_id=uuid.uuid4(),
        rating=FeedbackRating.HELPFUL,
        reason_code="outdated",
        outcome=AnswerOutcome.ANSWERED,
    )

    assert_violates(db_session, "ck_feedback_reason_only_for_not_helpful", row)


# --- Identity ---------------------------------------------------------------------------------


def test_me_returns_the_logged_in_users_scope_attributes(api: TestClient) -> None:
    body = api.get("/api/me", headers=HEADERS).json()

    assert body == {
        "subject": "dev-employee-north",
        "company_code": "DEMO-HEALTH",
        "location_code": "DEMO-NORTH",
        "category_code": "PERMANENT",
        "is_development_login": True,
    }


def test_me_requires_login(api: TestClient) -> None:
    assert api.get("/api/me").status_code == 401


def test_dev_users_lists_the_fictional_test_users(api: TestClient) -> None:
    subjects = {u["subject"] for u in api.get("/api/dev/users").json()}

    assert {"dev-employee-north", "dev-other-company"} <= subjects
