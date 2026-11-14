"""Open one registered website in Chromium and collect a bounded result.

The API calls `run()` and waits. Nothing here is scheduled, and nothing here
reads request headers, cookies, or bodies. A missing browser becomes a failed
result with a fixed sentence, not a stack trace.
"""

import asyncio
import logging
import time
from typing import Protocol
from urllib.parse import urlsplit

from app.services.network import (
    BLOCKED_REQUEST,
    UNSAFE_TARGET,
    ResolveHost,
    TargetNotAllowed,
    classify_browser_url,
    ensure_public_http_url,
)
from app.services.results import (
    BROWSER_UNAVAILABLE,
    CHECK_TIMED_OUT,
    PAGE_COULD_NOT_BE_OPENED,
    CheckObservation,
    FailedRequestSummary,
    elapsed_ms,
    failed_observation,
    http_failure,
    sanitize_observation,
    sanitize_url,
)

logger = logging.getLogger(__name__)

_LAUNCH_ALLOWANCE_SECONDS = 10
_COLLECT_LIMIT = 10


class CheckRunner(Protocol):
    """The shape the route needs. Tests supply a fake that records the URL."""

    async def run(self, url: str) -> CheckObservation:
        """Open `url` and return a sanitized observation."""


class PlaywrightCheckService:
    """One Chromium launch per check. The caller closes nothing; `run` does."""

    def __init__(
        self,
        *,
        navigation_timeout_ms: int = 15_000,
        budget_seconds: float | None = None,
        resolve: ResolveHost | None = None,
    ) -> None:
        self.navigation_timeout_ms = navigation_timeout_ms
        self.budget_seconds = (
            budget_seconds
            if budget_seconds is not None
            else (navigation_timeout_ms / 1000) + _LAUNCH_ALLOWANCE_SECONDS
        )
        self._resolve = resolve

    async def run(self, url: str) -> CheckObservation:
        """Run one check and stop it if the budget expires."""
        started = time.perf_counter()
        try:
            return await asyncio.wait_for(self._run(url, started), timeout=self.budget_seconds)
        except TimeoutError:
            return failed_observation(started, CHECK_TIMED_OUT)


    async def _run(self, url: str, started: float) -> CheckObservation:
        try:
            await ensure_public_http_url(url, resolve=self._resolve)
        except TargetNotAllowed as exc:
            return failed_observation(started, exc.message)

        playwright = None
        browser = None
        context = None
        try:
            try:
                from playwright.async_api import Error as PlaywrightError
                from playwright.async_api import TimeoutError as PlaywrightTimeoutError
                from playwright.async_api import async_playwright
            except ImportError:
                logger.warning("Website check browser import failed (ImportError)")
                return failed_observation(started, BROWSER_UNAVAILABLE)

            try:
                playwright = await async_playwright().start()
                browser = await playwright.chromium.launch(headless=True)
            except Exception as exc:
                logger.warning("Website check browser launch failed (%s)", exc.__class__.__name__)
                return failed_observation(started, BROWSER_UNAVAILABLE)

            context = await browser.new_context(ignore_https_errors=False)
            page = await context.new_page()
            page.set_default_navigation_timeout(self.navigation_timeout_ms)
            page.set_default_timeout(self.navigation_timeout_ms)

            console_errors: list[str] = []
            failed_requests: list[FailedRequestSummary] = []
            blocked_urls: set[str] = set()
            blocked_navigation = False
            decisions: dict[str, str] = {}

            def on_console(message) -> None:
                if message.type != "error" or len(console_errors) >= _COLLECT_LIMIT:
                    return
                console_errors.append(str(message.text)[:500])

            def on_request_failed(request) -> None:
                if request.url in blocked_urls or len(failed_requests) >= _COLLECT_LIMIT:
                    return
                failure = request.failure
                if isinstance(failure, dict):
                    error = str(failure.get("errorText") or "The request failed.")
                else:
                    error = "The request failed."
                if "BLOCKED_BY_CLIENT" in error.upper():
                    return
                failed_requests.append(FailedRequestSummary(sanitize_url(request.url), error[:200]))

            async def guard(route) -> None:
                nonlocal blocked_navigation
                request = route.request
                decision = await _cached_decision(request.url, decisions, self._resolve)
                if decision == "skip":
                    await route.continue_()
                    return
                if decision == "block":
                    blocked_urls.add(request.url)
                    if request.is_navigation_request():
                        blocked_navigation = True
                    if len(failed_requests) < _COLLECT_LIMIT:
                        failed_requests.append(
                            FailedRequestSummary(sanitize_url(request.url), BLOCKED_REQUEST)
                        )
                    await route.abort("blockedbyclient")
                    return
                await route.continue_()

            page.on("console", on_console)
            page.on("requestfailed", on_request_failed)
            await page.route("**/*", guard)

            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.navigation_timeout_ms,
                )
            except PlaywrightTimeoutError:
                return failed_observation(
                    started,
                    CHECK_TIMED_OUT,
                    console_errors=tuple(console_errors),
                    failed_requests=tuple(failed_requests),
                )
            except PlaywrightError:
                logger.warning("Website check navigation failed (Error)")
                message = UNSAFE_TARGET if blocked_navigation else PAGE_COULD_NOT_BE_OPENED
                return failed_observation(
                    started,
                    message,
                    console_errors=tuple(console_errors),
                    failed_requests=tuple(failed_requests),
                )

            status = response.status if response is not None else None
            try:
                title = await page.title()
            except PlaywrightError:
                title = None
            final_url = page.url
            outcome = "success" if status is not None and 200 <= status < 400 else "failed"
            error = None
            if outcome == "failed":
                error = http_failure(status) if status is not None else PAGE_COULD_NOT_BE_OPENED
            if blocked_navigation:
                outcome = "failed"
                error = UNSAFE_TARGET

            return sanitize_observation(
                CheckObservation(
                    outcome=outcome,
                    http_status=status,
                    page_title=title,
                    final_url=final_url,
                    duration_ms=elapsed_ms(started),
                    console_errors=tuple(console_errors),
                    failed_requests=tuple(failed_requests),
                    error_message=error,
                )
            )
        except Exception as exc:
            logger.warning("Website check failed (%s)", exc.__class__.__name__)
            return failed_observation(started, PAGE_COULD_NOT_BE_OPENED)
        finally:
            await _close_quietly(context)
            await _close_quietly(browser)
            await _stop_quietly(playwright)


