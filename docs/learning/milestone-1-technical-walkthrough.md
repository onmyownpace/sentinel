# Technical walkthrough

This document explains the code that is in the repository today. Sections 1 through 11 are the foundation: a FastAPI process, a Next.js status page, and one PostgreSQL container. Section 12 is the website registry built on that foundation.

Read it next to the files it names. When a section says a function does something, that function is the place to confirm it.

What this checkout actually does:

- `GET /health` reports that the API process can answer HTTP.
- `GET /health/ready` runs `SELECT 1` and reports whether PostgreSQL answered.
- The page at `/` asks the Next.js server to call those two routes and render the result.
- `POST`, `GET`, and `DELETE` under `/api/websites` store one shared list of sites.
- The page at `/websites` calls those routes from the browser.
- Pytest checks both contracts. One test runs `SELECT 1` against the database in `DATABASE_URL`. The registry tests apply the Alembic revision and then delete the rows they insert.

There is no saved monitor, user account, browser runner, or call to an external AI service in this code. Websites are remembered. Nobody owns them yet. If you cannot find a feature in the files below, it is not implemented.

Setup commands for this machine live in [the development-environment guide](development-environment.md). This walkthrough explains why those commands work.

## 1. Monorepo structure

### The idea

A monorepo is one version-control checkout that holds more than one program. Sentinel has two programs that must agree about HTTP: the API and the website. They share a documentation directory and a Compose file, and they stay in separate folders so their tools do not get mixed together.

Python packages live under `backend/`. Node packages live under `frontend/`. A virtual environment and `node_modules` are created on your machine and are not source code. `.gitignore` keeps them, and `.env`, out of git.

### How this repository is split

```text
Sentinel/
├── docker-compose.yml          one service: PostgreSQL
├── .env.example                names and defaults for Compose and the API
├── README.md
├── docs/
│   ├── architecture/overview.md
│   └── learning/
├── backend/
│   ├── pyproject.toml          Python dependencies and pytest settings
│   ├── alembic.ini             migration configuration
│   ├── alembic/                revisions, including websites
│   ├── app/
│   │   ├── main.py             application factory
│   │   ├── api/routes/health.py
│   │   ├── api/routes/websites.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   └── urls.py
│   │   └── models/website.py
│   └── tests/
└── frontend/
    ├── package.json
    ├── next.config.ts
    ├── app/                    status page and /websites
    ├── components/             header, form, and list
    └── lib/
        ├── api.ts              server-side health calls
        └── websites.ts         browser calls for the registry
```

| Path | Role in the running system |
| --- | --- |
| `backend/app/main.py` | Builds the FastAPI object Uvicorn serves. |
| `backend/app/core/config.py` | Reads environment variables and the root `.env` file. |
| `backend/app/core/database.py` | Creates the SQLAlchemy engine and runs `SELECT 1`. |
| `backend/app/api/routes/health.py` | Liveness and readiness. |
| `backend/app/api/routes/websites.py` | The website registry routes. |
| `backend/app/models/website.py` | The ORM model and database constraints. |
| `backend/tests/` | Automated checks. They are not imported by the running API. |
| `frontend/app/page.tsx` | The status page. |
| `frontend/app/websites/page.tsx` | The registry page. |
| `frontend/lib/api.ts` | Fetches `/health` and `/health/ready` while the status page is rendering. |
| `frontend/lib/websites.ts` | Typed browser requests for the registry. |
| `docker-compose.yml` | Starts PostgreSQL. It does not start the API or the website. |

`pyproject.toml` lists the Python packages `setuptools` installs: `app`, `app.api`, `app.api.routes`, `app.core`, and `app.models`. Tests are outside that list. They run because pytest is pointed at `backend/tests`, not because they are part of the installed package.

The website imports its own code with the TypeScript path `@/*`, defined in `frontend/tsconfig.json` as `./*`. `import { getApiSnapshot } from "@/lib/api"` means `frontend/lib/api.ts`.

### Why the split looks like this

The API and the website have different runtimes. Python does not understand `package.json`. Node does not understand `pyproject.toml`. Putting each tool's files in its own directory means `pip install` and `npm install` each have one obvious place to work.

The Compose file stays at the root because it is infrastructure for the whole checkout, and because the root `.env` file is the file Compose reads automatically when you run it from that directory.

### A practical check

From the repository root:

```powershell
Get-ChildItem -Name
```

You should see `backend`, `frontend`, `docs`, and `docker-compose.yml` as siblings. If `app` or `package.json` is at the root, the checkout is not the layout this document describes.

### Mistakes

- Running `pip install` or `pytest` from the repository root. The Python project is `backend/`.
- Running `npm install` from `backend/`. The Node project is `frontend/`.
- Committing `.env`, `.venv`, or `node_modules`. They are local.

## 2. FastAPI application lifecycle

### The idea

An ASGI application is a Python object that a server calls for each HTTP request. FastAPI builds that object. Uvicorn is the server that listens on a port and calls it.

The object is not the same thing as a request. Creating it reads configuration and registers routes. Starting it opens resources that should live for the whole process, such as a database pool. Stopping it closes those resources. A single request should not create the pool, and it should not be the thing that forgets to close it.

### Where it is implemented

`backend/app/main.py` has three layers:

1. `configure_logging()` sets a log format if the process does not already have one.
2. `create_app()` builds one FastAPI instance.
3. The module-level name `app` is the object Uvicorn imports.

The start command from `backend` is:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`app.main:app` means "the variable `app` inside the module `app.main`". Importing that module runs `app = create_app()` at the bottom of the file. Configuration is read at import time. The database pool is not connected at import time.

### Startup and shutdown

`create_app()` defines a `lifespan` function and passes it to `FastAPI(...)`. The function is an async context manager:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_db_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    logger.info("Starting %s %s (%s)", settings.app_name, settings.app_version, settings.environment)
    yield
    await engine.dispose()
```

Code before `yield` is startup. Code after `yield` is shutdown. `app.state` is a bag of objects FastAPI keeps on the application. Routes later read `request.app.state.engine`. Nothing in `main.py` opens a TCP connection to PostgreSQL. `create_async_engine` builds a pool. The first checkout of a connection happens on the first query.

Uvicorn runs startup when it begins serving, and shutdown when you stop the process. `--reload` starts a watcher. When a Python file changes, that watcher stops the server process and starts another one, which runs lifespan again. A change to `.env` is picked up only because the process restarts and `get_settings()` runs again. The settings object itself is cached.

Tests do not use the module-level `app`. `backend/tests/conftest.py` calls `create_app()` and wraps it in `TestClient`. Entering `with TestClient(app)` runs the same lifespan. Leaving the `with` block runs shutdown, including `engine.dispose()`.

### CORS

CORS is a browser rule. A page served by `http://127.0.0.1:3000` is a different origin from an API at `http://127.0.0.1:8000`. If JavaScript in that page calls the API, the browser asks whether the API allows that origin. The API answers with headers such as `Access-Control-Allow-Origin`.

