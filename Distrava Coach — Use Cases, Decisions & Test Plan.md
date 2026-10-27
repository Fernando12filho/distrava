# Distrava Coach — Use Cases, Decisions & Test Plan

Oct 18, 2026 · @fer · updated Oct 27, 2026: step 8 split into 8a (agent loop) and 8b (planning toward a season)

## Overview and principles

Coach Distrava is a weekly training board — seven day-rows of exercise cards — that an AI coach builds, explains and adjusts, and that the user can always edit by hand. The coach is an assistant that manipulates the plan through small, checked actions, not a chatbot that only talks.

- **No pressure.** No streaks, no red "missed" states, no guilt notifications. A skipped card is neutral; the week quietly rebalances.
- **LLM narrates, code decides.** The existing Distrava rule holds: the model proposes and explains; deterministic code does all math, validation and database writes.
- **User owns the plan.** Every coach change appears as a preview the user accepts or undoes. Manual edits always win.
- **Local-first.** Plan, check-ins and notes live in SQLite. Only the minimum context leaves the machine, and only to the provider the user chose.
- **Honest answers.** Fact checks return a verdict, a confidence level and what it rests on — never a confident guess.
- **Works without AI.** With no key connected, the board, manual cards and check-ins still work.

## Use cases

Seventeen use cases cover the feature; UC-15 guarantees the app stays useful with no AI connected.

| ID | Use case | Trigger | Result |
| --- | --- | --- | --- |
| UC-01 | Connect AI | User pastes an API key or connects their own agent | Coach enabled; key stored in OS keychain, never in SQLite |
| UC-02 | Plan from scratch | User states a goal and available days | Coach asks only missing info, proposes a week; user accepts |
| UC-03 | Plan from preset | User picks past weeks / activities already in Distrava | Week built from what the user already does, adjusted to goal |
| UC-04 | Import plan from PDF or document | User uploads a trainer's plan | Exercises extracted into day-rows; review screen before saving |
| UC-05 | Edit board manually | User drags, adds, deletes a card | Change saved; coach respects it |
| UC-06 | Ask about an exercise | User taps a card → "Ask coach" | How-to, muscles worked, common mistakes |
| UC-07 | Substitute, change, rest | "No barbell today" / "knee hurts" / "I need rest" | Coach proposes a swap or rest; preview diff |
| UC-08 | Did something else | User did a different workout than scheduled | Card replaced; rest of week rebalances automatically |
| UC-09 | Auto check-in | Imported activity matches a card | Card marked done, user confirms with one tap |
| UC-10 | Manual check-in | User taps done / partial / skip | Status saved, no judgment |
| UC-11 | Post-workout check-in | Workout completed | Up to 3 skippable questions (energy, effort, pain); suggestion if needed |
| UC-12 | Fact check | "Does creatine make you lose hair?" | Verdict + confidence + basis, in a few sentences |
| UC-13 | Trainer notes | User exports notes for a personal trainer | Readable log of check-ins and changes for a date range |
| UC-14 | Undo coach change | User taps undo | Board returns to previous state exactly |
| UC-15 | No AI | No key / offline | Board, cards, check-ins all work; coach panel shows setup hint |
| UC-16 | Plan around a situation | "I'm travelling for 2 weeks with dumbbells" / "only 30 min a day this week" | Coach asks only what's missing, then plans that stretch with what's available, toward the season goal |
| UC-17 | Season goal | User sets a main goal and this season's goal, or accepts one the coach proposes | Every plan and change works toward it; shown on the Coach page |

## Open decisions

Recommendation for v1: bring-your-own API key plus an MCP server for external agents, deterministic auto-matching for check-ins, and every coach change shown as an accept/undo preview. A Distrava login is deferred because it needs a server, which breaks local-first.

| # | Decision | Options | Recommendation | Why |
| --- | --- | --- | --- | --- |
| D1 | How AI is connected | A) User's own API key · B) Login to a Distrava account that proxies the model · C) Local model (Ollama) · D) User's own agent connects to Distrava via an MCP server | A + D now; C as a later plug-in | A and D keep data local and cost on the user. B needs a backend, billing and accounts. A provider interface makes C cheap to add later |
| D2 | How workouts get checked in | Auto-match imported activity · one-tap done / partial / skip · log sets inside the card · tell the coach in chat | Auto-match for cardio, one-tap for strength, chat optional | Matching by type + date + duration is pure code — no tokens, testable. One tap is the least friction for gym work |
| D3 | How the user reviews coach output | Apply silently · confirm dialog · preview on the board | Preview: proposed cards appear faded, with Accept / Undo and a "why" line | User sees exactly what changes, in place; nothing changes without consent |
| D4 | How a PDF plan is read | Text extraction + LLM to a fixed schema · LLM vision on page images · OCR | Text extraction (e.g. pdfplumber) → LLM fills a JSON schema → validator → review screen | Cheapest reliable path; scanned PDFs fall back to OCR later |
| D5 | Where fact checks come from | Model knowledge only · web search when provider supports it · curated source list | Model knowledge with explicit confidence; web search optional | Keeps tokens low; "low confidence" is an honest answer |
| D6 | Exercise data | Free text from the LLM · local exercise catalog with ids | Local catalog; LLM maps names to catalog ids; unknown → custom exercise | Rebalancing needs muscle groups per exercise, which free text can't guarantee. Hardness is not a catalog field: it comes from what was done (RULE-LOAD-04) |

