"""Application factory and the ASGI object Uvicorn loads."""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Docker Desktop port-forwarded Postgres on Windows is unreliable with the
# default Proactor loop (WinError 1225). Prefer Selector for local API runs.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.api.routes.analysis import router as analysis_router
from app.api.routes.auth import router as auth_router
from app.api.routes.checks import router as check_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.journeys import router as journey_router
from app.api.routes.incident_drafts import router as incident_draft_router
from app.api.routes.pattern_hints import router as pattern_hint_router
from app.api.routes.scenarios import router as scenario_router
from app.api.routes.stats import router as stats_router
from app.api.routes.websites import router as website_router
from app.core.config import get_settings
from app.core.database import create_db_engine, create_session_factory
from app.services.public_demo import ensure_public_shell_demo
from app.services.seed import ensure_seed_user

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Install a simple log format once. Uvicorn may already have configured logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_app() -> FastAPI:
    """Build a new API instance.

    Tests call this directly so each test gets its own app and its own engine.
    Uvicorn uses the module-level `app` object below.
    """
    settings = get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_db_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        logger.info(
            "Starting %s %s (%s) public_shell=%s live_browser=%s analysis=%s",
            settings.app_name,
            settings.app_version,
            settings.environment,
            settings.public_shell,
            settings.browser_execution_allowed,
            settings.effective_analysis_provider,
        )
        await ensure_seed_user(app.state.session_factory, settings)
        await ensure_public_shell_demo(app.state.session_factory, settings)
        yield
        await engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(website_router)
    app.include_router(check_router)
    app.include_router(journey_router)
    app.include_router(scenario_router)
    app.include_router(stats_router)
    app.include_router(analysis_router)
    app.include_router(pattern_hint_router)
    app.include_router(incident_draft_router)
    return app


app = create_app()
