# Dashboard health UI (DASH-2) + config (DASH-3)

How the signed-in dashboard presents MON-1 stats, site drill-down, check detail, and monitoring configuration without a chart SaaS.

## Pages

| Route | Role |
| --- | --- |
| `/dashboard` | Health overview + site list + recent checks |
| `/websites` | Registry + per-site **Monitoring configuration** (DASH-3) |
| `/websites/[id]` | Per-site summary, config, uptime/latency chart, run/history |
| `/checks/[id]` | Full check observation, AI analysis (failures), screenshot stub |

## Health overview

`GET /api/dashboard?stats_window=24h|7d|all` applies that window to stats **and** `recent_checks` (MON-3; see [check-history-windows.md](check-history-windows.md)). It also includes `health`:

- website / monitored counts
- sites with checks / with failures
- average uptime across sites that have samples
- recent failure count in the newest-check strip

The UI window selector reloads that roll-up. Charts on the site page are local SVG + outcome bars from `/api/websites/{id}/stats` points.

## Monitoring configuration (DASH-3)

Enrollment, thresholds, and notification rules share one panel on the registry and the site health page. Copy stays honest: Sentinel stores preferences; n8n owns the timer. Details: [monitoring-config.md](monitoring-config.md).

## Check detail

`GET /api/checks/{id}` feeds `/checks/[id]`. Failed checks keep **Analyze failure** / saved analysis. When `has_screenshot` is true, the panel loads `GET /api/checks/{id}/screenshot` (see [check screenshots](check-screenshots.md)).

## What stays out

- Paid chart / APM embeds
- Implementing BROW-1 capture beyond the current stub/wiring
- Editing n8n cron / interval inside Sentinel
