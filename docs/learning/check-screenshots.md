# Check screenshots (BROW-1)

Optional viewport PNG captured at the end of a bounded Playwright check. Builds on the one-shot browser check and the DASH-2 check detail page.

## Behavior

| Piece | Rule |
| --- | --- |
| Capture | After navigation + title; viewport only (`full_page=false`) |
| Timeout | `SCREENSHOT_TIMEOUT_MS` (default 5000); failures do **not** fail the check |
| Size | Rejected above `SCREENSHOT_MAX_BYTES` (default 512000); must start with PNG magic |
| Storage | Local files under `SCREENSHOT_DIR` as `{check_id}.png` |
| Database | `website_checks.screenshot_path` holds the relative filename (or null) |
| API | `has_screenshot` on check JSON; `GET /api/checks/{id}/screenshot` returns `image/png` |
| Auth | Same session / automation token as other check routes |
| SSRF | Unchanged — public URL policy still runs before the browser opens |

Disable capture with `SCREENSHOT_ENABLED=false`.

## UI

`/checks/[id]` loads the PNG with credentials when `has_screenshot` is true. Otherwise it shows an honest empty state (no invented image URLs).

## Tests

`tests/test_screenshots.py` uses a fake runner that returns PNG bytes — Chromium is not required for CI-style local pytest.

## What stays out

- Full-page or video capture
- Object storage / CDN
- Multi-step journeys (see [browser journeys](browser-journeys.md))
