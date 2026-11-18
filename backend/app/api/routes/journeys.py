"""CRUD and runs for declarative BROW-2 journeys (separate from one-shot checks)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_session, get_visible_website, require_actor
from app.core.config import get_settings
from app.models.website import Website
from app.models.website_journey import JourneyRun, WebsiteJourney
from app.services.journey_runner import JourneyObservation, JourneyRunner, journey_runner_from_settings
from app.services.journey_steps import (
    steps_as_json,
    validate_and_normalize_steps,
    validate_journey_name,
)
from app.services.network import ResolveHost

logger = logging.getLogger(__name__)

router = APIRouter(tags=["journeys"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)
_HISTORY_DEFAULT = 20
_HISTORY_MAX = 50


class JourneyCreate(BaseModel):
    name: str
    steps: list[dict[str, Any]] = Field(min_length=1)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Login smoke",
                    "steps": [
                        {"op": "navigate", "url": "/login"},
                        {"op": "fill", "selector": "#email", "value": "dev@example.com"},
                        {"op": "fill", "selector": "#password", "value": "secret"},
                        {"op": "click", "selector": "button[type=submit]"},
                        {"op": "assert_url_contains", "value": "/dashboard"},
                    ],
                }
            ]
        }
    )


class JourneyRunRequest(BaseModel):
    authorized: bool

    @field_validator("authorized")
    @classmethod
    def must_be_confirmed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Confirm that you are authorized to test this website")
        return value


class JourneyResponse(BaseModel):
    id: UUID
    website_id: UUID
    name: str
    steps: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StepResultResponse(BaseModel):
    index: int
    op: str
    ok: bool
    detail: str


class JourneyRunResponse(BaseModel):
    id: UUID
    journey_id: UUID
    website_id: UUID
    outcome: str
    duration_ms: int
    step_results: list[StepResultResponse]
    error_message: str | None
    final_url: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def get_journey_runner(request: Request) -> JourneyRunner:
    runner = getattr(request.app.state, "journey_runner", None)
    if runner is not None:
        return runner
    settings = get_settings()
    return journey_runner_from_settings(
        settings.check_navigation_timeout_seconds,
        budget_seconds=settings.journey_budget_seconds,
        resolve=getattr(request.app.state, "host_resolver", None),
    )


def get_host_resolver(request: Request) -> ResolveHost | None:
    return getattr(request.app.state, "host_resolver", None)


@router.post(
    "/api/websites/{website_id}/journeys",
    response_model=JourneyResponse,
    status_code=201,
)
async def create_journey(
    website_id: UUID,
    payload: JourneyCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> WebsiteJourney:
    website = await get_visible_website(session, website_id, actor)
    try:
        name = validate_journey_name(payload.name)
        steps = validate_and_normalize_steps(payload.steps, website_base_url=website.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = WebsiteJourney(
        website_id=website.id,
        name=name,
        steps=steps_as_json(steps),
    )
    session.add(row)
    await _commit(session)
    await _refresh(session, row)
    return row


@router.get("/api/websites/{website_id}/journeys", response_model=list[JourneyResponse])
async def list_journeys(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> list[WebsiteJourney]:
    await get_visible_website(session, website_id, actor)
    try:
        result = await session.execute(
            select(WebsiteJourney)
            .where(WebsiteJourney.website_id == website_id)
            .order_by(WebsiteJourney.created_at.desc(), WebsiteJourney.id.asc())
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return list(result.scalars().all())


@router.get("/api/journeys/{journey_id}", response_model=JourneyResponse)
async def get_journey(
    journey_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> WebsiteJourney:
    return await _get_visible_journey(session, journey_id, actor)


@router.delete("/api/journeys/{journey_id}", status_code=204)
async def delete_journey(
    journey_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> Response:
    journey = await _get_visible_journey(session, journey_id, actor)
    await session.delete(journey)
    await _commit(session)
    return Response(status_code=204)


@router.post(
    "/api/journeys/{journey_id}/runs",
    response_model=JourneyRunResponse,
    status_code=201,
)
async def run_journey(
    journey_id: UUID,
    payload: JourneyRunRequest,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    runner: JourneyRunner = Depends(get_journey_runner),
) -> JourneyRun:
    from app.api.public_shell import reject_if_live_browser_disabled

    reject_if_live_browser_disabled()
    if not payload.authorized:
        raise HTTPException(
            status_code=422,
            detail="Confirm that you are authorized to test this website",
        )
    journey = await _get_visible_journey(session, journey_id, actor)
    website = await get_visible_website(session, journey.website_id, actor)
    try:
        steps = validate_and_normalize_steps(journey.steps, website_base_url=website.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        observation = await runner.run(steps=steps, website_base_url=website.base_url)
    except Exception as exc:
        logger.warning("Journey runner failed (%s)", exc.__class__.__name__)
        observation = JourneyObservation(
            outcome="failed",
            duration_ms=0,
            step_results=(),
            error_message="The journey could not be completed.",
            final_url=None,
        )

    row = JourneyRun(
        journey_id=journey.id,
        website_id=website.id,
        outcome=observation.outcome,
        duration_ms=observation.duration_ms,
        step_results=[item.to_dict() for item in observation.step_results],
        error_message=observation.error_message,
        final_url=observation.final_url,
    )
    session.add(row)
    await _commit(session)
    await _refresh(session, row)
    return row


@router.get("/api/journeys/{journey_id}/runs", response_model=list[JourneyRunResponse])
async def list_journey_runs(
    journey_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    limit: int = Query(default=_HISTORY_DEFAULT, ge=1, le=_HISTORY_MAX),
) -> list[JourneyRun]:
    await _get_visible_journey(session, journey_id, actor)
    try:
        result = await session.execute(
            select(JourneyRun)
            .where(JourneyRun.journey_id == journey_id)
            .order_by(JourneyRun.created_at.desc(), JourneyRun.id.asc())
            .limit(limit)
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return list(result.scalars().all())


@router.get("/api/journey-runs/{run_id}", response_model=JourneyRunResponse)
async def get_journey_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> JourneyRun:
    try:
        run = await session.get(JourneyRun, run_id)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    if run is None:
        raise HTTPException(status_code=404, detail="Journey run not found.")
    await get_visible_website(session, run.website_id, actor)
    return run


async def _get_visible_journey(
    session: AsyncSession,
    journey_id: UUID,
    actor: Actor,
) -> WebsiteJourney:
    try:
        journey = await session.get(WebsiteJourney, journey_id)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    if journey is None:
        raise HTTPException(status_code=404, detail="Journey not found.")
    await get_visible_website(session, journey.website_id, actor)
    return journey


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except _DATABASE_ERRORS as exc:
        await session.rollback()
        _raise_database_error(exc)


async def _refresh(session: AsyncSession, row: object) -> None:
    try:
        await session.refresh(row)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Journey request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
