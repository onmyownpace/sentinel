"""Server-side session tokens stored as HttpOnly cookies.

The cookie carries a random token. The database stores only SHA-256 of that
token, so a stolen database row is not enough to forge the cookie.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserSession

SESSION_COOKIE_NAME = "sentinel_session"
_AUTOMATION_HEADER = "X-Automation-Token"


def automation_header_name() -> str:
    return _AUTOMATION_HEADER


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


async def create_session(
    session: AsyncSession,
    user_id: UUID,
    *,
    ttl_days: int,
) -> tuple[UserSession, str]:
    """Persist a session row and return `(row, raw_cookie_value)`."""
    raw = new_session_token()
    row = UserSession(
        user_id=user_id,
        token_hash=hash_session_token(raw),
        expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
    )
    session.add(row)
    await session.flush()
    return row, raw


async def load_user_for_token(
    session: AsyncSession,
    raw_token: str | None,
) -> User | None:
    """Resolve a cookie token to a user, or None when missing/expired."""
    if not raw_token:
        return None
    token_hash = hash_session_token(raw_token)
    result = await session.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == token_hash)
    )
    pair = result.first()
    if pair is None:
        return None
    user_session, user = pair
    expires = user_session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= datetime.now(UTC):
        await session.delete(user_session)
        await session.commit()
        return None
    return user


async def revoke_session(session: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    token_hash = hash_session_token(raw_token)
    result = await session.execute(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()
