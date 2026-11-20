# Public shell deploy (Render + Neon)

Portfolio-facing host: UI + API + Neon. **No live Playwright** on free-tier hosts. Local Compose keeps full Chromium.

**Signed-in workspace** may use Together (OpenAI-compatible) when `ANALYSIS_PROVIDER=openai` and a key are set on Render. **Seeded demo/portfolio checks** stay simulated and never call paid AI.

Assessment background: agent-store `docs/render-neon-compatibility.md` (**no-go** for public Chromium on Render Free).

## Local vs public

| | Local (default) | Public shell |
| --- | --- | --- |
| Config | root `.env` / `.env.example` | `deploy/public.env.example` → Render env |
| `PUBLIC_SHELL` | `false` | `true` |
| Playwright checks / journeys / scenarios / scheduled-checks | **on** | **503** + UI honesty |
| AI (signed-in workspace) | `ANALYSIS_PROVIDER=simulated` or `openai` | same — configured provider (Together OK) |
| AI (seeded `[Demo]` / demo-marker checks) | n/a | always **simulated** |
| Registration | open | **closed** (demo login only) |
| Postgres | Compose, usually no TLS | **Neon + SSL** |
| n8n / Mailpit | Compose profiles | **local only** — not on Render Free |
| Primary product surface | Dashboard | Dashboard (Status = footer Diagnostics) |

## Feature flags

- `PUBLIC_SHELL=true` — disables live browser, closes registration, prefers DB SSL. Does **not** force all analysis to simulated.
- `LIVE_BROWSER_ENABLED=false` — explicit kill switch (also implied by public shell).
- `ALLOW_REGISTRATION=false` — implied by public shell.
- `ANALYSIS_PROVIDER=openai` + `OPENAI_BASE_URL=https://api.together.ai/v1` + `OPENAI_API_KEY` or `TOGETHER_API_KEY` — Together for signed-in Analyze / patterns / drafts.
- `DATABASE_SSL=true` + `DATABASE_CONNECT_TIMEOUT_SECONDS=15` — Neon cold starts.
- `SESSION_COOKIE_SAMESITE=none` + `ENVIRONMENT=production` — cross-origin UI/API on HTTPS.

`GET /health` exposes `public_shell`, `live_browser_enabled`, `analysis_provider`, `analysis_model`, `analysis_base_host`, `registration_open`.

## Demo data

On public boot (after seed user), Sentinel inserts **`[Demo] Example status page`** with checks whose `error_message` starts with **Demo result — not a live browser check**. The UI labels those rows **Demo** so visitors do not confuse samples with live Chromium or their monitoring product. Analyzing those demo rows stays **simulated** even when Together is configured.

## Render env checklist (names only — no secret values)

Required for the public shell:

- `PUBLIC_SHELL`
- `LIVE_BROWSER_ENABLED`
- `ALLOW_REGISTRATION`
- `ENVIRONMENT`
- `DATABASE_URL`
- `DATABASE_SSL`
- `DATABASE_CONNECT_TIMEOUT_SECONDS`
- `CORS_ORIGINS`
- `SESSION_COOKIE_SAMESITE`
- `SESSION_TTL_DAYS`
- `SEED_USER_EMAIL`
- `SEED_USER_PASSWORD`

For hosted Together on signed-in workspace (after this fix is deployed):

- `ANALYSIS_PROVIDER`
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY` (or `TOGETHER_API_KEY` as fallback alias)
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_MAX_OUTPUT_TOKENS`

Web build:

- `NEXT_PUBLIC_API_URL`

## n8n

Keep workflows on local Compose. Public Free cannot host durable n8n + timers reliably.

## Remaining deploy steps for Together

1. Set the Render env names above (paste the Together key only in the dashboard).
2. Redeploy the API service so settings reload.
3. Sign in → open a **non-demo** failed check → Analyze. Health should show `analysis_provider: openai` and `analysis_base_host: api.together.ai`.
4. Confirm a `[Demo]` check Analyze still returns `provider: simulated`.
5. Confirm Run check still returns 503 on the public shell.

## Security

- No open registration on public.
- No Chromium execution paths on public (manual, scheduled, journey, scenario).
- Never commit Neon/Render/Together secrets.
- Demo/portfolio sample analysis never spends paid AI credits.
