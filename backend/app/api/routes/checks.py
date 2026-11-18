"""Run a browser check and read its history.

The request waits for the check. The wait is bounded by the runner. These
routes do not start a queue, and they do not return exception text.

Manual checks use the browser acknowledgement (`authorized: true`).
Scheduled checks use `POST .../scheduled-checks` with `X-Schedule-Check-Token`
and require `monitoring_enabled` on the website.
"""

import logging
import secrets
import time
from dataclasses import replace
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_session, get_visible_check, get_visible_website, require_actor
from app.api.public_shell import reject_if_live_browser_disabled
from app.core.config import get_settings
from app.models.website import Website
from app.models.website_check import WebsiteCheck
from app.services.browser import CheckRunner, runner_from_settings
from app.services.check_stats import clamp_history_limit, parse_window, window_since
from app.services.network import ResolveHost, TargetNotAllowed, ensure_public_http_url
from app.services.results import (
    PAGE_COULD_NOT_BE_OPENED,
    CheckObservation,
    failed_observation,
    sanitize_observation,
)
from app.services.screenshots import read_screenshot, write_screenshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["checks"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)
_SCHEDULE_TOKEN_HEADER = "X-Schedule-Check-Token"


class CheckRequest(BaseModel):
    """The caller must acknowledge that they may test the site."""

    authorized: bool

    model_config = ConfigDict(json_schema_extra={"examples": [{"authorized": True}]})

    @field_validator("authorized")
    @classmethod
    def must_be_confirmed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Confirm that you are authorized to test this website")
        return value


class FailedRequestResponse(BaseModel):
    """A failed or blocked request, without headers or a body."""

    url: str
    error: str


class CheckResponse(BaseModel):
    """One stored check. The fields are already sanitized."""

    id: UUID
    website_id: UUID
    outcome: str
    http_status: int | None
    page_title: str | None
    final_url: str | None
    duration_ms: int
    console_errors: list[str]
    failed_requests: list[FailedRequestResponse]
    error_message: str | None
    created_at: datetime
    has_screenshot: bool = False

    model_config = ConfigDict(from_attributes=True)


def get_check_runner(request: Request) -> CheckRunner:
    """Use a runner installed by tests, otherwise build the Playwright runner."""
    runner = getattr(request.app.state, "check_runner", None)
    if runner is not None:
        return runner
    settings = get_settings()
    return runner_from_settings(
        settings.check_navigation_timeout_seconds,
        getattr(request.app.state, "host_resolver", None),
        screenshot_enabled=settings.screenshot_enabled,
        screenshot_timeout_ms=settings.screenshot_timeout_ms,
        screenshot_max_bytes=settings.screenshot_max_bytes,
    )


def get_host_resolver(request: Request) -> ResolveHost | None:
    """A test can replace DNS. Production uses the system resolver."""
    return getattr(request.app.state, "host_resolver", None)


@router.post(
    "/api/websites/{website_id}/checks",
    response_model=CheckResponse,
    status_code=201,
)
async def run_check(
    website_id: UUID,
    payload: CheckRequest,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    runner: CheckRunner = Depends(get_check_runner),
    resolver: ResolveHost | None = Depends(get_host_resolver),
) -> WebsiteCheck:
    """Open the website after a human acknowledgement, store the result, and return it."""
    reject_if_live_browser_disabled()
    if not payload.authorized:
        raise HTTPException(
            status_code=422,
            detail="Confirm that you are authorized to test this website.",
        )
    website = await get_visible_website(session, website_id, actor)
    return await _run_and_store_check(session, website, runner, resolver)


@router.post(
    "/api/websites/{website_id}/scheduled-checks",
    response_model=CheckResponse,
    status_code=201,
)
async def run_scheduled_check(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    runner: CheckRunner = Depends(get_check_runner),
    resolver: ResolveHost | None = Depends(get_host_resolver),
    x_schedule_check_token: str | None = Header(default=None, alias=_SCHEDULE_TOKEN_HEADER),
) -> WebsiteCheck:
    """Run one check for an enrolled site when the schedule token matches.

    The token is a machine acknowledgement for automation. It is not a user
    account and does not prove ownership of the site.
    """
    reject_if_live_browser_disabled()
    _require_schedule_token(x_schedule_check_token)
    website = await _get_website(session, website_id)
    if not website.monitoring_enabled:
        raise HTTPException(
            status_code=422,
            detail="This website is not enrolled in scheduled monitoring.",
        )
    return await _run_and_store_check(session, website, runner, resolver)


