"""MON-3: capped check-history windows; dashboard uses the same window."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.check_stats import (
    clamp_history_limit,
    max_history_limit,
    parse_window,
    window_since,
)
from app.services.results import CheckObservation


class ScriptedRunner:
    def __init__(self, observations: list[CheckObservation]) -> None:
        self.observations = list(observations)

    async def run(self, url: str) -> CheckObservation:
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


def _age_check(check_id: str, *, days: int) -> None:
    """Bump created_at via a fresh asyncpg connection (not the TestClient pool)."""
    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    aged = datetime.now(UTC) - timedelta(days=days)

    async def _run() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                "UPDATE website_checks SET created_at = $1 WHERE id = $2::uuid",
                aged,
                check_id,
            )
        finally:
            await conn.close()

    asyncio.run(_run())


def test_window_helpers_refuse_unknown_and_cap_history() -> None:
    assert parse_window("24h") == "24h"
    assert parse_window("7d") == "7d"
    assert parse_window("all") == "all"
    try:
        parse_window("year")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "24h" in str(exc)
    assert window_since("all") is None
    since_24h = window_since("24h")
    assert since_24h is not None
    assert since_24h <= datetime.now(UTC)
    assert clamp_history_limit(None) == 20
    assert clamp_history_limit(50) == max_history_limit()
    try:
        clamp_history_limit(51)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_list_checks_window_filters_and_caps(registry_client: TestClient) -> None:
    runner = ScriptedRunner([_observation(), _observation(duration_ms=120)])
    registry_client.app.state.check_runner = runner
    created = registry_client.post(
        "/api/websites",
        json={"name": "History windows", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    try:
        first = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        second = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert first.status_code == 201
        assert second.status_code == 201
        old_id = first.json()["id"]
        new_id = second.json()["id"]
        _age_check(old_id, days=3)

        within_day = registry_client.get(
            f"/api/websites/{website_id}/checks",
            params={"window": "24h", "limit": 20},
        )
        assert within_day.status_code == 200
        day_ids = {item["id"] for item in within_day.json()}
        assert new_id in day_ids
        assert old_id not in day_ids

        within_week = registry_client.get(
            f"/api/websites/{website_id}/checks",
            params={"window": "7d", "limit": 20},
        )
        assert within_week.status_code == 200
        week_ids = {item["id"] for item in within_week.json()}
        assert old_id in week_ids
        assert new_id in week_ids

        all_rows = registry_client.get(
            f"/api/websites/{website_id}/checks",
            params={"window": "all", "limit": 1},
        )
        assert all_rows.status_code == 200
        assert len(all_rows.json()) == 1
        assert all_rows.json()[0]["id"] == new_id

        bad = registry_client.get(
            f"/api/websites/{website_id}/checks",
            params={"window": "year"},
        )
        assert bad.status_code == 422

        over = registry_client.get(
            f"/api/websites/{website_id}/checks",
            params={"limit": 51},
        )
        assert over.status_code == 422
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_dashboard_recent_checks_use_stats_window(registry_client: TestClient) -> None:
    runner = ScriptedRunner([_observation(), _observation(duration_ms=90)])
    registry_client.app.state.check_runner = runner
    created = registry_client.post(
        "/api/websites",
        json={"name": "Dash history", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    try:
        first = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        second = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert first.status_code == 201 and second.status_code == 201
        old_id = first.json()["id"]
        new_id = second.json()["id"]
        _age_check(old_id, days=3)

        day = registry_client.get("/api/dashboard", params={"stats_window": "24h"})
        assert day.status_code == 200
        body = day.json()
        assert body["stats_window"] == "24h"
        assert body["history_window"] == "24h"
        assert body["recent_check_limit"] == 20
        recent_ids = {item["id"] for item in body["recent_checks"] if item["website_id"] == website_id}
        assert new_id in recent_ids
        assert old_id not in recent_ids

        week = registry_client.get("/api/dashboard", params={"stats_window": "7d"})
        assert week.status_code == 200
        week_ids = {
            item["id"]
            for item in week.json()["recent_checks"]
            if item["website_id"] == website_id
        }
        assert old_id in week_ids
        assert new_id in week_ids
    finally:
        registry_client.delete(f"/api/websites/{website_id}")
