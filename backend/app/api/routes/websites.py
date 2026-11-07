"""Create, list, read, and delete registered websites.

Authentication is intentionally absent. Every caller of this development
process sees the same rows.
"""

import logging
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.urls import normalize_base_url
from app.models.website import Website

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


class WebsiteResponse(BaseModel):
    """One stored website, safe to return to the browser."""

    id: UUID
    name: str
    base_url: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.post("", status_code=201, response_model=WebsiteResponse)
async def create_website(
    payload: WebsiteCreate,
    session: AsyncSession = Depends(get_session),
) -> Website:
    """Store a website and return the row, including database timestamps."""
    website = Website(name=payload.name, base_url=payload.base_url)
    session.add(website)
    await _commit(session, website_conflict=True)
    await _refresh(session, website)
    logger.info("Registered website %s", website.id)
    return website


@router.get("", response_model=list[WebsiteResponse])
async def list_websites(session: AsyncSession = Depends(get_session)) -> list[Website]:
    """Return every website, newest first."""
    try:
        result = await session.execute(
            select(Website).order_by(Website.created_at.desc(), Website.id.asc())
        )
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    return list(result.scalars().all())


@router.get("/{website_id}", response_model=WebsiteResponse)
async def get_website(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Website:
    """Return one website, or 404 when the id is unknown."""
    website = await _get_or_404(session, website_id)
    return website


@router.delete("/{website_id}", status_code=204)
async def delete_website(
    website_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete one website. The response body is empty."""
    website = await _get_or_404(session, website_id)
    await session.delete(website)
    await _commit(session, website_conflict=False)
    logger.info("Deleted website %s", website_id)
    return Response(status_code=204)


async def _get_or_404(session: AsyncSession, website_id: UUID) -> Website:
    try:
        website = await session.get(Website, website_id)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found.")
    return website


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
