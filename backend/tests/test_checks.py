"""Website check API. The runner is a fake, so these tests never open a site."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.results import CheckObservation, FailedRequestSummary


class ScriptedRunner:
    """Returns prepared observations and records every URL it was asked to open."""

    def __init__(self, observations: list[CheckObservation]) -> None:
        self.observations = list(observations)
        self.calls: list[str] = []

    async def run(self, url: str) -> CheckObservation:
        self.calls.append(url)
        if not self.observations:
            raise AssertionError("the check runner was called more times than scripted")
        return self.observations.pop(0)


class ExplodingRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, url: str) -> CheckObservation:
        self.calls.append(url)
        raise RuntimeError("postgresql+asyncpg://sentinel:super-secret@localhost:5432/sentinel")


def _observation(**overrides) -> CheckObservation:
    values: dict = {
        "outcome": "success",
        "http_status": 200,
        "page_title": "Checked page",
        "final_url": "http://8.8.8.8/checked",
        "duration_ms": 125,
        "console_errors": (),
        "failed_requests": (),
        "error_message": None,
    }
    values.update(overrides)
    return CheckObservation(**values)


def _install(client: TestClient, runner: ScriptedRunner | ExplodingRunner) -> None:
    client.app.state.check_runner = runner


def _create_website(client: TestClient, base_url: str) -> str:
    created = client.post(
        "/api/websites",
        json={"name": "Check target", "base_url": base_url},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _delete_website(client: TestClient, website_id: str) -> None:
    client.delete(f"/api/websites/{website_id}")


def test_successful_navigation_is_stored(registry_client: TestClient) -> None:
    runner = ScriptedRunner([_observation()])
    _install(registry_client, runner)
    website_id = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["outcome"] == "success"
        assert body["http_status"] == 200
        assert body["page_title"] == "Checked page"
        assert body["final_url"] == "http://8.8.8.8/checked"
        assert body["duration_ms"] == 125
        assert body["console_errors"] == []
        assert body["failed_requests"] == []
        assert body["error_message"] is None
        assert runner.calls

        fetched = registry_client.get(f"/api/checks/{body['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == body["id"]
    finally:
        _delete_website(registry_client, website_id)


def test_an_http_failure_is_stored_as_failed(registry_client: TestClient) -> None:
    runner = ScriptedRunner(
        [_observation(outcome="failed", http_status=503, page_title="Unavailable", error_message=None)]
    )
    _install(registry_client, runner)
    website_id = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["outcome"] == "failed"
        assert body["http_status"] == 503
        assert body["error_message"] == "The page responded with HTTP 503."
    finally:
        _delete_website(registry_client, website_id)


def test_a_navigation_timeout_is_stored(registry_client: TestClient) -> None:
    runner = ScriptedRunner(
        [
            _observation(
                outcome="failed",
                http_status=None,
                page_title=None,
                final_url=None,
                duration_ms=15_000,
                error_message="The check timed out before the page finished loading.",
            )
        ]
    )
    _install(registry_client, runner)
    website_id = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["outcome"] == "failed"
        assert body["http_status"] is None
        assert body["error_message"] == "The check timed out before the page finished loading."
        assert "Traceback" not in response.text
    finally:
        _delete_website(registry_client, website_id)


def test_console_errors_and_failed_requests_are_stored_without_secrets(
    registry_client: TestClient,
) -> None:
    runner = ScriptedRunner(
        [
            _observation(
                console_errors=("Authorization: Bearer super-secret", "Failed to load image"),
                failed_requests=(
                    FailedRequestSummary(
                        url="https://8.8.8.8/asset.js?token=super-secret",
                        error="net::ERR_FAILED",
                    ),
                ),
            )
        ]
    )
    _install(registry_client, runner)
    website_id = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert response.status_code == 201
        body = response.json()
        assert "super-secret" not in response.text
        assert body["console_errors"][0] == "Authorization: [redacted]"
        assert body["console_errors"][1] == "Failed to load image"
        assert body["failed_requests"] == [
            {"url": "https://8.8.8.8/asset.js", "error": "net::ERR_FAILED"}
        ]

        history = registry_client.get(f"/api/websites/{website_id}/checks")
        assert history.status_code == 200
        assert history.json()[0]["id"] == body["id"]
        assert "super-secret" not in history.text
    finally:
        _delete_website(registry_client, website_id)


def test_a_runner_exception_is_stored_without_its_text(registry_client: TestClient) -> None:
    runner = ExplodingRunner()
    _install(registry_client, runner)
    website_id = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["outcome"] == "failed"
        assert body["error_message"] == "The page could not be opened."
        assert "super-secret" not in response.text
        assert "RuntimeError" not in response.text
        assert "postgresql" not in response.text
    finally:
        _delete_website(registry_client, website_id)


def test_recent_history_is_newest_first_and_limited(registry_client: TestClient) -> None:
    runner = ScriptedRunner(
        [
            _observation(page_title="First"),
            _observation(page_title="Second"),
            _observation(page_title="Third"),
        ]
    )
    _install(registry_client, runner)
    website_id = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        for _ in range(3):
            created = registry_client.post(
                f"/api/websites/{website_id}/checks",
                json={"authorized": True},
            )
            assert created.status_code == 201

        history = registry_client.get(f"/api/websites/{website_id}/checks", params={"limit": 2})
        assert history.status_code == 200
        titles = [item["page_title"] for item in history.json()]
        assert titles == ["Third", "Second"]
    finally:
        _delete_website(registry_client, website_id)


def test_deleting_a_website_deletes_its_check_history(registry_client: TestClient) -> None:
    runner = ScriptedRunner([_observation()])
    _install(registry_client, runner)
    website_id = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    created = registry_client.post(
        f"/api/websites/{website_id}/checks",
        json={"authorized": True},
    )
    assert created.status_code == 201
    check_id = created.json()["id"]

    deleted = registry_client.delete(f"/api/websites/{website_id}")
    assert deleted.status_code == 204

    missing_check = registry_client.get(f"/api/checks/{check_id}")
    assert missing_check.status_code == 404
    assert missing_check.json()["detail"] == "Check not found."

    missing_history = registry_client.get(f"/api/websites/{website_id}/checks")
    assert missing_history.status_code == 404


def test_a_missing_website_is_not_checked(registry_client: TestClient) -> None:
    runner = ScriptedRunner([_observation()])
    _install(registry_client, runner)

    response = registry_client.post(
        f"/api/websites/{uuid4()}/checks",
        json={"authorized": True},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Website not found."
    assert runner.calls == []


def test_a_missing_check_is_not_found(registry_client: TestClient) -> None:
    response = registry_client.get(f"/api/checks/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Check not found."


@pytest.mark.parametrize("limit", [0, 51])
def test_history_limit_is_rejected_outside_one_to_fifty(registry_client: TestClient, limit: int) -> None:
    response = registry_client.get(f"/api/websites/{uuid4()}/checks", params={"limit": limit})

    assert response.status_code == 422


def test_an_id_that_is_not_a_uuid_is_rejected(client: TestClient) -> None:
    response = client.post("/api/websites/not-a-uuid/checks", json={"authorized": True})

    assert response.status_code == 422


def test_a_check_requires_authorization(registry_client: TestClient) -> None:
    runner = ScriptedRunner([_observation()])
    _install(registry_client, runner)
    website_id = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": False},
        )
        assert response.status_code == 422
        assert "authorized" in response.text.lower()
        assert runner.calls == []
    finally:
        _delete_website(registry_client, website_id)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://10.2.3.4/",
        "http://169.254.169.254/",
        "http://[::1]/",
        "http://metadata.google.internal/",
        "http://2130706433/",
    ],
)
def test_restricted_registered_urls_are_not_opened(
    registry_client: TestClient,
    base_url: str,
) -> None:
    runner = ScriptedRunner([_observation()])
    _install(registry_client, runner)
    suffix = uuid4().hex
    separator = "" if base_url.endswith("/") else "/"
    website_id = _create_website(registry_client, f"{base_url}{separator}{suffix}")
    try:
        response = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "This website cannot be checked because its address is not a public HTTP or HTTPS site."
        )
        assert runner.calls == []
        assert "postgresql" not in response.text
    finally:
        _delete_website(registry_client, website_id)


def test_a_hostname_that_resolves_to_a_private_address_is_not_opened(
    registry_client: TestClient,
) -> None:
    async def resolve_private(_host: str, _port: int):
        import ipaddress

        return [ipaddress.ip_address("192.168.1.9")]

    runner = ScriptedRunner([_observation()])
    _install(registry_client, runner)
    registry_client.app.state.host_resolver = resolve_private
    website_id = _create_website(registry_client, f"https://rebind.invalid/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert response.status_code == 422
        assert "not a public" in response.json()["detail"]
        assert runner.calls == []
    finally:
        _delete_website(registry_client, website_id)


def test_a_final_url_on_a_private_address_is_not_stored(registry_client: TestClient) -> None:
    runner = ScriptedRunner([_observation(final_url="http://127.0.0.1/admin")])
    _install(registry_client, runner)
    website_id = _create_website(registry_client, f"http://8.8.8.8/{uuid4().hex}")
    try:
        response = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["outcome"] == "failed"
        assert body["final_url"] is None
        assert "127.0.0.1" not in response.text
    finally:
        _delete_website(registry_client, website_id)
