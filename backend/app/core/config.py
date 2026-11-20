"""Runtime configuration.

Settings are read once, the first time `get_settings()` is called, and then
cached for the life of the process. A change to `.env` is picked up by
restarting the API, not by the next request.

The env file path is anchored to this source file. It does not depend on the
directory the process was started from.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repository root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"

# Stock OpenAI default. When OPENAI_BASE_URL points at Together and the model
# is still this value, Settings substitutes DEFAULT_TOGETHER_MODEL.
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
# Sensible Together chat model for the OpenAI-compatible /v1 endpoint.
DEFAULT_TOGETHER_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
TOGETHER_API_HOST = "api.together.ai"


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
    # Public shell: $0 Render+Neon portfolio mode. Disables live Chromium
    # and closes open registration. Does not force analysis to simulated —
    # PUBLIC_SHELL / anonymous demo Analyze uses ANALYSIS_PROVIDER as configured
    # (Together via openai + OPENAI_BASE_URL + key when set on Render).
    # Local default is off.
    public_shell: bool = False
    # Explicit kill switch for Playwright execution. Public shell forces off
    # even if this is left true in a misconfigured env file.
    live_browser_enabled: bool = True
    # Open sign-up. Public shell forces this off so the registry is not a
    # shared writable free-for-all.
    allow_registration: bool = True
    database_url: str = "postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel"
    # Neon and other hosted Postgres require TLS. None = auto (on when public_shell).
    # Set DATABASE_SSL=false to force plaintext (local Compose while testing public_shell).
    database_ssl: bool | None = None
    # asyncpg connect timeout (seconds). Raise for Neon cold starts in public env.
    database_connect_timeout_seconds: float = 2
    # Comma-separated browser origins. The status page calls the API from the
    # Next.js server. The website registry calls it from the browser, so the
    # origin of the page has to be listed. localhost and 127.0.0.1 differ.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Session cookie SameSite. Use "none" with HTTPS when UI and API differ by host.
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # How long one navigation may take. The browser service adds a short
    # allowance for launching Chromium, then stops the check.
    check_navigation_timeout_seconds: float = 15
    # BROW-1: optional viewport PNG after navigation. Stored under screenshot_dir.
    screenshot_enabled: bool = True
    screenshot_dir: str = str(_REPO_ROOT / "backend" / "data" / "screenshots")
    screenshot_max_bytes: int = 512_000
    screenshot_timeout_ms: int = 5_000
    # BROW-2: request-bound journey budget (seconds) for the whole mini-journey.
    journey_budget_seconds: float = 45
    # Failure analysis provider. `simulated` is the development default and
    # never calls an external AI API. `openai` uses the OpenAI-compatible client
    # (OpenAI itself or Together via OPENAI_BASE_URL). DB/provider label stays
    # `openai` when using Together so check constraints stay valid.
    analysis_provider: Literal["simulated", "openai"] = "simulated"
    openai_api_key: str | None = None
    # Optional OpenAI-compatible base URL (e.g. https://api.together.ai/v1).
    openai_base_url: str | None = None
    openai_model: str = DEFAULT_OPENAI_MODEL
    openai_timeout_seconds: float = 30
    openai_max_output_tokens: int = 1200
    # Fallback alias: used only when OPENAI_API_KEY is empty. Never logged.
    together_api_key: str | None = None
    # Shared secret for n8n scheduled checks. Empty means the scheduled-check
    # route refuses work. This is a machine acknowledgement, not user auth.
    schedule_check_token: str | None = None
    # Shared secret for automation GETs (registry / checks / analysis) from n8n.
    # Empty means only a signed-in browser session can call those routes.
    automation_token: str | None = None
    # Cookie session lifetime for email/password sign-in.
    session_ttl_days: int = 14
    # Dev convenience: create this account on API startup when missing.
    # Leave email empty to skip seeding.
    seed_user_email: str = "dev@sentinel.local"
    seed_user_password: str = "dev-password-change-me"

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

    @field_validator("screenshot_max_bytes")
    @classmethod
    def screenshot_max_bytes_must_be_bounded(cls, value: int) -> int:
        if value < 10_000 or value > 2_000_000:
            raise ValueError("SCREENSHOT_MAX_BYTES must be between 10000 and 2000000")
        return value

    @field_validator("screenshot_timeout_ms")
    @classmethod
    def screenshot_timeout_must_be_bounded(cls, value: int) -> int:
        if value < 500 or value > 30_000:
            raise ValueError("SCREENSHOT_TIMEOUT_MS must be between 500 and 30000")
        return value

    @field_validator("journey_budget_seconds")
    @classmethod
    def journey_budget_must_be_bounded(cls, value: float) -> float:
        if value < 5 or value > 120:
            raise ValueError("JOURNEY_BUDGET_SECONDS must be between 5 and 120")
        return value

    @property
    def screenshot_root(self) -> Path:
        return Path(self.screenshot_dir).expanduser()

    @field_validator("analysis_provider", mode="before")
    @classmethod
    def analysis_provider_must_be_known(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("openai_timeout_seconds")
    @classmethod
    def openai_timeout_must_be_bounded(cls, value: float) -> float:
        if value < 1 or value > 120:
            raise ValueError("OPENAI_TIMEOUT_SECONDS must be between 1 and 120")
        return value

    @field_validator("openai_max_output_tokens")
    @classmethod
    def openai_output_tokens_must_be_bounded(cls, value: int) -> int:
        if value < 100 or value > 4000:
            raise ValueError("OPENAI_MAX_OUTPUT_TOKENS must be between 100 and 4000")
        return value

    @field_validator("openai_model")
    @classmethod
    def openai_model_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("OPENAI_MODEL must not be blank")
        return cleaned

    @field_validator("openai_base_url", mode="before")
    @classmethod
    def openai_base_url_blank_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("session_ttl_days")
    @classmethod
    def session_ttl_must_be_bounded(cls, value: int) -> int:
        if value < 1 or value > 90:
            raise ValueError("SESSION_TTL_DAYS must be between 1 and 90")
        return value

    @field_validator("seed_user_email")
    @classmethod
    def seed_email_normalized(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("database_connect_timeout_seconds")
    @classmethod
    def database_timeout_must_be_bounded(cls, value: float) -> float:
        if value < 1 or value > 60:
            raise ValueError("DATABASE_CONNECT_TIMEOUT_SECONDS must be between 1 and 60")
        return value

    @field_validator("session_cookie_samesite", mode="before")
    @classmethod
    def cookie_samesite_normalized(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @model_validator(mode="after")
    def public_shell_safety(self) -> "Settings":
        # Public shell still disables browser + registration via properties.
        # Analysis provider is left as configured so signed-in workspace can
        # use Together/OpenAI-compatible keys on Render.
        # TOGETHER_API_KEY is a documented alias for the OpenAI-compatible key.
        if not (self.openai_api_key and self.openai_api_key.strip()):
            together = (self.together_api_key or "").strip()
            if together:
                object.__setattr__(self, "openai_api_key", together)
        # Together endpoint + unset/stock OpenAI model → Together-hosted default.
        if self.is_together_endpoint and self.openai_model == DEFAULT_OPENAI_MODEL:
            object.__setattr__(self, "openai_model", DEFAULT_TOGETHER_MODEL)
        if self.session_cookie_samesite == "none" and self.environment.lower() != "production":
            # Browsers require Secure with SameSite=None; production sets Secure.
            pass
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def browser_execution_allowed(self) -> bool:
        """False in the public shell or when LIVE_BROWSER_ENABLED=false."""
        if self.public_shell:
            return False
        return self.live_browser_enabled

    @property
    def registration_allowed(self) -> bool:
        if self.public_shell:
            return False
        return self.allow_registration

    @property
    def database_ssl_required(self) -> bool:
        """TLS for asyncpg. Explicit DATABASE_SSL wins; else public_shell defaults on."""
        if self.database_ssl is not None:
            return self.database_ssl
        return self.public_shell

    @property
    def analysis_base_host(self) -> str | None:
        """Hostname of the OpenAI-compatible endpoint, or None for the SDK default.

        Never includes credentials. Used in health/status and startup logs so a
        Together base URL is visible without printing keys.
        """
        if not self.openai_base_url:
            return None
        parsed = urlparse(self.openai_base_url)
        host = (parsed.hostname or "").strip().lower()
        return host or None

    @property
    def is_together_endpoint(self) -> bool:
        return self.analysis_base_host == TOGETHER_API_HOST

    @property
    def effective_analysis_provider(self) -> Literal["simulated", "openai"]:
        """Provider for signed-in and public demo Analyze.

        Public shell does not override this. Anonymous `/api/public/demo`
        analysis uses the same configured provider (Together when openai +
        base URL + key are set).
        """
        return self.analysis_provider

    @property
    def effective_analysis_model(self) -> str:
        """Model label for health/UI. Simulated never exposes a live model id."""
        if self.effective_analysis_provider == "simulated":
            return "simulated-local"
        return self.openai_model


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""
    return Settings()