`create_app()` adds `CORSMiddleware`:

- `allow_origins` comes from `settings.cors_origin_list`. The default is `http://localhost:3000`.
- `allow_credentials` is `True`. That is safe here because the origin list is explicit. An allow-list of `*` combined with credentials would be invalid and unsafe.
- Methods include `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, and `OPTIONS`.
- Request headers are allowed with `*`.

`test_frontend_origin_is_allowed` sends `Origin: http://localhost:3000` and expects the response header `access-control-allow-origin` to echo that origin.

The current status page does not trigger this browser check. The Next.js server calls the API, and a server-to-server call has no CORS. The middleware is still part of the app, and the test locks the header, because the configuration is real.

### Request flow inside the process

```mermaid
sequenceDiagram
  participant Uvicorn
  participant App as FastAPI app
  participant Life as lifespan
  participant Route as route function

  Uvicorn->>App: import app.main:app
  Note over App: create_app reads settings and registers routes
  Uvicorn->>Life: startup
  Life->>App: store engine and session factory on app.state
  Uvicorn->>Route: one HTTP request
  Route-->>Uvicorn: response
  Uvicorn->>Life: shutdown
  Life->>Life: engine.dispose
```

### A practical example

Start the API, then open `http://127.0.0.1:8000/docs`. FastAPI builds that page from the route declarations. You do not write the HTML. The title on that page is `settings.app_name`, which defaults to `Sentinel`, and the version is `settings.app_version`, which is `0.1.0`.

The log line from startup looks like:

```text
INFO app.main Starting Sentinel 0.1.0 (development)
```

### Mistakes

- Editing `.env` and expecting the next request to see it. Restart Uvicorn. With `--reload`, saving a Python file also restarts it. Saving `.env` might not, because the watcher is watching Python files.
- Importing `app` from `app.main` in a test and then changing an environment variable. `create_app()` already called `get_settings()`, and the result is cached. Tests that change the environment call `get_settings.cache_clear()` first.
- Assuming CORS explains a failure of the status page. If the page says the API could not be read, the Next.js server failed its `fetch`. Look at whether Uvicorn is running before you look at CORS headers.

## 3. Configuration management

### The idea

Configuration is the set of values that change between machines without a code change: a database address, a password, an allowed browser origin. Those values belong in the environment or in a file that is not committed. The program reads them once at startup into a typed object so routes do not call `os.environ` themselves.

### How Sentinel reads them

`backend/app/core/config.py` defines `Settings` with `pydantic-settings`. Each field has a default. An environment variable with the same name in uppercase replaces the default: `database_url` reads `DATABASE_URL`, `environment` reads `ENVIRONMENT`, `cors_origins` reads `CORS_ORIGINS`.

The file path is computed from the source file:

```python
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"
```

`config.py` lives at `backend/app/core/config.py`. Counting parents: `core`, then `app`, then `backend`, then the repository root. The path does not depend on the directory from which you launched Uvicorn.

`get_settings()` is wrapped in `@lru_cache`. The first call constructs `Settings`. Later calls return that same object. Process environment variables override the env file. The env file overrides the defaults written on the class. Unknown names are ignored because `extra="ignore"`. That is why `POSTGRES_PASSWORD` can sit in the same `.env` file as `DATABASE_URL`. Compose reads the first name. The API reads the second. Neither crashes on the other's variables.

`.env.example` documents the names. A local `.env` is the same content copied into place. Git ignores `.env`.

### Values that must agree

Compose does not build `DATABASE_URL`. You keep two descriptions of one database in sync:

| Compose variable | Matching part of `DATABASE_URL` |
| --- | --- |
| `POSTGRES_USER` | user |
| `POSTGRES_PASSWORD` | password |
| `POSTGRES_DB` | database name |
| `POSTGRES_PORT` | host port, the number before the slash |

The default URL is:

```text
postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel
```

`database_url_must_use_asyncpg` rejects a value that does not start with `postgresql+asyncpg://`. `test_database_url_rejects_a_sync_driver` sets `DATABASE_URL` to a `postgresql://` URL and expects `ValidationError`.

`cors_origin_list` splits `CORS_ORIGINS` on commas and drops empty pieces. One origin is configured today.

The website does not read the root `.env`. Next.js reads environment files inside `frontend/`. `frontend/lib/api.ts` uses `process.env.NEXT_PUBLIC_API_URL` when it is non-empty, and otherwise `http://localhost:8000`. The `NEXT_PUBLIC_` prefix is Next.js's rule for a variable that may be visible to browser code. This milestone reads it on the server.

### A practical example

From `backend`, with the virtual environment:

```powershell
.\.venv\Scripts\python.exe -c "from app.core.config import get_settings; s = get_settings(); print(s.environment); print(s.database_url.split('@')[-1])"
```

Print the host and database, not the whole URL. The whole URL contains the password.

A wrong driver prefix fails when settings are constructed, which is when `create_app()` runs. The error text from the validator is: `DATABASE_URL must start with postgresql+asyncpg://`.

### Mistakes

- Changing `POSTGRES_PASSWORD` and forgetting to change the password inside `DATABASE_URL`. The container and the API then disagree. Readiness returns `503`. The log records the exception class, not the message, so it will not show the password back to you.
- Putting `NEXT_PUBLIC_API_URL` only in the root `.env`. Next.js will not see it.
- Calling `get_settings()` in a test, then changing the environment, then calling it again. Clear the cache between those steps, and clear it again in a `finally` so the next test sees a fresh read.

## 4. Async SQLAlchemy and PostgreSQL

### The idea

PostgreSQL speaks its own protocol over TCP. A Python driver translates that protocol into function calls. SQLAlchemy sits above the driver and gives the application a connection pool, a way to run SQL text, and, later, a session for transactions.

"Async" here means the FastAPI process can wait for the database without blocking the whole interpreter on that wait. The function that waits is declared with `async def` and uses `await`. SQLAlchemy's async API needs the `sqlalchemy[asyncio]` extra. That extra installs `greenlet`. Application code does not call greenlet. The library uses it to adapt its internals.

The URL scheme selects the driver. `postgresql+asyncpg://` tells SQLAlchemy to use asyncpg. A URL that starts with `postgresql://` would select a synchronous driver, which cannot be used as this engine. The settings validator stops that earlier.

### What the module does, and what it does not do

`backend/app/core/database.py` exports three functions:

| Function | What it does |
| --- | --- |
| `create_db_engine` | Builds an `AsyncEngine` from `settings.database_url`. |
| `create_session_factory` | Builds an `async_sessionmaker` bound to that engine. |
| `database_is_reachable` | Opens one connection, runs `SELECT 1`, and returns `True` or `False`. |

Importing the module does not connect. The pool connects on first use.

`create_db_engine` passes two extra arguments:

- `pool_pre_ping=True`. Before SQLAlchemy hands out a pooled connection, it checks that the connection is still alive. That matters when the container restarts while the API process keeps running.
- `connect_args={"timeout": 2}`. asyncpg treats `timeout` as the connection timeout, in seconds. A database that does not answer fails the readiness request in about two seconds.

