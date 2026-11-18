"""Per-website uptime summaries (MON-1) and monitoring state (MON-2)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_session, get_visible_website, require_actor
from app.models.website_check import WebsiteCheck
from app.services.check_stats import (
    CheckSample,
    CheckStatsSummary,
    clamp_sample_limit,
    parse_window,
    summarize_checks,
    window_since,
)
from app.services.monitoring_state import evaluate_monitoring_state
from app.services.notification_rules import NotificationRules, evaluate_notification_intents

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)


class StatsPoint(BaseModel):
    created_at: datetime
    outcome: str
    duration_ms: int
    http_status: int | None


class WebsiteStatsResponse(BaseModel):
    website_id: UUID
    window: str
    sample_limit: int
    check_count: int
    success_count: int
    failure_count: int
    uptime_percent: float | None
    avg_duration_ms: float | None
    p95_duration_ms: int | None
    points: list[StatsPoint]

    model_config = ConfigDict(from_attributes=True)


@router.get("/api/websites/{website_id}/stats", response_model=WebsiteStatsResponse)
async def get_website_stats(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    window: str = Query(default="7d", description="One of: 24h, 7d, all"),
    sample_limit: int = Query(default=100, ge=1, le=200),
) -> WebsiteStatsResponse:
    """Return capped uptime and latency stats for one visible website."""
    try:
        window_name = parse_window(window)
        limit = clamp_sample_limit(sample_limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await get_visible_website(session, website_id, actor)
    since = window_since(window_name)
    try:
        stmt = select(WebsiteCheck).where(WebsiteCheck.website_id == website_id)
        if since is not None:
            stmt = stmt.where(WebsiteCheck.created_at >= since)
        stmt = stmt.order_by(WebsiteCheck.created_at.desc(), WebsiteCheck.id.asc()).limit(limit)
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)

    samples = [
        CheckSample(
            created_at=row.created_at,
            outcome=row.outcome,
            duration_ms=row.duration_ms,
            http_status=row.http_status,
        )
        for row in rows
    ]
    summary = summarize_checks(
        website_id,
        samples,
        window=window_name,
        sample_limit=limit,
    )
    return _to_response(summary)


class MonitoringStateResponse(BaseModel):
    """Branchable monitoring flags for UI and n8n (no Redis)."""

    website_id: UUID
    status: str
    recovered: bool
    still_failing: bool
    latency_breached: bool
    latency_threshold_ms: int | None
    failure_threshold_count: int
    consecutive_failures: int
    latest_outcome: str | None
    latest_duration_ms: int | None
    latest_http_status: int | None
    latest_created_at: datetime | None
    previous_outcome: str | None
    # AUTO-2 rule settings (stored on the website).
    notify_on_fail: bool
    notify_on_recover: bool
    notify_on_latency: bool
    # Evaluated intents for n8n IF nodes (signal AND rule).
    should_notify_fail: bool
    should_notify_recover: bool
    should_notify_latency: bool


@router.get(
    "/api/websites/{website_id}/monitoring-state",
    response_model=MonitoringStateResponse,
)
async def get_monitoring_state(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    history_limit: int = Query(default=20, ge=2, le=50),
) -> MonitoringStateResponse:
    """Return still_failing / recovered from recent checks and site thresholds."""
    website = await get_visible_website(session, website_id, actor)
    try:
        result = await session.execute(
            select(WebsiteCheck)
            .where(WebsiteCheck.website_id == website_id)
            .order_by(WebsiteCheck.created_at.desc(), WebsiteCheck.id.asc())
            .limit(history_limit)
        )
        rows = list(result.scalars().all())
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)

    samples = [
        CheckSample(
            created_at=row.created_at,
            outcome=row.outcome,
            duration_ms=row.duration_ms,
            http_status=row.http_status,
        )
        for row in rows
    ]
    state = evaluate_monitoring_state(
        website_id,
        samples,
        latency_threshold_ms=website.latency_threshold_ms,
        failure_threshold_count=website.failure_threshold_count,
    )
    intents = evaluate_notification_intents(
        state,
        NotificationRules(
            notify_on_fail=website.notify_on_fail,
            notify_on_recover=website.notify_on_recover,
            notify_on_latency=website.notify_on_latency,
        ),
    )
    return MonitoringStateResponse(
        website_id=state.website_id,
        status=state.status,
        recovered=state.recovered,
        still_failing=state.still_failing,
        latency_breached=state.latency_breached,
        latency_threshold_ms=state.latency_threshold_ms,
        failure_threshold_count=state.failure_threshold_count,
        consecutive_failures=state.consecutive_failures,
        latest_outcome=state.latest_outcome,
        latest_duration_ms=state.latest_duration_ms,
        latest_http_status=state.latest_http_status,
        latest_created_at=state.latest_created_at,
        previous_outcome=state.previous_outcome,
        notify_on_fail=intents.notify_on_fail,
        notify_on_recover=intents.notify_on_recover,
        notify_on_latency=intents.notify_on_latency,
        should_notify_fail=intents.should_notify_fail,
        should_notify_recover=intents.should_notify_recover,
        should_notify_latency=intents.should_notify_latency,
    )


def _to_response(summary: CheckStatsSummary) -> WebsiteStatsResponse:
    return WebsiteStatsResponse(
        website_id=summary.website_id,
        window=summary.window,
        sample_limit=summary.sample_limit,
        check_count=summary.check_count,
        success_count=summary.success_count,
        failure_count=summary.failure_count,
        uptime_percent=summary.uptime_percent,
        avg_duration_ms=summary.avg_duration_ms,
        p95_duration_ms=summary.p95_duration_ms,
        points=[
            StatsPoint(
                created_at=point.created_at,
                outcome=point.outcome,
                duration_ms=point.duration_ms,
                http_status=point.http_status,
            )
            for point in summary.points
        ],
    )


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Stats request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
