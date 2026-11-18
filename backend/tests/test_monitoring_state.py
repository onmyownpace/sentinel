"""MON-2 thresholds and recovery monitoring state."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.services.check_stats import CheckSample
from app.services.monitoring_state import evaluate_monitoring_state
from app.services.results import CheckObservation


class ScriptedRunner:
    def __init__(self, observations: list[CheckObservation]) -> None:
        self.observations = list(observations)

    async def run(self, url: str) -> CheckObservation:
        if not self.observations:
            raise AssertionError("runner called more times than scripted")
        return self.observations.pop(0)


def _sample(outcome: str, duration_ms: int, *, minutes_ago: int = 0) -> CheckSample:
    return CheckSample(
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        outcome=outcome,
        duration_ms=duration_ms,
        http_status=200 if outcome == "success" else 503,
    )


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


def test_evaluate_marks_recovered_after_failure_then_success() -> None:
    website_id = uuid4()
    state = evaluate_monitoring_state(
        website_id,
        [_sample("success", 120), _sample("failed", 400, minutes_ago=1)],
        latency_threshold_ms=None,
        failure_threshold_count=1,
    )
    assert state.status == "recovered"
    assert state.recovered is True
    assert state.still_failing is False
    assert state.consecutive_failures == 0


def test_evaluate_still_failing_respects_consecutive_threshold() -> None:
    website_id = uuid4()
    rows = [
        _sample("failed", 10),
        _sample("failed", 10, minutes_ago=1),
        _sample("success", 10, minutes_ago=2),
    ]
    one = evaluate_monitoring_state(
        website_id, rows, latency_threshold_ms=None, failure_threshold_count=3
    )
    assert one.still_failing is False
    assert one.status == "failing"
    assert one.consecutive_failures == 2

    two = evaluate_monitoring_state(
        website_id, rows, latency_threshold_ms=None, failure_threshold_count=2
    )
    assert two.still_failing is True
    assert two.status == "failing"


def test_evaluate_latency_breach_is_degraded() -> None:
    state = evaluate_monitoring_state(
        uuid4(),
        [_sample("success", 5000)],
        latency_threshold_ms=1000,
        failure_threshold_count=1,
    )
    assert state.latency_breached is True
    assert state.still_failing is True
    assert state.status == "degraded"


def test_thresholds_patch_and_monitoring_state_endpoint(registry_client: TestClient) -> None:
    runner = ScriptedRunner(
        [
            _observation(outcome="failed", http_status=503, duration_ms=200),
            _observation(duration_ms=90),
        ]
    )
    registry_client.app.state.check_runner = runner
    created = registry_client.post(
        "/api/websites",
        json={"name": "Threshold site", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    try:
        patched = registry_client.patch(
            f"/api/websites/{website_id}",
            json={"latency_threshold_ms": 2000, "failure_threshold_count": 1},
        )
        assert patched.status_code == 200
        assert patched.json()["latency_threshold_ms"] == 2000
        assert patched.json()["failure_threshold_count"] == 1

        fail = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert fail.status_code == 201
        failing = registry_client.get(f"/api/websites/{website_id}/monitoring-state")
        assert failing.status_code == 200
        body = failing.json()
        assert body["still_failing"] is True
        assert body["recovered"] is False
        assert body["status"] == "failing"

        ok = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert ok.status_code == 201
        recovered = registry_client.get(f"/api/websites/{website_id}/monitoring-state")
        assert recovered.status_code == 200
        recovered_body = recovered.json()
        assert recovered_body["recovered"] is True
        assert recovered_body["still_failing"] is False
        assert recovered_body["status"] == "recovered"

        cleared = registry_client.patch(
            f"/api/websites/{website_id}",
            json={"latency_threshold_ms": None, "failure_threshold_count": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["latency_threshold_ms"] is None
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_monitoring_state_requires_auth(client: TestClient) -> None:
    response = client.get(f"/api/websites/{uuid4()}/monitoring-state")
    assert response.status_code == 401
