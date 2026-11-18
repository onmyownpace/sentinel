"""Async SQLAlchemy access to PostgreSQL.

Importing this module does not open a connection. The application factory
creates the engine during startup and closes it during shutdown. The pool
connects on first use.
"""

import logging
import ssl

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

logger = logging.getLogger(__name__)


def create_db_engine(settings: Settings) -> AsyncEngine:
    """Build a connection pool for `settings.database_url`.

    Local Compose Postgres stays plaintext (DATABASE_SSL=false). Neon / public
    shell enables TLS via asyncpg `ssl=True` without changing the local default.
    """
    connect_args: dict = {"timeout": settings.database_connect_timeout_seconds}
    if settings.database_ssl_required:
        # Verify TLS for hosted Postgres. Local public_shell misconfig would also
        # request SSL — operators should point DATABASE_URL at Neon, not Compose.
        connect_args["ssl"] = ssl.create_default_context()

    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Factory for request-scoped sessions.

    `expire_on_commit=False` keeps loaded attributes usable after a commit.
    Async code cannot refresh them with an implicit lazy load. Website routes
    commit through a session from this factory, then refresh explicitly when
    they need database-generated values such as timestamps.
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
