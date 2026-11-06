"""Health routes. Database success and failure are both specified here.

The monkeypatched cases lock the HTTP contract without a server.
The refused-connection case runs the real driver against a closed port so a
failure cannot leak the URL, and so the suite does not pretend PostgreSQL is up.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def test_liveness_does_not_depend_on_the_database(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "sentinel-api",
        "version": "0.1.0",
        "environment": "development",
    }


def test_startup_creates_engine_and_session_factory(client: TestClient) -> None:
    assert client.app.state.engine is not None
    assert client.app.state.session_factory is not None


def test_frontend_origin_is_allowed(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_readiness_is_ok_when_the_database_check_succeeds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reachable(_engine: object) -> bool:
        return True

    monkeypatch.setattr("app.api.routes.health.database_is_reachable", reachable)

    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": "ok"}


def test_readiness_is_degraded_when_the_database_check_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unreachable(_engine: object) -> bool:
        return False

    monkeypatch.setattr("app.api.routes.health.database_is_reachable", unreachable)

    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"] == {"database": "unavailable"}


def test_readiness_fails_closed_when_postgres_refuses_the_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hit a closed local port with a distinctive password and require it to stay private."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://sentinel:secret-password@127.0.0.1:1/sentinel",
    )
    get_settings.cache_clear()
    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/health/ready")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"] == {"database": "unavailable"}
    assert "secret-password" not in response.text
    assert "postgresql+asyncpg" not in response.text
