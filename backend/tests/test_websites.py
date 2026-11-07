"""Website registry contract.

Validation tests do not need a migrated database. Persistence tests apply the
Alembic revision, then delete only the rows they insert.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture(scope="session")
def migrated_database() -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    command.upgrade(config, "head")


@pytest.fixture
def registry_client(migrated_database: None, client: TestClient) -> TestClient:
    return client


def test_rejects_a_non_http_url(client: TestClient) -> None:
    response = client.post(
        "/api/websites",
        json={"name": "Example", "base_url": "ftp://example.com"},
    )

    assert response.status_code == 422
    assert "postgresql+asyncpg" not in response.text


def test_rejects_a_blank_name(client: TestClient) -> None:
    response = client.post(
        "/api/websites",
        json={"name": "   ", "base_url": "https://example.com"},
    )

    assert response.status_code == 422


def test_rejects_an_id_that_is_not_a_uuid(client: TestClient) -> None:
    response = client.get("/api/websites/not-a-uuid")

    assert response.status_code == 422


def test_create_list_get_and_delete_round_trip(registry_client: TestClient) -> None:
    created = registry_client.post(
        "/api/websites",
        json={"name": "  Docs  ", "base_url": "https://Example.COM:443/guide/"},
    )
    assert created.status_code == 201
    body = created.json()
    website_id = body["id"]
    try:
        assert body["name"] == "Docs"
        assert body["base_url"] == "https://example.com/guide"
        assert body["created_at"]
        assert body["updated_at"]

        fetched = registry_client.get(f"/api/websites/{website_id}")
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "Docs"

        listed = registry_client.get("/api/websites")
        assert listed.status_code == 200
        assert any(item["id"] == website_id for item in listed.json())
    finally:
        deleted = registry_client.delete(f"/api/websites/{website_id}")
        assert deleted.status_code == 204
        assert deleted.content == b""

    missing = registry_client.get(f"/api/websites/{website_id}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Website not found."


def test_duplicate_base_url_conflicts_after_normalization(registry_client: TestClient) -> None:
    suffix = uuid4().hex
    first = registry_client.post(
        "/api/websites",
        json={"name": "First", "base_url": f"https://duplicate.invalid/{suffix}"},
    )
    assert first.status_code == 201
    website_id = first.json()["id"]
    try:
        second = registry_client.post(
            "/api/websites",
            json={"name": "Second", "base_url": f"https://DUPLICATE.invalid/{suffix}/"},
        )
        assert second.status_code == 409
        assert second.json()["detail"] == "A website with this base URL is already registered."
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_missing_website_is_not_found(registry_client: TestClient) -> None:
    response = registry_client.get(f"/api/websites/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Website not found."


def test_delete_missing_website_is_not_found(registry_client: TestClient) -> None:
    response = registry_client.delete(f"/api/websites/{uuid4()}")

    assert response.status_code == 404


def test_newest_website_is_listed_first(registry_client: TestClient) -> None:
    suffix = uuid4().hex
    ids: list[str] = []
    try:
        for name in ("Older", "Newer"):
            response = registry_client.post(
                "/api/websites",
                json={"name": name, "base_url": f"https://order.invalid/{suffix}/{name}"},
            )
            assert response.status_code == 201
            ids.append(response.json()["id"])
        listed = registry_client.get("/api/websites")
        positions = [item["id"] for item in listed.json() if item["id"] in ids]
        assert positions == [ids[1], ids[0]]
    finally:
        for website_id in ids:
            registry_client.delete(f"/api/websites/{website_id}")


def test_missing_table_reports_that_the_schema_is_not_ready(client: TestClient) -> None:
    """A programming error must not echo SQL text back to the caller."""

    class UnreadySession:
        def __call__(self) -> "UnreadySession":
            return self

        async def __aenter__(self) -> "UnreadySession":
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

        async def execute(self, *_args: object, **_kwargs: object) -> None:
            raise ProgrammingError("SELECT", {}, Exception("relation websites does not exist"))

    client.app.state.session_factory = UnreadySession()
    response = client.get("/api/websites")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "The database schema is not ready. Apply migrations and try again."
    )
    assert "relation websites" not in response.text


def test_website_write_fails_closed_when_postgres_refuses_the_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://sentinel:secret-password@127.0.0.1:1/sentinel",
    )
    get_settings.cache_clear()
    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/websites",
                json={"name": "Example", "base_url": "https://example.com"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "The database is unavailable."
    assert "secret-password" not in response.text
    assert "postgresql+asyncpg" not in response.text
