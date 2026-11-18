# Free email path (AUTO-3)

Optional local mail sink for failure / recover / latency drafts. No paid ESP (no SendGrid, SES, Mailgun, Postmark, etc.). Sentinel still does **not** send mail from FastAPI or Next.js — n8n does, when you wire it.

## Default vs optional

| Path | Cost | Role |
| --- | --- | --- |
| Empty `webhookUrl` | free | Drafts stay in the n8n execution only |
| Free webhook (webhook.site / Slack / Discord) | free | HTTP delivery — see [failure draft delivery](failure-draft-delivery.md) |
| **Mailpit** (this note) | free, local | Catch SMTP in a browser inbox for demos |

Mailpit is opt-in via Compose profile `mail`. Plain `docker compose up -d` does not start it.

## Start Mailpit

From the repo root (volumes untouched — do **not** pass `-v`):

```bash
docker compose --profile mail up -d
```

| Endpoint | Address |
| --- | --- |
| Inbox UI | http://localhost:8025 |
| SMTP (from host) | `localhost:1025` |
| SMTP (from n8n container) | host `mailpit`, port `1025` |

Optional `.env` overrides (documentation / compose ports only):

- `MAILPIT_UI_PORT` (default `8025`)
- `MAILPIT_SMTP_PORT` (default `1025`)

Auth is intentionally open for local use (`MP_SMTP_AUTH_ACCEPT_ANY`). Do not expose Mailpit SMTP to the public internet.

## Pattern A — n8n Email node → Mailpit (preferred)

Committed workflow JSON files stay **without** an Email node (webhook delivery remains the shared free default). Add SMTP only in your editor when you want mail:

1. Import / open `failed-check-follow-up` or `scheduled-website-checks` (or incident draft).
2. After **Notification draft** (or alongside **Deliver draft**), add an **Email Send** node.
3. SMTP settings:
   - Host: `mailpit`
   - Port: `1025`
   - SSL/TLS: off (Mailpit accepts plain SMTP on 1025)
   - User / password: any (accepted) or leave blank if the node allows
4. Message:
   - To: e.g. `dev@sentinel.local`
   - Subject: use the draft `text` or a short fixed subject
   - Body: the same `text` field (or stringify the draft JSON)
5. Connect it so it runs only when you intend to notify (same branch as fail / recover / latency intents on the scheduled workflow).
6. Execute once → open http://localhost:8025 and confirm the message landed.

Keep the Email node **out of git** unless the team later decides to ship a separate inactive sample workflow. The repo tests assert the stock JSON files do not bake in Gmail/SES/`emailsend`.

## Pattern B — webhook delivery only

If you do not want SMTP at all, leave Mailpit stopped and use `webhookUrl` with webhook.site / Slack / Discord. That path is already AUTO-1 / BASE-6 and does not need Mailpit.

Mailpit does **not** accept the existing HTTP `webhookUrl` POST as email. Bridging webhook→SMTP would require another free service or a custom listener — out of scope; use Pattern A.

## What this does not do

- Require a paid email provider
- Store SMTP credentials in Postgres
- Change Sentinel API routes
- Auto-start Mailpit on every `compose up`
- Replace notification rules (AUTO-2) — rules still gate *whether* a draft should notify

## Demo checklist

1. `docker compose --profile mail up -d`
2. Confirm http://localhost:8025 loads an empty inbox.
3. In n8n, add Email Send → `mailpit:1025` as above (or use webhook.site if you only need HTTP).
4. Produce a failed check / notify intent and execute the workflow.
5. Read the message in Mailpit.
6. When finished experimenting: `docker compose --profile mail stop` (no volume deletes).
