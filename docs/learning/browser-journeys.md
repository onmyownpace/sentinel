# Browser journeys (BROW-2)

Declarative mini-journeys for a registered site. Kept **separate** from one-shot `website_checks`. Portfolio-simple — not a Selenium IDE or full recorder.

## Idea

A journey is a short JSON step list attached to one website:

1. **navigate** (required first) — absolute `http(s)` URL or a path like `/login` joined to the site base URL  
2. Optional **fill** / **click**  
3. Asserts: **assert_text**, **assert_url_contains**, **assert_visible**

Max **8** steps. Runs are request-bound (`JOURNEY_BUDGET_SECONDS`, default 45). **ENG-3 decision: no background queue** — the budget still fits; retries are another POST from the UI or n8n, not Redis/Celery.

## SSRF

Every navigate target is checked with the same public-URL policy as one-shot checks. Playwright also uses the request guard so subresources to private hosts are blocked.

## Storage

| Table | Role |
| --- | --- |
| `website_journeys` | Name + steps JSON |
| `journey_runs` | Outcome, duration, per-step results |

Deleting a website cascades both. One-shot checks and screenshots are unchanged.

## API

- `POST/GET /api/websites/{id}/journeys`
- `GET/DELETE /api/journeys/{id}`
- `POST /api/journeys/{id}/runs` with `{ "authorized": true }`
- `GET /api/journeys/{id}/runs`, `GET /api/journey-runs/{id}`

## UI

**Journeys** panel on `/websites` and site health: paste steps JSON, save, run, see step results.

## Example

```json
[
  { "op": "navigate", "url": "/login" },
  { "op": "fill", "selector": "#email", "value": "dev@example.com" },
  { "op": "fill", "selector": "#password", "value": "secret" },
  { "op": "click", "selector": "button[type=submit]" },
  { "op": "assert_url_contains", "value": "/dashboard" }
]
```

## Related

Named reusable library entries that wrap a journey: **BROW-3** — see `docs/learning/browser-scenarios.md`.

## What stays out

- Waits, iframes, file uploads, multi-tab flows  
- Background queues for long journeys (ENG-3 assessed: not needed)
