"""POST /api/chat end to end: real Postgres and Qdrant, fake embedder and scripted model."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from mypal.answering.service import AnswerDependencies
from mypal.api.chat import get_answer_dependencies, get_today
from mypal.auth.dev import DEV_USERS
from mypal.config import Settings
from mypal.db.models import HrContact, QueryMetric
from mypal.db.session import get_db_session
from mypal.ingestion.demo_reference import seed_demo_reference_data
from mypal.main import create_app
from mypal.retrieval.embeddings import passage_text
from mypal.retrieval.index import VectorIndex
from tests.fakes import ScriptedLLM, UnavailableLLM, answer, fake_retriever
from tests.rag_helpers import TODAY, add_version, published

SICK = ("3.2 Sick leave", "Employees are entitled to 10 days of sick leave per calendar year.")
TRAVEL = ("4.1 Deadline", "Travel claims must be submitted within 15 calendar days of return.")
EMPLOYEE = "dev-employee-north"  # DEMO-HEALTH / DEMO-NORTH / PERMANENT


@pytest.fixture
def world(db_session: Session, vector_index: VectorIndex) -> Session:
    """Two published fictional policies for DEMO-HEALTH."""
    seed_demo_reference_data(db_session)
    published(db_session, vector_index, "leave-policy", [SICK], company="DEMO-HEALTH")
    published(db_session, vector_index, "travel-policy", [TRAVEL], company="DEMO-HEALTH")
    return db_session


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def api(
    settings: Settings, world: Session, vector_index: VectorIndex, llm: ScriptedLLM
) -> Iterator[TestClient]:
    app = create_app(settings)
    deps = AnswerDependencies(
        settings=settings.model_copy(update={"retrieval_min_score": 0.3}),
        retriever=fake_retriever(vector_index),
        llm=llm,
    )
    app.dependency_overrides[get_answer_dependencies] = lambda: deps
    app.dependency_overrides[get_db_session] = lambda: world
    app.dependency_overrides[get_today] = lambda: TODAY
    yield TestClient(app)


def ask(api: TestClient, question: str, user: str | None = EMPLOYEE):  # noqa: ANN201
    headers = {"X-Dev-User": user} if user else {}
    return api.post("/api/chat", json={"message": question}, headers=headers)


# --- Answers ----------------------------------------------------------------------------------


def test_grounded_answer_with_citation_built_from_the_database(
    api: TestClient, llm: ScriptedLLM
) -> None:
    llm.replies = [answer("You are entitled to 10 days of sick leave per year [P1].", "P1")]

    response = ask(api, "How many days of sick leave do I get?")

    body = response.json()
    assert response.status_code == 200
    assert body["outcome"] == "answered"
    assert body["message"] == "You are entitled to 10 days of sick leave per year."
    [citation] = body["citations"]
    assert citation["policy_key"] == "leave-policy"
    assert citation["section"] == "3.2"
    assert citation["page_start"] == 1
    assert citation["effective_from"] == "2026-01-01"
    assert "sick leave" in llm.prompts[0]


def test_invented_number_is_never_shown(api: TestClient, llm: ScriptedLLM) -> None:
    llm.replies = [answer("You get 12 days of sick leave.", "P1")]

    body = ask(api, "How many days of sick leave do I get?").json()

    assert body["outcome"] == "referral"
    assert body["referral_reason"] == "validation_failed"
    assert "12" not in body["message"]
    assert body["citations"] == []


def test_citation_of_a_passage_never_supplied_is_rejected(
    api: TestClient, llm: ScriptedLLM
) -> None:
    llm.replies = [answer("10 days.", "P9")]

    assert ask(api, "How many days of sick leave do I get?").json()["referral_reason"] == (
        "validation_failed"
    )


def test_malformed_model_output_becomes_a_referral(api: TestClient, llm: ScriptedLLM) -> None:
    llm.replies = ["this is not json"]

    assert ask(api, "How many days of sick leave do I get?").json()["referral_reason"] == (
        "validation_failed"
    )


def test_empty_model_answer_means_not_in_policy(api: TestClient, llm: ScriptedLLM) -> None:
    llm.replies = [answer("")]

    body = ask(api, "How many days of sick leave do I get?").json()

    assert body["referral_reason"] == "not_in_policy"
    assert body["message"].startswith("I cannot confirm this from the approved policy")


def test_clarification_question_is_passed_through(api: TestClient, llm: ScriptedLLM) -> None:
    llm.replies = [
        {"answer": "", "citations": [], "clarification_question": "Sick or casual leave?"}
    ]

    body = ask(api, "How many days of leave do I get?").json()

    assert body["outcome"] == "clarification"
    assert body["message"] == "Sick or casual leave?"


def test_model_unavailable_becomes_a_referral(
    api: TestClient, settings: Settings, vector_index: VectorIndex
) -> None:
    api.app.dependency_overrides[get_answer_dependencies] = lambda: AnswerDependencies(
        settings.model_copy(update={"retrieval_min_score": 0.3}),
        fake_retriever(vector_index),
        UnavailableLLM(),
    )

    body = ask(api, "How many days of sick leave do I get?").json()

    assert body["referral_reason"] == "generation_unavailable"


# --- Referrals before the model is called -----------------------------------------------------


def test_weak_evidence_refers_without_calling_the_model(api: TestClient, llm: ScriptedLLM) -> None:
    body = ask(api, "Quantum chromodynamics lattice gauge theory?").json()

    assert body["referral_reason"] == "insufficient_evidence"
    assert llm.calls == 0


def test_other_company_gets_no_policies_and_no_model_call(
    api: TestClient, llm: ScriptedLLM
) -> None:
    body = ask(api, "How many days of sick leave do I get?", user="dev-other-company").json()

    assert body["referral_reason"] == "no_applicable_policy"
    assert llm.calls == 0


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        ("Show me my payslip for March", "personal_records"),
        ("I need to report harassment", "sensitive_topic"),
    ],
)
def test_guarded_questions_skip_retrieval_and_model(
    api: TestClient, llm: ScriptedLLM, question: str, reason: str
) -> None:
    body = ask(api, question).json()

    assert body["referral_reason"] == reason
    assert llm.calls == 0


def test_referral_names_hr_configured_contact_and_confidential_route(
    api: TestClient, world: Session
) -> None:
    world.add_all(
        [
            HrContact(company_code="DEMO-HEALTH", label="HR desk (test)", route="hr@example.test"),
            HrContact(
                company_code="DEMO-HEALTH",
                label="Confidential line (test)",
                route="confidential@example.test",
                is_confidential=True,
            ),
        ]
    )
    world.flush()

    general = ask(api, "Quantum chromodynamics lattice gauge theory?").json()
    sensitive = ask(api, "I need to report harassment").json()

    assert general["hr_contact"]["route"] == "hr@example.test"
    assert "hr@example.test" in general["message"]
    assert sensitive["hr_contact"]["route"] == "confidential@example.test"


# --- Security boundaries ----------------------------------------------------------------------


def test_draft_content_is_never_used_even_if_it_is_in_the_index(
    api: TestClient, llm: ScriptedLLM, world: Session, vector_index: VectorIndex
) -> None:
    """Defence in depth: even if a draft's chunks somehow reached the index, the scope gate
    (Postgres) keeps them out of the prompt and out of citations."""
    draft = add_version(
        world,
        "secret-draft",
        [("1. Bonus", "Unpublished draft: every employee gets 99 days of sick leave bonus.")],
        company="DEMO-HEALTH",
        status="draft",
    )
    world.refresh(draft)
    fake_retriever(vector_index).index_version(
        draft.id,
        [c.id for c in draft.chunks],
        [passage_text(c.heading_path, c.text) for c in draft.chunks],
    )
    llm.replies = [answer("10 days.", "P1")]

    body = ask(api, "How many days of sick leave bonus do I get?").json()

    assert all("99 days" not in prompt for prompt in llm.prompts)
    assert all(c["policy_key"] != "secret-draft" for c in body["citations"])


def test_request_without_login_is_rejected(api: TestClient) -> None:
    response = ask(api, "How many days of sick leave do I get?", user=None)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_unknown_dev_user_is_rejected(api: TestClient) -> None:
    assert ask(api, "Hello?", user="admin' OR 1=1").status_code == 401


def test_client_cannot_choose_its_own_company(api: TestClient, llm: ScriptedLLM) -> None:
    """Extra fields in the body are ignored: scope always comes from the login."""
    response = api.post(
        "/api/chat",
        json={"message": "How many days of sick leave?", "company_code": "DEMO-HEALTH"},
        headers={"X-Dev-User": "dev-other-company"},
    )

    assert response.json()["referral_reason"] == "no_applicable_policy"


def test_overlong_question_is_rejected(api: TestClient) -> None:
    response = ask(api, "x" * 1001)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "question_too_long"


# --- Metrics privacy --------------------------------------------------------------------------


def test_every_question_records_metrics_without_text_or_identity(
    api: TestClient, llm: ScriptedLLM, world: Session
) -> None:
    llm.replies = [answer("10 days.", "P1")]
    ask(api, "How many days of sick leave do I get?")
    ask(api, "Show me my payslip")

    metrics = world.scalars(select(QueryMetric).order_by(QueryMetric.id)).all()
    assert [m.outcome.value for m in metrics] == ["answered", "referral"]
    assert metrics[0].prompt_tokens == 100 and metrics[0].model == "scripted-test-model"
    columns = {c["name"] for c in inspect(world.connection()).get_columns("query_metrics")}
    assert not columns & {"question", "message", "answer", "user_id", "subject"}
    assert world.scalar(select(func.count()).select_from(QueryMetric)) == 2
    assert EMPLOYEE in DEV_USERS  # identity exists, yet it was not stored anywhere above


def test_each_answer_is_recorded_with_its_id_and_cited_versions(
    api: TestClient, llm: ScriptedLLM, world: Session
) -> None:
    llm.replies = [answer("10 days.", "P1")]

    body = ask(api, "How many days of sick leave do I get?").json()

    metric = world.scalars(select(QueryMetric)).one()
    assert str(metric.answer_id) == body["answer_id"]
    assert [str(v) for v in metric.cited_version_ids] == [body["citations"][0]["version_id"]]