`create_session_factory` sets `expire_on_commit=False`. After a commit, SQLAlchemy would otherwise expire loaded attributes and try to refresh them on the next read. That refresh is a lazy load, and async code cannot do an implicit lazy load. Website routes open a session from `app.state.session_factory`, commit, and call `session.refresh()` when they need `created_at` and `updated_at`. Health routes do not open a session. `test_startup_creates_engine_and_session_factory` asserts both objects exist. It still does not run SQL.

`database_is_reachable` uses `sqlalchemy.text("SELECT 1")`. Any exception becomes `False`. The `except` block logs the exception class name only:

```python
logger.warning("Database readiness check failed (%s)", exc.__class__.__name__)
```

asyncpg can include the database URL in an error string. The URL contains the password. The class name (`TimeoutError`, `InvalidPasswordError`, and so on, once SQLAlchemy wraps it) is the clue that is safe to log.

`SELECT 1` does not need a table. The `websites` table is created by Alembic, not by this readiness check. See section 12.

### Data flow for one connectivity check

```mermaid
sequenceDiagram
  participant Route as readiness
  participant Check as database_is_reachable
  participant Pool as AsyncEngine pool
  participant Driver as asyncpg
  participant DB as PostgreSQL

  Route->>Check: await database_is_reachable(engine)
  Check->>Pool: connect
  Pool->>Driver: connect with a 2 second timeout
  Driver->>DB: startup packet
  alt connection and query succeed
    Check->>DB: SELECT 1
    DB-->>Check: 1
    Check-->>Route: True
  else any exception
    Check-->>Route: False
    Note over Check: log the exception class only
  end
```

### A practical example

With the container running, from `backend`:

```powershell
.\.venv\Scripts\python.exe -c "import asyncio; from sqlalchemy import text; from app.core.config import get_settings; from app.core.database import create_db_engine
async def main():
    engine = create_db_engine(get_settings())
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text('SELECT 1'))
            print(result.scalar_one())
    finally:
        await engine.dispose()
asyncio.run(main())"
```

A successful run prints `1`. If it raises, read the exception class first. Then check that port `5432` is published and that the user, password, and database name in the URL match the container.

### Mistakes

- Treating the session factory as proof that a particular route saved a row. Health does not use it. The website routes do.
- Raising the driver's exception from `database_is_reachable`. The health route would then turn a down database into an unhandled `500`, and the response might contain the URL.
- Setting the page's fetch timeout to the same two seconds. The driver may use the whole two seconds and a little more before it returns `503`. The page waits eight seconds so it can still read that response. Those two numbers live in `database.py` (`_CONNECT_TIMEOUT_SECONDS`) and `frontend/lib/api.ts` (`REQUEST_TIMEOUT_MS`).

## 5. Docker Engine, images, containers, volumes, and Compose

### The idea

A container is a running process with its own filesystem view, started from an image. An image is a packed snapshot of files, such as the PostgreSQL binaries and their default configuration. The image does not contain your data. Data that must survive a new container goes in a volume, which is storage Docker keeps outside the container's writable layer.

Docker Engine is the program that pulls images, creates containers, and mounts volumes. On this machine the engine runs inside Ubuntu on WSL 2. It is not a Windows service. You talk to it with the `docker` command in Ubuntu.

Docker Compose reads `docker-compose.yml` and asks the engine to create the services in that file. This file declares one service.

### What the file declares

`docker-compose.yml` sets the project name to `sentinel`. The service is named `postgres`. Compose's default container name joins those, which is why the running container is `sentinel-postgres-1`. The file does not set `container_name` itself.

| Compose field | Value in this file | Effect |
| --- | --- | --- |
| `image` | `postgres:16-alpine` | Run PostgreSQL 16 from the Alpine-based official image. The major version is pinned. `latest` is not used. |
| `restart` | `unless-stopped` | The engine starts the container again after a daemon restart, unless you stopped it yourself. |
| `environment` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | The image's entrypoint creates that user and database on the first initialization of an empty data directory. |
| `ports` | `"${POSTGRES_PORT:-5432}:5432"` | Publish container port `5432` on the host port, default `5432`. |
| `volumes` | `sentinel_postgres_data` mounted at `/var/lib/postgresql/data` | Keep the database files outside the container. |
| `healthcheck` | `pg_isready` | The engine marks the container healthy only after PostgreSQL accepts connections. |

`${POSTGRES_USER:-sentinel}` means "use the variable if it is set, otherwise `sentinel`". Compose reads a `.env` file in the directory where you run the command, which is the repository root when you follow the guide. Those substitutions happen on the Ubuntu side, before the container starts.

The healthcheck contains `$$POSTGRES_USER`. Compose treats `$` as its own substitution. `$$` becomes a single `$` in the command that runs inside the container. The shell in the container then expands `POSTGRES_USER`, which the image put into the container environment. Writing `$POSTGRES_USER` in that test would let Compose replace it on the host, often with an empty string.

The volume key in the file is `sentinel_postgres_data`. Compose also prefixes the project name, so the Docker volume object is `sentinel_sentinel_postgres_data`. Deleting the container does not delete that volume. `docker compose down -v` does.

The image's initialization of the user and database happens when the data directory is empty. If you change `POSTGRES_PASSWORD` after the volume already exists, the existing database keeps the old password. The environment variables do not rewrite a password that was set on first boot.

### How the processes communicate

```mermaid
flowchart TB
  subgraph windows [Windows]
    powershell[PowerShell]
    uvicorn[Uvicorn in backend/.venv]
    next[Next.js]
    relay[wslrelay on localhost:5432]
  end

  subgraph wsl [Ubuntu on WSL 2]
    engine[Docker Engine]
    container["container sentinel-postgres-1"]
    volume["volume sentinel_sentinel_postgres_data"]
  end

  powershell -->|starts| uvicorn
  powershell -->|starts| next
  next -->|HTTP localhost:8000| uvicorn
  uvicorn -->|TCP localhost:5432| relay
  relay --> container
  engine --> container
  container --> volume
```

Windows programs use `localhost:5432`. `wslrelay.exe` forwards that port into WSL, where the container published `5432`. You can see the forward with `netstat` in PowerShell. The listening process name is `wslrelay`.

### A practical example

From a new Ubuntu terminal:

```bash
cd /mnt/c/Users/<you>/Desktop/Sentinel
docker compose ps
```

A healthy milestone database looks like `sentinel-postgres-1` with a status containing `healthy` and a port mapping `0.0.0.0:5432->5432/tcp`.

From PowerShell, the matching check is a TCP listener on `5432`, then a query through the virtual environment, as in section 4. `docker compose` in PowerShell fails because `docker` is not a Windows command in this setup.

### Mistakes

