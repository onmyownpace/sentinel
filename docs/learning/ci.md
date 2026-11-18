# Continuous integration (ENG-1)

Free GitHub Actions runs on every **push** and **pull_request**.

## Workflow

File: `.github/workflows/ci.yml`

| Job | What it runs |
| --- | --- |
| `backend` | Postgres 16 service + `pip install -e ".[dev]"` + `pytest -q` |
| `frontend` | `npm ci` + `npm run typecheck` + `npm run build` |

Auth, SSRF address policy, and validation already live in the API and pytest suite. This milestone adds the **CI wiring** so those checks run on the remote free runner.

## Secrets hygiene

- CI uses **disposable** env values (`ci-*-token`, local Postgres password `sentinel`). They are not production credentials.
- The workflow does **not** print `env`, dump secrets, or enable debug logging that would echo headers/tokens.
- `ANALYSIS_PROVIDER=simulated` and empty `OPENAI_API_KEY` so CI never calls a paid AI API.
- Prefer `-q` / short tracebacks on pytest to keep accidental secret-shaped strings out of noisy logs.

Do not add steps like `printenv`, `env | sort`, or `echo "${{ secrets.* }}"`.

## Local parity

```bash
# backend (with Compose Postgres up)
cd backend
python -m pip install -e ".[dev]"
python -m pytest -q

# frontend
cd frontend
npm ci
npm run typecheck
npm run build
```

Chromium is not installed in CI; check/journey tests use scripted runners.
