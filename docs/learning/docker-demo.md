# Docker demo path (ENG-4)

Run Postgres + n8n as usual, or opt into containerized API and web with Compose profile **`app`**. Named volumes stay intact across `docker compose down` — **do not** pass `-v` unless you mean to delete local data.

## Profiles

| Profile | Services |
| --- | --- |
| *(default)* | `postgres`, `n8n` — API/web still run on the host for hot reload |
| `app` | adds `api` + `web` images built from `backend/Dockerfile` and `frontend/Dockerfile` |
| `mail` | adds Mailpit (see [free-email-path.md](free-email-path.md)) |

## Host-dev path (unchanged)

```bash
docker compose up -d
# then uvicorn + npm run dev on the host — see development-environment.md
```

## Full container demo

From the repository root (WSL/Ubuntu if you are on Windows):

```bash
# Build and start Postgres, n8n, API, and web. Volumes are created if missing.
docker compose --profile app up -d --build
```

| URL | Service |
| --- | --- |
| http://localhost:3000 | Next.js UI |
| http://localhost:8000/docs | FastAPI OpenAPI |
| http://localhost:8000/health | API liveness |
| http://localhost:5678 | n8n editor |

Optional Mailpit as well:

```bash
docker compose --profile app --profile mail up -d --build
```

### Notes for the `app` profile

- API waits for Postgres healthy, runs `alembic upgrade head`, then Uvicorn.
- Browser-facing `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000` (host ports). Override at build via that env var in `.env`.
- From **n8n inside Compose**, set the workflow `apiBase` to `http://api:8000` (service DNS) instead of `http://host.docker.internal:8000`.
- Screenshots persist in volume `sentinel_api_screenshots`.
- Stop without wiping data: `docker compose --profile app down` (no `-v`).

## What this is not

- Production hardening / TLS / DEPLOY-1 hosting (still gated on approval)
- A Redis/Celery stack (ENG-3: not needed)
