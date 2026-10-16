from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from mypal.config import Settings
from mypal.main import create_app

# Nothing listens on port 1, so connections are refused immediately.
UNREACHABLE_DATABASE_URL = SecretStr("postgresql+psycopg://mypal:wrong@127.0.0.1:1/mypal_test")


def test_ready_when_database_answers(db_engine: Engine, client: TestClient) -> None:
    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_not_ready_when_database_is_unreachable(settings: Settings) -> None:
    broken = settings.model_copy(
        update={"database_url": UNREACHABLE_DATABASE_URL, "database_connect_timeout": 1}
    )

    response = TestClient(create_app(broken)).get("/api/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "127.0.0.1" not in response.text  # connection details stay in the server log


def test_liveness_does_not_depend_on_database(settings: Settings) -> None:
    broken = settings.model_copy(update={"database_url": UNREACHABLE_DATABASE_URL})

    assert TestClient(create_app(broken)).get("/api/health").status_code == 200
