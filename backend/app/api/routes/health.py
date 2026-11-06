"""Process liveness and database readiness.

These are separate because they answer different questions:

- Liveness: is this process able to respond at all?
- Readiness: can this process do useful work, which today means reaching PostgreSQL?

A database outage makes the API unready. It does not mean the process itself
is dead. That distinction matters once a supervisor starts restarting unhealthy
processes.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import database_is_reachable

router = APIRouter(tags=["health"])

_SERVICE_NAME = "sentinel-api"


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class ReadinessResponse(HealthResponse):
    checks: dict[str, str]


def _identity() -> dict[str, str]:
    settings = get_settings()
    return {
        "service": _SERVICE_NAME,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the process is running. This route does not touch the database."""
    return HealthResponse(status="ok", **_identity())


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(request: Request) -> JSONResponse:
    """Report whether PostgreSQL accepted a trivial query."""
    engine = getattr(request.app.state, "engine", None)
    reachable = engine is not None and await database_is_reachable(engine)
    body = ReadinessResponse(
        status="ok" if reachable else "degraded",
        checks={"database": "ok" if reachable else "unavailable"},
        **_identity(),
    )
    return JSONResponse(
        status_code=200 if reachable else 503,
        content=body.model_dump(),
    )
