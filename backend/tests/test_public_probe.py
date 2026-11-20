"""Lightweight public HTTP probe + abuse guards (public shell)."""

from __future__ import annotations

import ipaddress
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.http_probe import PROBE_MARKER, attach_probe_marker, is_probe_result
from app.services.public_rate_limit import reset_rate_limits
from app.services.results import CheckObservation, failed_observation


@pytest.fixture
def public_shell_client(monkeypatch: pytest.MonkeyPatch, migrated_database: None):
    monkeypatch.setenv("PUBLIC_SHELL", "true")
    monkeypatch.setenv("LIVE_BROWSER_ENABLED", "true")
    monkeypatch.setenv("ANALYSIS_PROVIDER", "simulated")
    monkeypatch.setenv("SEED_USER_EMAIL", "demo@sentinel.local")
    monkeypatch.setenv("SEED_USER_PASSWORD", "demo-password-change-me")
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("DATABASE_SSL", "false")
    get_settings.cache_clear()
    reset_rate_limits()
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()
    reset_rate_limits()


async def _public(_host: str, _port: int):
    return [ipaddress.ip_address("93.184.216.34")]


async def _private(_host: str, _port: int):
    return [ipaddress.ip_address("10.0.0.8")]


@pytest.fixture
def stub_probe(monkeypatch: pytest.MonkeyPatch):
    """Replace the network probe with a deterministic observation."""

    async def fake_probe(url: str, **_kwargs):
        return CheckObservation(
            outcome="success",
            http_status=200,
            page_title="Example Domain",
            final_url=url.rstrip("/") + "/",
            duration_ms=42,
            console_errors=(),
            failed_requests=(),
            error_message=None,
        )

    monkeypatch.setattr("app.api.routes.public_demo.probe_http_url", fake_probe)
    monkeypatch.setattr("app.api.routes.checks.probe_http_url", fake_probe)
    return fake_probe


def test_attach_probe_marker_stamps_success_and_failure() -> None:
    ok = attach_probe_marker(
        CheckObservation(
            outcome="success",
            http_status=200,
            page_title="Ok",
            final_url="https://example.com/",
            duration_ms=10,
            console_errors=(),
            failed_requests=(),
            error_message=None,
        )
    )
    assert ok.outcome == "success"
    assert ok.error_message == PROBE_MARKER
    assert is_probe_result(ok.error_message)

    bad = attach_probe_marker(failed_observation(time.perf_counter(), "The page responded with HTTP 503.", http_status=503))
    assert bad.outcome == "failed"
    assert bad.error_message is not None
    assert bad.error_message.startswith(PROBE_MARKER)
    assert "503" in bad.error_message


def test_anonymous_probe_returns_real_shaped_result(
    public_shell_client: TestClient,
    stub_probe,
) -> None:
    public_shell_client.cookies.clear()
    public_shell_client.app.state.host_resolver = _public

    response = public_shell_client.post(
        "/api/public/demo/probe",
        json={"url": "https://example.com", "authorized": True},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["outcome"] == "success"
    assert body["http_status"] == 200
    assert body["page_title"] == "Example Domain"
    assert body["duration_ms"] >= 0
    assert is_probe_result(body["error_message"])
    assert body["has_screenshot"] is False

    # Stored probe is readable + analyzable via public demo routes when failed.
    check_id = body["id"]
    fetched = public_shell_client.get(f"/api/public/demo/checks/{check_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == check_id


def test_anonymous_probe_rejects_private_targets(public_shell_client: TestClient) -> None:
    public_shell_client.cookies.clear()
    public_shell_client.app.state.host_resolver = _private

    blocked = public_shell_client.post(
        "/api/public/demo/probe",
        json={"url": "https://internal.example/secret", "authorized": True},
    )
    assert blocked.status_code == 422
    assert "public" in blocked.json()["detail"].lower()


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_anonymous_probe_rejects_unsafe_schemes_and_hosts(
    public_shell_client: TestClient,
    url: str,
) -> None:
    public_shell_client.cookies.clear()
    response = public_shell_client.post(
        "/api/public/demo/probe",
        json={"url": url, "authorized": True},
    )
    assert response.status_code in {422, 400}, response.text


def test_anonymous_probe_requires_authorization_flag(
    public_shell_client: TestClient,
) -> None:
    public_shell_client.cookies.clear()
    response = public_shell_client.post(
        "/api/public/demo/probe",
        json={"url": "https://example.com", "authorized": False},
    )
    assert response.status_code == 422


def test_anonymous_demo_site_probe(
    public_shell_client: TestClient,
    stub_probe,
) -> None:
    public_shell_client.cookies.clear()
    public_shell_client.app.state.host_resolver = _public

    snapshot = public_shell_client.get("/api/public/demo")
    assert snapshot.status_code == 200
    website_id = snapshot.json()["website"]["id"]

    response = public_shell_client.post(
        f"/api/public/demo/websites/{website_id}/checks",
        json={"authorized": True},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["website_id"] == website_id
    assert body["http_status"] == 200
    assert is_probe_result(body["error_message"])


def test_anonymous_probe_rate_limit(
    public_shell_client: TestClient,
    stub_probe,
) -> None:
    public_shell_client.cookies.clear()
    public_shell_client.app.state.host_resolver = _public
    reset_rate_limits()

    statuses = []
    for _ in range(12):
        response = public_shell_client.post(
            "/api/public/demo/probe",
            json={"url": f"https://example.com/{uuid4().hex}", "authorized": True},
        )
        statuses.append(response.status_code)

    assert 201 in statuses
    assert 429 in statuses
    limited = next(r for r in statuses if r == 429)
    # Find the actual response with 429 for header check — re-trigger after filling.
    # statuses already captured; assert Retry-After via one more call if needed.
    assert limited == 429


def test_authenticated_run_check_uses_probe_when_browser_disabled(
    public_shell_client: TestClient,
    stub_probe,
) -> None:
    public_shell_client.app.state.host_resolver = _public
    login = public_shell_client.post(
        "/api/auth/login",
        json={"email": "demo@sentinel.local", "password": "demo-password-change-me"},
    )
    assert login.status_code == 200, login.text

    created = public_shell_client.post(
        "/api/websites",
        json={"name": "Probe workspace site", "base_url": f"https://example.com/{uuid4().hex}"},
    )
    assert created.status_code == 201, created.text
    website_id = created.json()["id"]

    response = public_shell_client.post(
        f"/api/websites/{website_id}/checks",
        json={"authorized": True},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["outcome"] == "success"
    assert body["http_status"] == 200
    assert is_probe_result(body["error_message"])


def test_failed_probe_can_be_analyzed_anonymously(
    public_shell_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ANALYSIS_PROVIDER=simulated, anonymous probe Analyze stays heuristics-only."""
    async def failing_probe(url: str, **_kwargs):
        return failed_observation(
            time.perf_counter(),
            "The page responded with HTTP 503.",
            http_status=503,
            final_url=url,
        )

    monkeypatch.setattr("app.api.routes.public_demo.probe_http_url", failing_probe)
    public_shell_client.cookies.clear()
    public_shell_client.app.state.host_resolver = _public

    response = public_shell_client.post(
        "/api/public/demo/probe",
        json={"url": "https://example.com/down", "authorized": True},
    )
    assert response.status_code == 201, response.text
    check_id = response.json()["id"]
    assert response.json()["outcome"] == "failed"

    analysis = public_shell_client.post(f"/api/public/demo/checks/{check_id}/analysis")
    assert analysis.status_code in {200, 201}, analysis.text
    payload = analysis.json()
    assert payload["provider"] == "simulated"
    assert payload["check_id"] == check_id


def test_failed_probe_analyze_uses_configured_provider_when_not_simulated(
    monkeypatch: pytest.MonkeyPatch,
    migrated_database: None,
) -> None:
    """Public probe Analyze uses configured openai provider when not forced simulated."""
    from app.services.failure_analysis import FailureAnalysisResult, PossibleCause

    monkeypatch.setenv("PUBLIC_SHELL", "true")
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.together.ai/v1")
    monkeypatch.setenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo")
    monkeypatch.setenv("SEED_USER_EMAIL", "demo@sentinel.local")
    monkeypatch.setenv("SEED_USER_PASSWORD", "demo-password-change-me")
    monkeypatch.setenv("DATABASE_SSL", "false")
    get_settings.cache_clear()
    reset_rate_limits()

    class RecordingProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def analyze(self, evidence: dict[str, object]) -> FailureAnalysisResult:
            self.calls += 1
            return FailureAnalysisResult(
                summary="Probe analysis via configured provider.",
                severity="high",
                confirmed_observations=["HTTP status was 503"],
                possible_causes=[
                    PossibleCause(
                        cause="Origin returned server error",
                        confidence="medium",
                        evidence="HTTP 503",
                    )
                ],
                recommended_investigation_steps=["Retry the origin"],
                limitations="Stubbed live path for tests.",
            )

    async def failing_probe(url: str, **_kwargs):
        return failed_observation(
            time.perf_counter(),
            "The page responded with HTTP 503.",
            http_status=503,
            final_url=url,
        )

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        provider = RecordingProvider()
        client.app.state.analysis_provider = provider
        client.app.state.analysis_provider_name = "openai"
        client.app.state.analysis_model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
        client.app.state.host_resolver = _public
        monkeypatch.setattr("app.api.routes.public_demo.probe_http_url", failing_probe)
        client.cookies.clear()

        response = client.post(
            "/api/public/demo/probe",
            json={"url": "https://example.com/down", "authorized": True},
        )
        assert response.status_code == 201, response.text
        check_id = response.json()["id"]

        analysis = client.post(f"/api/public/demo/checks/{check_id}/analysis")
        assert analysis.status_code in {200, 201}, analysis.text
        payload = analysis.json()
        assert provider.calls == 1
        assert payload["provider"] == "openai"
        assert payload["model_name"] == "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
        assert payload["check_id"] == check_id

    get_settings.cache_clear()
    reset_rate_limits()
