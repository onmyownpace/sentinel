"""Shared fixtures for the API tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """HTTP client wrapped around a fresh app. Entering the context runs startup."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


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
def registry_client(migrated_database: None, client: TestClient) -> TestClient:
    """The API client after the website schema has been applied."""
    return client
