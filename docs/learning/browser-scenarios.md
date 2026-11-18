# Scenario library (BROW-3)

Named reusable **scenarios** attached to a website. Each scenario wraps one existing **journey** (BROW-2) for steps — it does not duplicate the step list.

## Naming

| Concept | Role |
| --- | --- |
| **Journey** | Declarative step sequence (`navigate` → fill/click → assert) |
| **Scenario** | Library label + optional description pointing at a journey; run on demand |

Keep the names distinct in UI and API so journeys stay the step authoring surface and scenarios stay the reusable catalog.

## Storage

| Table | Role |
| --- | --- |
| `website_scenarios` | Name, description, `journey_id`, `schedule_eligible` |
| `scenario_runs` | On-demand execution history (outcome, duration, step results) |

`schedule_eligible` defaults to `false` and is **not** wired to n8n in BROW-3. Later enrollment can read the flag without blocking this milestone.

Deleting a website cascades scenarios and their runs. Deleting the underlying journey also cascades linked scenarios (FK `ON DELETE CASCADE`).

## API

- `POST/GET /api/websites/{id}/scenarios`
- `GET/PATCH/DELETE /api/scenarios/{id}`
- `POST /api/scenarios/{id}/runs` with `{ "authorized": true }`
- `GET /api/scenarios/{id}/runs`, `GET /api/scenario-runs/{id}`

Runs reuse the BROW-2 journey runner and SSRF policy. Authorization ack matches one-shot checks and journeys.

## UI

**Scenario library** panel on `/websites` and site health: pick an existing journey, name the scenario, optional description / schedule-eligible flag, run on demand, see step results.

## What stays out

- Duplicating journey steps inside the scenario row  
- n8n / schedule enrollment (flag only)  
- Background queues (ENG-3 only if needed later)