@router.get("/api/websites/{website_id}/checks", response_model=list[CheckResponse])
async def list_checks(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    window: str = Query(
        default="all",
        description="History window: 24h, 7d, or all (default all keeps newest-N for n8n)",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=50,
        description="Max rows (1–50). Default 20. Unbounded scans are refused.",
    ),
) -> list[WebsiteCheck]:
    """Return newest checks in a time window, always capped by `limit` (MON-3)."""
    await get_visible_website(session, website_id, actor)
    try:
        window_name = parse_window(window)
        row_limit = clamp_history_limit(limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        stmt = (
            select(WebsiteCheck)
            .where(WebsiteCheck.website_id == website_id)
            .order_by(WebsiteCheck.created_at.desc(), WebsiteCheck.id.asc())
            .limit(row_limit)
        )
        since = window_since(window_name)
        if since is not None:
            stmt = stmt.where(WebsiteCheck.created_at >= since)
        result = await session.execute(stmt)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return list(result.scalars().all())


@router.get("/api/checks/{check_id}", response_model=CheckResponse)
async def get_check(
    check_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> WebsiteCheck:
    """Return one check, or 404 when it was never stored or its website was deleted."""
    try:
        return await get_visible_check(session, check_id, actor)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


@router.get("/api/checks/{check_id}/screenshot")
async def get_check_screenshot(
    check_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> Response:
    """Return the stored PNG for a check, or 404 when none exists."""
    try:
        check = await get_visible_check(session, check_id, actor)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    settings = get_settings()
    png = read_screenshot(
        settings.screenshot_root,
        check.screenshot_path,
        max_bytes=settings.screenshot_max_bytes,
    )
    if png is None:
        raise HTTPException(status_code=404, detail="Screenshot not found.")
    return Response(content=png, media_type="image/png")


async def _run_and_store_check(
    session: AsyncSession,
    website: Website,
    runner: CheckRunner,
    resolver: ResolveHost | None,
) -> WebsiteCheck:
    """Shared path for manual and scheduled checks."""
    try:
        await ensure_public_http_url(website.base_url, resolve=resolver)
    except TargetNotAllowed as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc

    started = time.perf_counter()
    try:
        observation = await runner.run(website.base_url)
    except Exception as exc:
        logger.warning("Website check runner failed (%s)", exc.__class__.__name__)
        observation = failed_observation(started, PAGE_COULD_NOT_BE_OPENED)

    observation = await _scrub_final_url(observation, resolver)
    row = WebsiteCheck(
        website_id=website.id,
        outcome=observation.outcome,
        http_status=observation.http_status,
        page_title=observation.page_title,
        final_url=observation.final_url,
        duration_ms=observation.duration_ms,
        console_errors=list(observation.console_errors),
        failed_requests=[
            {"url": item.url, "error": item.error} for item in observation.failed_requests
        ],
        error_message=observation.error_message,
        screenshot_path=None,
    )
    session.add(row)
    await _commit(session)
    await _refresh(session, row)

    if observation.screenshot_png:
        settings = get_settings()
        relative = write_screenshot(
            settings.screenshot_root,
            row.id,
            observation.screenshot_png,
            max_bytes=settings.screenshot_max_bytes,
        )
        if relative:
            row.screenshot_path = relative
            await _commit(session)
            await _refresh(session, row)
    return row


def _require_schedule_token(presented: str | None) -> None:
    settings = get_settings()
    expected = settings.schedule_check_token
    if not expected or not expected.strip():
        raise HTTPException(
            status_code=503,
            detail=(
                "Scheduled checks are not configured. Set SCHEDULE_CHECK_TOKEN in the "
                "environment and restart the API."
            ),
        )
    expected = expected.strip()
    if presented is None or not _tokens_equal(presented, expected):
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or missing {_SCHEDULE_TOKEN_HEADER} header.",
        )


def _tokens_equal(presented: str, expected: str) -> bool:
    if len(presented) != len(expected):
        return False
    return secrets.compare_digest(presented, expected)


async def _get_website(session: AsyncSession, website_id: UUID) -> Website:
    try:
        website = await session.get(Website, website_id)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found.")
    return website


async def _scrub_final_url(
    observation: CheckObservation,
    resolver: ResolveHost | None,
) -> CheckObservation:
    """Drop a final URL that the runner should not have been able to open."""
    cleaned = sanitize_observation(observation)
    if cleaned.final_url is None:
        return cleaned
    try:
        await ensure_public_http_url(cleaned.final_url, resolve=resolver)
    except TargetNotAllowed:
        cleaned = sanitize_observation(
            replace(
                cleaned,
                outcome="failed",
                final_url=None,
                error_message=(
                    "This website cannot be checked because its address is not a public "
                    "HTTP or HTTPS site."
                ),
            )
        )
    return cleaned


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except _DATABASE_ERRORS as exc:
        await _rollback(session)
        _raise_database_error(exc)


async def _refresh(session: AsyncSession, row: WebsiteCheck) -> None:
    try:
        await session.refresh(row)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except _DATABASE_ERRORS:
        logger.warning("Website check rollback failed")


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Website check request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
