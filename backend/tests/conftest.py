import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from mypal.config import Environment, Settings
from mypal.main import create_app
from mypal.retrieval.index import VectorIndex, create_index

BACKEND_DIR = Path(__file__).resolve().parents[1]
# Used by tests that never touch the database (the engine connects lazily, so nothing dials it).
UNUSED_DATABASE_URL = "postgresql+psycopg://unused@127.0.0.1:1/unused"


class _TestServiceSettings(BaseSettings):
    """Where the test Postgres and Qdrant are: from the environment or backend/.env."""

    model_config = SettingsConfigDict(
        env_prefix="MYPAL_", env_file=BACKEND_DIR / ".env", extra="ignore"
    )
    test_database_url: SecretStr | None = None
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: SecretStr | None = None


def _test_database_url() -> str | None:
    url = _TestServiceSettings().test_database_url
    return url.get_secret_value() if url else None


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: tests must not depend on a developer's local .env for app settings.
    return Settings(
        _env_file=None,
        environment=Environment.TEST,
        log_json=True,
        database_url=_test_database_url() or UNUSED_DATABASE_URL,
        qdrant_url=_TestServiceSettings().qdrant_url,
        qdrant_api_key=_TestServiceSettings().qdrant_api_key,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


# --- Database fixtures ------------------------------------------------------------------------


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    # configparser treats % specially, so escape it in case the password contains one.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def db_url() -> str:
    url = _test_database_url()
    if url is None:
        pytest.skip("MYPAL_TEST_DATABASE_URL is not set (see backend/.env.example)")
    # Safety guard: these tests drop every table, so refuse anything but a *_test database.
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail(f"Refusing to run destructive tests against database {database!r}")
    return url


@pytest.fixture(scope="session")
def db_engine(db_url: str) -> Iterator[Engine]:
    engine = create_engine(db_url, connect_args={"connect_timeout": 5})
    try:
        engine.connect().close()
    except OperationalError:
        pytest.skip("Test Postgres is not reachable - start it with: docker compose up -d")

    # Rebuild the schema from scratch through the real migrations, once per test run.
    config = alembic_config(db_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after the test, so tests never see
    each other's data. Commits inside the test only release a SAVEPOINT."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# --- Vector index fixture ---------------------------------------------------------------------


@pytest.fixture
def vector_index(settings: Settings) -> Iterator[VectorIndex]:
    """A fresh, uniquely named Qdrant collection per test, deleted afterwards. The development
    collection is never touched."""
    index = create_index(settings, collection=f"test_{uuid.uuid4().hex[:12]}")
    try:
        index._client.get_collections()
    except Exception:  # connection refused, timeout, wrong key...
        pytest.skip("Qdrant is not reachable - start it with: docker compose up -d")
    yield index
    index._client.delete_collection(index.collection)
