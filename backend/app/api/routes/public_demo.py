"""Anonymous read (+ simulated analyze) for the seeded portfolio demo only.

These routes never require a session cookie. They expose only the seeded
`[Demo]` site and checks marked with the public-demo / lightweight-probe
markers. Non-demo rows stay 404. Writes are limited to lightweight HTTP
probes and storing a simulated analysis — no registry mutations, no Playwright.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.check_analysis import CheckFailureAnalysis
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
from app.services.failure_analysis import build_evidence, provider_from_settings
from app.services.http_probe import attach_probe_marker, probe_http_url
from app.services.network import ResolveHost, TargetNotAllowed, ensure_public_http_url
from app.services.public_demo import (
    get_seeded_demo_website,
    is_demo_check_result,
    require_demo_check,
    require_demo_website,
)
from app.services.public_rate_limit import RateLimited, check_rate_limit
from app.services.results import sanitize_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public/demo", tags=["public-demo"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)
_RECENT_CHECK_LIMIT = 20
_DASH_STATS_SAMPLE = 100


class PublicDemoWebsite(BaseModel):
    id: UUID
    name: str
    base_url: str
    monitoring_enabled: bool
    latency_threshold_ms: int | None = None
    failure_threshold_count: int | None = None
    notify_on_fail: bool = True
    notify_on_recover: bool = True
    notify_on_latency: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicDemoFailedRequest(BaseModel):
    url: str
    error: str


class PublicDemoCheck(BaseModel):
    id: UUID
    website_id: UUID
    outcome: str
    http_status: int | None
    page_title: str | None
    final_url: str | None
    duration_ms: int
    console_errors: list[str]
    failed_requests: list[PublicDemoFailedRequest]
    error_message: str | None
    created_at: datetime
    has_screenshot: bool = False

    model_config = ConfigDict(from_attributes=True)


class PublicDemoCause(BaseModel):
    cause: str
    confidence: str
    evidence: str


class PublicDemoAnalysis(BaseModel):
    id: UUID
    check_id: UUID
    summary: str
    severity: str
    confirmed_observations: list[str]
    possible_causes: list[PublicDemoCause]
    recommended_investigation_steps: list[str]
    limitations: str
    model_name: str
    provider: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicDemoSnapshot(BaseModel):
    website: PublicDemoWebsite
    checks: list[PublicDemoCheck]
    failed_check_id: UUID | None
    analysis: PublicDemoAnalysis | None


class PublicDemoDashboardCheck(BaseModel):
    id: UUID
    website_id: UUID
    website_name: str
    outcome: str
    http_status: int | None
    duration_ms: int
    error_message: str | None
    created_at: datetime


class PublicDemoDashboardStats(BaseModel):
    website_id: UUID
    window: str
    check_count: int
    success_count: int
    failure_count: int
    uptime_percent: float | None
    avg_duration_ms: float | None
    p95_duration_ms: int | None


class PublicDemoDashboardHealth(BaseModel):
    website_count: int
    monitored_count: int
    sites_with_checks: int
    sites_with_failures: int
    avg_uptime_percent: float | None
    recent_failure_count: int


class PublicDemoDashboard(BaseModel):
    websites: list[PublicDemoWebsite]
    recent_checks: list[PublicDemoDashboardCheck]
    website_stats: list[PublicDemoDashboardStats]
    stats_window: str
    history_window: str
    recent_check_limit: int
    health: PublicDemoDashboardHealth


class PublicProbeRequest(BaseModel):
    """Anonymous lightweight check: public HTTP(S) URL only."""

    url: str = Field(min_length=8, max_length=2048)
    authorized: bool

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"url": "https://example.com", "authorized": True}]
        }
    )

    @field_validator("authorized")
    @classmethod
    def must_be_confirmed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Confirm that you are authorized to test this website")
        return value

    @field_validator("url")
    @classmethod
    def url_must_look_http(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.lower().startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return cleaned


class PublicDemoCheckRequest(BaseModel):
    authorized: bool

    @field_validator("authorized")
    @classmethod
    def must_be_confirmed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Confirm that you are authorized to test this website")
        return value


def get_host_resolver(request: Request) -> ResolveHost | None:
    return getattr(request.app.state, "host_resolver", None)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/probe", response_model=PublicDemoCheck, status_code=201)
async def run_public_probe(
    payload: PublicProbeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    resolver: ResolveHost | None = Depends(get_host_resolver),
) -> PublicDemoCheck:
    """Anonymous lightweight HTTP probe. Stores the result on the demo site."""
    try:
        check_rate_limit(f"probe:{_client_key(request)}")
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many public checks from this address. Try again in a minute.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    try:
        await ensure_public_http_url(payload.url, resolve=resolver)
    except TargetNotAllowed as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc

    try:
        website = await get_seeded_demo_website(session)
        if website is None:
            raise HTTPException(status_code=404, detail="Public demo is not available.")
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)

    observation = attach_probe_marker(
        await probe_http_url(payload.url, resolve=resolver)
    )
    row = WebsiteCheck(
        website_id=website.id,
        outcome=observation.outcome,
        http_status=observation.http_status,
        page_title=observation.page_title,
        final_url=observation.final_url or sanitize_url(payload.url),
        duration_ms=observation.duration_ms,
        console_errors=list(observation.console_errors),
        failed_requests=[
            {"url": item.url, "error": item.error} for item in observation.failed_requests
        ],
        error_message=observation.error_message,
        screenshot_path=None,
    )
    if row.final_url == "non-http resource":
        row.final_url = None
    session.add(row)
    try:
        await session.commit()
        await session.refresh(row)
    except _DATABASE_ERRORS as exc:
        try:
            await session.rollback()
        except _DATABASE_ERRORS:
            logger.warning("Public probe rollback failed")
        _raise_database_error(exc)
    return _check_response(row)


@router.post(
    "/websites/{website_id}/checks",
    response_model=PublicDemoCheck,
    status_code=201,
)
async def run_public_demo_site_probe(
    website_id: UUID,
    payload: PublicDemoCheckRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    resolver: ResolveHost | None = Depends(get_host_resolver),
) -> PublicDemoCheck:
    """Lightweight probe of the seeded demo site's base URL (no Playwright)."""
    try:
        check_rate_limit(f"probe:{_client_key(request)}")
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many public checks from this address. Try again in a minute.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    try:
        website = await require_demo_website(session, website_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Website not found.") from None
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)

    try:
        await ensure_public_http_url(website.base_url, resolve=resolver)
    except TargetNotAllowed as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc

    observation = attach_probe_marker(
        await probe_http_url(website.base_url, resolve=resolver)
    )
    row = WebsiteCheck(
        website_id=website.id,
        outcome=observation.outcome,
        http_status=observation.http_status,
        page_title=observation.page_title,
        final_url=observation.final_url or sanitize_url(website.base_url),
        duration_ms=observation.duration_ms,
        console_errors=list(observation.console_errors),
        failed_requests=[
            {"url": item.url, "error": item.error} for item in observation.failed_requests
        ],
        error_message=observation.error_message,
        screenshot_path=None,
    )
    if row.final_url == "non-http resource":
        row.final_url = None
    session.add(row)
    try:
        await session.commit()
        await session.refresh(row)
    except _DATABASE_ERRORS as exc:
        try:
            await session.rollback()
        except _DATABASE_ERRORS:
            logger.warning("Public demo site probe rollback failed")
        _raise_database_error(exc)
    return _check_response(row)


