"""AI-3 on-demand incident summary drafts (UI + n8n automation)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_session, get_visible_website, require_actor
from app.core.config import get_settings
from app.models.check_analysis import CheckFailureAnalysis
from app.models.website import Website
from app.models.website_check import WebsiteCheck
from app.models.website_incident_draft import WebsiteIncidentDraft
from app.services.incident_drafts import (
    AnalysisNotConfiguredError,
    AnalysisProviderError,
    IncidentDraftResult,
    ResolvedIncidentDraftProvider,
    build_incident_evidence,
    clamp_failed_check_limit,
    default_failed_check_limit,
    incident_provider_from_settings,
    source_fingerprint,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["incident-drafts"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)
_HISTORY_DEFAULT = 10
_HISTORY_MAX = 20

_OPENAI_UNCONFIGURED = (
    "AI incident drafts are set to openai but OPENAI_API_KEY is missing. "
    "Set the key, or set ANALYSIS_PROVIDER=simulated, then restart the API."
)


class IncidentDraftResponse(BaseModel):
    """Webhook-friendly incident draft (includes Slack-style `text`)."""

    id: UUID
    website_id: UUID
    website_name: str
    base_url: str
    failed_check_limit: int
    failed_check_count: int
    source_fingerprint: str
    check_ids: list[str]
    analysis_ids: list[str]
    paragraph: str
    text: str
    severity: str
    observations: list[str]
    limitations: str
    model_name: str
    provider: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def get_resolved_incident_provider(request: Request) -> ResolvedIncidentDraftProvider | None:
    if hasattr(request.app.state, "resolved_incident_draft_provider"):
        return request.app.state.resolved_incident_draft_provider
    if hasattr(request.app.state, "incident_draft_provider"):
        installed = request.app.state.incident_draft_provider
        if installed is None:
            return None
        model_name = getattr(request.app.state, "incident_draft_model_name", "test-model")
        provider_name = getattr(request.app.state, "incident_draft_provider_name", "simulated")
        return ResolvedIncidentDraftProvider(
            provider=installed,
            provider_name=provider_name,
            model_name=model_name if isinstance(model_name, str) else "test-model",
        )

    settings = get_settings()
    try:
        return incident_provider_from_settings(
            analysis_provider=settings.effective_analysis_provider,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_output_tokens=settings.openai_max_output_tokens,
        )
    except AnalysisNotConfiguredError:
        return None


@router.post(
    "/api/websites/{website_id}/incident-drafts",
    response_model=IncidentDraftResponse,
    status_code=201,
)
async def create_incident_draft(
    website_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    resolved: ResolvedIncidentDraftProvider | None = Depends(get_resolved_incident_provider),
    limit: int | None = Query(default=None, ge=1, le=20, description="Newest failed checks to include"),
    refresh: bool = Query(default=False, description="Force a new provider run"),
) -> WebsiteIncidentDraft:
    """Build an incident paragraph from recent failed checks + analyses."""
    website = await get_visible_website(session, website_id, actor)
    try:
        failed_limit = clamp_failed_check_limit(
            limit if limit is not None else default_failed_check_limit()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    checks = await _load_failed_checks(session, website.id, failed_limit)
    if not checks:
        raise HTTPException(
            status_code=422,
            detail="Incident drafts need at least one stored failed check for this site.",
        )

    fingerprint = source_fingerprint([row.id for row in checks])
    if not refresh:
        existing = await _latest_matching(session, website.id, fingerprint, failed_limit)
        if existing is not None:
            response.status_code = 200
            return existing

    if resolved is None:
        raise HTTPException(status_code=503, detail=_OPENAI_UNCONFIGURED)

    analyses = await _load_analyses(session, [row.id for row in checks])
    evidence = build_incident_evidence(
        website,
        checks,
        analyses,
        failed_check_limit=failed_limit,
    )
    try:
        result = await resolved.provider.draft(evidence)
    except AnalysisProviderError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    row = _row_from_result(
        website=website,
        checks=checks,
        analyses=analyses,
        failed_limit=failed_limit,
        fingerprint=fingerprint,
        result=result,
        model_name=resolved.model_name,
        provider_name=resolved.provider_name,
    )
    session.add(row)
    try:
        await session.commit()
    except _DATABASE_ERRORS as exc:
        await _rollback(session)
        _raise_database_error(exc)

    await _refresh(session, row)
    response.status_code = 201
    return row


@router.get(
    "/api/websites/{website_id}/incident-drafts",
    response_model=list[IncidentDraftResponse],
)
async def list_incident_drafts(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    history_limit: int = Query(default=_HISTORY_DEFAULT, ge=1, le=_HISTORY_MAX, alias="limit"),
) -> list[WebsiteIncidentDraft]:
    await get_visible_website(session, website_id, actor)
    try:
        result = await session.execute(
            select(WebsiteIncidentDraft)
            .where(WebsiteIncidentDraft.website_id == website_id)
            .order_by(WebsiteIncidentDraft.created_at.desc(), WebsiteIncidentDraft.id.asc())
            .limit(history_limit)
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return list(result.scalars().all())


@router.get(
    "/api/incident-drafts/{draft_id}",
    response_model=IncidentDraftResponse,
)
async def get_incident_draft(
    draft_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> WebsiteIncidentDraft:
    try:
        draft = await session.get(WebsiteIncidentDraft, draft_id)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    if draft is None:
        raise HTTPException(status_code=404, detail="Incident draft not found.")
    await get_visible_website(session, draft.website_id, actor)
    return draft


async def _load_failed_checks(
    session: AsyncSession,
    website_id: UUID,
    limit: int,
) -> list[WebsiteCheck]:
    try:
        result = await session.execute(
            select(WebsiteCheck)
            .where(
                WebsiteCheck.website_id == website_id,
                WebsiteCheck.outcome == "failed",
            )
            .order_by(WebsiteCheck.created_at.desc(), WebsiteCheck.id.asc())
            .limit(limit)
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return list(result.scalars().all())


async def _load_analyses(
    session: AsyncSession,
    check_ids: list[UUID],
) -> dict[UUID, CheckFailureAnalysis]:
    if not check_ids:
        return {}
    try:
        result = await session.execute(
            select(CheckFailureAnalysis).where(CheckFailureAnalysis.check_id.in_(check_ids))
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return {row.check_id: row for row in result.scalars().all()}


async def _latest_matching(
    session: AsyncSession,
    website_id: UUID,
    fingerprint: str,
    failed_limit: int,
) -> WebsiteIncidentDraft | None:
    try:
        result = await session.execute(
            select(WebsiteIncidentDraft)
            .where(
                WebsiteIncidentDraft.website_id == website_id,
                WebsiteIncidentDraft.source_fingerprint == fingerprint,
                WebsiteIncidentDraft.failed_check_limit == failed_limit,
            )
            .order_by(WebsiteIncidentDraft.created_at.desc(), WebsiteIncidentDraft.id.asc())
            .limit(1)
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return result.scalar_one_or_none()


def _row_from_result(
    *,
    website: Website,
    checks: list[WebsiteCheck],
    analyses: dict[UUID, CheckFailureAnalysis],
    failed_limit: int,
    fingerprint: str,
    result: IncidentDraftResult,
    model_name: str,
    provider_name: str,
) -> WebsiteIncidentDraft:
    analysis_ids = [str(analyses[row.id].id) for row in checks if row.id in analyses]
    return WebsiteIncidentDraft(
        website_id=website.id,
        failed_check_limit=failed_limit,
        failed_check_count=len(checks),
        source_fingerprint=fingerprint,
        check_ids=[str(row.id) for row in checks],
        analysis_ids=analysis_ids,
        website_name=website.name,
        base_url=website.base_url,
        paragraph=result.paragraph,
        text=result.text,
        severity=result.severity,
        observations=list(result.observations),
        limitations=result.limitations,
        model_name=model_name,
        provider=provider_name,
    )


async def _refresh(session: AsyncSession, row: WebsiteIncidentDraft) -> None:
    try:
        await session.refresh(row)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except _DATABASE_ERRORS:
        logger.warning("Incident-draft rollback failed")


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Incident-draft request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
