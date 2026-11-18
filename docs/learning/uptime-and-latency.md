# Uptime and latency trends (MON-1)

How Sentinel summarizes stored checks into uptime and response-time numbers. Read after [accounts and dashboard](accounts-and-dashboard.md) and the check section of the [technical walkthrough](milestone-1-technical-walkthrough.md).

## The idea

Every Playwright check already stores `outcome` and `duration_ms`. MON-1 adds a **capped sample** aggregate so the dashboard and website page can show:

- uptime % (success / total in the sample)
- average duration
- approximate p95 duration
- a small series of recent points for a simple bar strip

This is not a metrics warehouse. Samples are limited so queries stay cheap on one Postgres instance.

## API

`GET /api/websites/{id}/stats`

| Query | Values | Default |
| --- | --- | --- |
| `window` | `24h`, `7d`, `all` | `7d` |
| `sample_limit` | 1–200 | `100` |

Requires a session cookie or `X-Automation-Token`. Returns 404 when the website is not visible to the caller.

`GET /api/dashboard?stats_window=7d` includes a `website_stats` array with the same aggregates (without the full point series) plus `stats_window`.

## UI

- **Dashboard** — each site row shows uptime, check count, avg, and p95 for the window.
- **Websites** — “Uptime & latency” panel with window selector and a CSS bar strip (no chart SaaS).

## Related

Raw check rows with the same window vocabulary (and stricter row caps): **MON-3** — see [check-history-windows.md](check-history-windows.md).

## What stays out

- Prometheus / Grafana / paid APM
- Unbounded history scans
- Alert thresholds (that is **MON-2**)
- Claiming public SLOs from this sample

## Demo

1. Sign in, register a site you may test, run a few checks.
2. Open `/websites` and switch the stats window.
3. Open `/dashboard` and confirm the same site shows uptime/latency.
