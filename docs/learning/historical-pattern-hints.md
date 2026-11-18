# Historical pattern hints (AI-2)

On-demand summary of **repeated failures** and **latency spikes** across recent checks for one website. Builds on AI-1’s provider switch and MON-1’s check windows. Never required for demos.

## What it does

A person (or automation token) asks the API to summarize recent `website_checks` for one site. The API loads a capped newest-first sample (`24h` / `7d` / `all`), builds sanitized evidence, runs the configured provider once, and stores one row per website.

**Development default:** `ANALYSIS_PROVIDER=simulated` — deterministic local heuristics, **zero** AI network calls.

**Optional:** `ANALYSIS_PROVIDER=openai` with `OPENAI_API_KEY` — same switch as single-check failure analysis (AI-1). Not needed for local demos or tests.

What it does **not** do:

- Auto-run after every check  
- Replace single-check **Analyze failure** (AI-1)  
- Incident paragraphs for n8n (that is **AI-3** — see [incident-summary-drafts.md](incident-summary-drafts.md))  
- Require paid AI for demos  

## Naming

| Feature | Scope |
| --- | --- |
| AI-1 failure analysis | One stored **failed** check |
| AI-2 pattern hints | Recent checks for **one website** (success + failure) |

## API

- `POST /api/websites/{id}/pattern-hints?window=7d&sample_limit=50`  
  - Creates hints, or returns `200` with the stored row when window/sample/latest-check fingerprint still matches  
  - `refresh=true` forces a new provider run  
- `GET /api/websites/{id}/pattern-hints` — read only; never calls a provider  

Needs at least one stored check in the window (`422` otherwise).

## Storage

Table `website_pattern_hints`: unique `website_id`. Deleting the website cascades the row. `based_on_latest_check_id` is set null if that check is deleted.

## Simulated heuristics

Flags (when evidence supports them):

- **repeated_failure** — failure rate in the sample  
- **status_cluster** — repeated HTTP status among failures  
- **failure_streak** — newest consecutive failures  
- **latency_spike** — peak duration ≫ sample average  
- **stable** / **insufficient_data** — otherwise  

Limitations always say `SIMULATED PATTERN HINTS` so the UI can banner clearly.

## UI

**Historical pattern hints** on `/websites` and site health: Summarize / Show saved / Refresh.
