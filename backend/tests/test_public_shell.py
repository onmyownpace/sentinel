"""Public shell: no live Chromium, closed registration, simulated AI."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.database import create_db_engine
from app.services.results import CheckObservation


class ScriptedRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, url: str) -> CheckObservation:
        self.calls += 1
        return CheckObservation(
            outcome="success",
            http_status=200,
            page_title="Should not run",
            final_url=url,
            duration_ms=1,
            console_errors=(),
            failed_requests=(),
            error_message=None,
        )


@pytest.fixture
def public_shell_client(monkeypatch: pytest.MonkeyPatch, migrated_database: None):
    monkeypatch.setenv("PUBLIC_SHELL", "true")
    monkeypatch.setenv("LIVE_BROWSER_ENABLED", "true")  # must still be forced off
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-be-used")
    # Together-oriented env must still be ignored in the public portfolio shell.
    monkeypatch.setenv("TOGETHER_API_KEY", "together-should-not-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.together.ai/v1")
    monkeypatch.setenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo")
    monkeypatch.setenv("SEED_USER_EMAIL", "demo@sentinel.local")
    monkeypatch.setenv("SEED_USER_PASSWORD", "demo-password-change-me")
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("DATABASE_SSL", "false")  # local Postgres in tests
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def test_public_shell_settings_force_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_SHELL", "true")
    monkeypatch.setenv("LIVE_BROWSER_ENABLED", "true")
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("DATABASE_SSL", "false")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.public_shell is True
        assert settings.browser_execution_allowed is False
        assert settings.registration_allowed is False
        assert settings.effective_analysis_provider == "simulated"
        assert settings.database_ssl_required is False  # explicit DATABASE_SSL=false
    finally:
        get_settings.cache_clear()


def test_public_shell_defaults_ssl_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_SHELL", "true")
    monkeypatch.delenv("DATABASE_SSL", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.database_ssl_required is True
    finally:
        get_settings.cache_clear()


def test_database_engine_uses_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("DATABASE_SSL", "false")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        engine = create_db_engine(settings)
        assert settings.database_connect_timeout_seconds == 12
        assert engine is not None
    finally:
        get_settings.cache_clear()


def test_health_reports_public_shell(public_shell_client: TestClient) -> None:
    response = public_shell_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["public_shell"] is True
    assert body["live_browser_enabled"] is False
    assert body["analysis_provider"] == "simulated"
    assert body["analysis_model"] == "simulated-local"
    assert body["analysis_base_host"] is None
    assert body["registration_open"] is False


def test_public_shell_analysis_never_calls_external_ai(
    public_shell_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Portfolio demo must stay simulated even with Together keys/base_url set."""

    def boom_openai(*_args, **_kwargs):
        raise AssertionError("AsyncOpenAI must not be constructed in public shell")

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", boom_openai)

    login = public_shell_client.post(
        "/api/auth/login",
        json={"email": "demo@sentinel.local", "password": "demo-password-change-me"},
    )
    assert login.status_code == 200, login.text

    websites = public_shell_client.get("/api/websites")
    assert websites.status_code == 200
    sites = websites.json()
    assert sites, "public shell should seed a demo website"
    website_id = sites[0]["id"]

    checks = public_shell_client.get(f"/api/websites/{website_id}/checks")
    assert checks.status_code == 200
    failed = [row for row in checks.json() if row["outcome"] == "failed"]
    assert failed, "public shell should seed a failed demo check"
    check_id = failed[0]["id"]

    response = public_shell_client.post(f"/api/checks/{check_id}/analysis")
    assert response.status_code in {200, 201}, response.text
    body = response.json()
    assert body["provider"] == "simulated"
    assert body["model_name"] == "simulated-local"
    assert "SIMULATED" in body["limitations"].upper() or "simulated" in body["summary"].lower()


def test_registration_blocked(public_shell_client: TestClient) -> None:
    response = public_shell_client.post(
        "/api/auth/register",
        json={"email": f"open-{uuid4().hex}@example.com", "password": "long-enough-password"},
    )
    assert response.status_code == 403
    assert "registration" in response.json()["detail"].lower()


def test_live_check_blocked(public_shell_client: TestClient) -> None:
    runner = ScriptedRunner()
    public_shell_client.app.state.check_runner = runner
    login = public_shell_client.post(
        "/api/auth/login",
        json={"email": "demo@sentinel.local", "password": "demo-password-change-me"},
    )
    assert login.status_code == 200, login.text
    created = public_shell_client.post(
        "/api/websites",
        json={"name": "Probe", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201, created.text
    website_id = created.json()["id"]
    blocked = public_shell_client.post(
        f"/api/websites/{website_id}/checks",
        json={"authorized": True},
    )
    assert blocked.status_code == 503
    assert "public shell" in blocked.json()["detail"].lower()
    assert runner.calls == 0


def test_scheduled_check_blocked_without_token_path(public_shell_client: TestClient) -> None:
    runner = ScriptedRunner()
    public_shell_client.app.state.check_runner = runner
    login = public_shell_client.post(
        "/api/auth/login",
        json={"email": "demo@sentinel.local", "password": "demo-password-change-me"},
    )
    assert login.status_code == 200
    created = public_shell_client.post(
        "/api/websites",
        json={"name": "Sched", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    website_id = created.json()["id"]
    public_shell_client.patch(f"/api/websites/{website_id}", json={"monitoring_enabled": True})
    blocked = public_shell_client.post(f"/api/websites/{website_id}/scheduled-checks")
    assert blocked.status_code == 503
    assert runner.calls == 0


def test_local_defaults_allow_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUBLIC_SHELL", raising=False)
    monkeypatch.setenv("LIVE_BROWSER_ENABLED", "true")
    get_settings.cache_clear()
    try:
        settings = Settings()
        assert settings.browser_execution_allowed is True
        assert settings.registration_allowed is True
    finally:
        get_settings.cache_clear()
