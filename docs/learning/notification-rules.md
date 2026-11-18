# Notification rules (AUTO-2)

Per-site toggles that decide which monitoring drafts n8n may deliver. Builds on [thresholds and recovery](thresholds-and-recovery.md) and [failure draft delivery](failure-draft-delivery.md).

## Rules (stored in Sentinel)

Each website has three booleans (default **true**):

| Field | Fires when |
| --- | --- |
| `notify_on_fail` | Consecutive failures ≥ `failure_threshold_count` |
| `notify_on_recover` | Previous check was bad, latest is good |
| `notify_on_latency` | Latest success exceeded `latency_threshold_ms` |

`GET /api/websites/{id}/monitoring-state` returns both the stored rules and evaluated intents:

- `should_notify_fail` / `should_notify_recover` / `should_notify_latency`

n8n IF nodes branch on those intents — no Redis, no paid email.

## Delivery (still AUTO-1)

Drafts POST to the free `webhookUrl` in the scheduled workflow **API address** Set node:

- [webhook.site](https://webhook.site)
- Slack Incoming Webhook (`text` field)
- Discord webhook (map `text` → `content` if needed)

Leave `webhookUrl` empty to keep drafts local.

## API / UI

- `PATCH /api/websites/{id}` with any of the three `notify_on_*` fields
- UI: **Notification rules** block inside **Monitoring configuration** on `/websites` and `/websites/[id]` (DASH-3; see [monitoring-config.md](monitoring-config.md))
- Websites page: **Notification rules** checkboxes

## n8n path

`scheduled-website-checks.json` after **Read monitoring state**:

1. **Notify on fail** → Failure draft  
2. else **Notify on latency** → Latency draft  
3. else **Notify on recover** → Recovery draft  
4. **Webhook configured** → **Deliver draft**

## What stays out

- Paid ESP / Gmail nodes
- Complex rule engines, quiet hours, flapping windows (beyond consecutive count)
- Paid ESP (use [free email path](free-email-path.md) / Mailpit or webhooks instead)
