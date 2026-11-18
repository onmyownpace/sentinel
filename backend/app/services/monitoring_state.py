"""Per-site monitoring state: thresholds, still failing, recovered.

Derived from the newest stored checks plus optional website thresholds.
No Redis and no background workers — n8n (or the UI) reads this after a check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence
from uuid import UUID

from app.services.check_stats import CheckSample

MonitoringStatus = Literal["unknown", "healthy", "failing", "degraded", "recovered"]

_DEFAULT_FAILURE_THRESHOLD = 1
_MAX_HISTORY = 50


@dataclass(frozen=True)
class MonitoringState:
    website_id: UUID
    status: MonitoringStatus
    recovered: bool
    still_failing: bool
    latency_breached: bool
    latency_threshold_ms: int | None
    failure_threshold_count: int
    consecutive_failures: int
    latest_outcome: str | None
    latest_duration_ms: int | None
    latest_http_status: int | None
    latest_created_at: datetime | None
    previous_outcome: str | None


def effective_failure_threshold(configured: int | None) -> int:
    if configured is None:
        return _DEFAULT_FAILURE_THRESHOLD
    return configured


def check_is_bad(
    sample: CheckSample,
    *,
    latency_threshold_ms: int | None,
) -> bool:
    """A check is bad when it failed or exceeded the optional latency budget."""
    if sample.outcome == "failed":
        return True
    if latency_threshold_ms is not None and sample.duration_ms > latency_threshold_ms:
        return True
    return False


def consecutive_failure_count(rows: Sequence[CheckSample]) -> int:
    """Count newest-first failed outcomes until the first success."""
    count = 0
    for row in rows:
        if row.outcome != "failed":
            break
        count += 1
    return count


def evaluate_monitoring_state(
    website_id: UUID,
    rows: Sequence[CheckSample],
    *,
    latency_threshold_ms: int | None,
    failure_threshold_count: int | None,
) -> MonitoringState:
    """Compute branchable monitoring flags. `rows` must be newest-first."""
    history = list(rows[:_MAX_HISTORY])
    threshold = effective_failure_threshold(failure_threshold_count)
    latest = history[0] if history else None
    previous = history[1] if len(history) > 1 else None

    failures = consecutive_failure_count(history)
    latency_breached = bool(
        latest is not None
        and latest.outcome == "success"
        and latency_threshold_ms is not None
        and latest.duration_ms > latency_threshold_ms
    )
    # n8n branches on still_failing only after the consecutive threshold (or latency).
    still_failing = failures >= threshold or latency_breached

    previous_bad = (
        previous is not None
        and check_is_bad(previous, latency_threshold_ms=latency_threshold_ms)
    )
    latest_ok = latest is not None and not check_is_bad(
        latest, latency_threshold_ms=latency_threshold_ms
    )
    recovered = bool(previous_bad and latest_ok)

    if latest is None:
        status: MonitoringStatus = "unknown"
    elif recovered:
        status = "recovered"
    elif failures >= threshold:
        status = "failing"
    elif latency_breached:
        status = "degraded"
    elif latest.outcome == "failed":
        # Below consecutive threshold: visible as failing, not yet still_failing.
        status = "failing"
    else:
        status = "healthy"

    return MonitoringState(
        website_id=website_id,
        status=status,
        recovered=recovered,
        still_failing=still_failing,
        latency_breached=latency_breached,
        latency_threshold_ms=latency_threshold_ms,
        failure_threshold_count=threshold,
        consecutive_failures=failures,
        latest_outcome=None if latest is None else latest.outcome,
        latest_duration_ms=None if latest is None else latest.duration_ms,
        latest_http_status=None if latest is None else latest.http_status,
        latest_created_at=None if latest is None else latest.created_at,
        previous_outcome=None if previous is None else previous.outcome,
    )
