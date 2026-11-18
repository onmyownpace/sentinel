# Accounts and product dashboard

Learning-scale sign-in and a simple dashboard. This is not an enterprise identity system.

## What you get

| Piece | Behavior |
| --- | --- |
| Email + password | Register / login; bcrypt hashes in `users` |
| Session cookie | HttpOnly `sentinel_session`; server row in `user_sessions` |
| Ownership | `websites.owner_id` set on create for signed-in users |
| Dashboard | `GET /api/dashboard` → sites, recent checks, MON-1 stats, `health` roll-up |
| Pages | `/login`, `/register`, `/dashboard`, `/websites/[id]` health, `/checks/[id]` detail |

Health routes stay public. Registry, checks (except scheduled), analysis, and dashboard require a session **or** `X-Automation-Token`.

## Automation vs schedule tokens

| Header | Used for |
| --- | --- |
| `X-Automation-Token` | n8n **GET**s (list websites, latest checks) so workflows keep working without a browser cookie |
| `X-Schedule-Check-Token` | n8n **POST** `/scheduled-checks` only (still the machine acknowledgement to open a browser) |

Put matching values in `.env` (`AUTOMATION_TOKEN`, `SCHEDULE_CHECK_TOKEN`) and in each workflow’s **API address** Set node (`automationToken`, `scheduleToken`).

## Dev seed

On API startup, if `SEED_USER_EMAIL` is set and that email is missing, Sentinel creates the account and claims websites with a null `owner_id`.

Defaults (see `.env.example`):

- email `dev@sentinel.local`
- password `dev-password-change-me`

Set `SEED_USER_EMAIL=` empty to skip seeding.

## Migrate and try

```bash
cd backend
alembic upgrade head
# restart the API so seed + new settings load
```

1. Open `http://127.0.0.1:3000/login` with the seed account (or register).
2. Open **Dashboard** — health overview, sites you own, and recent checks (links into site/check drill-down).
3. **Websites** still runs Playwright checks; fetches send cookies (`credentials: "include"`). See also [dashboard health UI](dashboard-health-ui.md).
4. Re-import n8n workflows (or edit **API address**) so `automationToken` is present, then keep scheduled checks + webhook delivery as before.

## What stays out

- OAuth, MFA, password reset mail, roles/RBAC
- Per-tenant databases or billing
- JWT access tokens in localStorage
- Locking down `/health`