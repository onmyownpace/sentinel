# Monitoring configuration (DASH-3)

One UI surface for enrollment, thresholds, and notification rules. Sentinel stores preferences; **n8n owns the timer**.

## Where it lives

| Place | Role |
| --- | --- |
| `/websites` | Each registered site embeds **Monitoring configuration** |
| `/websites/[id]` | Same surface on the health drill-down, next to summary |

Component: `WebsiteMonitoringConfig` (enrollment + `WebsiteThresholds` + `WebsiteNotificationRules`).

## Blocks

1. **Enrollment** — `monitoring_enabled` via `PATCH /api/websites/{id}`. Off until you opt in; still no schedule until n8n `scheduled-website-checks` is active with `SCHEDULE_CHECK_TOKEN`.
2. **Thresholds & recovery** — optional `latency_threshold_ms` / `failure_threshold_count` (MON-2).
3. **Notification rules** — `notify_on_fail` / `notify_on_recover` / `notify_on_latency` (AUTO-2). Gates which drafts n8n may POST; defaults on.

Honest copy on the panel states that nothing runs on a timer from Sentinel alone.

## API

Same `PATCH /api/websites/{id}` body fields as before; the UI may save blocks separately or (API) all together. See [scheduled monitoring](scheduled-monitoring.md), [thresholds and recovery](thresholds-and-recovery.md), and [notification rules](notification-rules.md).

## What stays out

- Interval / cron editors in Sentinel (n8n workflow settings)
- Paid ESP (optional free Mailpit path: [free-email-path.md](free-email-path.md))