- Running Compose from PowerShell and concluding Docker is missing. Run it in Ubuntu.
- Using an Ubuntu shell that was opened before your user was added to the `docker` group. The socket `/var/run/docker.sock` is group-readable by `docker`. A new login picks up the group. `wsl --shutdown` would also start a new session, and it stops the container. Prefer a new terminal.
- Changing the password in `.env` and expecting an existing volume to notice. Either keep the password that initialized the volume, or remove the volume knowingly and initialize again.
- Expecting Compose to start Uvicorn or Next.js. The file's only service is `postgres`.

## 6. `/health` and `/health/ready`

### The idea

Two questions get confused if one URL tries to answer both.

Liveness asks: is this process able to respond at all? A supervisor that restarts a process on a failed liveness check should not restart it merely because a different machine, the database, is down. Restarting would not fix the database, and it can cause a restart loop.

Readiness asks: can this process do the work it exists to do right now? For this API, that work depends on PostgreSQL. A failed readiness check means "do not send this process work that needs the database." It does not mean "kill the process."

This milestone has no supervisor. The routes still give different answers so the distinction is visible and tested.

### How the routes differ

Both functions are in `backend/app/api/routes/health.py`. The router has no path prefix. The paths are `/health` and `/health/ready`.

`health()` builds a `HealthResponse` and returns it. FastAPI serializes that model with status `200`. The function does not receive `Request` and does not touch `app.state`. The body is:

```json
{
  "status": "ok",
  "service": "sentinel-api",
  "version": "0.1.0",
  "environment": "development"
}
```

`service` is the constant `_SERVICE_NAME`. `version` and `environment` come from `get_settings()` through `_identity()`.

`readiness()` reads `request.app.state.engine`. If the attribute is missing, `getattr` yields `None` and the check is treated as failed. If the engine exists, it awaits `database_is_reachable`. The response model is `ReadinessResponse`, which adds `checks`. The function returns a `JSONResponse` so it can choose the status code:

| Database | HTTP status | `status` | `checks.database` |
| --- | --- | --- | --- |
| Answered `SELECT 1` | `200` | `ok` | `ok` |
| Did not answer, or no engine | `503` | `degraded` | `unavailable` |

The body stays JSON in both cases. The OpenAPI declaration includes `503` with the same model, so `/docs` shows both outcomes.

A successful readiness body adds one field to the liveness shape:

```json
{
  "status": "ok",
  "service": "sentinel-api",
  "version": "0.1.0",
  "environment": "development",
  "checks": { "database": "ok" }
}
```

### A practical example

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

PowerShell throws when the status is `503`. That throw means the readiness check failed. Read the response body. It still says whether the database was `unavailable`. A connection error from `Invoke-RestMethod`, before any HTTP status, means Uvicorn is not accepting connections.

Stop the container from Ubuntu and call `/health` again. It stays `200`. Call `/health/ready` again. It becomes `503`, and the API log contains `Database readiness check failed` plus an exception class. Start the container again. The next readiness call can succeed without restarting Uvicorn, because the pool connects on use and `pool_pre_ping` checks the connection it reuses.

### Mistakes

- Using `/health` as proof that PostgreSQL is up. It never queries the database.
- Treating `503` as a bug in the route. For a stopped database, `503` with `degraded` is the specified result. `test_readiness_is_degraded_when_the_database_check_fails` locks that mapping.
- Expecting the response body to explain the driver error. It will not contain the URL or the password. `test_readiness_fails_closed_when_postgres_refuses_the_connection` points the engine at `127.0.0.1:1` with the password `secret-password` and asserts that neither that password nor the string `postgresql+asyncpg` appears in the response text.

## 7. How an HTTP request travels from the browser to FastAPI

### The idea

The browser asks for a document from the site it was pointed at. In this milestone that site is Next.js on port `3000`. The HTML document is already filled in when the browser receives it. The browser does not then call port `8000`.

The Next.js server is the HTTP client of the API. FastAPI is the HTTP server. They are different processes. They talk over TCP on the machine, using `localhost`.

### The path for one refresh

`frontend/app/page.tsx` is an async server component. When a request for `/` arrives, Next.js calls `HomePage`. That function immediately calls `getApiSnapshot()` in `frontend/lib/api.ts`.

`getApiSnapshot` resolves the API address, then calls `readJson("/health")` and, only if that call returns, `readJson("/health/ready")`. `readJson` uses `fetch` with `cache: "no-store"` and `AbortSignal.timeout(8000)`. `no-store` tells Next.js not to reuse an old health document. The abort limit is eight seconds per call.

`fetch` to `http://localhost:8000/health` arrives at Uvicorn. Uvicorn calls the FastAPI app. Routing matches `/health` to `health()`. The function returns a model. FastAPI writes JSON and status `200`. The same happens for `/health/ready`, except that route may take about two seconds when the database is down, and it may return `503`.

`readJson` does not treat `503` as a thrown error. `fetch` resolves for any HTTP status. The function reads `response.status` and `response.json()`. A `503` with a valid readiness body still counts as "the API was reached."

If `fetch` throws, because nothing is listening or the abort fires, `getApiSnapshot` returns `reached: false` and `describe(error)`. `HomePage` then renders the paragraph that starts "The API could not be read."

If both bodies have the expected fields, `HomePage` renders the definition list. Next.js sends that HTML to the browser.

```mermaid
sequenceDiagram
  participant Browser
  participant Next as Next.js server :3000
  participant API as Uvicorn and FastAPI :8000
  participant DB as PostgreSQL :5432

  Browser->>Next: GET /
  Next->>API: GET /health
  API-->>Next: 200 JSON, no database call
  Next->>API: GET /health/ready
  API->>DB: SELECT 1
  alt database answers
    DB-->>API: 1
    API-->>Next: 200 database ok
  else database does not answer
    API-->>Next: 503 database unavailable
  end
  Next-->>Browser: HTML status page
```

### A practical example

Load `http://127.0.0.1:3000` with the API stopped. The page still returns HTTP `200` from Next.js. The text says the API could not be read, and it prints the address it tried, by default `http://localhost:8000`.

Start the API and refresh. The definition list appears. "API process" comes from the liveness JSON and the liveness HTTP status. "Database" comes from `checks.database` and the readiness HTTP status. A `503` from readiness is shown as `unavailable (503)`, not as a failed page load.

Watch the Uvicorn log while you refresh. You should see `GET /health` and then `GET /health/ready`. You should not see the browser listed as a separate client of those routes beyond the Next.js server. The client address in the log is the machine running Next.js, which is this same computer.

### Mistakes

- Looking in the browser's network panel for `localhost:8000` and treating its absence as a bug. The panel shows the request the browser made, which is `GET /` to port `3000`.
- Adding browser JavaScript to call the API and forgetting CORS. The current page does not do that. A later change that does would need the origin in `CORS_ORIGINS` to match the origin the browser actually uses, including `localhost` versus `127.0.0.1`. Those are different origins.
- Letting the page abort at two seconds. The symptom is "The API could not be read" and a timeout message, while `/health` alone still returns `200`. The readiness call is the slow one when PostgreSQL is down.

## 8. How the frontend checks API and database health

### The idea

