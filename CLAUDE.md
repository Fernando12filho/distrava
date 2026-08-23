# CLAUDE.md — Distrava

## Project Overview
A local-first, open-source desktop app that replicates Strava's paid run analysis
features. No accounts, no subscriptions, no GPS tracking — just your data on your
machine. Import from Apple Health export.zip, analyze offline.

## Stack (locked — do not substitute)
- **Python 3.11+**
- **Flask** — serves both HTML pages and JSON API endpoints
- **SQLAlchemy + SQLite** — ORM + file-based database, zero server setup
- **Jinja2** — server-side HTML templates, no frontend build step
- **Chart.js** — local copy in /static (no CDN; desktop app = no internet assumption)
- **PyWebView** — wraps Flask in a native desktop window (no browser chrome)
- **defusedxml** — safe XML parsing (protects against entity-expansion DoS)
- **pytest** — test runner (TDD: tests written before production code)

## Architecture Decisions
- `analytics.py` contains **pure functions only** — no Flask, no SQLAlchemy.
  Input: plain Python dicts/lists. Output: computed results. This keeps every
  calculation unit-testable without HTTP or DB context.
- Routes in `routes.py` are thin: fetch from DB → convert to dicts → call analytics
  → render template or return JSON.
- `best_efforts` table stores pre-computed PRs, updated on every import. Fast to
  query, no on-the-fly recomputation.
- Two-pass streaming parser for Apple Health XML: pass 1 collects workout time
  windows, pass 2 buckets HR/distance records by time overlap. Never loads the
  full XML DOM into memory.
- Dedup key: `(activity_type, start_time, duration_seconds)` stored as a unique
  constraint. Prevents re-importing the same export.zip from creating duplicates.

## Development Rules
- **TDD strictly**: write the test first, run it (watch it fail), then write the
  minimum code to make it pass, then refactor.
- No mocking the database — use SQLite in-memory via conftest.py fixtures.
- No CDN links in templates — Chart.js and any other JS must be in /static.
- No code comments that explain WHAT the code does. Only comment WHY when the
  reason is non-obvious (e.g. the two-pass parser design, the dedup window logic).
- Keep routes thin. Business logic lives in analytics.py, not routes.py.
- Do not build features outside the Phase 1 scope listed in plan.md.
- **Never add "Co-Authored-By: Claude" or any AI/model/brand attribution to commit
  messages.** No mentions of Claude, Anthropic, or any AI tool in commits, code
  comments, or docs in this repo.

## Project Structure
```
/app
  __init__.py         app factory (create_app())
  models.py           SQLAlchemy models
  parser.py           Apple Health XML + GPX + CSV ingestion
  analytics.py        pure calculation functions (best efforts, HR zones, etc.)
  routes.py           Flask route handlers
  /templates
    base.html
    import.html
    activity_list.html
    activity_detail.html
    dashboard.html
  /static
    chart.js          local copy
    style.css
/tests
  conftest.py         pytest fixtures: in-memory DB, test client, sample builders
  /fixtures
    sample_export.xml minimal valid Apple Health XML for tests
    sample.gpx
    sample.csv
    sample_export.zip
  test_models.py
  test_parser.py
  test_analytics.py
  test_routes.py
run.py                entry point: starts Flask + opens PyWebView window
requirements.txt
pytest.ini
CLAUDE.md             this file
plan.md               full feature and TDD plan
```

## Running the App
```bash
pip install -r requirements.txt
python run.py
```

## Running Tests
```bash
pytest
pytest tests/test_analytics.py -v   # run one module
pytest -k "best_effort"              # run tests matching a name
```

## Best Effort Distances (mirrors Strava)
400m, 1/2 mile (~804m), 1km, 1 mile (~1609m), 2 miles (~3218m),
5km, 10km, 15km, 10 miles (~16093m), Half Marathon (21097m), Marathon (42195m)

## Data Import
- **Phase 1**: Apple Health export.zip (full export, one-time or manual re-export)
- **Phase 1 fallback**: .gpx and .csv files
- **Phase 2 (future)**: incremental import — skip activities already in DB by
  comparing start_time against the latest stored activity timestamp.

## Open Source Notes
- MIT license
- No telemetry, no network calls, fully offline
- All user data stays in the local SQLite file (./data/fitness.db)
