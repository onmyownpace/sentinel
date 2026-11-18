# Thresholds and recovery (MON-2)

How Sentinel turns recent checks into `still_failing` / `recovered` flags for the UI and n8n. Read after [uptime and latency](uptime-and-latency.md) and [scheduled monitoring](scheduled-monitoring.md).

## The idea

Each website may set optional thresholds:

| Field | Meaning |
| --- | --- |
| `latency_threshold_ms` | Successful check slower than this is a latency breach (`degraded`) |
| `failure_threshold_count` | How many newest consecutive **failed** checks count as `still_failing` (default **1** when unset) |

After a check, `GET /api/websites/{id}/monitoring-state` reads the newest history (no Redis) and returns branchable booleans.

## Status values

| `status` | Meaning |
| --- | --- |
| `unknown` | No checks yet |
| `failing` | Latest failed (may be below consecutive threshold) |
| `degraded` | Latest succeeded but over latency threshold |
| `recovered` | Previous check was bad, latest is good |
| `healthy` | Latest is good and not a recovery edge |

n8n should prefer the AUTO-2 evaluated intents (signal AND rule):

- `should_notify_fail` — failure draft
- `should_notify_latency` — latency draft
- `should_notify_recover` — recovery draft

`still_failing` / `recovered` remain available for debugging. See [notification rules](notification-rules.md).

## API

- `PATCH /api/websites/{id}` — `{ "monitoring_enabled"?, "latency_threshold_ms"?, "failure_threshold_count"? }` (JSON `null` clears a threshold)
- `GET /api/websites/{id}/monitoring-state` — requires session or `X-Automation-Token`

## n8n

`scheduled-website-checks.json` after **Run scheduled check**:

1. **Read monitoring state**
2. **Still failing** → Notification draft → optional webhook
3. else **Recovered** → Recovery draft → optional webhook

## UI

On `/websites` and `/websites/[id]`, **Thresholds & recovery** sits inside **Monitoring configuration** (DASH-3) with enrollment and notification rules. Latency ms and consecutive failures edit there; the panel also shows the current monitoring state.

## What stays out

- Redis / Celery alert workers
- Flapping suppression windows beyond consecutive count
- Paid APM or on-call tools
