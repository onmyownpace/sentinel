# Check history windows (MON-3)

Documented, **capped** time windows for raw check history and the dashboard recent-check list. Builds on MON-1 stats windows. Unbounded scans are refused on purpose.

## Windows

| Value | Meaning |
| --- | --- |
| `24h` | `created_at` within the last 24 hours |
| `7d` | within the last 7 days |
| `all` | no time filter — still capped by `limit` |

Shared helpers live in `app/services/check_stats.py` (`parse_window`, `window_since`, `clamp_history_limit`).

## Caps

| Surface | Cap |
| --- | --- |
| `GET /api/websites/{id}/checks` | `limit` 1–**50** (default **20**) |
| Dashboard `recent_checks` | `recent_limit` 1–**50** (default **20**) |
| Stats sample (MON-1) | `sample_limit` 1–200 (separate, larger) |

There is no “fetch everything” mode. `limit=51` (or higher) returns `422`.

## API

### Site check history

`GET /api/websites/{id}/checks?window=7d&limit=20`

- Default `window=all` so n8n’s `?limit=1` still returns the absolute newest check  
- UI requests `window=7d` (or 24h) explicitly  
- Auth: session cookie or `X-Automation-Token`

### Dashboard

`GET /api/dashboard?stats_window=7d&recent_limit=20`

- `stats_window` applies to **both** per-site uptime/latency stats **and** `recent_checks`  
- Response includes `history_window` (same value) and `recent_check_limit`

## UI

- **Dashboard** — health overview window selector also filters Recent checks  
- **Websites / site health** — Check history panel has its own 24h / 7d / all selector  

## What stays out

- Cursor/offset pagination beyond the cap  
- Prometheus / long-term cold storage  
- Claiming SLOs from a capped sample  

## Related

- MON-1 aggregates: [uptime-and-latency.md](uptime-and-latency.md)  
- Dashboard health UI: [dashboard-health-ui.md](dashboard-health-ui.md)
