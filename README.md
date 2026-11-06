# Sentinel

Sentinel is an AI-powered website testing and monitoring platform. The product will open a site in a browser, record what failed, and use AI to explain the failure. Notifications and follow-up workflows will go through n8n.

This repository is Milestone 1: the development foundation. It does not yet run browser tests, call an AI service, or provide a product dashboard.

## Current status

Milestone 1 is implemented. The running system is a FastAPI process, a Next.js status page, and PostgreSQL in Docker Compose.

| Piece | What it does today |
| --- | --- |
| `GET /health` | Reports that the API process can answer HTTP. It does not touch the database. |
| `GET /health/ready` | Runs `SELECT 1`. Returns `200` when PostgreSQL answers and `503` when it does not. |
| Next.js page at `/` | The server calls those two routes and renders the result. The browser does not call the API. |
| Pytest | Locks the health contract. The one live database test skips when PostgreSQL is unreachable. A skip is not a passing check. |

## Architecture

The browser talks to Next.js. Next.js talks to FastAPI while it builds the page. FastAPI talks to PostgreSQL only from the readiness route. Docker runs the database. The API and the website run on the host so reload stays ordinary.

```mermaid
flowchart TB
  browser[Browser]
  web["Next.js on port 3000"]
  api["FastAPI on port 8000"]
  db["PostgreSQL 16 on port 5432"]

  browser -->|"GET /"| web
  web -->|"GET /health, then GET /health/ready"| api
  api -->|"SELECT 1 through asyncpg"| db
```

On this machine, PostgreSQL runs in Docker Engine inside Ubuntu on WSL 2. Windows reaches it at `localhost:5432` through `wslrelay`.

## Technology stack

In use now:

- Python and FastAPI for the API
- Async SQLAlchemy and asyncpg for PostgreSQL
- PostgreSQL 16, started by Docker Compose
- Next.js, React, and TypeScript for the status page
- Pytest for the API contract

Planned, and not implemented in this repository:

- Playwright for browser automation and website testing
- The OpenAI API for failure analysis
- n8n for notifications and workflow automation
- A product dashboard, saved monitors, and user accounts
- PHP and Laravel in a later milestone, where a second backend fits the architecture
- Container images for the API and the website, if a later milestone needs them

There is no Redis, task queue, or database migration tool yet. The first feature that stores data should add its table and a migration together.

## Local development

Prerequisites used for this milestone:

- Python 3.11 or newer on Windows. This checkout was tested with Python 3.14.
- Node.js 22 on Windows.
- Docker Engine with Compose v2, inside Ubuntu on WSL 2. `docker` is not a PowerShell command in this setup.

From the repository root in PowerShell, copy the example environment file before you change any local value:

```powershell
Copy-Item .env.example .env
```

`.env.example` contains local placeholders, including the database password `sentinel`. That password is for a database that listens only on your machine. `.env` is gitignored. The copy is optional while you still use those defaults.

Start PostgreSQL from Ubuntu, in this repository. A Windows path such as `C:\Users\<you>\Desktop\Sentinel` is `/mnt/c/Users/<you>/Desktop/Sentinel` in WSL. The Ubuntu user must be in the `docker` group.

```bash
docker compose up -d
```

Backend, from `backend`:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, from `frontend`:

```powershell
npm install
npm run dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). Interactive API docs are at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### Checks

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

From `frontend`:

```powershell
npm run typecheck
```

`npm run typecheck` checks types. It does not start the website or call the API.

### Configuration

| Variable | Consumer | Purpose |
| --- | --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Docker Compose | Database account and published host port |
| `DATABASE_URL` | API | SQLAlchemy URL. It must start with `postgresql+asyncpg://` and match the `POSTGRES_*` values |
| `ENVIRONMENT` | API | Returned by the health endpoints. Default `development` |
| `CORS_ORIGINS` | API | Comma-separated browser origins allowed to call the API |
| `NEXT_PUBLIC_API_URL` | Next.js | API address the status page calls. Set this in `frontend/.env.local`, not in the root `.env` |

Compose does not build `DATABASE_URL`. If the password in one place changes, change the other. Next.js does not read the root `.env`. When `NEXT_PUBLIC_API_URL` is absent, the page uses `http://localhost:8000`.

## Documentation

- [Architecture overview](docs/architecture/overview.md) covers the layout, request flow, and design decisions.
- [Development environment](docs/learning/development-environment.md) is the machine-level setup and troubleshooting order.
- [Milestone 1 technical walkthrough](docs/learning/milestone-1-technical-walkthrough.md) explains the code that is in the repository today.
