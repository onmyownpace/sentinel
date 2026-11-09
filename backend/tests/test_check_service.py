"""Browser-check helpers that do not launch Chromium or open a socket."""

import asyncio

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.services.browser import PlaywrightCheckService
from app.services.results import (
    CHECK_TIMED_OUT,
    CheckObservation,
    FailedRequestSummary,
    redact,
    sanitize_observation,
    sanitize_url,
)


def test_navigation_timeout_must_stay_between_one_and_sixty_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHECK_NAVIGATION_TIMEOUT_SECONDS", "0")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError):
            get_settings()
    finally:
        get_settings.cache_clear()


async def test_a_check_stops_when_its_budget_expires() -> None:
    service = PlaywrightCheckService(navigation_timeout_ms=15_000, budget_seconds=0.05)

    async def hang(_url: str, _started: float) -> CheckObservation:
        await asyncio.sleep(5)
        raise AssertionError("the check ran past its budget")

    service._run = hang  # type: ignore[method-assign]
    result = await service.run("https://8.8.8.8/")

    assert result.outcome == "failed"
    assert result.error_message == CHECK_TIMED_OUT
    assert result.duration_ms < 5_000


def test_secrets_are_removed_before_a_result_can_be_stored() -> None:
    raw = CheckObservation(
        outcome="success",
        http_status=200,
        page_title="Authorization: Bearer super-secret",
        final_url="https://user:password@8.8.8.8/callback?token=super-secret",
        duration_ms=40,
        console_errors=(
            "postgresql+asyncpg://sentinel:super-secret@localhost:5432/sentinel",
            "Cookie: session=super-secret",
        ),
        failed_requests=(
            FailedRequestSummary(
                url="https://8.8.8.8/collect?token=super-secret",
                error="Bearer super-secret",
            ),
        ),
        error_message=None,
    )

    cleaned = sanitize_observation(raw)
    rendered = repr(cleaned)

    assert "super-secret" not in rendered
    assert "postgresql" not in rendered
    assert "password" not in cleaned.final_url if cleaned.final_url else True
    assert cleaned.final_url is None
    assert cleaned.failed_requests[0].url == "https://8.8.8.8/collect"
    assert "token=" not in cleaned.failed_requests[0].url
    assert cleaned.console_errors[0] == "[redacted-url]"


def test_a_public_url_keeps_its_path_and_drops_the_query() -> None:
    assert sanitize_url("https://8.8.8.8/docs/?token=abc#part") == "https://8.8.8.8/docs/"
    assert sanitize_url("file:///tmp/secret") == "non-http resource"


def test_redact_replaces_a_labeled_secret_without_keeping_the_value() -> None:
    cleaned = redact("password: hunter2")
    assert "hunter2" not in cleaned
    assert "password: [redacted]" in cleaned
