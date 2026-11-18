"""Dependencies shared by API routes."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.models.website import Website
from app.models.website_check import WebsiteCheck
from app.services.sessions import SESSION_COOKIE_NAME, automation_header_name, load_user_for_token


@dataclass(frozen=True)
class Actor:
    """Who is calling a protected route.

    Either a signed-in user (browser cookie) or automation (shared token for n8n).
    Scheduled browser opens still use SCHEDULE_CHECK_TOKEN on their own route.
    """

    user: User | None
    is_automation: bool


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield one database session for the current request.

    The session factory is created during application startup and stored on
    `app.state`. A missing factory means this process cannot do database work.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="The database is unavailable.")
    async with factory() as session:
        yield session


def _tokens_equal(presented: str, expected: str) -> bool:
    if len(presented) != len(expected):
        return False
    return secrets.compare_digest(presented, expected)


async def get_optional_actor(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_automation_token: str | None = Header(default=None, alias="X-Automation-Token"),
) -> Actor | None:
    """Return an actor when the cookie or automation header is valid."""
    settings = get_settings()
    expected = (settings.automation_token or "").strip()
    if expected and x_automation_token and _tokens_equal(x_automation_token, expected):
        return Actor(user=None, is_automation=True)

    raw = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        user = await load_user_for_token(session, raw)
    except Exception:
        raise HTTPException(status_code=503, detail="The database is unavailable.") from None
    if user is not None:
        return Actor(user=user, is_automation=False)
    return None


async def require_actor(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_automation_token: str | None = Header(default=None, alias="X-Automation-Token"),
) -> Actor:
    """Require a signed-in user or a matching automation token."""
    actor = await get_optional_actor(request, session, x_automation_token)
    if actor is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "Sign in required. Send a session cookie, or the "
                f"{automation_header_name()} header for automation."
            ),
        )
    return actor


async def require_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Require a browser session. Automation tokens are not enough."""
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        user = await load_user_for_token(session, raw)
    except Exception:
        raise HTTPException(status_code=503, detail="The database is unavailable.") from None
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user


def website_visible_to_user(owner_id: UUID | None, user_id: UUID) -> bool:
    return owner_id is None or owner_id == user_id


async def get_visible_website(
    session: AsyncSession,
    website_id: UUID,
    actor: Actor,
) -> Website:
    website = await session.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found.")
    if actor.is_automation:
        return website
    assert actor.user is not None
    if not website_visible_to_user(website.owner_id, actor.user.id):
        raise HTTPException(status_code=404, detail="Website not found.")
    return website


async def get_visible_check(
    session: AsyncSession,
    check_id: UUID,
    actor: Actor,
) -> WebsiteCheck:
    row = await session.get(WebsiteCheck, check_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Check not found.")
    await get_visible_website(session, row.website_id, actor)
    return row


async def list_visible_websites(
    session: AsyncSession,
    actor: Actor,
    *,
    monitoring: bool | None,
) -> list[Website]:
    stmt = select(Website)
    if not actor.is_automation:
        assert actor.user is not None
        stmt = stmt.where(
            or_(Website.owner_id == actor.user.id, Website.owner_id.is_(None))
        )
    if monitoring is True:
        stmt = stmt.where(Website.monitoring_enabled.is_(True))
    elif monitoring is False:
        stmt = stmt.where(Website.monitoring_enabled.is_(False))
    stmt = stmt.order_by(Website.created_at.desc(), Website.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())
