"""Helpers for the $0 public shell (no live Chromium on free hosts)."""

from __future__ import annotations

from fastapi import HTTPException

from app.core.config import Settings, get_settings

LIVE_BROWSER_DISABLED_DETAIL = (
    "Live browser checks are disabled in the public shell. "
    "Run Sentinel locally (or on a full deployment with adequate compute) "
    "for Playwright checks, journeys, and scenarios."
)

REGISTRATION_DISABLED_DETAIL = (
    "Public registration is disabled on this deployment. "
    "Sign in with the demo account from the portfolio docs, "
    "or run Sentinel locally to create your own accounts."
)


def reject_if_live_browser_disabled(settings: Settings | None = None) -> None:
    """Refuse Chromium-backed work when the public shell (or flag) turns it off."""
    cfg = settings or get_settings()
    if cfg.browser_execution_allowed:
        return
    raise HTTPException(status_code=503, detail=LIVE_BROWSER_DISABLED_DETAIL)


def reject_if_registration_disabled(settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    if cfg.registration_allowed:
        return
    raise HTTPException(status_code=403, detail=REGISTRATION_DISABLED_DETAIL)
