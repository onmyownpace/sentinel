"""Dependencies shared by API routes."""

from collections.abc import AsyncIterator

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession


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
