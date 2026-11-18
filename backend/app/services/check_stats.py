"""Uptime and latency summaries from stored checks.

Learning-scale aggregates over a capped recent sample. This is not a time-series
warehouse: unbounded history scans are refused on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Literal, Sequence
from uuid import UUID

WindowName = Literal["24h", "7d", "all"]

_DEFAULT_SAMPLE = 100
_MAX_SAMPLE = 200
_DEFAULT_POINTS = 40
# Raw check-history list caps (MON-3). Stricter than stats sample_limit.
_DEFAULT_HISTORY_LIMIT = 20
_MAX_HISTORY_LIMIT = 50


@dataclass(frozen=True)
class CheckSample:
    created_at: datetime
    outcome: str
    duration_ms: int
    http_status: int | None


@dataclass(frozen=True)
class CheckStatsSummary:
    website_id: UUID
    window: WindowName
    sample_limit: int
    check_count: int
    success_count: int
    failure_count: int
    uptime_percent: float | None
    avg_duration_ms: float | None
    p95_duration_ms: int | None
    points: tuple[CheckSample, ...]


def parse_window(window: str) -> WindowName:
    cleaned = window.strip().lower()
    if cleaned not in ("24h", "7d", "all"):
        raise ValueError("window must be one of: 24h, 7d, all")
    return cleaned  # type: ignore[return-value]


def window_since(window: WindowName, *, now: datetime | None = None) -> datetime | None:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    if window == "24h":
        return current - timedelta(hours=24)
    if window == "7d":
        return current - timedelta(days=7)
    return None


def clamp_sample_limit(value: int | None) -> int:
    if value is None:
        return _DEFAULT_SAMPLE
    if value < 1 or value > _MAX_SAMPLE:
        raise ValueError(f"sample_limit must be between 1 and {_MAX_SAMPLE}")
    return value


def clamp_history_limit(value: int | None) -> int:
    """Cap raw check-history pages. Refuses unbounded scans."""
    if value is None:
        return _DEFAULT_HISTORY_LIMIT
    if value < 1 or value > _MAX_HISTORY_LIMIT:
        raise ValueError(f"limit must be between 1 and {_MAX_HISTORY_LIMIT}")
    return value


def default_history_limit() -> int:
    return _DEFAULT_HISTORY_LIMIT


def max_history_limit() -> int:
    return _MAX_HISTORY_LIMIT


def summarize_checks(
    website_id: UUID,
    rows: Sequence[CheckSample],
    *,
    window: WindowName,
    sample_limit: int,
    point_limit: int = _DEFAULT_POINTS,
) -> CheckStatsSummary:
    """Compute uptime and latency stats. `rows` should be newest-first."""
    check_count = len(rows)
    success_count = sum(1 for row in rows if row.outcome == "success")
    failure_count = check_count - success_count
    uptime = None if check_count == 0 else round(100.0 * success_count / check_count, 2)

    durations = [row.duration_ms for row in rows]
    avg = None if not durations else round(sum(durations) / len(durations), 2)
    p95 = None if not durations else _percentile_nearest(durations, 95)

    points = tuple(rows[: max(0, point_limit)])
    return CheckStatsSummary(
        website_id=website_id,
        window=window,
        sample_limit=sample_limit,
        check_count=check_count,
        success_count=success_count,
        failure_count=failure_count,
        uptime_percent=uptime,
        avg_duration_ms=avg,
        p95_duration_ms=p95,
        points=points,
    )


def _percentile_nearest(values: list[int], percentile: int) -> int:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(1, ceil(percentile / 100 * len(ordered)))
    return ordered[rank - 1]
