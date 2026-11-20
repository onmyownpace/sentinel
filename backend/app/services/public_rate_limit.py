"""Tiny in-memory rate limiter for anonymous public probe endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_LOCK = threading.Lock()
_HITS: dict[str, deque[float]] = defaultdict(deque)

# Defaults sized for a free portfolio shell, not a production CDN.
DEFAULT_LIMIT = 10
DEFAULT_WINDOW_SECONDS = 60.0


class RateLimited(Exception):
    """Caller exceeded the public probe budget."""

    def __init__(self, retry_after_seconds: int = 60) -> None:
        super().__init__("rate limited")
        self.retry_after_seconds = retry_after_seconds


def check_rate_limit(
    key: str,
    *,
    limit: int = DEFAULT_LIMIT,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    now: float | None = None,
) -> None:
    """Raise RateLimited when `key` has more than `limit` hits in the window."""
    if limit < 1:
        raise RateLimited(1)
    stamp = time.monotonic() if now is None else now
    cutoff = stamp - window_seconds
    with _LOCK:
        bucket = _HITS[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            oldest = bucket[0]
            retry = max(1, int(window_seconds - (stamp - oldest)) + 1)
            raise RateLimited(retry)
        bucket.append(stamp)


def reset_rate_limits() -> None:
    """Test helper — clear all buckets."""
    with _LOCK:
        _HITS.clear()
