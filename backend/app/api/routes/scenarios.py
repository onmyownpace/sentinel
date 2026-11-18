"""BROW-3 scenario library: named reusable wrappers around BROW-2 journeys."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_session, get_visible_website, require_actor
from app.core.config import get_settings
from app.models.website_journey import WebsiteJourney
from app.models.website_scenario import ScenarioRun, WebsiteScenario
from app.services.journey_runner import JourneyObservation, JourneyRunner, journey_runner_from_settings
from app.services.journey_steps import validate_and_normalize_steps, validate_journey_name

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scenarios"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)
_HISTORY_DEFAULT = 20
_HISTORY_MAX = 50
_MAX_DESCRIPTION = 500


class ScenarioCreate(BaseModel):
    name: str
    journey_id: UUID
    description: str | None = None
    schedule_eligible: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Login smoke (library)",
                    "journey_id": "00000000-0000-0000-0000-000000000001",
                    "description": "Reusable login path for this site.",
                    "schedule_eligible": False,
                }
            ]
        }
    )


class ScenarioUpdate(BaseModel):
    """Patch library metadata. Omit fields to leave them unchanged."""

    name: str | None = None
    description: str | None = None
    journey_id: UUID | None = None
    schedule_eligible: bool | None = None


class ScenarioRunRequest(BaseModel):
    authorized: bool

    @field_validator("authorized")
    @classmethod
    def must_be_confirmed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Confirm that you are authorized to test this website")
        return value


class ScenarioResponse(BaseModel):
    id: UUID
    website_id: UUID
    journey_id: UUID
    name: str
    description: str | None
    schedule_eligible: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StepResultResponse(BaseModel):
    index: int
    op: str
    ok: bool
    detail: str


class ScenarioRunResponse(BaseModel):
    id: UUID
    scenario_id: UUID
    website_id: UUID
    journey_id: UUID
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


@router.post(
    "/api/websites/{website_id}/scenarios",
    response_model=ScenarioResponse,
    status_code=201,
)
async def create_scenario(
    website_id: UUID,
    payload: ScenarioCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> WebsiteScenario:
    website = await get_visible_website(session, website_id, actor)
    try:
        name = validate_journey_name(payload.name)
        description = _normalize_description(payload.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    journey = await _get_site_journey(session, website.id, payload.journey_id)
    row = WebsiteScenario(
        website_id=website.id,
        journey_id=journey.id,
        name=name,
        description=description,
        schedule_eligible=payload.schedule_eligible,
    )
    session.add(row)
    await _commit(session, name_conflict=True)
    await _refresh(session, row)
    return row


@router.get("/api/websites/{website_id}/scenarios", response_model=list[ScenarioResponse])
async def list_scenarios(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> list[WebsiteScenario]:
    await get_visible_website(session, website_id, actor)
    try:
        result = await session.execute(
            select(WebsiteScenario)
            .where(WebsiteScenario.website_id == website_id)
            .order_by(WebsiteScenario.created_at.desc(), WebsiteScenario.id.asc())
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return list(result.scalars().all())


@router.get("/api/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> WebsiteScenario:
    return await _get_visible_scenario(session, scenario_id, actor)


@router.patch("/api/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def update_scenario(
    scenario_id: UUID,
    payload: ScenarioUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> WebsiteScenario:
    provided = payload.model_fields_set
    if not provided:
        raise HTTPException(status_code=422, detail="Provide at least one field to update.")

    scenario = await _get_visible_scenario(session, scenario_id, actor)
    try:
        if "name" in provided and payload.name is not None:
            scenario.name = validate_journey_name(payload.name)
        if "description" in provided:
            scenario.description = _normalize_description(payload.description)
        if "schedule_eligible" in provided and payload.schedule_eligible is not None:
            scenario.schedule_eligible = payload.schedule_eligible
        if "journey_id" in provided and payload.journey_id is not None:
            journey = await _get_site_journey(session, scenario.website_id, payload.journey_id)
            scenario.journey_id = journey.id
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await _commit(session, name_conflict=True)
    await _refresh(session, scenario)
    return scenario


@router.delete("/api/scenarios/{scenario_id}", status_code=204)
async def delete_scenario(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> Response:
    scenario = await _get_visible_scenario(session, scenario_id, actor)
    await session.delete(scenario)
    await _commit(session, name_conflict=False)
    return Response(status_code=204)


@router.post(
    "/api/scenarios/{scenario_id}/runs",
    response_model=ScenarioRunResponse,
    status_code=201,
)
async def run_scenario(
    scenario_id: UUID,
    payload: ScenarioRunRequest,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    runner: JourneyRunner = Depends(get_journey_runner),
) -> ScenarioRun:
    from app.api.public_shell import reject_if_live_browser_disabled

    reject_if_live_browser_disabled()
    if not payload.authorized:
        raise HTTPException(
            status_code=422,
            detail="Confirm that you are authorized to test this website",
        )
    scenario = await _get_visible_scenario(session, scenario_id, actor)
    website = await get_visible_website(session, scenario.website_id, actor)
    journey = await _get_site_journey(session, website.id, scenario.journey_id)

    try:
        steps = validate_and_normalize_steps(journey.steps, website_base_url=website.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        observation = await runner.run(steps=steps, website_base_url=website.base_url)
    except Exception as exc:
        logger.warning("Scenario runner failed (%s)", exc.__class__.__name__)
        observation = JourneyObservation(
            outcome="failed",
            duration_ms=0,
            step_results=(),
            error_message="The scenario could not be completed.",
            final_url=None,
        )

    row = ScenarioRun(
        scenario_id=scenario.id,
        website_id=website.id,
        journey_id=journey.id,
        outcome=observation.outcome,
        duration_ms=observation.duration_ms,
        step_results=[item.to_dict() for item in observation.step_results],
        error_message=observation.error_message,
        final_url=observation.final_url,
    )
    session.add(row)
    await _commit(session, name_conflict=False)
    await _refresh(session, row)
    return row


@router.get("/api/scenarios/{scenario_id}/runs", response_model=list[ScenarioRunResponse])
async def list_scenario_runs(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    limit: int = Query(default=_HISTORY_DEFAULT, ge=1, le=_HISTORY_MAX),
) -> list[ScenarioRun]:
    await _get_visible_scenario(session, scenario_id, actor)
    try:
        result = await session.execute(
            select(ScenarioRun)
            .where(ScenarioRun.scenario_id == scenario_id)
            .order_by(ScenarioRun.created_at.desc(), ScenarioRun.id.asc())
            .limit(limit)
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return list(result.scalars().all())


@router.get("/api/scenario-runs/{run_id}", response_model=ScenarioRunResponse)
async def get_scenario_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> ScenarioRun:
    try:
        run = await session.get(ScenarioRun, run_id)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    if run is None:
        raise HTTPException(status_code=404, detail="Scenario run not found.")
    await get_visible_website(session, run.website_id, actor)
    return run


def _normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > _MAX_DESCRIPTION:
        raise ValueError(f"Description must be {_MAX_DESCRIPTION} characters or fewer.")
    return cleaned


async def _get_site_journey(
    session: AsyncSession,
    website_id: UUID,
    journey_id: UUID,
) -> WebsiteJourney:
    try:
        journey = await session.get(WebsiteJourney, journey_id)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    if journey is None or journey.website_id != website_id:
        raise HTTPException(
            status_code=422,
            detail="journey_id must refer to a journey on this website.",
        )
    return journey


async def _get_visible_scenario(
    session: AsyncSession,
    scenario_id: UUID,
    actor: Actor,
) -> WebsiteScenario:
    try:
        scenario = await session.get(WebsiteScenario, scenario_id)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    await get_visible_website(session, scenario.website_id, actor)
    return scenario


async def _commit(session: AsyncSession, *, name_conflict: bool) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if name_conflict:
            raise HTTPException(
                status_code=409,
                detail="A scenario with this name already exists on the website.",
            ) from exc
        logger.warning("Scenario request failed (%s)", exc.__class__.__name__)
        raise HTTPException(
            status_code=422,
            detail="The scenario was rejected by a database constraint.",
        ) from exc
    except _DATABASE_ERRORS as exc:
        await session.rollback()
        _raise_database_error(exc)


async def _refresh(session: AsyncSession, row: object) -> None:
    try:
        await session.refresh(row)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Scenario request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
