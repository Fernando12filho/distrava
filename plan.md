# Plan — Distrava (Phase 1)

## Goal
Reproduce Strava's paid run-analysis features locally. No GPS tracking, no social
features, no accounts. Import from Apple Health, analyze offline, view in a desktop
window powered by PyWebView + Flask.

---

## Database Schema

### activities
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| activity_type | TEXT | 'Run', 'Walk', 'Cycle', etc. |
| start_time | DATETIME | UTC |
| end_time | DATETIME | UTC |
| duration_seconds | INTEGER | |
| distance_meters | FLOAT | |
| avg_hr | FLOAT | nullable |
| max_hr | FLOAT | nullable |
| elevation_gain_meters | FLOAT | nullable |
| source | TEXT | 'apple_health', 'gpx', 'csv' |
| source_id | TEXT | Apple Health workout UUID if available |
| dedup_key | TEXT UNIQUE | hash(activity_type+start_time+duration_seconds) |
| created_at | DATETIME | |

### activity_streams
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| activity_id | INTEGER FK | CASCADE DELETE |
| stream_data | JSON | {hr: [], pace: [], elevation: [], distance: [], lat: [], lon: [], time: []} — `time` is the unified sorted set of elapsed-seconds offsets across all metrics; `hr`/`distance`/`elevation`/`lat`/`lon` are same-length arrays with `null` where that metric has no reading at that offset (Apple Health samples HR/distance independently and only has `lat`/`lon`/route-derived `elevation` for workouts with a linked GPS route file; GPX streams — both direct .gpx uploads and Apple Health route files — have no nulls since every trackpoint carries all metrics together) |

### best_efforts
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| distance_label | TEXT | '5K', '10K', 'Half Marathon', etc. |
| distance_meters | FLOAT | canonical distance |
| activity_id | INTEGER FK | activity where this PR was set |
| duration_seconds | FLOAT | best time for this distance |
| pace_per_km_seconds | FLOAT | derived from duration/distance |
| achieved_at | DATETIME | = activity start_time |

### hr_zones
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| zone_number | INTEGER | 1–5 |
| label | TEXT | 'Zone 1 (Recovery)', etc. |
| min_bpm | INTEGER | |
| max_bpm | INTEGER | |

### exercises
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | |
| muscle_group | TEXT | |
| category | TEXT | (seeded, unused in Phase 1 UI) |

### user_settings
| column | type | notes |
|---|---|---|
| id | INTEGER PK | single row (id=1 in practice) |
| resting_hr | INTEGER | nullable, defaults to 60 if unset |
| max_hr | INTEGER | nullable, falls back to `220 - age` via birth_year if unset |
| birth_year | INTEGER | nullable, used only for the max_hr fallback |

Added during Step 6: TRIMP/CTL/ATL and HR-zone defaults need a resting/max HR
input that wasn't in the original schema.

---

## TDD Order of Work

### Step 1 — Test infrastructure
- [x] `pytest.ini` — configure test paths, markers
- [x] `tests/conftest.py` — in-memory SQLite DB, Flask test client, model factories
- [x] `tests/fixtures/` — build minimal sample XML, GPX, CSV, ZIP files

### Step 2 — Models (test first)
- [x] Write `tests/test_models.py`
- [x] Write `app/models.py` until all model tests pass

### Step 3 — Parser (test first)
- [x] Write `tests/test_parser.py`
- [x] Write `app/parser.py` until all parser tests pass

### Step 4 — Analytics (test first)
- [x] Write `tests/test_analytics.py`
- [x] Write `app/analytics.py` until all analytics tests pass

### Step 5 — Routes (test first)
- [x] Write `tests/test_routes.py`
- [x] Write `app/routes.py` + `app/__init__.py` until all route tests pass

### Step 6 — Templates
- [x] `base.html`, `import.html`, `activity_list.html`, `activity_detail.html`, `dashboard.html`, `settings.html`
- [x] Chart.js vendored to `app/static/chart.js` (v4.5.1, no CDN)
- [x] Added `user_settings` table (resting_hr, max_hr, birth_year) — not in original schema, needed for TRIMP/CTL/ATL/HR-zone defaults
- [x] Wired best-effort computation into the import pipeline (`parser.update_best_efforts`)
- [x] Smoke-test visually via `python run.py` + PyWebView — native WebView2 window
      opened and served `/`, `/activities`, `/dashboard`, and static assets (200s)

### Step 7 — Desktop wrapper
- [x] `run.py` — starts Flask in background thread, opens PyWebView window

---

## Test Plan Summary

### test_models.py
- Activity row created with all fields
- ActivityStream FK → Activity, CASCADE DELETE works
- Unique constraint on dedup_key prevents duplicate insert
- BestEffort FK → Activity

### test_parser.py
- Minimal Apple Health XML → correct Activity rows
- Two-pass: HR records bucketed into correct workout window
- Records outside all workout windows are discarded (no crash)
- Dedup within one parse: overlapping workouts → keeps one
- Dedup across re-imports: importing same zip twice → no new rows
- GPX file → Activity + stream
- CSV file → Activity (no stream)
- Zip path traversal entry → raises error, no file written
- Zip missing export.xml → clean user-facing error
- Defusedxml: entity-expansion attempt → caught

### test_analytics.py
- Best effort: correct 5K from known stream
- Best effort: activity shorter than target → no result (no crash)
- Best effort: new PR replaces old; non-PR does not overwrite
- HR zones: time-in-zone sums to total duration
- HR zones: sample on boundary → correct zone
- Splits: 1km splits correct from known distance stream
- Splits: partial final split included
- Grade-adjusted pace: flat → same as raw
- Grade-adjusted pace: uphill → slower adjusted pace
- TRIMP: known HR + duration → expected value
- CTL/ATL: day-1 value equals that day's load
- CTL/ATL: decays correctly with zero-activity days
- Riegel: known 5K time → expected 10K within tolerance
- VO2max: known pace + HR → expected value within tolerance

### test_routes.py
- GET / → 302 to /activities
- GET /activities → 200
- GET /activities?type=Run → filtered results
- GET /activities?from=&to= → date-filtered results
- GET /activities/<id> → 200 for existing
- GET /activities/<id> → 404 for missing
- GET /activities/<id>/stream.json → valid JSON with expected keys
- POST /import valid zip → 200 + summary
- POST /import invalid file type → 400
- POST /import oversized → 413

---

## Out of Scope (Phase 1)
- GPS route map display
- Segment leaderboards
- Social / following / clubs
- Live tracking
- Strava API sync
- Garmin / Fitbit / Wahoo import (Phase 2)
- Incremental import (Phase 2)
- AI-generated workout summaries (Phase 3)
- Mobile app
- Packaging / PyInstaller distribution (after Phase 1 is stable)