@router.get("", response_model=PublicDemoSnapshot)
async def get_public_demo(
    session: AsyncSession = Depends(get_session),
) -> PublicDemoSnapshot:
    """Anonymous portfolio sample: demo site, checks, and any stored analysis."""
    try:
        website = await get_seeded_demo_website(session)
        if website is None:
            raise HTTPException(status_code=404, detail="Public demo is not available.")
        checks = await _list_demo_checks(session, website.id)
        failed = next((row for row in checks if row.outcome == "failed"), None)
        analysis = None
        if failed is not None:
            analysis = await _get_analysis(session, failed.id)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return PublicDemoSnapshot(
        website=PublicDemoWebsite.model_validate(website),
        checks=[_check_response(row) for row in checks],
        failed_check_id=failed.id if failed is not None else None,
        analysis=PublicDemoAnalysis.model_validate(analysis) if analysis else None,
    )


@router.get("/dashboard", response_model=PublicDemoDashboard)
async def get_public_demo_dashboard(
    session: AsyncSession = Depends(get_session),
    stats_window: str = Query(default="7d"),
) -> PublicDemoDashboard:
    """Dashboard-shaped snapshot scoped to the seeded demo site only."""
    try:
        window_name = parse_window(stats_window)
        history_limit = clamp_history_limit(_RECENT_CHECK_LIMIT)
        sample_limit = clamp_sample_limit(_DASH_STATS_SAMPLE)
        website = await get_seeded_demo_website(session)
        if website is None:
            raise HTTPException(status_code=404, detail="Public demo is not available.")
        since = window_since(window_name)
        stmt = (
            select(WebsiteCheck)
            .where(WebsiteCheck.website_id == website.id)
            .order_by(WebsiteCheck.created_at.desc(), WebsiteCheck.id.asc())
            .limit(history_limit)
        )
        if since is not None:
            stmt = stmt.where(WebsiteCheck.created_at >= since)
        rows = list((await session.execute(stmt)).scalars().all())
        demo_rows = [row for row in rows if is_demo_check_result(row.error_message)]
        samples = [
            CheckSample(
                created_at=row.created_at,
                outcome=row.outcome,
                duration_ms=row.duration_ms,
                http_status=row.http_status,
            )
            for row in demo_rows[:sample_limit]
        ]
        summary = summarize_checks(
            website.id,
            samples,
            window=window_name,
            sample_limit=sample_limit,
        )
        stats = PublicDemoDashboardStats(
            website_id=summary.website_id,
            window=summary.window,
            check_count=summary.check_count,
            success_count=summary.success_count,
            failure_count=summary.failure_count,
            uptime_percent=summary.uptime_percent,
            avg_duration_ms=summary.avg_duration_ms,
            p95_duration_ms=summary.p95_duration_ms,
        )
        recent = [
            PublicDemoDashboardCheck(
                id=row.id,
                website_id=row.website_id,
                website_name=website.name,
                outcome=row.outcome,
                http_status=row.http_status,
                duration_ms=row.duration_ms,
                error_message=row.error_message,
                created_at=row.created_at,
            )
            for row in demo_rows
        ]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)

    health = PublicDemoDashboardHealth(
        website_count=1,
        monitored_count=1 if website.monitoring_enabled else 0,
        sites_with_checks=1 if stats.check_count > 0 else 0,
        sites_with_failures=1 if stats.failure_count > 0 else 0,
        avg_uptime_percent=stats.uptime_percent,
        recent_failure_count=sum(1 for row in recent if row.outcome == "failed"),
    )
    return PublicDemoDashboard(
        websites=[PublicDemoWebsite.model_validate(website)],
        recent_checks=recent,
        website_stats=[stats],
        stats_window=window_name,
        history_window=window_name,
        recent_check_limit=history_limit,
        health=health,
    )


