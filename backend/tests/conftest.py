"""Shared fixtures for the API tests."""

import asyncio
import sys

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

# asyncpg + Docker Desktop on Windows often fails under the default Proactor
# loop with WinError 1225. Selector matches what works for local Postgres.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

SEED_EMAIL = "dev@sentinel.local"
SEED_PASSWORD = "dev-password-change-me"
TEST_AUTOMATION_TOKEN = "test-automation-token"


@pytest.fixture(scope="session")
def migrated_database() -> None:
    """Apply Alembic revisions once for tests that persist rows."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    command.upgrade(config, "head")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """HTTP client wrapped around a fresh app. Entering the context runs startup."""
    monkeypatch.setenv("SEED_USER_EMAIL", SEED_EMAIL)
    monkeypatch.setenv("SEED_USER_PASSWORD", SEED_PASSWORD)
    monkeypatch.setenv("AUTOMATION_TOKEN", TEST_AUTOMATION_TOKEN)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture
def registry_client(migrated_database: None, client: TestClient) -> TestClient:
    """API client after schema migrate, signed in as the seed user."""
    response = client.post(
        "/api/auth/login",
        json={"email": SEED_EMAIL, "password": SEED_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def automation_headers() -> dict[str, str]:
    """Headers that authenticate n8n-style automation calls in tests."""
    return {"X-Automation-Token": TEST_AUTOMATION_TOKEN}
