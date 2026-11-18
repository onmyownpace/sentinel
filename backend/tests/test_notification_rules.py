"""AUTO-2 notification rules and intents."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.services.check_stats import CheckSample
from app.services.monitoring_state import evaluate_monitoring_state
from app.services.notification_rules import NotificationRules, evaluate_notification_intents
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


def test_intents_respect_disabled_fail_rule() -> None:
    state = evaluate_monitoring_state(
        uuid4(),
        [_sample("failed", 10)],
        latency_threshold_ms=None,
        failure_threshold_count=1,
    )
    intents = evaluate_notification_intents(
        state,
        NotificationRules(notify_on_fail=False, notify_on_recover=True, notify_on_latency=True),
    )
    assert state.still_failing is True
    assert intents.should_notify_fail is False
    assert intents.should_notify_recover is False
    assert intents.should_notify_latency is False


def test_intents_latency_and_recover() -> None:
    degraded = evaluate_monitoring_state(
        uuid4(),
        [_sample("success", 5000)],
        latency_threshold_ms=1000,
        failure_threshold_count=1,
    )
    latency_intents = evaluate_notification_intents(
        degraded,
        NotificationRules(notify_on_fail=True, notify_on_recover=True, notify_on_latency=True),
    )
    assert latency_intents.should_notify_latency is True
    assert latency_intents.should_notify_fail is False

    recovered = evaluate_monitoring_state(
        uuid4(),
        [_sample("success", 80), _sample("failed", 200, minutes_ago=1)],
        latency_threshold_ms=None,
        failure_threshold_count=1,
    )
    recover_intents = evaluate_notification_intents(
        recovered,
        NotificationRules(notify_on_fail=True, notify_on_recover=True, notify_on_latency=True),
    )
    assert recover_intents.should_notify_recover is True
    assert recover_intents.should_notify_fail is False


def test_patch_config_surface_fields_together(registry_client: TestClient) -> None:
    """DASH-3: enrollment, thresholds, and notify rules share one PATCH surface."""
    created = registry_client.post(
        "/api/websites",
        json={"name": "Config surface", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    try:
        patched = registry_client.patch(
            f"/api/websites/{website_id}",
            json={
                "monitoring_enabled": True,
                "latency_threshold_ms": 1500,
                "failure_threshold_count": 3,
                "notify_on_fail": False,
                "notify_on_recover": True,
                "notify_on_latency": False,
            },
        )
        assert patched.status_code == 200
        body = patched.json()
        assert body["monitoring_enabled"] is True
        assert body["latency_threshold_ms"] == 1500
        assert body["failure_threshold_count"] == 3
        assert body["notify_on_fail"] is False
        assert body["notify_on_recover"] is True
        assert body["notify_on_latency"] is False

        fetched = registry_client.get(f"/api/websites/{website_id}")
        assert fetched.status_code == 200
        assert fetched.json() == body
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_patch_rules_and_monitoring_state_intents(registry_client: TestClient) -> None:
    runner = ScriptedRunner(
        [
            _observation(outcome="failed", http_status=503, duration_ms=200),
            _observation(duration_ms=90),
        ]
    )
    registry_client.app.state.check_runner = runner
    created = registry_client.post(
        "/api/websites",
        json={"name": "Notify site", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    assert created.json()["notify_on_fail"] is True
    try:
        silenced = registry_client.patch(
            f"/api/websites/{website_id}",
            json={"notify_on_fail": False, "notify_on_recover": True, "notify_on_latency": False},
        )
        assert silenced.status_code == 200
        assert silenced.json()["notify_on_fail"] is False
        assert silenced.json()["notify_on_latency"] is False

        fail = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert fail.status_code == 201
        failing = registry_client.get(f"/api/websites/{website_id}/monitoring-state")
        assert failing.status_code == 200
        body = failing.json()
        assert body["still_failing"] is True
        assert body["should_notify_fail"] is False
        assert body["notify_on_fail"] is False

        ok = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert ok.status_code == 201
        recovered = registry_client.get(f"/api/websites/{website_id}/monitoring-state")
        assert recovered.status_code == 200
        recovered_body = recovered.json()
        assert recovered_body["recovered"] is True
        assert recovered_body["should_notify_recover"] is True
    finally:
        registry_client.delete(f"/api/websites/{website_id}")
