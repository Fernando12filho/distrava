# CLAUDE.md — Distrava

## What this is
A local-first desktop training app (Flask + PyWebView) for a running + gym
"specialist": Strava-style run analysis, then strength, mobility and an AI coach.
No accounts, no subscriptions, data stays in the local SQLite file.

This repo is the **active** Distrava project. The 2026-09-07 freeze was reversed
on 2026-10-09. The native iOS app at `~/Desktop/Fernando/Distrava` is a
**separate project** — never redirect work there or treat this repo as its
reference.

**`plan.md` is the plan**: goals, milestones M1 → M2 → M3 → M4 (built in that
order), status of every feature, and every rule the app follows with its source.
Read it before starting work.

## Stack (locked — do not substitute)
Flask, SQLAlchemy + SQLite, Jinja2 server templates (no frontend build step),
Chart.js served from `/static`, PyWebView, defusedxml, pytest.

## Architecture rules
- `analytics.py` is **pure functions only** — no Flask, no SQLAlchemy. Plain
  dicts/lists in, results out. New calculation code (coach rebalancer, check-in
  matcher) follows the same rule in its own pure module.
- Routes stay thin: fetch → convert to dicts → call pure code → render/JSON.
- Schema changes: `Base.metadata.create_all()` never alters an existing table.
  New columns on existing tables go in `_SCHEMA_UPGRADES` in `app/__init__.py`;
  never wipe `data/fitness.db` (it holds the user's real health data).
- `_resolve_hr_profile` lives in `routes.py` and is shared by several screens —
  don't move it into an AI/coach module.

## Development rules
- **TDD strictly**: write the test, watch it fail, write the minimum code, refactor.
- No mocking the database — in-memory SQLite via `conftest.py` fixtures.
- No CDN links — every JS/CSS asset lives in `/static`.
- Comments explain WHY, never WHAT.
- The regression net (`test_*_snapshot.py`, `test_hr_zones.py`,
  `test_race_prediction.py`, `test_activity_import.py`, `test_migrations.py`,
  `test_routes_smoke.py`) pins pre-coach behaviour. Never regenerate a snapshot
  to turn a test green without knowing why the number moved.

## Standing UX rules
- Numbers show **at most 2 decimals everywhere**, including page source, JS
  payloads, chart tooltips and LLM prose (round payloads before the model sees them).
- Every blocking user-triggered call (LLM especially) shows a loading state.
- HR zones use five **distinct hues** — #38BDF8 / #4ADE80 / #FDE047 / #F97316 /
  #E11D48 — never a single-hue ramp.
- New UI follows the design handoff in `design_handoff_distrava/` (`.dc.html`
  per screen + the Design System file).

## Coach
Spec: `Distrava Coach — Use Cases, Decisions & Test Plan.md` (use cases, AC ids,
test files, build order). Follow its build order; reuse AC ids in test names.
- **The LLM never computes.** Every number comes from deterministic code; the
  model only proposes and explains. A number not in the payload must not appear.
- The model never writes to the database — it calls small tools, code validates,
  the result is a preview the user accepts or undoes.
- No pressure copy on coach screens: no streaks, no red "missed" states.
- The only permitted network traffic is the coach's call to the user's chosen
  provider. CI and tests never call a real LLM — use the fake provider.
- API keys live in the OS keychain, never in SQLite or logs. `.env` is gitignored.

## Evidence
- **Training advice needs research.** Any rule that tells the user how to train
  (effort, recovery, spacing, volume, progression) must cite a study or guideline,
  tagged [R] in `plan.md` §4. The user's own preferences are tagged [Y].
  Assumptions are tagged [A] and must never ship as advice.
- Research arrives as `research/training-rules.md` (generated from
  `research/PROMPT.md`). Only cite sources listed there; never invent one.

## Workflow
- After every piece of work: update `plan.md` (status, rules table, log), then run
  `python scripts/build_roadmap.py`. `tests/test_roadmap.py` fails if
  `docs/roadmap.html` is stale.
- Work is tracked on GitHub `Fernando12filho/distrava`: issues with type + `area:`
  labels, milestones M1–M4 (M4 = Coach & trainer), Projects kanban. Find or
  create the issue before starting; reference it with `Closes #N`. Keep the board
  in step with `plan.md` (needs a session started with `ai-jail --github`).
- **Never add "Co-Authored-By: Claude" or any AI/model/brand attribution to commit
  messages.** No mentions of Claude, Anthropic, or any AI tool in commits, code
  comments, or docs in this repo.

## Running under ai-jail
Sessions here usually run inside `ai-jail` (sandbox-exec). Inside it:
- `git` fails on the denied `~/.gitconfig`; prefix with `GIT_CONFIG_GLOBAL=/dev/null`
  (commits then need `-c user.name=… -c user.email=…`).
- zsh heredocs fail (`/tmp` is read-only); write files with the editor tools instead.