async def _cached_decision(url: str, decisions: dict[str, str], resolve: ResolveHost | None) -> str:
    """Reuse one host decision for the rest of this check.

    Chromium still connects on its own after this lookup. A DNS change between
    the lookup and the connection is not closed by the cache, and the cache
    makes that window longer for later requests to the same host.
    """
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "block"
    if parsed.scheme.lower() in {"data", "blob"}:
        return "skip"
    host = (parsed.hostname or "").lower().rstrip(".")
    cached = decisions.get(host)
    if host and cached is not None:
        return cached
    decision = await classify_browser_url(url, resolve=resolve)
    if host:
        decisions[host] = decision
    return decision


async def _close_quietly(resource) -> None:
    if resource is None:
        return
    try:
        await resource.close()
    except Exception as exc:
        logger.warning("Browser resource close failed (%s)", exc.__class__.__name__)


async def _stop_quietly(playwright) -> None:
    if playwright is None:
        return
    try:
        await playwright.stop()
    except Exception as exc:
        logger.warning("Browser stop failed (%s)", exc.__class__.__name__)


def runner_from_settings(timeout_seconds: float, resolve: ResolveHost | None = None) -> PlaywrightCheckService:
    """Build the real runner. Routes call this when no test runner was installed."""
    return PlaywrightCheckService(
        navigation_timeout_ms=round(timeout_seconds * 1000),
        resolve=resolve,
    )