Still open: which providers to support first, whether sets/reps are logged in v1 or only done/skip, and which activity sources feed auto-matching (FIT/GPX import, Garmin, others).

## Coach as an agent

The coach never rewrites the whole week and never touches the database: it calls small tools, code validates each call, and the result becomes a preview. The same tools back the MCP server, so the user's own agent gets exactly the same powers.

&#91;embedded content: coach request flow · 1 decision, 1 retry loop\]

Simple actions skip the model entirely; anything the model proposes must pass code validation and the user's accept.

| Tool | Kind | What it does |
| --- | --- | --- |
| `get_week(week)` | read | Compact summary: day, card ids, exercise ids, status |
| `get_exercise(id)` | read | Catalog entry: muscles, equipment |
| `get_load()` | read | CTL / ATL / TSB and recent volume, computed by existing code |
| `get_checkins(from, to)` | read | Post-workout answers and notes |
| `propose_week(days)` | write | Full week from scratch, preset or PDF — the only bulk write |
| `swap_exercise(card, exercise)` | write | Substitute one exercise |
| `move_card(card, day)` | write | Move to another day |
| `adjust_card(card, sets, reps, duration)` | write | Change volume |
| `add_rest(day)` | write | Turn a day into rest or mobility |
| `rebalance_week(from_day)` | write | Runs the deterministic rebalancer; LLM only explains the result |
| `log_note(text, tags)` | write | Adds to trainer notes |
| `fact_check(claim)` | answer | Verdict, confidence, basis |

**Rebalancer (pure code).** When a day changes, it redistributes the remaining week with fixed rules: no hard sessions on the same muscle group on consecutive days, keep weekly targets where possible, and drop missed work rather than stack it. Rules are configurable and fully unit-tested.

## Agent loop (step 8a)

Added Oct 27, 2026. Step 7 is single-shot: the model sees the week once, proposes, and gets one correction. Planning needs more: the coach works the way a coding agent does — **read what it needs, write down a plan, act, check its own work, ask when stuck** — and code still decides what is allowed.

Each round the model picks the next step; code runs the tool and returns the result; the loop ends when the coach answers, asks the user a question, or presents its draft.

| Tool | Kind | What it does |
| --- | --- | --- |
| `get_week(week_start)` | read | Any week, past or planned: sessions, items, status, what can change |
| `get_history(from, to)` | read | Runs and lifts in a range with load, distance, hard sets per muscle — computed by existing code, rounded to 2 decimals |
| `get_goals()` | read | Main goal, season goal and training profile (8b adds situation notes) |
| `search_rules(topic)` | read | Matching rules from `research/training-rules.md`: id, rule, parameters, sources |
| `search_exercises(muscle, equipment, category)` | read | Catalog entries that fit, e.g. "legs, dumbbells only" |
| `check_plan()` | read | Runs the Week check on the current draft: clashes, distance jumps, hard-run count |
| `update_plan(steps)` | progress | The coach's short to-do list, shown live in the Coach panel while it works (the loading state) |
| `ask_user(question, options)` | pause | Shown as a question with option buttons; the loop stops until the user answers, and the answer continues the same request with its draft |
| step 7 write tools | write | Change the request's **draft**, never the board; the draft becomes one preview at the end |

- **Limits.** A step cap and a cost cap per request live in `llm_config`. On reaching either, the coach stops and shows what it has; it never continues silently.
- **Self-check.** A draft is run through `check_plan` before it is shown; a draft that adds a clash is never presented as clean.
- **Numbers.** Tool results join the numbers the coach may use; the invented-number guard is unchanged.
- **Knowledge.** Training advice comes only from `search_rules`. A question the research doesn't cover is answered as "not covered" and becomes a research gap — no web search for now.
- **Writes.** Read tools never write. The board changes only when the user accepts the preview; undo stays exact.

