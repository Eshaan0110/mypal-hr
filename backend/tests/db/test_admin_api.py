"""HR administration API end to end: real Postgres and Qdrant, fake embedder, scripted model.

Covers the Phase 7 acceptance criterion: an authorised development user can complete the policy
lifecycle (upload -> preview -> review -> approve -> publish -> replace -> restore) without draft
content ever reaching normal chat retrieval.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mypal.answering.service import AnswerDependencies
from mypal.api.admin import get_retriever
from mypal.api.chat import get_answer_dependencies, get_today
from mypal.config import Settings
from mypal.db.session import get_db_session
from mypal.ingestion.demo_reference import seed_demo_reference_data
from mypal.main import create_app
from mypal.retrieval.index import VectorIndex
from tests.fakes import ScriptedLLM, answer, fake_retriever
from tests.ingestion.builders import docx_bytes
from tests.rag_helpers import TODAY

ADMIN, REVIEWER, EMPLOYEE = "dev-hr-admin", "dev-hr-reviewer", "dev-employee-north"
QUESTION = "How many sick leave days do I get per year?"
V1 = [("h1", "3. Sick leave"), ("p", "Employees get 10 days of sick leave per year.")]
V2 = [("h1", "3. Sick leave"), ("p", "Employees get 12 days of sick leave per year.")]


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def api(
    settings: Settings, db_session: Session, vector_index: VectorIndex, llm: ScriptedLLM
) -> Iterator[TestClient]:
    seed_demo_reference_data(db_session)
    retriever = fake_retriever(vector_index)
    app = create_app(settings)
    deps = AnswerDependencies(
        settings=settings.model_copy(update={"retrieval_min_score": 0.3}),
        retriever=retriever,
        llm=llm,
    )
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[get_retriever] = lambda: retriever
    app.dependency_overrides[get_answer_dependencies] = lambda: deps
    app.dependency_overrides[get_today] = lambda: TODAY
    yield TestClient(app)


def as_user(user: str | None) -> dict[str, str]:
    return {"X-Dev-User": user} if user else {}


def upload(api: TestClient, spec=V1, label: str = "v1", user: str = ADMIN, **fields):  # noqa: ANN001, ANN201
    data = {
        "policy_key": "leave-policy",
        "title": "Leave Policy",
        "owner": "HR Operations (fictional)",
        "version_label": label,
        "effective_from": "2026-01-01",
        "scope": ["DEMO-HEALTH"],
        **fields,
    }
    files = {"file": (f"leave-{label}.docx", docx_bytes(spec), "application/octet-stream")}
    return api.post("/api/admin/versions", data=data, files=files, headers=as_user(user))


def act(api: TestClient, version_id: str, action: str, user: str, reason: str | None = None):  # noqa: ANN201
    body = {"reason": reason} if reason is not None else None
    return api.post(f"/api/admin/versions/{version_id}/{action}", json=body, headers=as_user(user))


def publish_via_api(api: TestClient, spec=V1, label: str = "v1") -> str:  # noqa: ANN001
    version_id = upload(api, spec, label).json()["id"]
    assert act(api, version_id, "submit", ADMIN).status_code == 200
    assert act(api, version_id, "approve", REVIEWER).status_code == 200
    assert act(api, version_id, "publish", REVIEWER).json()["status"] == "active"
    return version_id


def ask(api: TestClient, llm: ScriptedLLM, reply: str | None = None) -> dict:
    if reply is not None:
        llm.replies = [answer(reply, "P1")]
    return api.post("/api/chat", json={"message": QUESTION}, headers=as_user(EMPLOYEE)).json()


# --- Access control ---------------------------------------------------------------------------


@pytest.mark.parametrize(("user", "status"), [(None, 401), (EMPLOYEE, 403)])
def test_admin_api_is_restricted_to_hr_administrators(
    api: TestClient, user: str | None, status: int
) -> None:
    for response in (
        api.get("/api/admin/policies", headers=as_user(user)),
        upload(api, user=user),  # type: ignore[arg-type]
    ):
        assert response.status_code == status


def test_identity_reports_roles_so_the_interface_can_offer_admin_screens(api: TestClient) -> None:
    assert api.get("/api/me", headers=as_user(ADMIN)).json()["roles"] == ["hr_admin"]
    assert api.get("/api/me", headers=as_user(EMPLOYEE)).json()["roles"] == []


# --- Upload and preview -----------------------------------------------------------------------


def test_upload_creates_a_draft_with_preview_and_the_uploader_from_the_login(
    api: TestClient,
) -> None:
    response = upload(api)

    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "draft"
    assert body["created_by"] == ADMIN  # from the login; the form cannot set it
    assert body["scopes"] == [
        {"company_code": "DEMO-HEALTH", "location_code": None, "category_code": None}
    ]
    assert any("10 days of sick leave" in chunk["text"] for chunk in body["chunks"])
    assert body["parse_report"]["blocking"] is False
    assert [h["action"] for h in body["history"]] == ["policy_version.upload"]

    listed = api.get("/api/admin/policies", headers=as_user(ADMIN)).json()
    assert listed[0]["policy_key"] == "leave-policy"
    assert listed[0]["versions"][0]["status"] == "draft"


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"scope": ["NO-SUCH-COMPANY"]}, "unknown_scope_code"),
        ({"policy_key": "Leave Policy!"}, "validation_error"),
        ({"scope": ["DEMO-HEALTH:A:B:C"]}, "validation_error"),
    ],
)
def test_invalid_upload_metadata_is_rejected(api: TestClient, fields: dict, code: str) -> None:
    response = upload(api, **fields)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_a_file_that_is_not_a_policy_document_is_rejected(api: TestClient) -> None:
    response = api.post(
        "/api/admin/versions",
        data={
            "policy_key": "leave-policy",
            "title": "Leave Policy",
            "owner": "HR",
            "version_label": "v1",
            "effective_from": "2026-01-01",
            "scope": ["DEMO-HEALTH"],
        },
        files={"file": ("policy.pdf", b"MZ\x90\x00 not really a pdf", "application/pdf")},
        headers=as_user(ADMIN),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_format"


# --- Lifecycle --------------------------------------------------------------------------------


def test_full_lifecycle_with_four_eyes_and_drafts_hidden_from_chat(
    api: TestClient, llm: ScriptedLLM
) -> None:
    version_id = upload(api).json()["id"]

    # A draft is invisible to employees: no applicable policy, the model is never called.
    assert ask(api, llm)["referral_reason"] == "no_applicable_policy"
    assert act(api, version_id, "submit", ADMIN).json()["status"] == "in_review"
    assert ask(api, llm)["referral_reason"] == "no_applicable_policy"  # in review: still hidden

    own = act(api, version_id, "approve", ADMIN)
    assert own.status_code == 409
    assert own.json()["error"]["code"] == "four_eyes_violation"

    approved = act(api, version_id, "approve", REVIEWER).json()
    assert (approved["status"], approved["approved_by"]) == ("approved", REVIEWER)
    assert ask(api, llm)["referral_reason"] == "no_applicable_policy"  # approved, not published
    assert llm.calls == 0

    assert act(api, version_id, "publish", REVIEWER).json()["status"] == "active"
    body = ask(api, llm, "You get 10 days of sick leave per year.")
    assert body["outcome"] == "answered"
    assert body["citations"][0]["version_id"] == version_id

    history = act(api, version_id, "publish", REVIEWER)  # already active: refused
    assert history.status_code == 409
    actions = [
        h["action"]
        for h in api.get(f"/api/admin/versions/{version_id}", headers=as_user(ADMIN)).json()[
            "history"
        ]
    ]
    assert actions == [
        "policy_version.upload",
        "policy_version.submit",
        "policy_version.approve",
        "policy_version.publish",
    ]


def test_replacement_supersedes_the_old_version_and_restore_rolls_it_back(
    api: TestClient, llm: ScriptedLLM
) -> None:
    v1 = publish_via_api(api, V1, "v1")
    v2 = publish_via_api(api, V2, "v2")

    def status(version_id: str) -> str:
        return api.get(f"/api/admin/versions/{version_id}", headers=as_user(ADMIN)).json()["status"]

    assert (status(v1), status(v2)) == ("superseded", "active")
    assert ask(api, llm, "You get 12 days.")["citations"][0]["version_id"] == v2

    # Rollback: v2 turned out to be wrong.
    assert act(api, v1, "restore", ADMIN, reason="no").status_code == 422  # needs a reason
    restored = act(api, v1, "restore", ADMIN, reason="v2 has the wrong number of days")
    assert restored.json()["status"] == "active"
    assert status(v2) == "superseded"
    assert ask(api, llm, "You get 10 days.")["citations"][0]["version_id"] == v1

    last = restored.json()["history"][-1]
    assert last["action"] == "policy_version.restore"
    assert last["actor_id"] == ADMIN
    assert last["after"]["reason"] == "v2 has the wrong number of days"


def test_only_a_superseded_version_can_be_restored(api: TestClient) -> None:
    active = publish_via_api(api)

    response = act(api, active, "restore", ADMIN, reason="trying to restore the active one")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_lifecycle_transition"


def test_rejection_needs_another_reviewer_and_a_reason(api: TestClient) -> None:
    version_id = upload(api).json()["id"]
    act(api, version_id, "submit", ADMIN)

    assert act(api, version_id, "reject", ADMIN, reason="my own upload").status_code == 409
    assert act(api, version_id, "reject", REVIEWER, reason="no").status_code == 422
    rejected = act(api, version_id, "reject", REVIEWER, reason="Wrong effective date")

    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["history"][-1]["after"]["reason"] == "Wrong effective date"
    assert act(api, version_id, "approve", REVIEWER).status_code == 409  # rejected is final


def test_unknown_version_is_not_found(api: TestClient) -> None:
    response = api.get(
        "/api/admin/versions/00000000-0000-0000-0000-000000000000", headers=as_user(ADMIN)
    )

    assert response.status_code == 404
