"""Public shell: no live Chromium, closed registration; demo AI stays simulated."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import DEFAULT_TOGETHER_MODEL, Settings, get_settings
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
    monkeypatch.setenv("OPENAI_API_KEY", "sk-workspace-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.together.ai/v1")
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("DATABASE_SSL", "false")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.public_shell is True
        assert settings.browser_execution_allowed is False
        assert settings.registration_allowed is False
        # Signed-in workspace may use the configured provider (Together/OpenAI).
        assert settings.effective_analysis_provider == "openai"
        assert settings.analysis_base_host == "api.together.ai"
        assert settings.openai_model == DEFAULT_TOGETHER_MODEL
        assert settings.database_ssl_required is False  # explicit DATABASE_SSL=false
    finally:
        get_settings.cache_clear()


def test_public_shell_defaults_ssl_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_SHELL", "true")
    monkeypatch.delenv("DATABASE_SSL", raising=False)
    get_settings.cache_clear()
    try:
        # Ignore repo .env DATABASE_SSL so the public_shell default (TLS on) applies.
        settings = Settings(
            _env_file=None,
            public_shell=True,
            database_url="postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel",
        )
        assert settings.database_ssl is None
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
    # Workspace provider is configured (Together-compatible); demo rows stay simulated
    # in the analysis routes, not via this health field.
    assert body["analysis_provider"] == "openai"
    assert body["analysis_model"] == "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    assert body["analysis_base_host"] == "api.together.ai"
    assert body["registration_open"] is False


def test_public_shell_demo_analysis_stays_simulated(
    public_shell_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seeded portfolio demo checks must stay simulated even with Together keys set."""

    def boom_openai(*_args, **_kwargs):
        raise AssertionError("AsyncOpenAI must not be constructed for demo checks")

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
    demo_sites = [site for site in sites if site["name"].startswith("[Demo]")]
    assert demo_sites, "public shell should seed a demo website"
    website_id = demo_sites[0]["id"]

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


def test_public_shell_workspace_analysis_uses_configured_provider(
    public_shell_client: TestClient,
) -> None:
    """Non-demo failed checks on the public shell use the configured openai provider."""
    import asyncio

    import asyncpg

    from app.services.failure_analysis import FailureAnalysisResult, PossibleCause

    class RecordingProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def analyze(self, evidence: dict[str, object]) -> FailureAnalysisResult:
            self.calls += 1
            return FailureAnalysisResult(
                summary="Workspace analysis via configured provider.",
                severity="medium",
                confirmed_observations=["HTTP status was 503"],
                possible_causes=[
                    PossibleCause(
                        cause="Upstream outage",
                        confidence="medium",
                        evidence="HTTP 503",
                    )
                ],
                recommended_investigation_steps=["Check origin health"],
                limitations="Test provider — not a live model call.",
            )

    provider = RecordingProvider()
    public_shell_client.app.state.analysis_provider = provider
    public_shell_client.app.state.analysis_provider_name = "openai"
    public_shell_client.app.state.analysis_model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"

    login = public_shell_client.post(
        "/api/auth/login",
        json={"email": "demo@sentinel.local", "password": "demo-password-change-me"},
    )
    assert login.status_code == 200, login.text

    created = public_shell_client.post(
        "/api/websites",
        json={"name": "Private workspace site", "base_url": f"https://example.com/{uuid4().hex}"},
    )
    assert created.status_code == 201, created.text
    site = created.json()
    website_id = site["id"]
    base_url = site["base_url"]
    check_id = str(uuid4())

    # Insert via a fresh asyncpg connection (avoids TestClient event-loop reuse).
    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    async def _insert_failed_check() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                """
                INSERT INTO website_checks (
                    id, website_id, outcome, http_status, page_title, final_url,
                    duration_ms, console_errors, failed_requests, error_message, created_at
                ) VALUES (
                    $1::uuid, $2::uuid, 'failed', 503, NULL, $3,
                    90, '[]'::jsonb, '[]'::jsonb, $4, NOW()
                )
                """,
                check_id,
                website_id,
                base_url,
                "The page responded with HTTP 503.",
            )
        finally:
            await conn.close()

    asyncio.run(_insert_failed_check())

    response = public_shell_client.post(f"/api/checks/{check_id}/analysis")
    assert response.status_code in {200, 201}, response.text
    body = response.json()
    assert provider.calls == 1
    assert body["provider"] == "openai"
    assert body["model_name"] == "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"


def test_anonymous_can_load_demo_failure_and_analysis(
    public_shell_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strangers load the seeded failure + simulated analysis with no cookies."""

    def boom_openai(*_args, **_kwargs):
        raise AssertionError("AsyncOpenAI must not be constructed for public demo analysis")

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", boom_openai)

    # No login — clear any cookies the client may hold.
    public_shell_client.cookies.clear()

    snapshot = public_shell_client.get("/api/public/demo")
    assert snapshot.status_code == 200, snapshot.text
    body = snapshot.json()
    assert body["website"]["name"].startswith("[Demo]")
    failed_id = body["failed_check_id"]
    assert failed_id, "public demo should expose a failed check"
    assert any(row["id"] == failed_id and row["outcome"] == "failed" for row in body["checks"])

    check = public_shell_client.get(f"/api/public/demo/checks/{failed_id}")
    assert check.status_code == 200, check.text
    assert check.json()["http_status"] == 503

    analysis = public_shell_client.post(f"/api/public/demo/checks/{failed_id}/analysis")
    assert analysis.status_code in {200, 201}, analysis.text
    payload = analysis.json()
    assert payload["provider"] == "simulated"
    assert payload["model_name"] == "simulated-local"
    assert payload["check_id"] == failed_id

    dashboard = public_shell_client.get("/api/public/demo/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    dash = dashboard.json()
    assert len(dash["websites"]) == 1
    assert dash["websites"][0]["name"].startswith("[Demo]")
    assert dash["health"]["recent_failure_count"] >= 1


def test_anonymous_public_demo_hides_non_demo_data(
    public_shell_client: TestClient,
) -> None:
    """Private workspace rows must not leak through the anonymous demo API."""
    login = public_shell_client.post(
        "/api/auth/login",
        json={"email": "demo@sentinel.local", "password": "demo-password-change-me"},
    )
    assert login.status_code == 200, login.text
    created = public_shell_client.post(
        "/api/websites",
        json={"name": "Secret private site", "base_url": f"https://example.com/{uuid4().hex}"},
    )
    assert created.status_code == 201, created.text
    private_id = created.json()["id"]

    public_shell_client.cookies.clear()

    denied_site = public_shell_client.get(f"/api/public/demo/websites/{private_id}")
    assert denied_site.status_code == 404

    denied_list = public_shell_client.get(f"/api/public/demo/websites/{private_id}/checks")
    assert denied_list.status_code == 404

    # Authenticated list still includes the private site; anonymous demo snapshot does not.
    login = public_shell_client.post(
        "/api/auth/login",
        json={"email": "demo@sentinel.local", "password": "demo-password-change-me"},
    )
    assert login.status_code == 200
    owned = public_shell_client.get("/api/websites")
    assert owned.status_code == 200
    assert any(site["id"] == private_id for site in owned.json())

    public_shell_client.cookies.clear()
    demo = public_shell_client.get("/api/public/demo")
    assert demo.status_code == 200
    assert demo.json()["website"]["id"] != private_id
    assert "Secret private" not in demo.text


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
