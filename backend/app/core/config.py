"""Runtime configuration.

Settings are read once, the first time `get_settings()` is called, and then
cached for the life of the process. A change to `.env` is picked up by
restarting the API, not by the next request.

The env file path is anchored to this source file. It does not depend on the
directory the process was started from.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repository root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Values that differ between machines and must not be hardcoded in routes."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sentinel"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel"
    # Comma-separated browser origins. The status page calls the API from the
    # Next.js server. The website registry calls it from the browser, so the
    # origin of the page has to be listed. localhost and 127.0.0.1 differ.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # How long one navigation may take. The browser service adds a short
    # allowance for launching Chromium, then stops the check.
    check_navigation_timeout_seconds: float = 15

    @field_validator("database_url")
    @classmethod
    def database_url_must_use_asyncpg(cls, value: str) -> str:
        prefix = "postgresql+asyncpg://"
        if not value.startswith(prefix):
            raise ValueError(
                "DATABASE_URL must start with postgresql+asyncpg:// "
                "so SQLAlchemy uses the async driver."
            )
        return value

    @field_validator("check_navigation_timeout_seconds")
    @classmethod
    def navigation_timeout_must_be_bounded(cls, value: float) -> float:
        if value < 1 or value > 60:
            raise ValueError("CHECK_NAVIGATION_TIMEOUT_SECONDS must be between 1 and 60")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""
    return Settings()