@router.get("/websites/{website_id}", response_model=PublicDemoWebsite)
async def get_public_demo_website(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Website:
    try:
        return await require_demo_website(session, website_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Website not found.") from None
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


@router.get("/websites/{website_id}/checks", response_model=list[PublicDemoCheck])
async def list_public_demo_checks(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[PublicDemoCheck]:
    try:
        await require_demo_website(session, website_id)
        rows = await _list_demo_checks(session, website_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Website not found.") from None
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return [_check_response(row) for row in rows]


@router.get("/checks/{check_id}", response_model=PublicDemoCheck)
async def get_public_demo_check(
    check_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PublicDemoCheck:
    try:
        row = await require_demo_check(session, check_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Check not found.") from None
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return _check_response(row)


@router.get("/checks/{check_id}/analysis", response_model=PublicDemoAnalysis)
async def get_public_demo_analysis(
    check_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> CheckFailureAnalysis:
    try:
        await require_demo_check(session, check_id)
        existing = await _get_analysis(session, check_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Check not found.") from None
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    if existing is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return existing


@router.post(
    "/checks/{check_id}/analysis",
    response_model=PublicDemoAnalysis,
    status_code=201,
)
async def create_public_demo_analysis(
    check_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> CheckFailureAnalysis:
    """Simulated analysis for a demo failure. Never calls a paid provider."""
    try:
        check = await require_demo_check(session, check_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Check not found.") from None
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)

    existing = await _get_analysis(session, check_id)
    if existing is not None:
        response.status_code = 200
        return existing

    if check.outcome != "failed":
        raise HTTPException(status_code=422, detail="Only failed checks can be analyzed.")

    resolved = provider_from_settings(
        analysis_provider="simulated",
        api_key=None,
        model="simulated-local",
        timeout_seconds=30,
        max_output_tokens=1200,
    )
    evidence = build_evidence(check)
    result = await resolved.provider.analyze(evidence)
    row = CheckFailureAnalysis(
        check_id=check_id,
        summary=result.summary,
        severity=result.severity,
        confirmed_observations=list(result.confirmed_observations),
        possible_causes=[cause.model_dump() for cause in result.possible_causes],
        recommended_investigation_steps=list(result.recommended_investigation_steps),
        limitations=result.limitations,
        model_name=resolved.model_name,
        provider=resolved.provider_name,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _get_analysis(session, check_id)
        if existing is not None:
            response.status_code = 200
            return existing
        raise HTTPException(status_code=503, detail="The database is unavailable.") from None
    except _DATABASE_ERRORS as exc:
        try:
            await session.rollback()
        except _DATABASE_ERRORS:
            logger.warning("Public demo analysis rollback failed")
        _raise_database_error(exc)

    try:
        await session.refresh(row)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    response.status_code = 201
    return row


async def _list_demo_checks(session: AsyncSession, website_id: UUID) -> list[WebsiteCheck]:
    result = await session.execute(
        select(WebsiteCheck)
        .where(WebsiteCheck.website_id == website_id)
        .order_by(WebsiteCheck.created_at.desc(), WebsiteCheck.id.asc())
    )
    return [row for row in result.scalars().all() if is_demo_check_result(row.error_message)]


async def _get_analysis(
    session: AsyncSession,
    check_id: UUID,
) -> CheckFailureAnalysis | None:
    result = await session.execute(
        select(CheckFailureAnalysis).where(CheckFailureAnalysis.check_id == check_id)
    )
    return result.scalar_one_or_none()


def _check_response(row: WebsiteCheck) -> PublicDemoCheck:
    failed_requests: list[PublicDemoFailedRequest] = []
    raw = row.failed_requests or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                url = item.get("url")
                error = item.get("error")
                if isinstance(url, str) and isinstance(error, str):
                    failed_requests.append(PublicDemoFailedRequest(url=url, error=error))
    return PublicDemoCheck(
        id=row.id,
        website_id=row.website_id,
        outcome=row.outcome,
        http_status=row.http_status,
        page_title=row.page_title,
        final_url=row.final_url,
        duration_ms=row.duration_ms,
        console_errors=list(row.console_errors or []),
        failed_requests=failed_requests,
        error_message=row.error_message,
        created_at=row.created_at,
        has_screenshot=False,
    )


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Public demo request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc

