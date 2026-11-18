"""AUTO-2 notification intents from monitoring state + per-site rules.

n8n (or the UI) reads `should_notify_*` after a check. Delivery still goes through
the free webhook path from AUTO-1 — no paid email.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.monitoring_state import MonitoringState


@dataclass(frozen=True)
class NotificationRules:
    notify_on_fail: bool = True
    notify_on_recover: bool = True
    notify_on_latency: bool = True


@dataclass(frozen=True)
class NotificationIntents:
    """Which drafts n8n should emit for this site right now."""

    should_notify_fail: bool
    should_notify_recover: bool
    should_notify_latency: bool
    notify_on_fail: bool
    notify_on_recover: bool
    notify_on_latency: bool


def evaluate_notification_intents(
    state: MonitoringState,
    rules: NotificationRules,
) -> NotificationIntents:
    """Combine MON-2 signals with rule toggles.

    - on fail: consecutive failures reached the site threshold
    - on latency: latest success exceeded latency_threshold_ms
    - on recover: previous bad → latest good

    Fail and latency are mutually exclusive for a single latest check (latency
    breach requires outcome success). Recover is exclusive with still-failing.
    """
    failure_signal = state.consecutive_failures >= state.failure_threshold_count
    latency_signal = state.latency_breached
    recover_signal = state.recovered

    return NotificationIntents(
        should_notify_fail=bool(failure_signal and rules.notify_on_fail),
        should_notify_recover=bool(recover_signal and rules.notify_on_recover),
        should_notify_latency=bool(latency_signal and rules.notify_on_latency),
        notify_on_fail=rules.notify_on_fail,
        notify_on_recover=rules.notify_on_recover,
        notify_on_latency=rules.notify_on_latency,
    )