The page is a view of two HTTP responses. It does not open a database connection, and it does not decide that the database is up by catching an exception inside Next.js. It shows the fields the API returned, after checking that those fields exist.

### The snapshot

`getApiSnapshot()` returns an `ApiSnapshot`:

| Field | Meaning when `reached` is true | Meaning when `reached` is false |
| --- | --- | --- |
| `apiUrl` | The base URL that was called. | The base URL it tried to call. |
| `reached` | Both responses were JSON of the expected shape. | The call threw, or the JSON shape was wrong. |
| `error` | `null` | A short description. |
| `livenessStatus`, `liveness` | Status code and body of `/health`. | `null` |
| `readinessStatus`, `readiness` | Status code and body of `/health/ready`. | `null` |

`resolveApiUrl()` trims `NEXT_PUBLIC_API_URL` and removes one trailing slash so the path join does not become `http://localhost:8000//health`.

`isHealthBody` and `isReadinessBody` are type predicates. They look at a value that TypeScript only knows as `unknown`. They check `status`, `service`, `version`, `environment`, and, for readiness, `checks.database`. `isReadinessBody` reads `checks` from the raw object before `isHealthBody` narrows the type. That order is deliberate: after the predicate narrows the value to `HealthBody`, TypeScript no longer allows a `checks` property on it.

A body that fails those checks produces the error string "The API responded, but the health payload was not in the expected shape." The page does not throw on that case.

`describe` prefers `error.cause.message` when the cause is an `Error`. A refused connection often shows up as a message plus a cause, which is more useful than `fetch failed` alone.

### What the page does with the snapshot

`HomePage` in `frontend/app/page.tsx` branches:

- `reached` is true and both bodies exist: render the definition list. `tone()` returns the CSS class `ok` when the text is `ok`, an empty string for null, and `bad` for every other string. `unavailable` is therefore `bad`.
- Otherwise: one paragraph, class `bad`, containing "The API could not be read." and `snapshot.error`.
- When the API was reached: a link whose address is `` `${snapshot.apiUrl}/docs` ``. The link text is "Open the API documentation".
- When the API was reached and `checks.database` is not `ok`: a hint that tells you to start Docker Compose and refresh. That sentence is the literal copy in `page.tsx`. On this machine the Compose command runs in Ubuntu. The development-environment guide has the command that matches the machine.
- When the API was not reached: a hint that tells you to start the API and names `snapshot.apiUrl`.

The page does not poll. A refresh is a new request, which calls `getApiSnapshot()` again. `export const dynamic = "force-dynamic"` tells Next.js to render the page for each request rather than freeze the HTML at build time. A build does not need the API to be up, and a running server does not keep serving the first health result it ever saw.

### A practical example

With both processes and the database up, the list reads:

```text
API process    ok (200)
Database       ok (200)
Service        sentinel-api
Version        0.1.0
Environment    development
API address    http://localhost:8000
```

Stop PostgreSQL only. Refresh. The API line stays `ok (200)`. The database line becomes `unavailable (503)`. The Compose hint appears. The docs link remains, because the API was reached.

### Mistakes

- Casting JSON with `as HealthBody` and skipping the checks. A missing field would then throw while rendering. The predicates exist so the page can show a sentence instead.
- Reading `response.ok` and throwing on `503`. That would hide a valid readiness body and make a down database look like a dead API.
- Caching the fetch. Health is a current observation. `cache: "no-store"` is there so a later request cannot reuse an earlier `ok`.

## 9. Next.js architecture and the status page

### The idea

Next.js, in this repository, is a React framework with the App Router. A folder named `app` contains routes. `app/page.tsx` is the route `/`. `app/websites/page.tsx` is the route `/websites`. `app/layout.tsx` is the document wrapped around every page, including the header.

A server component runs in the Node.js process while the response is being built. It can `await` a function. The result is HTML. The status page has no `"use client"` directive. There is no component state, no `useEffect`, and no click handler on that page. The registry page is different: its form and list are client components, described in section 12.

### The files

| File | What it contributes |
| --- | --- |
| `frontend/app/layout.tsx` | `<html lang="en">`, `<body>`, the header, the page title `Sentinel`, the description, and `globals.css`. |
| `frontend/app/page.tsx` | `HomePage`, `dynamic = "force-dynamic"`, and the status markup. |
| `frontend/app/globals.css` | Colors, the card, the registry form, and a one-column layout under 480px. |
| `frontend/lib/api.ts` | Server-side health calls for the status page. |
| `frontend/next.config.ts` | `reactStrictMode: true`, and `turbopack.root` set to the directory that contains the config file. |
| `frontend/package.json` | Scripts `dev`, `build`, `start`, and `typecheck`. There is no `test` script. |
| `frontend/tsconfig.json` | `strict: true`, `jsx: react-jsx`, and the `@/*` path. |

`reactStrictMode` makes React run extra checks in development. It does not add a second health request by itself. The two API calls are the two `readJson` lines.

`turbopack.root` is pinned because the Next.js dev server looks upward for a lockfile when it guesses the project root. A `package-lock.json` in a parent directory, including a home directory, must not become the project. The root is the frontend directory, derived from `import.meta.url`.

`npm run dev` starts the development server. On this project the command used in the guide is `next dev` on port `3000`. `npm run typecheck` runs `tsc --noEmit`. It checks types and does not start the server, and it does not prove the page shows the right status.

`frontend/AGENTS.md` is a note Next.js writes for coding agents about this Next.js release. It is not the architecture of Sentinel.

### How a render is assembled

1. A request arrives for `/`.
2. `RootLayout` supplies the document shell. Its `children` will be the page.
3. `HomePage` runs on the server and awaits `getApiSnapshot()`.
4. The snapshot decides which children the `<section>` has.
5. React turns that tree into HTML.
6. The browser paints HTML and CSS. It does not re-run `getApiSnapshot` until the next document request.

The definition list uses `<dl>`, `<dt>`, and `<dd>`. Each pair sits in a `<div>` so CSS grid can place the label and the value on one row, and stack them on a narrow screen. The section has `aria-label="Runtime status"` so the region has a name.

### A practical example

```powershell
cd frontend
npm run dev
```

Open `http://127.0.0.1:3000`. Use the browser's view-source or the document inspector. The status words are in the HTML that arrived. They are not filled in by a script after load.

Then run:

```powershell
npm run typecheck
```

A type error fails that command. A down database does not. Typecheck never calls the API.

### Mistakes

- Adding `"use client"` so you can `fetch` in the browser, and then wondering why the server snapshot stopped running. The current design depends on `HomePage` being a server component.
- Removing `force-dynamic` and building the site while the API is down or stale. The frozen page would not be a live check.
- Looking for `/docs` under `frontend/app`. That link on the status page points at the API origin, not at a Next.js route. The Next.js routes are `/` and `/websites`.

## 10. Automated testing

### The idea

A test is a small program that calls your code and asserts a result. Pytest finds functions named `test_*`, runs them, and reports pass, fail, or skip.

A fixture is a function pytest runs to build something a test needs. The test asks for it by naming a parameter. `monkeypatch` is a fixture pytest provides. It changes an attribute or an environment variable for one test and puts the original back afterward.

An integration test calls a real dependency. Sentinel has one: `test_configured_database_answers_select_one`. The other tests either stay inside the process or point the driver at a closed port. They do not require the Compose container.

### How this suite is arranged

Configuration is in `backend/pyproject.toml`:

- `testpaths = ["tests"]`
- `pythonpath = ["."]` so `import app` works when the current directory is `backend`
- `asyncio_mode = "auto"` so an `async def` test runs on an event loop without a manual decorator
- `asyncio_default_fixture_loop_scope = "function"`
- A marker named `integration` for the live database test

Dev dependencies include `pytest`, `pytest-asyncio`, and `httpx2`. Starlette's `TestClient` imports `httpx2`. The comment in `pyproject.toml` records that the older `httpx` package still works and that current Starlette warns if you use it for this.

Run the suite from `backend` with the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

`pytest` with no path uses Windows Python, which does not have pytest installed. That failure is a wrong interpreter, not a broken test.

### The client fixture

`backend/tests/conftest.py` defines `client`. Pytest sees the file name `conftest.py` and makes the fixture available to tests in that directory.

```python
@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
```

`create_app()` builds a new FastAPI instance. `TestClient` is a synchronous client that drives the ASGI app in-process. It does not open port `8000`. Entering the `with` block runs lifespan, so `app.state.engine` exists before the test body. Exiting runs shutdown. `yield` is what makes the fixture's cleanup happen after the test.

Tests that need a different database URL do not use this fixture. They clear the settings cache, call `create_app()` themselves, and clear the cache again in `finally`. The fixture would have called `get_settings()` too early, or would share a cached URL with other tests.

### What each test locks

| Test | Mechanism | Assertion |
| --- | --- | --- |
| `test_database_url_rejects_a_sync_driver` | Sets `DATABASE_URL` to a `postgresql://` URL. | `get_settings()` raises `ValidationError`. |
| `test_liveness_does_not_depend_on_the_database` | `client.get("/health")`. | Status `200` and the exact JSON object, including `environment` `development`. |
| `test_startup_creates_engine_and_session_factory` | Reads `client.app.state`. | Both objects are not `None`. It does not run SQL. |
| `test_frontend_origin_is_allowed` | Sends `Origin: http://localhost:3000`. | The CORS response header equals that origin. |
| `test_readiness_is_ok_when_the_database_check_succeeds` | Replaces `database_is_reachable` with an async function that returns `True`. | Status `200`, `status` `ok`, `checks.database` `ok`. |
| `test_readiness_is_degraded_when_the_database_check_fails` | The replacement returns `False`. | Status `503`, `status` `degraded`, `checks.database` `unavailable`. |
| `test_readiness_fails_closed_when_postgres_refuses_the_connection` | Real engine, URL host `127.0.0.1` port `1`, password `secret-password`. | `503`, and the password and driver scheme are absent from the body. |
| `test_configured_database_answers_select_one` | Real engine from `get_settings()`, `SELECT 1`. | The scalar result is `1`. |

The monkeypatch target is the string `"app.api.routes.health.database_is_reachable"`. That is the name the route function looks up. Patching `app.core.database.database_is_reachable` would change the original function and leave the name already imported into `health.py` untouched. The route would still call the real function.

### The integration test

`test_database.py` marks the test with `@pytest.mark.integration`. The test creates an engine, connects, and runs `SELECT 1`. `result.scalar_one()` returns that single value. The assertion is `value == 1`.

If connect or execute raises `OSError` or `SQLAlchemyError`, the test calls `pytest.skip` with the exception class name. `pytest.skip` raises a special exception that is not an `Exception` subclass, so the `except` clause does not catch it again. The `finally` block still runs and calls `engine.dispose()` before the skip propagates. A skip means the check did not run. Pytest will not count it as a pass.

When the container is healthy and `DATABASE_URL` matches it, the `except` branch does not run. The test passes.

Run only that test:

```powershell
.\.venv\Scripts\python.exe -m pytest -m integration -v
```

`-rs` adds the skip reason when the test skips. Use it when you need to see the exception class. Do not read a summary line of "1 skipped" as evidence that PostgreSQL answered.

### A practical example

Stop the container. Run the integration test with `-rs`. The skip line names the exception class, often a timeout or a connection error, and says the check did not run. Start the container, wait until `docker compose ps` shows healthy, and run the same command. The test should pass, and the summary should not say skipped.

The closed-port test still passes while the container is down. It never uses `DATABASE_URL` from `.env`. It proves the route hides a real driver failure. It does not prove your configured database is the one you think it is. Only the integration test does that.

### Mistakes

- Installing pytest into Windows Python so that the bare command `pytest` works. The project interpreter is `backend\.venv\Scripts\python.exe`.
- Forgetting `cache_clear()` around a test that sets `DATABASE_URL`. Later tests then construct the app with the test URL, including a test password.
- Patching the function in `database.py` and watching the route still call the original. Patch the name in `health.py`.
- Asserting on a skip. If you need the database, make the connection work and require `PASSED`. The skip is the behavior when the connection cannot be made, not a successful check.

## 11. Local development environment

### The idea

Four programs cooperate, and only two of them are application code.

| Program | Operating system | How you start it |
| --- | --- | --- |
| Docker Engine and the PostgreSQL container | Ubuntu on WSL 2 | `docker compose up -d` in the repository |
| `wslrelay` | Windows | Started by WSL when a WSL port is published |
| Uvicorn | Windows | The virtual environment in `backend` |
| Next.js | Windows | `npm run dev` in `frontend` |

The repository directory is the same files on Windows and in Ubuntu. A Windows path such as `C:\Users\<you>\Desktop\Sentinel` is `/mnt/c/Users/<you>/Desktop/Sentinel` in Ubuntu. Compose and Uvicorn are reading one `.env` if you created it at that root.

### The path of a database connection

1. `get_settings()` reads `DATABASE_URL`. The default host is `localhost` and the port is `5432`.
2. asyncpg asks Windows to connect to that address.
3. `wslrelay` accepts the connection because the container published port `5432`.
4. Docker Engine delivers the bytes to `sentinel-postgres-1`.
5. PostgreSQL checks the user, password, and database name, then answers the query.

The API does not know that Docker or WSL exists. It knows a TCP address. That is why a wrong password and a stopped container both become "the driver raised" inside `database_is_reachable`, and both become `503` on the readiness route. Distinguishing them is a job for the Ubuntu `docker compose ps` output and for the exception class in the API log.

### Commands that match each side

Ubuntu, new terminal, user in the `docker` group:

```bash
cd /mnt/c/Users/<you>/Desktop/Sentinel
docker compose ps
```

PowerShell, from the repository root:

```powershell
netstat -ano | findstr ":5432"
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Another PowerShell window, from the repository root:

```powershell
cd frontend
npm run dev
```

Another, for tests, from the repository root:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -v
```

`Invoke-RestMethod http://127.0.0.1:8000/health/ready` talks only to Uvicorn. If that command cannot connect, the virtual environment server is not running. If it returns JSON with `"database":"ok"`, Windows reached PostgreSQL through the chain above.

### Debugging order

When the page looks wrong, check in this order. Each step has one owner.

1. **Browser document.** Does the HTML say "could not be read", or does it show a database word? The first means Next.js never got a usable API response. The second means it did, and the word is the API's word.
2. **Uvicorn.** Is `http://127.0.0.1:8000/health` a `200`? If this fails, do not debug PostgreSQL yet.
3. **Readiness body.** Is `/health/ready` a `200` with `database` `ok`, or a `503` with `unavailable`? Read the API log for the exception class.
4. **Port forward.** Does PowerShell show `5432` listened by `wslrelay`? If not, Windows cannot use `localhost:5432`.
5. **Container.** In Ubuntu, is `sentinel-postgres-1` healthy? If the socket permission is denied, open a new Ubuntu terminal rather than stopping WSL.
6. **Credentials.** Do `POSTGRES_*` and `DATABASE_URL` describe the same user, password, database, and host port? If the volume was created with an older password, the container still has that password.
7. **Which Python.** `python -c "import sys; print(sys.executable)"` in the shell you used for pytest. It should end in `backend\.venv\Scripts\python.exe`.

### Mistakes

- Installing project packages with the system `python` so that a bare `pytest` works. Keep those packages in `.venv`.
- Starting a second Uvicorn because the first one failed for an unrelated reason. Port `8000` then belongs to a process you forgot. The log of the running process is the one that matters.
- Assuming `localhost` in the browser, `127.0.0.1` in Uvicorn's `--host`, and `localhost` in `DATABASE_URL` are one string. Uvicorn bound to `127.0.0.1` still accepts connections to `localhost` when that name resolves to `127.0.0.1`. CORS does care about the spelling of the site origin. The default allowed origins are `http://localhost:3000` and `http://127.0.0.1:3000`. An existing root `.env` overrides that default.
- Running `wsl --shutdown` to fix a Docker permission error. That stops the engine and the container. A new Ubuntu terminal is the smaller step after a group change.

## 12. Website registry

### The idea

A registry is a list the program can remember after the process restarts. Milestone 2 stores that list in PostgreSQL. The row is a name, a base URL, and two timestamps. The id is a UUID so the URL can change later without the identity of the row changing. Nothing in this milestone opens that URL.

This is one list for the whole development process. There is no user id on the row. Adding accounts later should add a real owner, not a fake one now.

### Where it is implemented

| File | Role |
| --- | --- |
| `backend/app/models/website.py` | SQLAlchemy model, unique `base_url`, and check constraints. |
| `backend/app/core/urls.py` | `normalize_base_url()`. HTTP and HTTPS only. |
| `backend/app/api/deps.py` | `get_session()`, which opens `app.state.session_factory`. |
| `backend/app/api/routes/websites.py` | The four routes. |
| `backend/alembic/versions/0001_create_websites.py` | The migration that creates the table. |
| `backend/alembic/env.py` | Points Alembic at `DATABASE_URL` and runs it with asyncpg. |
| `frontend/lib/websites.ts` | Types, form checks, and `fetch` calls. |
| `frontend/components/WebsiteRegistry.tsx` | Loading, success, error, and delete confirmation. |
| `frontend/app/websites/page.tsx` | The page shell. The interactive part is a client component. |

`create_app()` includes the website router next to the health router. Startup is unchanged: the engine and session factory are created in the lifespan, and the pool still connects on first use.

### The table

`websites` has `id`, `name`, `base_url`, `created_at`, and `updated_at`. PostgreSQL generates the UUID if a raw insert omits it. The ORM also assigns `uuid4()` before insert, so the route knows the id. The timestamps come from `now()` in the database. After commit, the route refreshes the object so the JSON includes those timestamps. `expire_on_commit=False` would otherwise leave them missing, and an implicit refresh is not allowed in async code.

The unique constraint is `uq_websites_base_url`. The checks are `ck_websites_base_url_http` and `ck_websites_name_not_blank`. Application validation runs first. The constraints are the backstop for any insert that does not go through the route.

Apply the revision from `backend`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The API does not call Alembic when it starts. A missing table becomes HTTP `503` with the detail `The database schema is not ready. Apply migrations and try again.` The driver message stays in the log as an exception class name.

### Normalization and HTTP status

`WebsiteCreate` strips the name and rejects a blank name or a name longer than 120 characters. `normalize_base_url()` then requires `http` or `https`, a host, and no username, password, query, or fragment. It lowercases the scheme and host, removes a default port, and removes one trailing slash from the path. Invalid input is HTTP `422` from FastAPI, before a query runs.

| Situation | Status | Body |
| --- | --- | --- |
| New website | `201` | The stored website, with the normalized URL |
| Same normalized URL again | `409` | `A website with this base URL is already registered.` |
| Unknown UUID | `404` | `Website not found.` |
| Id is not a UUID | `422` | FastAPI's validation body |
| Database connection failed | `503` | `The database is unavailable.` |
| Table missing | `503` | The schema-not-ready sentence |

`DELETE` returns `204` and an empty body. `GET /api/websites` returns a JSON array, newest `created_at` first.

A unique violation is PostgreSQL sqlstate `23505`. The route treats that as `409`. Other integrity errors become `422` with a generic constraint sentence. None of these responses include `DATABASE_URL`.

### Data flow for one added website

```mermaid
sequenceDiagram
  participant Browser
  participant Page as WebsiteRegistry
  participant API as FastAPI
  participant DB as PostgreSQL

  Browser->>Page: submit the form
  Page->>Page: validateWebsiteInput
  Page->>API: POST /api/websites
  API->>API: strip name and normalize_base_url
  API->>DB: INSERT
  DB-->>API: row and timestamps
  API-->>Page: 201 JSON
  Page-->>Browser: success text and the new row
```

The status page does not participate. Its server-side `fetch` is still the path in section 7. The registry request is cross-origin: the page is port `3000` and the API is port `8000`. `CORS_ORIGINS` has to name the page origin exactly. A direct browser call is why the default list includes both `localhost` and `127.0.0.1`.

### What the page shows

`WebsiteRegistry` loads the list on mount. While that request is in flight, the section says `Loading websites…`. A network or HTTP failure replaces the list with the error and a `Try again` button. An empty table says `No websites registered yet.`

The form checks the name and URL before `fetch`. Server `422` and `409` responses are written next to the field that failed. A successful create clears the inputs and shows `{name} was added.`

Delete first changes the row to `Delete {name}?` with `Delete` and `Cancel`. The `DELETE` request is sent only from the confirm button. On success the row disappears. A `404` also removes the row, because the server no longer has it.

### A practical example

With the migration applied and Uvicorn running:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/websites -Method Post -ContentType "application/json" -Body '{"name":"Example","base_url":"https://Example.com/docs/"}'
```

The returned `base_url` is `https://example.com/docs`. `GET /api/websites` includes that object. `DELETE /api/websites/{id}` returns no body.

Then open `http://127.0.0.1:3000/websites`. Add a site, reject `ftp://example.com` in the form, and delete a row only after the confirmation appears. Refresh `/` and the status list should still render. The header links the two pages.

### Mistakes

- Forgetting `alembic upgrade head` and reading the website `503` as a broken route. `/health` can still be `200`. The detail sentence names the schema.
- Sending the browser to port `8000` from an origin that is not in `CORS_ORIGINS`. The status page can look healthy because the Next.js server made those calls. The registry then fails in the browser.
- Comparing `https://example.com` and `https://example.com/` as different sites. Normalization makes them one row, and the second insert is `409`.
- Putting a user id on the model before accounts exist. The code would pretend a tenant boundary that this process does not enforce.

## Glossary

| Term | Meaning in this repository |
| --- | --- |
| ASGI | The calling convention Uvicorn uses to hand a request to the FastAPI app. |
| Application factory | `create_app()`. It returns a new FastAPI instance. Tests call it. Uvicorn uses the `app` it created at import. |
| Lifespan | The async context manager that stores the engine on `app.state` at startup and calls `engine.dispose()` at shutdown. |
| `app.state` | The place `lifespan` keeps the engine and the session factory for routes to read. |
| Settings | The `Settings` class in `config.py`. One cached object per process. |
| Env file | The root `.env`, found by walking three parents up from `config.py`. Git ignores it. |
| Engine | The SQLAlchemy `AsyncEngine`, a pool of database connections. |
| Session factory | `async_sessionmaker` created at startup. Website routes open a session from it. |
| Alembic revision | `0001_create_websites`. It creates the `websites` table. The API does not run it on startup. |
| Normalized base URL | The stored form of a site address. Scheme and host are lowercased, and a trailing slash or default port is removed. |
| asyncpg | The PostgreSQL driver selected by `postgresql+asyncpg://`. |
| Pool pre-ping | A check SQLAlchemy runs before reusing a pooled connection. |
| Liveness | `/health`. The process can answer. The database is not involved. |
| Readiness | `/health/ready`. PostgreSQL answered `SELECT 1`, or the route returns `503`. |
| CORS | Browser permission headers set by `CORSMiddleware`. The current page's server-side `fetch` does not use them. |
| Server component | `HomePage` and `RootLayout`. They run in Node while HTML is produced. |
| `force-dynamic` | The page is rendered per request, not frozen at build time. |
| Snapshot | The `ApiSnapshot` object `getApiSnapshot()` returns to the page. |
| Fixture | Pytest's `client` fixture, or the built-in `monkeypatch` fixture. |
| `TestClient` | Starlette's in-process HTTP client. It runs lifespan and does not bind port `8000`. It needs `httpx2`. |
| Integration test | `test_configured_database_answers_select_one`. It uses the real `DATABASE_URL`. |
| Skip | Pytest's way of saying a test did not run. The database test skips when the driver raises `OSError` or `SQLAlchemyError`. |
| Image | `postgres:16-alpine`. Files used to start a container. It is not your data. |
| Container | `sentinel-postgres-1`, the running PostgreSQL process. |
| Volume | `sentinel_sentinel_postgres_data`, the data directory that survives a new container. |
| Compose | The `docker-compose.yml` file plus the `docker compose` command, run in Ubuntu. |
| WSL | Windows Subsystem for Linux. Ubuntu and Docker Engine run there. |
| `wslrelay` | The Windows process that publishes the container's port `5432` on Windows `localhost`. |

## Questions

Answer from the code and from a running stack. Each question names the file that holds the evidence. Write the answer in your own words before you open the file.

1. Which process opens a TCP connection to port `5432`, and which file builds the URL it uses? (`backend/app/core/config.py`, `backend/app/core/database.py`)
2. Why does `create_app()` call `get_settings()` before lifespan connects to anything? What has happened by the time Uvicorn prints "Waiting for application startup"? (`backend/app/main.py`)
3. A colleague changes `ENVIRONMENT` in `.env` and the next `/health` response still says `development`. What has to happen before the response changes, and why? (`backend/app/core/config.py`)
4. `POSTGRES_PASSWORD` and the password inside `DATABASE_URL` differ. Which program reads which name, and what does `/health/ready` return? (`.env.example`, `backend/app/api/routes/health.py`)
5. Why is `postgresql://sentinel:sentinel@localhost:5432/sentinel` rejected even though PostgreSQL would understand a URL of that shape? (`backend/app/core/config.py`, `backend/tests/test_config.py`)
6. Name a route that opens a session from `app.state.session_factory`. What does `test_startup_creates_engine_and_session_factory` prove without that route? (`backend/app/api/routes/websites.py`, `backend/tests/test_health.py`)
7. `/health` returns `200` while `/health/ready` returns `503`. Is the API process down? What does each route refuse to do? (`backend/app/api/routes/health.py`)
8. The readiness log says `Database readiness check failed (TimeoutError)` and the HTTP body does not contain the database URL. Where is that choice made? (`backend/app/core/database.py`)
9. You refresh the status page and the browser's network panel shows one request, to port `3000`. How many requests does the Next.js server then make, and in what order? (`frontend/lib/api.ts`)
10. The database container is stopped. Why can the page still show `unavailable (503)` instead of "The API could not be read"? Which two timeouts make that possible? (`frontend/lib/api.ts`, `backend/app/core/database.py`)
11. What does `export const dynamic = "force-dynamic"` change about when `getApiSnapshot()` runs? (`frontend/app/page.tsx`)
12. `test_readiness_is_ok_when_the_database_check_succeeds` passes with the container stopped. Why is that not a false pass? What does it deliberately avoid calling? (`backend/tests/test_health.py`)
13. You patch `app.core.database.database_is_reachable` and the route still queries PostgreSQL. Which name does the route call, and where must the patch point? (`backend/app/api/routes/health.py`)
14. Pytest prints `SKIPPED` for `test_configured_database_answers_select_one`. Did `SELECT 1` return `1`? What are the two exception types that cause the skip? (`backend/tests/test_database.py`)
15. Why is the Docker volume named `sentinel_sentinel_postgres_data` when the Compose file only writes `sentinel_postgres_data`? What command deletes that data? (`docker-compose.yml`)
16. `docker compose ps` works in a new Ubuntu terminal and fails with `permission denied` on `/var/run/docker.sock` in an older one. The container is healthy the whole time. What is different about the two shells? ([development-environment.md](development-environment.md))
17. PowerShell says `No module named pytest`. The file `backend\.venv\Scripts\python.exe` runs the suite. Which interpreter did the failing command use, and what is the command that uses the right one? (`backend/pyproject.toml`)
18. The status page link "Open the API documentation" goes to port `8000`, not to a page under `frontend/app`. What URL does the component build, and which server renders Swagger UI? (`frontend/app/page.tsx`, `backend/app/main.py`)
