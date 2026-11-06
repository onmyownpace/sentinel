"""Async SQLAlchemy access to PostgreSQL.

Importing this module does not open a connection. The application factory
creates the engine during startup and closes it during shutdown. The pool
connects on first use.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Passed through to asyncpg.connect. Two seconds is long enough for a local
# database and short enough that the status page, which waits longer, can
# still receive the 503 instead of aborting the request.
_CONNECT_TIMEOUT_SECONDS = 2


def create_db_engine(settings: Settings) -> AsyncEngine:
    """Build a connection pool for `settings.database_url`."""
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"timeout": _CONNECT_TIMEOUT_SECONDS},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Factory for request-scoped sessions.

    `expire_on_commit=False` keeps loaded attributes usable after a commit.
    Async code cannot refresh them with an implicit lazy load. No route
    commits anything yet; the factory is ready for the first persisted feature.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


async def database_is_reachable(engine: AsyncEngine) -> bool:
    """Return whether PostgreSQL answers `SELECT 1`.

    The driver message is deliberately not logged or returned. Connection
    errors from asyncpg can include the database URL, password included.
    """
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database readiness check failed (%s)", exc.__class__.__name__)
        return False
