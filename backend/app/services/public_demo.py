"""Seed clearly labelled demo rows for the public shell (no Playwright)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.user import User
from app.models.website import Website
from app.models.website_check import WebsiteCheck

logger = logging.getLogger(__name__)

DEMO_SITE_NAME = "[Demo] Example status page"
DEMO_SITE_URL = "https://example.com"
DEMO_MARKER = "Demo result — not a live browser check. Live Playwright runs require a local or full deployment."
DEMO_NAME_PREFIX = "[Demo]"


def is_demo_website_name(name: str | None) -> bool:
    """True for seeded portfolio sample sites (not the user's live product)."""
    return bool(name) and name.strip().startswith(DEMO_NAME_PREFIX)


def is_demo_check_result(error_message: str | None) -> bool:
    """True when the check row is sample/portfolio data, not a live browser run."""
    if not error_message:
        return False
    return error_message.startswith("Demo result — not a live browser check")


async def ensure_public_shell_demo(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Insert one demo site + sample checks when PUBLIC_SHELL is on."""
    if not settings.public_shell:
        return
    email = (settings.seed_user_email or "").strip().lower()
    if not email:
        logger.warning("Public shell demo skipped: SEED_USER_EMAIL is empty")
        return

    try:
        async with session_factory() as session:
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if user is None:
                logger.warning("Public shell demo skipped: seed user %s missing", email)
                return

            existing = (
                await session.execute(
                    select(Website).where(
                        Website.owner_id == user.id,
                        Website.name == DEMO_SITE_NAME,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                site = Website(
                    name=DEMO_SITE_NAME,
                    base_url=DEMO_SITE_URL,
                    owner_id=user.id,
                    monitoring_enabled=False,
                )
                session.add(site)
                await session.flush()
            else:
                site = existing

            check_count = (
                await session.execute(
                    select(WebsiteCheck).where(WebsiteCheck.website_id == site.id).limit(1)
                )
            ).scalar_one_or_none()
            if check_count is None:
                now = datetime.now(UTC)
                session.add_all(
                    [
                        WebsiteCheck(
                            website_id=site.id,
                            outcome="success",
                            http_status=200,
                            page_title="[Demo] Sample homepage",
                            final_url=DEMO_SITE_URL,
                            duration_ms=142,
                            console_errors=[],
                            failed_requests=[],
                            error_message=DEMO_MARKER,
                            created_at=now - timedelta(minutes=12),
                        ),
                        WebsiteCheck(
                            website_id=site.id,
                            outcome="failed",
                            http_status=503,
                            page_title=None,
                            final_url=DEMO_SITE_URL,
                            duration_ms=88,
                            console_errors=[],
                            failed_requests=[],
                            error_message=DEMO_MARKER,
                            created_at=now - timedelta(minutes=5),
                        ),
                    ]
                )
            await session.commit()
            logger.info("Public shell demo data ready for %s", email)
    except (SQLAlchemyError, OSError, TimeoutError, ConnectionError) as exc:
        logger.warning("Public shell demo skipped (%s)", exc.__class__.__name__)
    except Exception as exc:
        logger.warning("Public shell demo skipped (%s)", exc.__class__.__name__)
