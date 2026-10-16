import pytest
from fastapi.testclient import TestClient

from mypal.config import Environment, Settings
from mypal.main import create_app


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: tests must not depend on a developer's local .env file.
    return Settings(_env_file=None, environment=Environment.TEST, log_json=True)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
