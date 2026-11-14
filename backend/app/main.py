"""Application factory and the ASGI object Uvicorn loads."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.checks import router as check_router
from app.api.routes.health import router as health_router
from app.api.routes.websites import router as website_router
from app.core.config import get_settings
from app.core.database import create_db_engine, create_session_factory

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
        logger.info("Starting %s %s (%s)", settings.app_name, settings.app_version, settings.environment)
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
    app.include_router(website_router)
    app.include_router(check_router)
    return app


app = create_app()
