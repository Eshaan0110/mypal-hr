import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mypal.config import Environment, Settings
from mypal.main import create_app
from tests.conftest import UNUSED_DATABASE_URL


def test_settings_are_read_from_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYPAL_ENVIRONMENT", "staging")
    monkeypatch.setenv("MYPAL_CORS_ORIGINS", '["http://localhost:5173"]')
    monkeypatch.setenv("MYPAL_DATABASE_URL", UNUSED_DATABASE_URL)

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.STAGING
    assert settings.cors_origins == ["http://localhost:5173"]


def test_invalid_settings_fail_fast() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=UNUSED_DATABASE_URL, environment="prod-ish")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=UNUSED_DATABASE_URL, log_level="LOUD")


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYPAL_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_database_password_is_hidden_in_repr() -> None:
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://u:hunter2@127.0.0.1/db")

    assert "hunter2" not in repr(settings)
    assert "hunter2" not in str(settings.model_dump())


def test_api_docs_are_disabled_in_production() -> None:
    settings = Settings(_env_file=None, environment="production", database_url=UNUSED_DATABASE_URL)
    client = TestClient(create_app(settings))

    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


def test_api_docs_are_available_outside_production(client: TestClient) -> None:
    assert client.get("/api/openapi.json").status_code == 200
