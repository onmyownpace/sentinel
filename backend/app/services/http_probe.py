"""Lightweight HTTP GET probe for the public shell (no Playwright).

Fetches a URL with bounded time and body size, records status / latency /
optional HTML title. Reuses the public-address policy so private and
metadata targets stay blocked — including redirect hops.
"""

from __future__ import annotations

import asyncio
import re
import time
from html import unescape
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.services.network import ResolveHost, TargetNotAllowed, ensure_public_http_url
from app.services.results import (
    CHECK_TIMED_OUT,
    PAGE_COULD_NOT_BE_OPENED,
    CheckObservation,
    elapsed_ms,
    failed_observation,
    http_failure,
    sanitize_observation,
    sanitize_url,
)

PROBE_MARKER: Final = (
    "Lightweight HTTP probe — not a full browser check. "
    "No Chromium, console capture, or screenshots."
)

_DEFAULT_TIMEOUT_SECONDS: Final = 8.0
_MAX_BODY_BYTES: Final = 64_000
_MAX_REDIRECTS: Final = 5
_USER_AGENT: Final = "SentinelPublicProbe/1.0 (+https://sentinel.mindfold.fyi)"
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class _NoRedirect(HTTPRedirectHandler):
    """Surface redirects as HTTPError so each hop can be re-validated."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


async def probe_http_url(
    url: str,
    *,
    resolve: ResolveHost | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_body_bytes: int = _MAX_BODY_BYTES,
) -> CheckObservation:
    """GET `url` after public-address checks; never follows into private hosts."""
    started = time.perf_counter()
    current = url.strip()
    opener = build_opener(_NoRedirect)

    try:
        for _ in range(_MAX_REDIRECTS + 1):
            try:
                await ensure_public_http_url(current, resolve=resolve)
            except TargetNotAllowed as exc:
                return failed_observation(started, exc.message)

            try:
                status, final_url, body, location = await asyncio.wait_for(
                    asyncio.to_thread(
                        _fetch_once,
                        opener,
                        current,
                        timeout_seconds,
                        max_body_bytes,
                    ),
                    timeout=timeout_seconds + 1.0,
                )
            except TimeoutError:
                return failed_observation(started, CHECK_TIMED_OUT)
            except URLError:
                return failed_observation(started, PAGE_COULD_NOT_BE_OPENED)
            except Exception:
                return failed_observation(started, PAGE_COULD_NOT_BE_OPENED)

            if status in {301, 302, 303, 307, 308} and location:
                current = urljoin(final_url or current, location)
                continue

            title = _extract_title(body)
            cleaned_final = sanitize_url(final_url or current)
            if cleaned_final == "non-http resource":
                cleaned_final = None
            if not 200 <= status < 400:
                return failed_observation(
                    started,
                    http_failure(status),
                    http_status=status,
                    page_title=title,
                    final_url=cleaned_final,
                )
            return sanitize_observation(
                CheckObservation(
                    outcome="success",
                    http_status=status,
                    page_title=title,
                    final_url=cleaned_final,
                    duration_ms=elapsed_ms(started),
                    console_errors=(),
                    failed_requests=(),
                    error_message=None,
                    screenshot_png=None,
                )
            )
    except TimeoutError:
        return failed_observation(started, CHECK_TIMED_OUT)

    return failed_observation(started, "Too many redirects while probing the URL.")


def attach_probe_marker(observation: CheckObservation) -> CheckObservation:
    """Stamp every probe row so public demo routes can list and analyze it."""
    cleaned = sanitize_observation(observation)
    if cleaned.outcome == "success":
        message = PROBE_MARKER
    elif cleaned.error_message and cleaned.error_message.startswith(PROBE_MARKER):
        message = cleaned.error_message
    elif cleaned.error_message:
        message = f"{PROBE_MARKER} {cleaned.error_message}"
    else:
        message = PROBE_MARKER
    return CheckObservation(
        outcome=cleaned.outcome,
        http_status=cleaned.http_status,
        page_title=cleaned.page_title,
        final_url=cleaned.final_url,
        duration_ms=cleaned.duration_ms,
        console_errors=cleaned.console_errors,
        failed_requests=cleaned.failed_requests,
        error_message=message,
        screenshot_png=None,
    )


def is_probe_result(error_message: str | None) -> bool:
    return bool(error_message) and error_message.startswith("Lightweight HTTP probe")


def _fetch_once(
    opener,
    url: str,
    timeout_seconds: float,
    max_body_bytes: int,
) -> tuple[int, str, bytes, str | None]:
    request = Request(
        url,
        method="GET",
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en",
        },
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", None) or response.getcode() or 0)
            final = response.geturl() or url
            body = response.read(max_body_bytes + 1)[:max_body_bytes]
            return status, final, body, None
    except HTTPError as exc:
        status = int(exc.code)
        final = exc.geturl() if hasattr(exc, "geturl") else url
        location = exc.headers.get("Location") if exc.headers else None
        if status in {301, 302, 303, 307, 308} and location:
            return status, final or url, b"", location
        try:
            body = exc.read(max_body_bytes + 1)[:max_body_bytes] if exc.fp is not None else b""
        except Exception:
            body = b""
        return status, final or url, body, None


def _extract_title(body: bytes) -> str | None:
    if not body:
        return None
    text = body.decode("utf-8", errors="ignore")
    match = _TITLE_RE.search(text)
    if not match:
        return None
    title = unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    return title[:300] if title else None
