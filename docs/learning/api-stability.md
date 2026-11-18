# API stability expectations (ENG-2)

How Sentinel treats HTTP paths while the portfolio stays on a single FastAPI app.

## What is already there

| Surface | Role |
| --- | --- |
| Interactive docs | `GET /docs` (Swagger UI from FastAPI) |
| OpenAPI schema | `GET /openapi.json` |
| Route prefix | Application routes live under `/api/...` (plus `/health` and `/health/ready`) |

OpenAPI is generated from the code. Prefer reading `/docs` over duplicating every field in markdown.

## Stability rules

1. **No premature `/api/v1`.** Paths stay at `/api/...` until a **breaking** change cannot be shipped additively. Introducing `v1` “just in case” would churn clients (Next.js, n8n workflows, tests) for no gain.
2. **Additive first.** New fields on JSON responses, new optional query params, and new routes are preferred. Clients should ignore unknown fields.
3. **Breaking means…** renaming/removing a field or route clients rely on, changing auth header semantics, or tightening validation so previously valid bodies fail. Only then consider either a careful migration **or** a versioned prefix.
4. **If versioning is forced:** add `/api/v1/...` alongside the old paths, document the sunset window in this file and the roadmap, and update n8n Set-node URLs deliberately. Do not flip the default prefix overnight.
5. **Automation tokens** (`X-Automation-Token`, `X-Schedule-Check-Token`) and cookie sessions are part of the contract; do not rename headers casually.
6. **Errors:** prefer stable HTTP status codes and short `detail` strings. Do not put secrets, stack traces, or raw driver errors in responses or CI logs.

## What is explicitly unstable / local-only

- Absolute URL of the API on a developer machine (`localhost` vs `host.docker.internal`)
- Seed user email/password and disposable CI tokens
- Optional Mailpit / webhook destinations configured only in n8n

## Related

- Auth and dashboard: [accounts-and-dashboard.md](accounts-and-dashboard.md)
- CI that exercises the suite without calling paid APIs: [ci.md](ci.md)
