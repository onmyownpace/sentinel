# Public shell deploy prep (Render + Neon, $0)

Portfolio-facing mode: UI + API + Neon + **simulated** AI. **No live Playwright** on free-tier hosts. Local Compose keeps full Chromium.

Assessment background: agent-store `docs/render-neon-compatibility.md` (**no-go** for public Chromium on Render Free).

## Local vs public

| | Local (default) | Public shell |
| --- | --- | --- |
| Config | root `.env` / `.env.example` | `deploy/public.env.example` → Render env |
| `PUBLIC_SHELL` | `false` | `true` |
| Playwright checks / journeys / scenarios / scheduled-checks | **on** | **503** + UI honesty |
| AI | `ANALYSIS_PROVIDER=simulated` (or openai if you set a key) | forced **simulated** |
| Registration | open | **closed** (demo login only) |
| Postgres | Compose, usually no TLS | **Neon + SSL** |
| n8n / Mailpit | Compose profiles | **local only** — not on Render Free |

## Feature flags

- `PUBLIC_SHELL=true` — disables live browser, closes registration, forces simulated AI, prefers DB SSL.
- `LIVE_BROWSER_ENABLED=false` — explicit kill switch (also implied by public shell).
- `ALLOW_REGISTRATION=false` — implied by public shell.
- `DATABASE_SSL=true` + `DATABASE_CONNECT_TIMEOUT_SECONDS=15` — Neon cold starts.
- `SESSION_COOKIE_SAMESITE=none` + `ENVIRONMENT=production` — cross-origin UI/API on HTTPS.

`GET /health` exposes `public_shell`, `live_browser_enabled`, `analysis_provider`, `registration_open` for the UI banner.

## Demo data

On public boot (after seed user), Sentinel inserts **`[Demo] Example status page`** with checks whose `error_message` starts with **Demo result — not a live browser check**. The UI banners that text so visitors do not confuse samples with live Chromium.

## n8n

Keep workflows on local Compose. Public Free cannot host durable n8n + timers reliably. Document schedules as local-only in the portfolio README when you publish.

## Remaining steps before a real deploy (accounts / DNS — not done in prep)

1. User approves DEPLOY-1 and the honest “no public Playwright” claim.
2. Create **Neon** Free project; copy URI; convert to `postgresql+asyncpg://…`; set as `DATABASE_URL` with `DATABASE_SSL=true`.
3. Create **Render** workspace; two Free Web Services (web + api) from existing Dockerfiles.
4. Paste API env from `deploy/public.env.example` (strong secrets; empty automation/schedule tokens).
5. Build web with `NEXT_PUBLIC_API_URL` from `frontend/.env.public.example`.
6. DNS: `sentinel.mindfold.fyi` → web, `api.sentinel.mindfold.fyi` → API; wait for TLS.
7. Smoke: `/health` shows `public_shell: true`; login demo user; open demo history; confirm Run check returns 503.
8. Do **not** mark DEPLOY-1 done until an external browser verifies the public URL.

## Security

- No open registration on public.
- No Chromium execution paths on public (manual, scheduled, journey, scenario).
- SSRF policy unchanged for when browser is re-enabled locally/full host.
- Never commit Neon/Render secrets; never enable `openai` on the public shell.
