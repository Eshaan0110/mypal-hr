"""Application settings, loaded from environment variables (and a local .env in development).

Every configurable value lives here so the rest of the code never reads os.environ directly.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MYPAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "My Pal"
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    # JSON logs suit log collectors; plain text is easier to read in a local terminal.
    log_json: bool = True
    # Browser origins allowed to call the API (the Vite dev server in Phase 6).
    cors_origins: list[str] = Field(default_factory=list)

    # Required, no default: the app refuses to start rather than guess a database.
    # SecretStr keeps the password out of logs and reprs; read it with .get_secret_value().
    database_url: SecretStr
    # Seconds to wait when opening a connection, so an unreachable database fails fast.
    database_connect_timeout: int = Field(default=5, ge=1, le=60)

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are a development aid, not something to expose in production."""
        return self.environment is not Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process. Tests build their own Settings instead of using this."""
    return Settings()
