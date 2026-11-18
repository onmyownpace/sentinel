# Scheduled website monitoring (n8n)

This note explains opt-in scheduled checks. Read it after [n8n follow-up](n8n-follow-up.md) and the check section of the [technical walkthrough](milestone-1-technical-walkthrough.md).

## The idea

A person enrolls a registered website for monitoring. n8n, on a schedule, asks Sentinel which sites are enrolled and runs one bounded Playwright check for each. Failed results feed the same notification **draft** shape as the manual follow-up, with optional webhook delivery when `webhookUrl` is set (see [failure draft delivery](failure-draft-delivery.md)). Nothing calls OpenAI automatically.

Sentinel remains the system of record (`websites`, `website_checks`). n8n is the timer and the caller. There is still no Redis and no in-process cron inside FastAPI.

## Opt-in enrollment

| Piece | Behavior |
| --- | --- |
| `websites.monitoring_enabled` | Boolean, default `false` |
| Registry UI | Checkbox **Include in scheduled monitoring** with copy that a schedule may open the URL |
| `PATCH /api/websites/{id}` | Body `{ "monitoring_enabled": true \| false }` |
| `GET /api/websites?monitoring=true` | Only enrolled sites (what n8n lists) |

No site is checked on a timer until enrollment is on **and** the n8n workflow is activated.

## Scheduled check API

`POST /api/websites/{id}/scheduled-checks`

- Requires header `X-Schedule-Check-Token` equal to `SCHEDULE_CHECK_TOKEN`.
- Requires `monitoring_enabled=true` on that website.
- Runs the same bounded public-URL check path as the manual route.
- Does **not** use the browser `authorized` checkbox body; that path stays for humans on `POST /api/websites/{id}/checks`.

The token is a machine acknowledgement for automation. It is not a Sentinel login and does not prove ownership of the site.

If `SCHEDULE_CHECK_TOKEN` is empty, the scheduled route returns `503`. A wrong or missing header returns `401`. A site that is not enrolled returns `422`.

## Workflow file

`n8n/workflows/scheduled-website-checks.json`

| Property | Value |
| --- | --- |
| Active on import | `false` |
| Trigger | Schedule every **6 hours** |
| List | `GET .../api/websites?monitoring=true` with `X-Automation-Token` |
| Check | `POST .../api/websites/{id}/scheduled-checks` with the schedule token header |
| On failure | **Notification draft**, then optional webhook delivery if `webhookUrl` is set |
| Send mail/chat | None baked in; generic JSON POST only when configured |

Edit the **API address** node: set `apiBase` (usually `http://host.docker.internal:8000`), `scheduleToken` to match `SCHEDULE_CHECK_TOKEN`, `automationToken` to match `AUTOMATION_TOKEN`, and optional `webhookUrl` for draft delivery. n8n still does not read container env vars inside nodes, so those values live in the workflow Set node on purpose.

## How to demo on this machine

1. Apply migrations (`alembic upgrade head`) so `monitoring_enabled` exists.
2. Set `SCHEDULE_CHECK_TOKEN=change-me-schedule-token` in the root `.env` (same placeholder as `.env.example` / the workflow) and restart the API on an address n8n can reach (`0.0.0.0:8000` from Ubuntu when using `host.docker.internal`).
3. Import the workflow (inactive):
   ```bash
   docker compose exec -u node n8n n8n import:workflow --input=/files/scheduled-website-checks.json
   ```
4. On `http://127.0.0.1:3000/websites` (or the site health page), open **Monitoring configuration** and enable **Include in scheduled monitoring**.
5. In n8n, open the workflow, confirm `scheduleToken`, then either **Activate** for the 6-hour tick or run once manually with **Execute workflow** after temporarily adding a Manual Trigger for a one-shot test (or wait for the schedule after activate).
6. Refresh check history on `/websites` — a new `website_checks` row should appear for the enrolled site.

Keep the workflow inactive when you are not deliberately monitoring. Prefer long intervals so Playwright requests do not overlap on one API process.

## What stays out

- Redis / Celery / APScheduler inside the API
- Built-in paid email; optional free Mailpit / webhook paths are documented separately
- Auto AI analysis on every failure
- Billing or multi-tenant isolation beyond simple `owner_id`
- Aggressive short intervals

Accounts and the dashboard are covered in [accounts and dashboard](accounts-and-dashboard.md).
