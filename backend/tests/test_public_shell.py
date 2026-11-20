"""Public shell: no live Chromium, closed registration; Analyze uses configured provider."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import DEFAULT_TOGETHER_MODEL, Settings, get_settings
from app.core.database import create_db_engine
from app.services.failure_analysis import AnalysisProviderError, FailureAnalysisResult, PossibleCause
from app.services.public_rate_limit import reset_rate_limits
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
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-together-key-not-real")
    monkeypatch.setenv("TOGETHER_API_KEY", "together-alias-unused-when-openai-set")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.together.ai/v1")
    monkeypatch.setenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo")
    monkeypatch.setenv("SEED_USER_EMAIL", "demo@sentinel.local")
    monkeypatch.setenv("SEED_USER_PASSWORD", "demo-password-change-me")
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("DATABASE_SSL", "false")  # local Postgres in tests
    get_settings.cache_clear()
    reset_rate_limits()
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()
    reset_rate_limits()


class RecordingProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def analyze(self, evidence: dict[str, object]) -> FailureAnalysisResult:
        self.calls += 1
        if self.fail:
            raise AnalysisProviderError("The analysis provider could not complete the request.")
        return FailureAnalysisResult(
            summary="Live demo analysis via configured provider.",
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
            limitations="Test provider — stubbed live path.",
        )


def _clear_analysis(check_id: str) -> None:
    """Remove any stored analysis so provider tests start from a clean check."""
    import asyncio

    import asyncpg

    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    async def _delete() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                "DELETE FROM check_failure_analyses WHERE check_id = $1::uuid",
                check_id,
            )
        finally:
            await conn.close()

    asyncio.run(_delete())


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
    # Health reports the configured workspace/public provider (Together-compatible).
    assert body["analysis_provider"] == "openai"
    assert body["analysis_model"] == "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    assert body["analysis_base_host"] == "api.together.ai"
    assert body["registration_open"] is False


def test_public_shell_demo_analysis_uses_configured_provider(
    public_shell_client: TestClient,
) -> None:
    """Seeded portfolio demo checks use the configured openai provider when not forced simulated."""
    provider = RecordingProvider()
    public_shell_client.app.state.analysis_provider = provider
    public_shell_client.app.state.analysis_provider_name = "openai"
    public_shell_client.app.state.analysis_model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"

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
    _clear_analysis(check_id)

    response = public_shell_client.post(f"/api/checks/{check_id}/analysis")
    assert response.status_code in {200, 201}, response.text
    body = response.json()
    assert provider.calls == 1
    assert body["provider"] == "openai"
    assert body["model_name"] == "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    assert "Live demo analysis" in body["summary"]


def test_public_shell_workspace_analysis_uses_configured_provider(
    public_shell_client: TestClient,
) -> None:
    """Non-demo failed checks on the public shell use the configured openai provider."""
    import asyncio

    import asyncpg

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


def test_anonymous_public_analyze_uses_configured_provider(
    public_shell_client: TestClient,
) -> None:
    """Anonymous public Analyze uses configured provider when not forced simulated."""
    provider = RecordingProvider()
    public_shell_client.app.state.analysis_provider = provider
    public_shell_client.app.state.analysis_provider_name = "openai"
    public_shell_client.app.state.analysis_model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"

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
    _clear_analysis(failed_id)

    analysis = public_shell_client.post(f"/api/public/demo/checks/{failed_id}/analysis")
    assert analysis.status_code in {200, 201}, analysis.text
    payload = analysis.json()
    assert provider.calls == 1
    assert payload["provider"] == "openai"
    assert payload["model_name"] == "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    assert payload["check_id"] == failed_id
    assert "Live demo analysis" in payload["summary"]

    # Repeat Analyze reuses the stored live row (no second provider call).
    again = public_shell_client.post(f"/api/public/demo/checks/{failed_id}/analysis")
    assert again.status_code == 200, again.text
    assert provider.calls == 1
    assert again.json()["provider"] == "openai"

    dashboard = public_shell_client.get("/api/public/demo/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    dash = dashboard.json()
    assert len(dash["websites"]) == 1
    assert dash["websites"][0]["name"].startswith("[Demo]")
    assert dash["health"]["recent_failure_count"] >= 1


def test_anonymous_public_analyze_upgrades_leftover_simulated(
    public_shell_client: TestClient,
) -> None:
    """Leftover simulated rows are replaced when openai/Together is configured."""
    import asyncio

    import asyncpg

    public_shell_client.cookies.clear()
    snapshot = public_shell_client.get("/api/public/demo")
    failed_id = snapshot.json()["failed_check_id"]
    assert failed_id
    _clear_analysis(failed_id)

    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    async def _insert_simulated() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                """
                INSERT INTO check_failure_analyses (
                    id, check_id, summary, severity, confirmed_observations,
                    possible_causes, recommended_investigation_steps, limitations,
                    model_name, provider, created_at
                ) VALUES (
                    gen_random_uuid(), $1::uuid,
                    'Simulated analysis of the stored failed check.',
                    'medium', '["obs"]'::jsonb,
                    '[{"cause":"c","confidence":"low","evidence":"e"}]'::jsonb,
                    '["step"]'::jsonb, 'SIMULATED only.',
                    'simulated-local', 'simulated', NOW()
                )
                """,
                failed_id,
            )
        finally:
            await conn.close()

    asyncio.run(_insert_simulated())

    provider = RecordingProvider()
    public_shell_client.app.state.analysis_provider = provider
    public_shell_client.app.state.analysis_provider_name = "openai"
    public_shell_client.app.state.analysis_model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"

    response = public_shell_client.post(f"/api/public/demo/checks/{failed_id}/analysis")
    assert response.status_code == 201, response.text
    body = response.json()
    assert provider.calls == 1
    assert body["provider"] == "openai"
    assert "Live demo analysis" in body["summary"]


def test_anonymous_public_analyze_surfaces_provider_failure(
    public_shell_client: TestClient,
) -> None:
    """Together/provider failure must return a clear 502 — not silent simulated success."""
    provider = RecordingProvider(fail=True)
    public_shell_client.app.state.analysis_provider = provider
    public_shell_client.app.state.analysis_provider_name = "openai"
    public_shell_client.app.state.analysis_model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    public_shell_client.cookies.clear()

    snapshot = public_shell_client.get("/api/public/demo")
    assert snapshot.status_code == 200
    failed_id = snapshot.json()["failed_check_id"]
    assert failed_id
    _clear_analysis(failed_id)

    response = public_shell_client.post(f"/api/public/demo/checks/{failed_id}/analysis")
    assert response.status_code == 502, response.text
    detail = response.json()["detail"]
    assert "provider" in detail.lower()
    assert provider.calls == 1
    # No simulated row should have been stored.
    missing = public_shell_client.get(f"/api/public/demo/checks/{failed_id}/analysis")
    assert missing.status_code == 404


def test_anonymous_public_analyze_rate_limited(
    public_shell_client: TestClient,
) -> None:
    """Public Analyze is abuse-guarded with a per-client rate limit."""
    provider = RecordingProvider()
    public_shell_client.app.state.analysis_provider = provider
    public_shell_client.app.state.analysis_provider_name = "openai"
    public_shell_client.app.state.analysis_model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    public_shell_client.cookies.clear()

    snapshot = public_shell_client.get("/api/public/demo")
    failed_id = snapshot.json()["failed_check_id"]
    assert failed_id
    _clear_analysis(failed_id)

    # First call creates; subsequent reuse still counts against the rate limit.
    statuses = []
    for _ in range(6):
        statuses.append(
            public_shell_client.post(f"/api/public/demo/checks/{failed_id}/analysis").status_code
        )
    assert 429 in statuses
    assert any(code in {200, 201} for code in statuses)


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


def test_live_check_falls_back_to_http_probe(public_shell_client: TestClient, monkeypatch) -> None:
    """Public shell must not 503 on Run check — use lightweight HTTP probe instead."""
    from app.services.results import CheckObservation

    runner = ScriptedRunner()
    public_shell_client.app.state.check_runner = runner

    async def fake_probe(url: str, **_kwargs):
        return CheckObservation(
            outcome="success",
            http_status=200,
            page_title="Probed",
            final_url=url,
            duration_ms=12,
            console_errors=(),
            failed_requests=(),
            error_message=None,
        )

    monkeypatch.setattr("app.api.routes.checks.probe_http_url", fake_probe)

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
    response = public_shell_client.post(
        f"/api/websites/{website_id}/checks",
        json={"authorized": True},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["http_status"] == 200
    assert "Lightweight HTTP probe" in (body["error_message"] or "")
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
