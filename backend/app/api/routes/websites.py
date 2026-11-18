"""Create, list, read, update enrollment/thresholds, and delete websites.

Browser callers must be signed in. Automation (n8n) may use
`X-Automation-Token` instead of a session cookie. New sites are owned by the
signed-in user. Automation listing can see every row.
"""

import logging
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Actor,
    get_session,
    get_visible_website,
    list_visible_websites,
    require_actor,
)
from app.core.config import get_settings
from app.core.urls import normalize_base_url
from app.models.website import Website
from app.models.website_check import WebsiteCheck
from app.services.screenshots import delete_screenshots

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/websites", tags=["websites"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)


class WebsiteCreate(BaseModel):
    """Payload for registering one website."""

    name: str
    base_url: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name": "Example", "base_url": "https://example.com"}]
        }
    )

    @field_validator("name")
    @classmethod
    def name_must_be_visible(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name must not be blank")
        if len(cleaned) > 120:
            raise ValueError("Name must be at most 120 characters")
        return cleaned

    @field_validator("base_url")
    @classmethod
    def base_url_must_be_http(cls, value: str) -> str:
        return normalize_base_url(value)


class WebsiteUpdate(BaseModel):
    """Patch enrollment, MON-2 thresholds, and AUTO-2 notification rules.

    Omit a field to leave it unchanged. Send JSON null for a threshold to clear it.
    """

    monitoring_enabled: bool | None = None
    latency_threshold_ms: int | None = None
    failure_threshold_count: int | None = None
    notify_on_fail: bool | None = None
    notify_on_recover: bool | None = None
    notify_on_latency: bool | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "monitoring_enabled": True,
                    "latency_threshold_ms": 3000,
                    "failure_threshold_count": 2,
                    "notify_on_fail": True,
                    "notify_on_recover": True,
                    "notify_on_latency": False,
                }
            ]
        }
    )

    @field_validator("latency_threshold_ms")
    @classmethod
    def latency_must_be_bounded(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1 or value > 120_000:
            raise ValueError("latency_threshold_ms must be between 1 and 120000")
        return value

    @field_validator("failure_threshold_count")
    @classmethod
    def failure_count_must_be_bounded(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1 or value > 20:
            raise ValueError("failure_threshold_count must be between 1 and 20")
        return value


class WebsiteResponse(BaseModel):
    """One stored website, safe to return to the browser."""

    id: UUID
    name: str
    base_url: str
    monitoring_enabled: bool
    latency_threshold_ms: int | None = None
    failure_threshold_count: int | None = None
    notify_on_fail: bool = True
    notify_on_recover: bool = True
    notify_on_latency: bool = True
    owner_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.post("", status_code=201, response_model=WebsiteResponse)
async def create_website(
    payload: WebsiteCreate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> Website:
    """Store a website owned by the signed-in user (or unowned for automation)."""
    owner_id = None if actor.is_automation or actor.user is None else actor.user.id
    website = Website(
        name=payload.name,
        base_url=payload.base_url,
        monitoring_enabled=False,
        owner_id=owner_id,
    )
    session.add(website)
    await _commit(session, website_conflict=True)
    await _refresh(session, website)
    logger.info("Registered website %s", website.id)
    return website


@router.get("", response_model=list[WebsiteResponse])
async def list_websites(
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
    monitoring: bool | None = Query(
        default=None,
        description="When true, only enrolled sites. When false, only sites not enrolled.",
    ),
) -> list[Website]:
    """Return websites visible to the caller, newest first."""
    try:
        return await list_visible_websites(session, actor, monitoring=monitoring)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


@router.get("/{website_id}", response_model=WebsiteResponse)
async def get_website(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> Website:
    """Return one website, or 404 when the id is unknown or not visible."""
    try:
        return await get_visible_website(session, website_id, actor)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


@router.patch("/{website_id}", response_model=WebsiteResponse)
async def update_website(
    website_id: UUID,
    payload: WebsiteUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> Website:
    """Update monitoring enrollment, thresholds, and/or notification rules."""
    provided = payload.model_fields_set
    if not provided:
        raise HTTPException(status_code=422, detail="Provide at least one field to update.")

    try:
        website = await get_visible_website(session, website_id, actor)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)

    if "monitoring_enabled" in provided and payload.monitoring_enabled is not None:
        website.monitoring_enabled = payload.monitoring_enabled
    if "latency_threshold_ms" in provided:
        website.latency_threshold_ms = payload.latency_threshold_ms
    if "failure_threshold_count" in provided:
        website.failure_threshold_count = payload.failure_threshold_count
    if "notify_on_fail" in provided and payload.notify_on_fail is not None:
        website.notify_on_fail = payload.notify_on_fail
    if "notify_on_recover" in provided and payload.notify_on_recover is not None:
        website.notify_on_recover = payload.notify_on_recover
    if "notify_on_latency" in provided and payload.notify_on_latency is not None:
        website.notify_on_latency = payload.notify_on_latency

    await _commit(session, website_conflict=False)
    await _refresh(session, website)
    logger.info("Updated website %s fields=%s", website_id, sorted(provided))
    return website


@router.delete("/{website_id}", status_code=204)
async def delete_website(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
    actor: Actor = Depends(require_actor),
) -> Response:
    """Delete one website. The response body is empty."""
    try:
        website = await get_visible_website(session, website_id, actor)
        paths = list(
            (
                await session.execute(
                    select(WebsiteCheck.screenshot_path).where(WebsiteCheck.website_id == website_id)
                )
            ).scalars()
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    await session.delete(website)
    await _commit(session, website_conflict=False)
    delete_screenshots(get_settings().screenshot_root, paths)
    logger.info("Deleted website %s", website_id)
    return Response(status_code=204)


async def _commit(session: AsyncSession, *, website_conflict: bool) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await _rollback(session)
        if website_conflict and _is_unique_violation(exc):
            raise HTTPException(
                status_code=409,
                detail="A website with this base URL is already registered.",
            ) from exc
        logger.warning("Website request failed (%s)", exc.__class__.__name__)
        raise HTTPException(
            status_code=422,
            detail="The website was rejected by a database constraint.",
        ) from exc
    except _DATABASE_ERRORS as exc:
        await _rollback(session)
        _raise_database_error(exc)


async def _refresh(session: AsyncSession, website: Website) -> None:
    try:
        await session.refresh(website)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception as exc:
        logger.warning("Website session rollback failed (%s)", exc.__class__.__name__)


def _is_unique_violation(exc: IntegrityError) -> bool:
    origin = getattr(exc, "orig", None)
    if getattr(origin, "sqlstate", None) == "23505":
        return True
    return origin.__class__.__name__ == "UniqueViolationError"


def _raise_database_error(exc: Exception) -> NoReturn:
    """Turn a driver failure into a response that does not include the URL."""
    logger.warning("Website request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
