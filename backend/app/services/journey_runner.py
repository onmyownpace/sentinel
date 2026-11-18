"""Execute declarative BROW-2 journeys with the same SSRF policy as one-shot checks."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from app.services.journey_steps import JourneyStep
from app.services.network import (
    ResolveHost,
    TargetNotAllowed,
    classify_browser_url,
    ensure_public_http_url,
)
from app.services.results import elapsed_ms, sanitize_url

logger = logging.getLogger(__name__)

_LAUNCH_ALLOWANCE_SECONDS = 10
_MAX_DURATION_MS = 180_000


@dataclass(frozen=True)
class StepResult:
    index: int
    op: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "op": self.op,
            "ok": self.ok,
            "detail": self.detail[:300],
        }


@dataclass(frozen=True)
class JourneyObservation:
    outcome: str
    duration_ms: int
    step_results: tuple[StepResult, ...]
    error_message: str | None
    final_url: str | None


class JourneyRunner(Protocol):
    async def run(
        self,
        *,
        steps: list[JourneyStep],
        website_base_url: str,
    ) -> JourneyObservation:
        """Execute one journey."""


class PlaywrightJourneyService:
    """Request-bound Playwright runner for mini-journeys."""

    def __init__(
        self,
        *,
        step_timeout_ms: int = 15_000,
        budget_seconds: float = 45,
        resolve: ResolveHost | None = None,
    ) -> None:
        self.step_timeout_ms = step_timeout_ms
        self.budget_seconds = budget_seconds
        self._resolve = resolve

    async def run(
        self,
        *,
        steps: list[JourneyStep],
        website_base_url: str,
    ) -> JourneyObservation:
        started = time.perf_counter()
        try:
            return await asyncio.wait_for(
                self._run(steps, website_base_url, started),
                timeout=self.budget_seconds,
            )
        except TimeoutError:
            return JourneyObservation(
                outcome="failed",
                duration_ms=_duration(started),
                step_results=(),
                error_message="The journey timed out before all steps finished.",
                final_url=None,
            )

    async def _run(
        self,
        steps: list[JourneyStep],
        website_base_url: str,
        started: float,
    ) -> JourneyObservation:
        # SSRF on the site itself first.
        try:
            await ensure_public_http_url(website_base_url, resolve=self._resolve)
        except TargetNotAllowed as exc:
            return JourneyObservation(
                outcome="failed",
                duration_ms=_duration(started),
                step_results=(),
                error_message=exc.message,
                final_url=None,
            )

        for step in steps:
            if step.op == "navigate" and step.url:
                try:
                    await ensure_public_http_url(step.url, resolve=self._resolve)
                except TargetNotAllowed as exc:
                    return JourneyObservation(
                        outcome="failed",
                        duration_ms=_duration(started),
                        step_results=(
                            StepResult(0, "navigate", False, exc.message),
                        ),
                        error_message=exc.message,
                        final_url=None,
                    )

        playwright = None
        browser = None
        context = None
        results: list[StepResult] = []
        try:
            try:
                from playwright.async_api import Error as PlaywrightError
                from playwright.async_api import TimeoutError as PlaywrightTimeoutError
                from playwright.async_api import async_playwright
            except ImportError:
                return _failed(started, "The browser runner is not available.")

            try:
                playwright = await async_playwright().start()
                browser = await playwright.chromium.launch(headless=True)
            except Exception as exc:
                logger.warning("Journey browser launch failed (%s)", exc.__class__.__name__)
                return _failed(started, "The browser runner is not available.")

            context = await browser.new_context(ignore_https_errors=False)
            page = await context.new_page()
            page.set_default_timeout(self.step_timeout_ms)
            page.set_default_navigation_timeout(self.step_timeout_ms)

            decisions: dict[str, str] = {}

            async def guard(route) -> None:
                request = route.request
                decision = await _cached_decision(request.url, decisions, self._resolve)
                if decision == "skip":
                    await route.continue_()
                    return
                if decision == "block":
                    await route.abort("blockedbyclient")
                    return
                await route.continue_()

            await page.route("**/*", guard)

            for index, step in enumerate(steps):
                try:
                    ok, detail = await _execute_step(page, step, PlaywrightError, PlaywrightTimeoutError)
                except Exception as exc:
                    logger.warning("Journey step failed (%s)", exc.__class__.__name__)
                    ok, detail = False, "The step could not be completed."
                results.append(StepResult(index=index, op=step.op, ok=ok, detail=detail))
                if not ok:
                    final = sanitize_url(page.url) if page.url else None
                    if final == "non-http resource":
                        final = None
                    return JourneyObservation(
                        outcome="failed",
                        duration_ms=_duration(started),
                        step_results=tuple(results),
                        error_message=detail,
                        final_url=final,
                    )

            final = sanitize_url(page.url) if page.url else None
            if final == "non-http resource":
                final = None
            return JourneyObservation(
                outcome="success",
                duration_ms=_duration(started),
                step_results=tuple(results),
                error_message=None,
                final_url=final,
            )
        except Exception as exc:
            logger.warning("Journey failed (%s)", exc.__class__.__name__)
            return _failed(started, "The journey could not be completed.", tuple(results))
        finally:
            await _close_quietly(context)
            await _close_quietly(browser)
            await _stop_quietly(playwright)


async def _execute_step(page, step: JourneyStep, PlaywrightError, PlaywrightTimeoutError) -> tuple[bool, str]:
    if step.op == "navigate":
        assert step.url is not None
        try:
            response = await page.goto(step.url, wait_until="domcontentloaded")
        except PlaywrightTimeoutError:
            return False, "Navigation timed out."
        except PlaywrightError:
            return False, "Navigation failed."
        status = response.status if response is not None else None
        if status is not None and not 200 <= status < 400:
            return False, f"Navigation responded with HTTP {status}."
        return True, "Navigated."

    if step.op == "fill":
        assert step.selector is not None and step.value is not None
        try:
            await page.fill(step.selector, step.value)
        except PlaywrightTimeoutError:
            return False, "Fill timed out."
        except PlaywrightError:
            return False, "Fill failed."
        return True, "Filled."

    if step.op == "click":
        assert step.selector is not None
        try:
            await page.click(step.selector)
        except PlaywrightTimeoutError:
            return False, "Click timed out."
        except PlaywrightError:
            return False, "Click failed."
        return True, "Clicked."

    if step.op == "assert_text":
        assert step.selector is not None and step.value is not None
        try:
            text = await page.locator(step.selector).first.inner_text()
        except PlaywrightTimeoutError:
            return False, "Assert text timed out."
        except PlaywrightError:
            return False, "Assert text failed."
        if step.value not in (text or ""):
            return False, "Expected text was not found."
        return True, "Text matched."

    if step.op == "assert_url_contains":
        assert step.value is not None
        current = page.url or ""
        if step.value not in current:
            return False, "URL did not contain the expected value."
        return True, "URL matched."

    if step.op == "assert_visible":
        assert step.selector is not None
        try:
            await page.locator(step.selector).first.wait_for(state="visible")
        except PlaywrightTimeoutError:
            return False, "Element was not visible."
        except PlaywrightError:
            return False, "Assert visible failed."
        return True, "Element visible."

    return False, "Unknown step."


async def _cached_decision(url: str, decisions: dict[str, str], resolve: ResolveHost | None) -> str:
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


def _failed(
    started: float,
    message: str,
    step_results: tuple[StepResult, ...] = (),
) -> JourneyObservation:
    return JourneyObservation(
        outcome="failed",
        duration_ms=_duration(started),
        step_results=step_results,
        error_message=message,
        final_url=None,
    )


def _duration(started: float) -> int:
    return min(_MAX_DURATION_MS, elapsed_ms(started))


async def _close_quietly(resource) -> None:
    if resource is None:
        return
    try:
        await resource.close()
    except Exception as exc:
        logger.warning("Journey resource close failed (%s)", exc.__class__.__name__)


async def _stop_quietly(playwright) -> None:
    if playwright is None:
        return
    try:
        await playwright.stop()
    except Exception as exc:
        logger.warning("Journey stop failed (%s)", exc.__class__.__name__)


def journey_runner_from_settings(
    navigation_timeout_seconds: float,
    *,
    budget_seconds: float = 45,
    resolve: ResolveHost | None = None,
) -> PlaywrightJourneyService:
    return PlaywrightJourneyService(
        step_timeout_ms=round(navigation_timeout_seconds * 1000),
        budget_seconds=budget_seconds,
        resolve=resolve,
    )
