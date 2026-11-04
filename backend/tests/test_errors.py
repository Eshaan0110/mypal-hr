"""The error envelope must be identical for every kind of failure."""

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from qdrant_client.http.exceptions import ResponseHandlingException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from mypal.config import Settings
from mypal.errors import AppError
from mypal.main import create_app

# Routes that exist only in tests, to trigger each error path.
probe = APIRouter(prefix="/api/_probe")


class EchoRequest(BaseModel):
    name: str = Field(min_length=1)


@probe.post("/echo")
def echo(body: EchoRequest) -> dict[str, str]:
    return {"name": body.name}


@probe.get("/app-error")
def app_error() -> None:
    raise AppError("Version is already active.", code="policy_conflict", status_code=409)


@probe.get("/crash")
def crash() -> None:
    raise RuntimeError("secret internal detail: postgres://user:pw@host")


@probe.get("/integrity")
def integrity() -> None:
    raise IntegrityError("INSERT ...", {}, Exception('duplicate key "uq_versions_label"'))


@probe.get("/pool-timeout")
def pool_timeout() -> None:
    raise PoolTimeoutError("QueuePool limit of size 20 overflow 20 reached")


@probe.get("/db-down")
def db_down() -> None:
    raise OperationalError("SELECT 1", {}, Exception("connection refused: postgres:5432"))


@probe.get("/search-down")
def search_down() -> None:
    raise ResponseHandlingException(Exception("Connection refused: qdrant:6333"))


@pytest.fixture
def probe_client(settings: Settings) -> TestClient:
    app = create_app(settings)
    app.include_router(probe)
    # Return 500 responses instead of re-raising, like a real server would.
    return TestClient(app, raise_server_exceptions=False)


def test_unknown_route_uses_envelope(probe_client: TestClient) -> None:
    response = probe_client.get("/api/does-not-exist")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_wrong_method_uses_envelope(probe_client: TestClient) -> None:
    response = probe_client.post("/api/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_app_error_keeps_its_code_and_status(probe_client: TestClient) -> None:
    response = probe_client.get("/api/_probe/app-error")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "policy_conflict"
    assert response.json()["error"]["message"] == "Version is already active."


def test_validation_error_lists_fields_without_echoing_input(probe_client: TestClient) -> None:
    response = probe_client.post("/api/_probe/echo", json={"name": "", "extra": "x"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["body", "name"]
    assert "input" not in error["details"][0]


def test_unexpected_error_hides_internal_details(probe_client: TestClient) -> None:
    response = probe_client.get("/api/_probe/crash")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "postgres" not in response.text
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


def test_concurrent_change_conflict_is_a_409_without_database_details(
    probe_client: TestClient,
) -> None:
    response = probe_client.get("/api/_probe/integrity")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert "uq_versions_label" not in response.text


def test_exhausted_connection_pool_is_a_503_with_retry_after(probe_client: TestClient) -> None:
    response = probe_client.get("/api/_probe/pool-timeout")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "server_busy"
    assert response.headers["Retry-After"] == "5"
    assert "QueuePool" not in response.text


@pytest.mark.parametrize(
    ("path", "code", "hidden"),
    [
        ("/api/_probe/db-down", "database_unavailable", "postgres:5432"),
        ("/api/_probe/search-down", "search_unavailable", "qdrant:6333"),
    ],
)
def test_unavailable_dependency_is_a_503_without_details(
    probe_client: TestClient, path: str, code: str, hidden: str
) -> None:
    response = probe_client.get(path)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == code
    assert "Retry-After" in response.headers
    assert hidden not in response.text
