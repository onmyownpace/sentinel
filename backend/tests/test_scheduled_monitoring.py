"""Opt-in scheduled monitoring: enrollment, token gate, and n8n workflow shape."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
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


def _install_runner(client: TestClient, runner: ScriptedRunner) -> None:
    client.app.state.check_runner = runner


def _create_website(client: TestClient, base_url: str) -> dict:
    created = client.post(
        "/api/websites",
        json={"name": "Schedule target", "base_url": base_url},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["monitoring_enabled"] is False
    return body


def test_new_website_is_not_enrolled(registry_client: TestClient) -> None:
    website = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        fetched = registry_client.get(f"/api/websites/{website['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["monitoring_enabled"] is False
    finally:
        registry_client.delete(f"/api/websites/{website['id']}")


def test_monitoring_toggle_and_filter(registry_client: TestClient) -> None:
    suffix = uuid4().hex
    a = _create_website(registry_client, f"http://8.8.8.8/{suffix}/a")
    b = _create_website(registry_client, f"http://8.8.8.8/{suffix}/b")
    try:
        enabled = registry_client.patch(
            f"/api/websites/{a['id']}",
            json={"monitoring_enabled": True},
        )
        assert enabled.status_code == 200
        assert enabled.json()["monitoring_enabled"] is True

        enrolled = registry_client.get("/api/websites?monitoring=true")
        assert enrolled.status_code == 200
        ids = {item["id"] for item in enrolled.json()}
        assert a["id"] in ids
        assert b["id"] not in ids

        not_enrolled = registry_client.get("/api/websites?monitoring=false")
        false_ids = {item["id"] for item in not_enrolled.json()}
        assert b["id"] in false_ids
        assert a["id"] not in false_ids
    finally:
        registry_client.delete(f"/api/websites/{a['id']}")
        registry_client.delete(f"/api/websites/{b['id']}")


def test_scheduled_check_requires_configured_token(
    registry_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Empty string overrides .env; delenv alone still leaves the file value.
    monkeypatch.setenv("SCHEDULE_CHECK_TOKEN", "")
    get_settings.cache_clear()
    website = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        registry_client.patch(
            f"/api/websites/{website['id']}",
            json={"monitoring_enabled": True},
        )
        response = registry_client.post(
            f"/api/websites/{website['id']}/scheduled-checks",
            headers={"X-Schedule-Check-Token": "anything"},
        )
        assert response.status_code == 503
        assert "SCHEDULE_CHECK_TOKEN" in response.json()["detail"]
    finally:
        registry_client.delete(f"/api/websites/{website['id']}")
        get_settings.cache_clear()


def test_scheduled_check_rejects_wrong_token(
    registry_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCHEDULE_CHECK_TOKEN", "correct-token-value")
    get_settings.cache_clear()
    runner = ScriptedRunner([_observation()])
    _install_runner(registry_client, runner)
    website = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        registry_client.patch(
            f"/api/websites/{website['id']}",
            json={"monitoring_enabled": True},
        )
        missing = registry_client.post(f"/api/websites/{website['id']}/scheduled-checks")
        assert missing.status_code == 401
        wrong = registry_client.post(
            f"/api/websites/{website['id']}/scheduled-checks",
            headers={"X-Schedule-Check-Token": "wrong-token-value"},
        )
        assert wrong.status_code == 401
        assert runner.calls == []
    finally:
        registry_client.delete(f"/api/websites/{website['id']}")
        get_settings.cache_clear()


def test_scheduled_check_requires_enrollment(
    registry_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCHEDULE_CHECK_TOKEN", "schedule-secret")
    get_settings.cache_clear()
    runner = ScriptedRunner([_observation()])
    _install_runner(registry_client, runner)
    website = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website['id']}/scheduled-checks",
            headers={"X-Schedule-Check-Token": "schedule-secret"},
        )
        assert response.status_code == 422
        assert "not enrolled" in response.json()["detail"].lower()
        assert runner.calls == []
    finally:
        registry_client.delete(f"/api/websites/{website['id']}")
        get_settings.cache_clear()


def test_scheduled_check_runs_when_enrolled_and_token_matches(
    registry_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCHEDULE_CHECK_TOKEN", "schedule-secret")
    get_settings.cache_clear()
    runner = ScriptedRunner([_observation(outcome="failed", http_status=503, page_title="Down")])
    _install_runner(registry_client, runner)
    website = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        registry_client.patch(
            f"/api/websites/{website['id']}",
            json={"monitoring_enabled": True},
        )
        response = registry_client.post(
            f"/api/websites/{website['id']}/scheduled-checks",
            headers={"X-Schedule-Check-Token": "schedule-secret"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["outcome"] == "failed"
        assert body["http_status"] == 503
        assert len(runner.calls) == 1
    finally:
        registry_client.delete(f"/api/websites/{website['id']}")
        get_settings.cache_clear()


def test_manual_check_still_works_without_schedule_token(
    registry_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCHEDULE_CHECK_TOKEN", raising=False)
    get_settings.cache_clear()
    runner = ScriptedRunner([_observation()])
    _install_runner(registry_client, runner)
    website = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website['id']}/checks",
            json={"authorized": True},
        )
        assert response.status_code == 201
        assert response.json()["outcome"] == "success"
    finally:
        registry_client.delete(f"/api/websites/{website['id']}")
        get_settings.cache_clear()


def scheduled_workflow() -> dict:
    path = (
        Path(__file__).resolve().parents[2]
        / "n8n"
        / "workflows"
        / "scheduled-website-checks.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_scheduled_workflow_shape() -> None:
    document = scheduled_workflow()
    nodes = document["nodes"]
    by_name = {node["name"]: node for node in nodes}
    types = {node["type"] for node in nodes}

    assert document["active"] is False
    assert document["name"] == "Sentinel scheduled website checks"
    assert "n8n-nodes-base.scheduleTrigger" in types
    assert "n8n-nodes-base.manualTrigger" not in types

    schedule = by_name["Every 6 hours"]["parameters"]["rule"]["interval"][0]
    assert schedule["field"] == "hours"
    assert schedule["hoursInterval"] == 6

    assignments = {
        item["name"]: item["value"]
        for item in by_name["API address"]["parameters"]["assignments"]["assignments"]
    }
    assert assignments["apiBase"] == "http://host.docker.internal:8000"
    assert assignments["scheduleToken"] == "change-me-schedule-token"
    assert assignments["automationToken"] == "change-me-automation-token"
    assert assignments["webhookUrl"] == ""

    http_nodes = [node for node in nodes if node["type"] == "n8n-nodes-base.httpRequest"]
    assert [node["parameters"]["method"] for node in http_nodes] == ["GET", "POST", "GET", "POST"]
    assert "monitoring=true" in http_nodes[0]["parameters"]["url"]
    list_headers = http_nodes[0]["parameters"]["headerParameters"]["parameters"]
    assert any(item["name"] == "X-Automation-Token" for item in list_headers)
    assert "/scheduled-checks" in http_nodes[1]["parameters"]["url"]
    headers = http_nodes[1]["parameters"]["headerParameters"]["parameters"]
    assert any(item["name"] == "X-Schedule-Check-Token" for item in headers)
    assert "/monitoring-state" in http_nodes[2]["parameters"]["url"]
    state_headers = http_nodes[2]["parameters"]["headerParameters"]["parameters"]
    assert any(item["name"] == "X-Automation-Token" for item in state_headers)
    deliver = by_name["Deliver draft"]
    assert deliver["parameters"]["method"] == "POST"
    assert "webhookUrl" in deliver["parameters"]["url"]
    assert deliver.get("onError") == "continueRegularOutput"

    rendered = json.dumps(document).lower()
    assert "gmail" not in rendered
    assert "sendemail" not in rendered
    assert "n8n-nodes-base.emailsend" not in types
    assert "openai.com" not in rendered
    assert "n8n-nodes-base.openai" not in types
    assert "postgresql" not in rendered
    assert "should_notify_fail" in rendered
    assert "should_notify_latency" in rendered
    assert "should_notify_recover" in rendered

    assert document["connections"]["Run scheduled check"]["main"][0][0]["node"] == "Read monitoring state"
    assert document["connections"]["Notify on fail"]["main"][0][0]["node"] == "Failure draft"
    assert document["connections"]["Notify on fail"]["main"][1][0]["node"] == "Notify on latency"
    assert document["connections"]["Notify on latency"]["main"][0][0]["node"] == "Latency draft"
    assert document["connections"]["Notify on latency"]["main"][1][0]["node"] == "Notify on recover"
    assert document["connections"]["Notify on recover"]["main"][0][0]["node"] == "Recovery draft"
    assert document["connections"]["Notify on recover"]["main"][1] == []
    assert document["connections"]["Failure draft"]["main"][0][0]["node"] == "Webhook configured"
    assert document["connections"]["Latency draft"]["main"][0][0]["node"] == "Webhook configured"
    assert document["connections"]["Recovery draft"]["main"][0][0]["node"] == "Webhook configured"
    assert document["connections"]["Webhook configured"]["main"][0][0]["node"] == "Deliver draft"
    assert document["connections"]["Webhook configured"]["main"][1] == []
    assert document["settings"]["executionOrder"] == "v1"
