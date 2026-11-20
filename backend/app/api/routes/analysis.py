"""On-demand AI analysis for a stored failed check.

POST creates an analysis only when one does not already exist for that check.
A second POST returns the stored row and does not call the provider again.
Neither route starts a browser check.
"""

import logging
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_session, get_visible_check, require_actor
from app.core.config import get_settings
from app.models.check_analysis import CheckFailureAnalysis
from app.models.website_check import WebsiteCheck
from app.services.failure_analysis import (
    AnalysisNotConfiguredError,
    AnalysisProviderError,
    FailureAnalysisResult,
    ResolvedAnalysisProvider,
    build_evidence,
    provider_from_settings,
)
from app.services.public_demo import is_demo_check_result

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)

_OPENAI_UNCONFIGURED = (
    "AI failure analysis is set to openai but no API key is configured. "
    "Set OPENAI_API_KEY (or TOGETHER_API_KEY as a fallback alias), "
    "or set ANALYSIS_PROVIDER=simulated, then restart the API."
)


class PossibleCauseResponse(BaseModel):
    cause: str
    confidence: str
    evidence: str


class AnalysisResponse(BaseModel):
    """One stored analysis. Fields are already sanitized."""

    id: UUID
    check_id: UUID
    summary: str
    severity: str
    confirmed_observations: list[str]
    possible_causes: list[PossibleCauseResponse]
    recommended_investigation_steps: list[str]
    limitations: str
    model_name: str
    provider: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def get_resolved_analysis_provider(request: Request) -> ResolvedAnalysisProvider | None:
    """Use a provider installed by tests, otherwise build from settings.

    Tests may set `app.state.analysis_provider` to a fake AnalysisProvider, or to
    `None` to force the unconfigured path. They may also set
    `app.state.resolved_analysis_provider` to a full ResolvedAnalysisProvider.
    """
    if hasattr(request.app.state, "resolved_analysis_provider"):
        return request.app.state.resolved_analysis_provider
    if hasattr(request.app.state, "analysis_provider"):
        installed = request.app.state.analysis_provider
        if installed is None:
            return None
        model_name = getattr(request.app.state, "analysis_model_name", "test-model")
        provider_name = getattr(request.app.state, "analysis_provider_name", "simulated")
        return ResolvedAnalysisProvider(
            provider=installed,
            provider_name=provider_name,
            model_name=model_name if isinstance(model_name, str) else "test-model",
        )

    settings = get_settings()
    try:
        return provider_from_settings(
            analysis_provider=settings.effective_analysis_provider,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_output_tokens=settings.openai_max_output_tokens,
        )
    except AnalysisNotConfiguredError:
        return None


@router.post(
    "/api/checks/{check_id}/analysis",
    response_model=AnalysisResponse,
    status_code=201,
)
async def create_analysis(
    check_id: UUID,
    response: Response,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    resolved: ResolvedAnalysisProvider | None = Depends(get_resolved_analysis_provider),
) -> CheckFailureAnalysis:
    """Analyze a failed check once. Repeat calls return the stored analysis."""
    check = await get_visible_check(session, check_id, actor)
    existing = await _get_analysis_for_check(session, check_id)
    if existing is not None:
        # Cost control / reuse: do not call any provider again for the same check.
        response.status_code = 200
        return existing

    if check.outcome != "failed":
        raise HTTPException(
            status_code=422,
            detail="Only failed checks can be analyzed.",
        )

    # Portfolio/demo sample checks never call paid AI, even when the workspace
    # is configured for Together/OpenAI on the public shell.
    active = resolved
    if is_demo_check_result(check.error_message):
        active = provider_from_settings(
            analysis_provider="simulated",
            api_key=None,
            model="simulated-local",
            timeout_seconds=30,
            max_output_tokens=1200,
        )
    if active is None:
        raise HTTPException(status_code=503, detail=_OPENAI_UNCONFIGURED)

    evidence = build_evidence(check)
    try:
        result = await active.provider.analyze(evidence)
    except AnalysisProviderError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    row = _row_from_result(check_id, result, active.model_name, active.provider_name)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        # Another request stored the first analysis first. Return that row.
        await session.rollback()
        existing = await _get_analysis_for_check(session, check_id)
        if existing is not None:
            response.status_code = 200
            return existing
        raise HTTPException(status_code=503, detail="The database is unavailable.") from None
    except _DATABASE_ERRORS as exc:
        await _rollback(session)
        _raise_database_error(exc)

    await _refresh(session, row)
    response.status_code = 201
    return row


@router.get("/api/checks/{check_id}/analysis", response_model=AnalysisResponse)
async def get_analysis(
    check_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> CheckFailureAnalysis:
    """Return the stored analysis for a check, or 404 when none exists."""
    await get_visible_check(session, check_id, actor)
    existing = await _get_analysis_for_check(session, check_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return existing


def _row_from_result(
    check_id: UUID,
    result: FailureAnalysisResult,
    model_name: str,
    provider_name: str,
) -> CheckFailureAnalysis:
    return CheckFailureAnalysis(
        check_id=check_id,
        summary=result.summary,
        severity=result.severity,
        confirmed_observations=list(result.confirmed_observations),
        possible_causes=[cause.model_dump() for cause in result.possible_causes],
        recommended_investigation_steps=list(result.recommended_investigation_steps),
        limitations=result.limitations,
        model_name=model_name,
        provider=provider_name,
    )


async def _get_analysis_for_check(
    session: AsyncSession,
    check_id: UUID,
) -> CheckFailureAnalysis | None:
    try:
        result = await session.execute(
            select(CheckFailureAnalysis).where(CheckFailureAnalysis.check_id == check_id)
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return result.scalar_one_or_none()


async def _refresh(session: AsyncSession, row: CheckFailureAnalysis) -> None:
    try:
        await session.refresh(row)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except _DATABASE_ERRORS:
        logger.warning("Analysis rollback failed")


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Analysis request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