## Planning toward a season (step 8b)

Built on the 8a loop. The coach plans toward a lasting goal and adapts to what life brings.

- **Main goal + season goal.** The main goal is the long-term aim; the season goal has a start and end date. Set by the user, or proposed by the coach and accepted. The free-text profile goal becomes the main goal.
- **Situation notes.** Travel, equipment on hand, little time: the user says it in a request, or the coach asks with `ask_user`. The coach stores it with `remember(note, from, to)`; a note applies only inside its dates, shows on the board for those days, and the user can delete it. Location and equipment are never fixed settings.
- **New write tools.** `add_session(day, kind, focus, items)` and `plan_weeks(from_week, weeks)`: a draft can span several weeks and is accepted or undone as one.
- **Volumes from the user's own weeks.** Planned volumes start from recent weeks, replacing the fixed defaults (the 8 km running day is an [A]).
- **Rules.** RULE-WEEK-01..04 for the week's shape, RULE-PROG-02 for volume jumps, RULE-PROG-04 after a break; D2 (80/20 by time or by count) is decided before 8b ships.

## Weekly board and comfort

The main page is seven rows, Monday to Sunday, each holding that day's exercise cards left to right; the coach lives in a side drawer, never a pop-up.

- **Card:** exercise name, sets × reps or duration, muscle tag, status chip (planned, done, partial, skipped, moved). Tap → details and "Ask coach". Drag → move day.
- **Today** is highlighted; past days dim. Rest days are a calm card, not an empty row.
- **Skipped** uses a neutral grey, never red. No streak counters, no "you missed" copy.
- **Coach preview:** proposed cards appear faded with Accept / Undo and one "why" line.
- **Post-workout check-in:** at most 3 questions — energy (1–5), effort (RPE), any pain (where). Every question has a visible Skip; skipping twice in a row stops asking for that week.
- **Notifications:** off by default; optional single daily reminder the user sets.

A clickable mockup of the board is a good next step before building the UI.

## Token budget

The cheapest call is the one never made: anything the UI or code can do costs zero tokens, and the LLM is reserved for language, judgment and explanation.

1. **Zero-token path first.** Done/skip, drag-to-move, auto-matching and rebalancing are code. The coach is only invoked for questions and proposals.
2. **Compact context.** Send the week as short ids and codes, not prose or history. Check-in history is kept as a rolling summary, not raw logs.
3. **Prompt caching.** System prompt, tool definitions and the exercise catalog are stable — cache them where the provider supports it.
4. **Right-sized models.** A small model for extraction and intent; a larger one only for planning and fact checks. Configurable per task.
5. **Diffs, not weeks.** Write tools return changed cards only.
6. **Local answer cache.** Fact checks and exercise explanations are cached by normalized question.
7. **Reliability without extra calls.** Structured output against a JSON schema → validator → at most one retry → otherwise ask the user. Never silently accept invalid output. From step 8a, an agent request may take several rounds, bounded by its step and cost caps; a rejected write still gets one correction.

Budgets per call type live in config and are enforced by a test on the prompt builder (see Automated tests).

## Desired results

Each result is written so a test can prove it; the AC id is reused in test names.

| AC | Use case | Result we want |
| --- | --- | --- |
| AC-01 | UC-01 | API key is stored in the OS keychain; SQLite and logs never contain it |
| AC-02 | UC-02, 03 | A proposed week has 7 rows, every card maps to a catalog id or a custom exercise, and it passes rebalancer rules |
| AC-03 | UC-04 | A sample trainer PDF imports with the right days and exercises; nothing saves before the user confirms the review screen |
| AC-04 | UC-05 | A manual edit is never overwritten by a coach proposal without a new preview |
| AC-05 | UC-07, 08 | After a swap or replaced day, the remaining week has no back-to-back hard sessions on the same muscle group, and missed work is not stacked |
| AC-06 | UC-09 | An imported run within the matching tolerance marks the right card; ambiguous matches ask instead of guessing |
| AC-07 | UC-10, 11 | Skip and partial are saved with neutral wording; check-in questions are ≤ 3 and all skippable |
| AC-08 | UC-12 | Fact checks always return verdict + confidence + basis; no invented sources |
| AC-09 | UC-13 | Trainer export covers the chosen range and contains only check-ins and notes |
| AC-10 | UC-14 | Undo restores the board byte-for-byte to the previous state |
| AC-11 | UC-15 | With no provider, every non-coach feature works and no network call is made |
| AC-12 | all | Every LLM call stays within its configured token budget |
| AC-13 | all | Existing Distrava metrics and screens behave exactly as before |
| AC-14 | UC-02, 07, 16 | An agent request stops within its step and cost caps; on a stop it shows what it has and nothing changes unseen |
| AC-15 | all | Read tools never write; every write lands in the request's draft and reaches the board only through accept |
| AC-16 | UC-02, 07, 16 | Every draft passes `check_plan` before it is shown; a draft that adds a clash is never presented as clean |
| AC-17 | UC-16 | `ask_user` pauses the request; the answer resumes it with the same draft |
| AC-18 | UC-12, 16 | Every rule the coach cites is an id from `research/training-rules.md`; an uncovered question says so |
| AC-19 | UC-16, 17 | Plans work toward the season goal; a situation note applies only inside its dates |
| AC-20 | UC-02, 03 | A multi-week draft is accepted or undone as one, byte-for-byte |

