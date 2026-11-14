"""Check results, with secrets removed before anything is stored or returned.

Stored URLs keep the scheme, host, port, and path. Userinfo, query strings,
and fragments are dropped because they can carry tokens. Console text is
truncated and passed through a small set of redaction patterns. A page can
still print a secret in a shape these patterns do not recognize.
"""

import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.services.network import UNSAFE_TARGET

PAGE_COULD_NOT_BE_OPENED = "The page could not be opened."
CHECK_TIMED_OUT = "The check timed out before the page finished loading."
BROWSER_UNAVAILABLE = "The browser runner is not available."

_MAX_CONSOLE_ERRORS = 10
_MAX_FAILED_REQUESTS = 10
_MAX_TEXT = 300
_MAX_ERROR = 500
_MAX_URL = 2048
_MAX_DURATION_MS = 120_000

_LABELED_SECRET = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|token|password)\b\s*[:=]\s*[^\n\r]{1,200}"
)
_BEARER = re.compile(r"(?i)\bBearer\s+\S+")
_USERINFO_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@]+:[^\s/@]+@[^\s]+")


@dataclass(frozen=True)
class FailedRequestSummary:
    """A request that failed or was blocked, without headers or a body."""

    url: str
    error: str


@dataclass(frozen=True)
class CheckObservation:
    """What one check is allowed to remember."""

    outcome: str
    http_status: int | None
    page_title: str | None
    final_url: str | None
    duration_ms: int
    console_errors: tuple[str, ...]
    failed_requests: tuple[FailedRequestSummary, ...]
    error_message: str | None


def elapsed_ms(started: float) -> int:
    """Milliseconds since `started`, capped at the column's upper bound."""
    measured = round((time.perf_counter() - started) * 1000)
    return min(_MAX_DURATION_MS, max(0, measured))


def http_failure(status: int) -> str:
    return f"The page responded with HTTP {status}."


def failed_observation(
    started: float,
    message: str,
    *,
    http_status: int | None = None,
    page_title: str | None = None,
    final_url: str | None = None,
    console_errors: tuple[str, ...] = (),
    failed_requests: tuple[FailedRequestSummary, ...] = (),
) -> CheckObservation:
    """Build a failed result and run it through the same sanitizer as a success."""
    return sanitize_observation(
        CheckObservation(
            outcome="failed",
            http_status=http_status,
            page_title=page_title,
            final_url=final_url,
            duration_ms=elapsed_ms(started),
            console_errors=console_errors,
            failed_requests=failed_requests,
            error_message=message,
        )
    )


def sanitize_observation(observation: CheckObservation) -> CheckObservation:
    """Return a copy that is safe to store and send to the browser."""
    status = observation.http_status
    if status is not None and not 100 <= status <= 599:
        status = None

    outcome = observation.outcome if observation.outcome in {"success", "failed"} else "failed"
    if status is None or not 200 <= status < 400:
        outcome = "failed"

    title = _optional_text(observation.page_title, _MAX_TEXT)
    final_url = sanitize_url(observation.final_url) if observation.final_url else None
    if final_url == "non-http resource":
        final_url = None

    error = _optional_text(observation.error_message, _MAX_ERROR)
    if outcome == "success":
        error = None
    elif error is None:
        error = PAGE_COULD_NOT_BE_OPENED if status is None else http_failure(status)

    console_errors = tuple(
        item
        for item in (_optional_text(value, _MAX_TEXT) for value in observation.console_errors)
        if item is not None
    )[:_MAX_CONSOLE_ERRORS]

    failed_requests: list[FailedRequestSummary] = []
    for item in observation.failed_requests[:_MAX_FAILED_REQUESTS]:
        url = sanitize_url(item.url)
        reason = _optional_text(item.error, 200) or "The request failed."
        failed_requests.append(FailedRequestSummary(url=url, error=reason))

    duration = observation.duration_ms
    if not isinstance(duration, int) or isinstance(duration, bool):
        duration = 0
    duration = min(_MAX_DURATION_MS, max(0, duration))

    return CheckObservation(
        outcome=outcome,
        http_status=status,
        page_title=title,
        final_url=final_url,
        duration_ms=duration,
        console_errors=console_errors,
        failed_requests=tuple(failed_requests),
        error_message=error,
    )


def sanitize_url(value: str | None) -> str:
    """Return an HTTP(S) URL without userinfo, query, or fragment."""
    if not value:
        return "non-http resource"
    try:
        parsed = urlsplit(redact(value.strip()))
    except ValueError:
        return "non-http resource"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "non-http resource"

    host = parsed.hostname.lower().rstrip(".")
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        return "non-http resource"
    if port is not None and not (
        (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    rebuilt = f"{parsed.scheme}://{host}{parsed.path}"
    if len(rebuilt) > _MAX_URL:
        return rebuilt[:_MAX_URL]
    return rebuilt


def redact(value: str) -> str:
    """Remove credential-shaped text. This is a filter, not a guarantee."""
    value = _USERINFO_URL.sub("[redacted-url]", value)
    value = _BEARER.sub("Bearer [redacted]", value)
    return _LABELED_SECRET.sub(lambda match: f"{match.group(1)}: [redacted]", value)


def _optional_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = redact(str(value)).replace("\x00", "").strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def unsafe_result(started: float) -> CheckObservation:
    """A failed observation used when a stored URL points somewhere we will not open."""
    return failed_observation(started, UNSAFE_TARGET)
