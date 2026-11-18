"""Dev seed helpers.

Creates a local account on startup when SEED_USER_EMAIL is set and that email
is not already registered. Optionally claims websites that still have no owner
so the dashboard is not empty after upgrading an older database.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.core.config import Settings
from app.models.user import User
from app.models.website import Website
from app.services.passwords import hash_password, validate_password_plaintext

logger = logging.getLogger(__name__)


async def ensure_seed_user(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Create the configured seed user when missing. Safe to call repeatedly."""
    email = (settings.seed_user_email or "").strip().lower()
    password = settings.seed_user_password or ""
    if not email:
        return
    try:
        validate_password_plaintext(password)
    except ValueError as exc:
        logger.warning("Seed user skipped: %s", exc)
        return

    try:
        async with session_factory() as session:
            existing = await session.execute(select(User).where(User.email == email))
            user = existing.scalar_one_or_none()
            if user is None:
                user = User(email=email, password_hash=hash_password(password))
                session.add(user)
                await session.flush()
                logger.info("Seeded development user %s", email)
            await session.execute(
                update(Website).where(Website.owner_id.is_(None)).values(owner_id=user.id)
            )
            await session.commit()
    except (SQLAlchemyError, OSError, TimeoutError, ConnectionError) as exc:
        # Tables may not exist yet, or Postgres may be unreachable during tests.
        logger.warning("Seed user skipped (%s)", exc.__class__.__name__)
    except Exception as exc:
        # asyncpg can surface CancelledError wrappers on a refused connection.
        logger.warning("Seed user skipped (%s)", exc.__class__.__name__)