## Automated tests

Two suites: a regression net written before any coach code lands, and new tests written first for each feature. CI never calls a real LLM — a fake provider replays recorded responses.

**Regression net (write first, must stay green)**

| Test file | Protects |
| --- | --- |
| `test_training_load_snapshot.py` | CTL / ATL / TSB on fixture activities match stored values |
| `test_best_efforts_snapshot.py` | Best efforts unchanged |
| `test_hr_zones.py` | Zone boundaries and time-in-zone |
| `test_race_prediction.py` | Riegel and VDOT outputs |
| `test_activity_import.py` | Existing imports parse identically |
| `test_migrations.py` | New coach tables migrate up and down without touching existing tables or rows |
| `test_routes_smoke.py` | Every existing Flask route still returns 200 |

**New feature tests**

| Test file | Level | Covers |
| --- | --- | --- |
| `test_rebalancer.py` | unit | AC-05: muscle-group spacing, no stacking, weekly targets, edge cases (all days skipped, one day left) |
| `test_checkin_matcher.py` | unit | AC-06: type + date + duration tolerance, ambiguous → ask |
| `test_coach_tools_validation.py` | unit | Every tool rejects bad ids, impossible volumes, past days |
| `test_plan_schema.py` | unit | AC-02: schema + catalog mapping |
| `test_preview_undo.py` | integration | AC-04, AC-10: preview never writes; undo is exact |
| `test_pdf_import.py` | integration | AC-03: golden PDFs → expected JSON; no save before confirm |
| `test_coach_contract.py` | contract | Fake provider: malformed output → one retry → asks user |
| `test_fact_check_shape.py` | contract | AC-08: verdict, confidence, basis always present |
| `test_key_storage.py` | unit | AC-01: key only in keychain, redacted in logs |
| `test_no_ai_mode.py` | integration | AC-11: no provider → features work, zero network calls |
| `test_token_budget.py` | unit | AC-12: prompt builder output under each budget |
| `test_copy_lint.py` | unit | AC-07: UI strings contain no pressure words ("missed", "failed", "streak") |
| `test_mcp_server.py` | integration | External agent gets the same tools and the same validation |
| `test_agent_loop.py` | contract | AC-14, AC-16, AC-17: step and cost caps, self-check before showing, ask and resume |
| `test_read_tools.py` | unit | AC-15: read tools are pure, never write, numbers at most 2 decimals |
| `test_rule_search.py` | unit | AC-18: results are real rule ids with their sources; nothing found → "not covered" |
| `test_season_plan.py` | unit + integration | AC-19, AC-20: goal and situation notes shape the draft; multi-week accept and undo |

## Build order (TDD)

Build the board and all the pure-code logic before any AI, so the coach plugs into a system that already works and is already tested. Each step: write its tests red, make them green, keep the regression net green.

1. Regression net (all snapshot and smoke tests above)
2. Data model: weeks, day-rows, cards, check-ins, notes, exercise catalog + migrations
3. Board UI with manual cards, drag, done / partial / skip (UC-05, UC-10, UC-15)
4. Check-in matcher for imported activities (UC-09)
5. Deterministic rebalancer (UC-08)
6. Provider interface + bring-your-own key + fake provider for tests (UC-01)
7. Coach tools, preview and undo (UC-07, UC-14)
8. Plan from scratch and from presets, split on Oct 27, 2026:
   - 8a. Agent loop: read tools, rule search, live plan, ask the user, self-check (UC-02, UC-07, UC-16)
   - 8b. Planning toward a season: goals, situation notes, add sessions, multi-week drafts (UC-02, UC-03, UC-16, UC-17)
9. PDF import with review screen (UC-04)
10. Post-workout check-in and trainer export (UC-11, UC-13)
11. Exercise Q&A and fact check (UC-06, UC-12)
12. MCP server for external agents (UC-01, option D)
