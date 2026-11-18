"""AI-2 on-demand historical pattern hints for one website."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_session, get_visible_website, require_actor
from app.core.config import get_settings
from app.models.website_check import WebsiteCheck
from app.models.website_pattern_hint import WebsitePatternHint
from app.services.check_stats import clamp_sample_limit, parse_window, window_since
from app.services.pattern_hints import (
    AnalysisNotConfiguredError,
    AnalysisProviderError,
    PatternHintsResult,
    ResolvedPatternHintProvider,
    build_pattern_evidence,
    default_pattern_sample_limit,
    pattern_provider_from_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pattern-hints"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)

_OPENAI_UNCONFIGURED = (
    "AI pattern hints are set to openai but OPENAI_API_KEY is missing. "
    "Set the key, or set ANALYSIS_PROVIDER=simulated, then restart the API."
)


class PatternItemResponse(BaseModel):
    kind: str
    title: str
    detail: str
    confidence: str
    evidence: str


class PatternHintsResponse(BaseModel):
    id: UUID
    website_id: UUID
    window: str
    sample_limit: int
    check_count: int
    failure_count: int
    based_on_latest_check_id: UUID | None
    summary: str
    severity: str
    patterns: list[PatternItemResponse]
    confirmed_observations: list[str]
    recommended_investigation_steps: list[str]
    limitations: str
    model_name: str
    provider: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def get_resolved_pattern_provider(request: Request) -> ResolvedPatternHintProvider | None:
    """Prefer test overrides, otherwise build from ANALYSIS_PROVIDER settings."""
    if hasattr(request.app.state, "resolved_pattern_hint_provider"):
        return request.app.state.resolved_pattern_hint_provider
    if hasattr(request.app.state, "pattern_hint_provider"):
        installed = request.app.state.pattern_hint_provider
        if installed is None:
            return None
        model_name = getattr(request.app.state, "pattern_hint_model_name", "test-model")
        provider_name = getattr(request.app.state, "pattern_hint_provider_name", "simulated")
        return ResolvedPatternHintProvider(
            provider=installed,
            provider_name=provider_name,
            model_name=model_name if isinstance(model_name, str) else "test-model",
        )

    settings = get_settings()
    try:
        return pattern_provider_from_settings(
            analysis_provider=settings.effective_analysis_provider,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_output_tokens=settings.openai_max_output_tokens,
        )
    except AnalysisNotConfiguredError:
        return None


@router.post(
    "/api/websites/{website_id}/pattern-hints",
    response_model=PatternHintsResponse,
    status_code=201,
)
async def create_pattern_hints(
    website_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    resolved: ResolvedPatternHintProvider | None = Depends(get_resolved_pattern_provider),
    window: str = Query(default="7d", description="Stats window: 24h, 7d, or all"),
    sample_limit: int | None = Query(default=None, ge=1, le=200),
    refresh: bool = Query(default=False, description="Force a new provider run"),
) -> WebsitePatternHint:
    """Summarize recent checks. Reuses the stored row when the sample fingerprint matches."""
    website = await get_visible_website(session, website_id, actor)
    try:
        window_name = parse_window(window)
        limit = clamp_sample_limit(
            sample_limit if sample_limit is not None else default_pattern_sample_limit()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    checks = await _load_checks(session, website.id, window_name, limit)
    if not checks:
        raise HTTPException(
            status_code=422,
            detail="Pattern hints need at least one stored check in the selected window.",
        )

    latest_id = checks[0].id
    existing = await _get_hint(session, website.id)
    if (
        existing is not None
        and not refresh
        and existing.window == window_name
        and existing.sample_limit == limit
        and existing.based_on_latest_check_id == latest_id
        and existing.check_count == len(checks)
    ):
        response.status_code = 200
        return existing

    if resolved is None:
        raise HTTPException(status_code=503, detail=_OPENAI_UNCONFIGURED)

    evidence = build_pattern_evidence(checks, window=window_name, sample_limit=limit)
    try:
        result = await resolved.provider.analyze(evidence)
    except AnalysisProviderError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    row = _row_from_result(
        website_id=website.id,
        window=window_name,
        sample_limit=limit,
        check_count=len(checks),
        failure_count=sum(1 for row in checks if row.outcome == "failed"),
        latest_check_id=latest_id,
        result=result,
        model_name=resolved.model_name,
        provider_name=resolved.provider_name,
    )

    if existing is not None:
        await session.delete(existing)
        try:
            await session.flush()
        except _DATABASE_ERRORS as exc:
            await _rollback(session)
            _raise_database_error(exc)

    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raced = await _get_hint(session, website.id)
        if raced is not None:
            response.status_code = 200
            return raced
        raise HTTPException(status_code=503, detail="The database is unavailable.") from None
    except _DATABASE_ERRORS as exc:
        await _rollback(session)
        _raise_database_error(exc)

    await _refresh(session, row)
    response.status_code = 201
    return row


@router.get(
    "/api/websites/{website_id}/pattern-hints",
    response_model=PatternHintsResponse,
)
async def get_pattern_hints(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> WebsitePatternHint:
    """Return the stored pattern-hint row, or 404. Never calls a provider."""
    await get_visible_website(session, website_id, actor)
    existing = await _get_hint(session, website_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Pattern hints not found.")
    return existing


async def _load_checks(
    session: AsyncSession,
    website_id: UUID,
    window_name: str,
    limit: int,
) -> list[WebsiteCheck]:
    try:
        stmt = (
            select(WebsiteCheck)
            .where(WebsiteCheck.website_id == website_id)
            .order_by(WebsiteCheck.created_at.desc(), WebsiteCheck.id.asc())
            .limit(limit)
        )
        since = window_since(window_name)  # type: ignore[arg-type]
        if since is not None:
            stmt = stmt.where(WebsiteCheck.created_at >= since)
        result = await session.execute(stmt)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return list(result.scalars().all())


async def _get_hint(session: AsyncSession, website_id: UUID) -> WebsitePatternHint | None:
    try:
        result = await session.execute(
            select(WebsitePatternHint).where(WebsitePatternHint.website_id == website_id)
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return result.scalar_one_or_none()


def _row_from_result(
    *,
    website_id: UUID,
    window: str,
    sample_limit: int,
    check_count: int,
    failure_count: int,
    latest_check_id: UUID,
    result: PatternHintsResult,
    model_name: str,
    provider_name: str,
) -> WebsitePatternHint:
    return WebsitePatternHint(
        website_id=website_id,
        window=window,
        sample_limit=sample_limit,
        check_count=check_count,
        failure_count=failure_count,
        based_on_latest_check_id=latest_check_id,
        summary=result.summary,
        severity=result.severity,
        patterns=[item.model_dump() for item in result.patterns],
        confirmed_observations=list(result.confirmed_observations),
        recommended_investigation_steps=list(result.recommended_investigation_steps),
        limitations=result.limitations,
        model_name=model_name,
        provider=provider_name,
    )


async def _refresh(session: AsyncSession, row: WebsitePatternHint) -> None:
    try:
        await session.refresh(row)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except _DATABASE_ERRORS:
        logger.warning("Pattern-hint rollback failed")


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Pattern-hint request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
