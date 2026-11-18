"""Uptime / latency stats (MON-1)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.services.check_stats import CheckSample, summarize_checks
from app.services.results import CheckObservation


class ScriptedRunner:
    def __init__(self, observations: list[CheckObservation]) -> None:
        self.observations = list(observations)
        self.calls: list[str] = []

    async def run(self, url: str) -> CheckObservation:
        self.calls.append(url)
        if not self.observations:
            raise AssertionError("runner called more times than scripted")
        return self.observations.pop(0)


def _observation(**overrides) -> CheckObservation:
    values: dict = {
        "outcome": "success",
        "http_status": 200,
        "page_title": "Ok",
        "final_url": "http://8.8.8.8/ok",
        "duration_ms": 100,
        "console_errors": (),
        "failed_requests": (),
        "error_message": None,
    }
    values.update(overrides)
    return CheckObservation(**values)


def test_summarize_checks_computes_uptime_and_p95() -> None:
    website_id = uuid4()
    now = datetime.now(UTC)
    rows = [
        CheckSample(now, "success", 100, 200),
        CheckSample(now - timedelta(minutes=1), "failed", 400, 503),
        CheckSample(now - timedelta(minutes=2), "success", 120, 200),
        CheckSample(now - timedelta(minutes=3), "success", 200, 200),
    ]
    summary = summarize_checks(website_id, rows, window="7d", sample_limit=100)
    assert summary.check_count == 4
    assert summary.success_count == 3
    assert summary.failure_count == 1
    assert summary.uptime_percent == 75.0
    assert summary.avg_duration_ms == 205.0
    assert summary.p95_duration_ms == 400
    assert len(summary.points) == 4


def test_summarize_checks_empty_sample() -> None:
    summary = summarize_checks(uuid4(), [], window="24h", sample_limit=50)
    assert summary.check_count == 0
    assert summary.uptime_percent is None
    assert summary.avg_duration_ms is None
    assert summary.p95_duration_ms is None
    assert summary.points == ()


def test_website_stats_endpoint(registry_client: TestClient) -> None:
    runner = ScriptedRunner(
        [
            _observation(duration_ms=80),
            _observation(outcome="failed", http_status=503, duration_ms=300, page_title="Down"),
            _observation(duration_ms=90),
        ]
    )
    registry_client.app.state.check_runner = runner
    created = registry_client.post(
        "/api/websites",
        json={"name": "Stats site", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    try:
        for _ in range(3):
            response = registry_client.post(
                f"/api/websites/{website_id}/checks",
                json={"authorized": True},
            )
            assert response.status_code == 201

        stats = registry_client.get(f"/api/websites/{website_id}/stats?window=all")
        assert stats.status_code == 200
        body = stats.json()
        assert body["website_id"] == website_id
        assert body["check_count"] == 3
        assert body["success_count"] == 2
        assert body["failure_count"] == 1
        assert body["uptime_percent"] == 66.67
        assert body["avg_duration_ms"] is not None
        assert body["p95_duration_ms"] is not None
        assert len(body["points"]) == 3

        bad = registry_client.get(f"/api/websites/{website_id}/stats?window=year")
        assert bad.status_code == 422
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_dashboard_includes_website_stats(registry_client: TestClient) -> None:
    runner = ScriptedRunner([_observation(duration_ms=55)])
    registry_client.app.state.check_runner = runner
    created = registry_client.post(
        "/api/websites",
        json={"name": "Dash stats", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    try:
        check = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert check.status_code == 201
        dash = registry_client.get("/api/dashboard?stats_window=7d")
        assert dash.status_code == 200
        body = dash.json()
        assert body["stats_window"] == "7d"
        assert "website_stats" in body
        match = next(item for item in body["website_stats"] if item["website_id"] == website_id)
        assert match["check_count"] >= 1
        assert match["uptime_percent"] == 100.0
        health = body["health"]
        assert health["website_count"] >= 1
        assert health["sites_with_checks"] >= 1
        assert health["avg_uptime_percent"] is not None
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_stats_require_auth(client: TestClient) -> None:
    response = client.get(f"/api/websites/{uuid4()}/stats")
    assert response.status_code == 401
