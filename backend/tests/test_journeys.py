"""BROW-2 journeys: step validation + API with fake runner."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.services.journey_runner import JourneyObservation, StepResult
from app.services.journey_steps import JourneyStep, validate_and_normalize_steps


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


def test_validate_steps_requires_navigate_first() -> None:
    try:
        validate_and_normalize_steps(
            [{"op": "click", "selector": "button"}],
            website_base_url="https://example.com",
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "navigate" in str(exc).lower()


def test_validate_steps_resolves_relative_navigate() -> None:
    steps = validate_and_normalize_steps(
        [
            {"op": "navigate", "url": "/login"},
            {"op": "fill", "selector": "#email", "value": "a@b.c"},
            {"op": "assert_url_contains", "value": "/login"},
        ],
        website_base_url="https://example.com/app",
    )
    assert steps[0].url == "https://example.com/app/login"
    assert steps[1].op == "fill"
    assert steps[2].op == "assert_url_contains"


def test_create_run_list_journey_with_fake_runner(registry_client: TestClient) -> None:
    observation = JourneyObservation(
        outcome="success",
        duration_ms=120,
        step_results=(
            StepResult(0, "navigate", True, "Navigated."),
            StepResult(1, "assert_url_contains", True, "URL matched."),
        ),
        error_message=None,
        final_url="https://example.com/ok",
    )
    runner = ScriptedJourneyRunner([observation])
    registry_client.app.state.journey_runner = runner

    created_site = registry_client.post(
        "/api/websites",
        json={"name": "Journey site", "base_url": f"https://example.com/{uuid4().hex}"},
    )
    assert created_site.status_code == 201
    website_id = created_site.json()["id"]
    try:
        created = registry_client.post(
            f"/api/websites/{website_id}/journeys",
            json={
                "name": "Smoke path",
                "steps": [
                    {"op": "navigate", "url": "/"},
                    {"op": "assert_url_contains", "value": "example.com"},
                ],
            },
        )
        assert created.status_code == 201, created.text
        journey = created.json()
        assert journey["name"] == "Smoke path"
        assert journey["steps"][0]["op"] == "navigate"
        assert journey["steps"][0]["url"].startswith("https://example.com/")

        listed = registry_client.get(f"/api/websites/{website_id}/journeys")
        assert listed.status_code == 200
        assert any(item["id"] == journey["id"] for item in listed.json())

        run = registry_client.post(
            f"/api/journeys/{journey['id']}/runs",
            json={"authorized": True},
        )
        assert run.status_code == 201, run.text
        body = run.json()
        assert body["outcome"] == "success"
        assert body["duration_ms"] == 120
        assert len(body["step_results"]) == 2
        assert runner.calls

        history = registry_client.get(f"/api/journeys/{journey['id']}/runs")
        assert history.status_code == 200
        assert len(history.json()) >= 1

        fetched = registry_client.get(f"/api/journey-runs/{body['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == body["id"]

        # One-shot checks table is untouched by journeys.
        checks = registry_client.get(f"/api/websites/{website_id}/checks")
        assert checks.status_code == 200
        assert checks.json() == []
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_journey_run_requires_authorization(registry_client: TestClient) -> None:
    created_site = registry_client.post(
        "/api/websites",
        json={"name": "Auth journey", "base_url": f"https://example.com/{uuid4().hex}"},
    )
    assert created_site.status_code == 201, created_site.text
    website_id = created_site.json()["id"]
    try:
        journey = registry_client.post(
            f"/api/websites/{website_id}/journeys",
            json={
                "name": "Needs ack",
                "steps": [{"op": "navigate", "url": "/"}],
            },
        )
        assert journey.status_code == 201, journey.text
        denied = registry_client.post(
            f"/api/journeys/{journey.json()['id']}/runs",
            json={"authorized": False},
        )
        assert denied.status_code == 422
    finally:
        registry_client.delete(f"/api/websites/{website_id}")
