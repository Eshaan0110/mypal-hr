import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mypal.config import Environment, Settings
from mypal.main import create_app


def test_settings_are_read_from_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYPAL_ENVIRONMENT", "staging")
    monkeypatch.setenv("MYPAL_CORS_ORIGINS", '["http://localhost:5173"]')

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.STAGING
    assert settings.cors_origins == ["http://localhost:5173"]


def test_invalid_settings_fail_fast() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="prod-ish")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="LOUD")


def test_api_docs_are_disabled_in_production() -> None:
    client = TestClient(create_app(Settings(_env_file=None, environment="production")))

    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


def test_api_docs_are_available_outside_production(client: TestClient) -> None:
    assert client.get("/api/openapi.json").status_code == 200
