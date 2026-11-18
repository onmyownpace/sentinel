# Incident summary drafts (AI-3)

One-click or n8n-triggered **incident paragraph** from the newest failed checks for a site, plus any stored AI-1 analyses. Webhook-friendly JSON (AUTO-1-compatible `text` field). Simulated default — no paid AI required for demos.

## What it does

`POST /api/websites/{id}/incident-drafts?limit=5` loads up to N newest `outcome=failed` checks, attaches any `check_failure_analyses` rows, runs the configured provider once, and stores a draft.

**Development default:** `ANALYSIS_PROVIDER=simulated` — deterministic paragraph + Slack-style `text`. Zero AI network calls.

**Optional:** `ANALYSIS_PROVIDER=openai` with a key — same switch as AI-1 / AI-2. Not needed for demos or tests.

What it does **not** do:

- Auto-draft on every failure  
- Replace single-check analysis (AI-1) or pattern hints (AI-2)  
- Require paid email (optional free webhook delivery via n8n)

## Webhook-friendly JSON

Response fields useful for delivery (same idea as AUTO-1 failure drafts):

| Field | Role |
| --- | --- |
| `text` | One-line Slack/Discord-friendly summary |
| `paragraph` | Multi-sentence incident note |
| `website_name`, `base_url` | Site identity |
| `failed_check_count`, `check_ids`, `analysis_ids` | Provenance |
| `severity`, `provider`, `limitations` | Severity + honesty banner |

## API

- `POST /api/websites/{id}/incident-drafts?limit=5` — create or reuse when fingerprint matches  
- `POST …&refresh=true` — force a new provider run  
- `GET /api/websites/{id}/incident-drafts` — recent drafts  
- `GET /api/incident-drafts/{id}` — one draft  

Auth: browser session **or** `X-Automation-Token` (n8n).

## n8n

Inactive manual workflow: `n8n/workflows/incident-summary-draft.json`.

1. Import into n8n (same pattern as the follow-up workflow).  
2. Set `apiBase`, `automationToken`, optional `limit`, optional `webhookUrl`.  
3. Execute → **Request incident draft** → optional **Deliver draft** when `webhookUrl` is set.

Sites with no failed checks get a continued error from the HTTP node (`onError: continueRegularOutput`); other sites still draft.

## UI

**Incident summary draft** on `/websites` and site health: Draft / Show saved / Refresh.

## Related

- AI-1: [ai-failure-analysis.md](ai-failure-analysis.md)  
- AI-2: [historical-pattern-hints.md](historical-pattern-hints.md)  
- AUTO-1 delivery: [failure-draft-delivery.md](failure-draft-delivery.md)
