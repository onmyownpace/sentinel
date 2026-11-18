"""Product dashboard summary for the signed-in account."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_session, list_visible_websites, require_actor
from app.models.website import Website
from app.models.website_check import WebsiteCheck
from app.services.check_stats import (
    CheckSample,
    clamp_history_limit,
    clamp_sample_limit,
    parse_window,
    summarize_checks,
    window_since,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)
_RECENT_CHECK_LIMIT = 20
_DASH_STATS_SAMPLE = 100


class DashboardWebsite(BaseModel):
    id: UUID
    name: str
    base_url: str
    monitoring_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardCheck(BaseModel):
    id: UUID
    website_id: UUID
    website_name: str
    outcome: str
    http_status: int | None
    duration_ms: int
    error_message: str | None
    created_at: datetime


class DashboardWebsiteStats(BaseModel):
    website_id: UUID
    window: str
    check_count: int
    success_count: int
    failure_count: int
    uptime_percent: float | None
    avg_duration_ms: float | None
    p95_duration_ms: int | None


class DashboardHealth(BaseModel):
    """Account-level health roll-up for the DASH-2 overview."""

    website_count: int
    monitored_count: int
    sites_with_checks: int
    sites_with_failures: int
    avg_uptime_percent: float | None
    recent_failure_count: int


class DashboardResponse(BaseModel):
    websites: list[DashboardWebsite]
    recent_checks: list[DashboardCheck]
    website_stats: list[DashboardWebsiteStats]
    stats_window: str
    history_window: str
    recent_check_limit: int
    health: DashboardHealth


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    stats_window: str = Query(
        default="7d",
        description="Shared window for stats + recent check history: 24h, 7d, or all",
    ),
    recent_limit: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="Max recent checks across sites (1–50). Default 20.",
    ),
) -> DashboardResponse:
    """Return sites, windowed recent checks, and per-site uptime/latency summaries."""
    try:
        window_name = parse_window(stats_window)
        sample_limit = clamp_sample_limit(_DASH_STATS_SAMPLE)
        history_limit = clamp_history_limit(
            recent_limit if recent_limit is not None else _RECENT_CHECK_LIMIT
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        websites = await list_visible_websites(session, actor, monitoring=None)
        website_ids = [site.id for site in websites]
        recent: list[DashboardCheck] = []
        website_stats: list[DashboardWebsiteStats] = []

        if website_ids:
            since = window_since(window_name)
            recent_stmt = (
                select(WebsiteCheck, Website.name)
                .join(Website, Website.id == WebsiteCheck.website_id)
                .where(WebsiteCheck.website_id.in_(website_ids))
                .order_by(WebsiteCheck.created_at.desc(), WebsiteCheck.id.asc())
                .limit(history_limit)
            )
            if since is not None:
                recent_stmt = recent_stmt.where(WebsiteCheck.created_at >= since)
            result = await session.execute(recent_stmt)
            for check, site_name in result.all():
                recent.append(
                    DashboardCheck(
                        id=check.id,
                        website_id=check.website_id,
                        website_name=site_name,
                        outcome=check.outcome,
                        http_status=check.http_status,
                        duration_ms=check.duration_ms,
                        error_message=check.error_message,
                        created_at=check.created_at,
                    )
                )

            stats_stmt = select(WebsiteCheck).where(WebsiteCheck.website_id.in_(website_ids))
            if since is not None:
                stats_stmt = stats_stmt.where(WebsiteCheck.created_at >= since)
            stats_stmt = stats_stmt.order_by(
                WebsiteCheck.created_at.desc(),
                WebsiteCheck.id.asc(),
            )
            # Cap total rows pulled for the dashboard roll-up.
            stats_stmt = stats_stmt.limit(sample_limit * max(1, len(website_ids)))
            stats_rows = list((await session.execute(stats_stmt)).scalars().all())

            by_site: dict[UUID, list[CheckSample]] = defaultdict(list)
            for row in stats_rows:
                bucket = by_site[row.website_id]
                if len(bucket) >= sample_limit:
                    continue
                bucket.append(
                    CheckSample(
                        created_at=row.created_at,
                        outcome=row.outcome,
                        duration_ms=row.duration_ms,
                        http_status=row.http_status,
                    )
                )

            for site in websites:
                summary = summarize_checks(
                    site.id,
                    by_site.get(site.id, []),
                    window=window_name,
                    sample_limit=sample_limit,
                )
                website_stats.append(
                    DashboardWebsiteStats(
                        website_id=summary.website_id,
                        window=summary.window,
                        check_count=summary.check_count,
                        success_count=summary.success_count,
                        failure_count=summary.failure_count,
                        uptime_percent=summary.uptime_percent,
                        avg_duration_ms=summary.avg_duration_ms,
                        p95_duration_ms=summary.p95_duration_ms,
                    )
                )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)

    health = _build_health(websites, website_stats, recent)
    return DashboardResponse(
        websites=[DashboardWebsite.model_validate(site) for site in websites],
        recent_checks=recent,
        website_stats=website_stats,
        stats_window=window_name,
        history_window=window_name,
        recent_check_limit=history_limit,
        health=health,
    )


def _build_health(
    websites: list[Website],
    website_stats: list[DashboardWebsiteStats],
    recent: list[DashboardCheck],
) -> DashboardHealth:
    uptimes = [
        row.uptime_percent
        for row in website_stats
        if row.check_count > 0 and row.uptime_percent is not None
    ]
    avg_uptime = round(sum(uptimes) / len(uptimes), 2) if uptimes else None
    return DashboardHealth(
        website_count=len(websites),
        monitored_count=sum(1 for site in websites if site.monitoring_enabled),
        sites_with_checks=sum(1 for row in website_stats if row.check_count > 0),
        sites_with_failures=sum(1 for row in website_stats if row.failure_count > 0),
        avg_uptime_percent=avg_uptime,
        recent_failure_count=sum(1 for check in recent if check.outcome == "failed"),
    )


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Dashboard request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
