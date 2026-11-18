"""BROW-3 scenario library: wraps journeys; on-demand run with fake runner."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.services.journey_runner import JourneyObservation, StepResult
from app.services.journey_steps import JourneyStep


class ScriptedJourneyRunner:
    def __init__(self, observations: list[JourneyObservation]) -> None:
        self.observations = list(observations)
        self.calls: list[list[JourneyStep]] = []

    async def run(
        self,
        *,
        steps: list[JourneyStep],
        website_base_url: str,
    ) -> JourneyObservation:
        self.calls.append(list(steps))
        if not self.observations:
            raise AssertionError("journey runner called more times than scripted")
        return self.observations.pop(0)


def _create_site_and_journey(client: TestClient) -> tuple[str, str]:
    created_site = client.post(
        "/api/websites",
        json={"name": "Scenario site", "base_url": f"https://example.com/{uuid4().hex}"},
    )
    assert created_site.status_code == 201, created_site.text
    website_id = created_site.json()["id"]
    journey = client.post(
        f"/api/websites/{website_id}/journeys",
        json={
            "name": "Underlying path",
            "steps": [
                {"op": "navigate", "url": "/"},
                {"op": "assert_url_contains", "value": "example.com"},
            ],
        },
    )
    assert journey.status_code == 201, journey.text
    return website_id, journey.json()["id"]


def test_create_run_list_scenario_with_fake_runner(registry_client: TestClient) -> None:
    observation = JourneyObservation(
        outcome="success",
        duration_ms=95,
        step_results=(
            StepResult(0, "navigate", True, "Navigated."),
            StepResult(1, "assert_url_contains", True, "URL matched."),
        ),
        error_message=None,
        final_url="https://example.com/ok",
    )
    runner = ScriptedJourneyRunner([observation])
    registry_client.app.state.journey_runner = runner

    website_id, journey_id = _create_site_and_journey(registry_client)
    try:
        created = registry_client.post(
            f"/api/websites/{website_id}/scenarios",
            json={
                "name": "Login smoke (library)",
                "journey_id": journey_id,
                "description": "Reusable login path",
                "schedule_eligible": False,
            },
        )
        assert created.status_code == 201, created.text
        scenario = created.json()
        assert scenario["name"] == "Login smoke (library)"
        assert scenario["journey_id"] == journey_id
        assert scenario["schedule_eligible"] is False
        assert scenario["description"] == "Reusable login path"

        listed = registry_client.get(f"/api/websites/{website_id}/scenarios")
        assert listed.status_code == 200
        assert any(item["id"] == scenario["id"] for item in listed.json())

        run = registry_client.post(
            f"/api/scenarios/{scenario['id']}/runs",
            json={"authorized": True},
        )
        assert run.status_code == 201, run.text
        body = run.json()
        assert body["outcome"] == "success"
        assert body["scenario_id"] == scenario["id"]
        assert body["journey_id"] == journey_id
        assert body["duration_ms"] == 95
        assert len(body["step_results"]) == 2
        assert runner.calls

        history = registry_client.get(f"/api/scenarios/{scenario['id']}/runs")
        assert history.status_code == 200
        assert len(history.json()) >= 1

        fetched = registry_client.get(f"/api/scenario-runs/{body['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == body["id"]

        # Journeys and one-shot checks remain separate tables.
        journeys = registry_client.get(f"/api/websites/{website_id}/journeys")
        assert journeys.status_code == 200
        assert any(item["id"] == journey_id for item in journeys.json())
        checks = registry_client.get(f"/api/websites/{website_id}/checks")
        assert checks.status_code == 200
        assert checks.json() == []
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_scenario_rejects_foreign_journey(registry_client: TestClient) -> None:
    website_a, _ = _create_site_and_journey(registry_client)
    website_b, journey_b = _create_site_and_journey(registry_client)
    try:
        denied = registry_client.post(
            f"/api/websites/{website_a}/scenarios",
            json={
                "name": "Wrong site journey",
                "journey_id": journey_b,
            },
        )
        assert denied.status_code == 422
        assert "journey" in denied.json()["detail"].lower()
    finally:
        registry_client.delete(f"/api/websites/{website_a}")
        registry_client.delete(f"/api/websites/{website_b}")


def test_scenario_name_unique_per_website(registry_client: TestClient) -> None:
    website_id, journey_id = _create_site_and_journey(registry_client)
    try:
        first = registry_client.post(
            f"/api/websites/{website_id}/scenarios",
            json={"name": "Dup name", "journey_id": journey_id},
        )
        assert first.status_code == 201, first.text
        second = registry_client.post(
            f"/api/websites/{website_id}/scenarios",
            json={"name": "Dup name", "journey_id": journey_id},
        )
        assert second.status_code == 409
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_scenario_run_requires_authorization(registry_client: TestClient) -> None:
    website_id, journey_id = _create_site_and_journey(registry_client)
    try:
        scenario = registry_client.post(
            f"/api/websites/{website_id}/scenarios",
            json={"name": "Needs ack", "journey_id": journey_id},
        )
        assert scenario.status_code == 201, scenario.text
        denied = registry_client.post(
            f"/api/scenarios/{scenario.json()['id']}/runs",
            json={"authorized": False},
        )
        assert denied.status_code == 422
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_scenario_patch_and_delete(registry_client: TestClient) -> None:
    website_id, journey_id = _create_site_and_journey(registry_client)
    second_journey = registry_client.post(
        f"/api/websites/{website_id}/journeys",
        json={
            "name": "Alt path",
            "steps": [{"op": "navigate", "url": "/alt"}],
        },
    )
    assert second_journey.status_code == 201, second_journey.text
    alt_id = second_journey.json()["id"]
    try:
        created = registry_client.post(
            f"/api/websites/{website_id}/scenarios",
            json={
                "name": "Patch me",
                "journey_id": journey_id,
                "schedule_eligible": False,
            },
        )
        assert created.status_code == 201, created.text
        scenario_id = created.json()["id"]

        patched = registry_client.patch(
            f"/api/scenarios/{scenario_id}",
            json={
                "name": "Patched library",
                "description": "Updated note",
                "journey_id": alt_id,
                "schedule_eligible": True,
            },
        )
        assert patched.status_code == 200, patched.text
        body = patched.json()
        assert body["name"] == "Patched library"
        assert body["description"] == "Updated note"
        assert body["journey_id"] == alt_id
        assert body["schedule_eligible"] is True

        deleted = registry_client.delete(f"/api/scenarios/{scenario_id}")
        assert deleted.status_code == 204
        missing = registry_client.get(f"/api/scenarios/{scenario_id}")
        assert missing.status_code == 404
    finally:
        registry_client.delete(f"/api/websites/{website_id}")
