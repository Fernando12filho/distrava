# Plan — Distrava

_Living document. Updated at the end of every piece of work. Last update: 2026-10-20._

**See it visually:** open `docs/roadmap.html` in a browser. It is generated from
this file (`python scripts/build_roadmap.py`), so the two never disagree.

How to read this file:
- **Status:** ✅ done · 🔨 in progress · ⏭ next · ⬜ not started · 🔬 needs research first
- **Source** (for every rule the app follows):
  **[R]** research — a rule id from `research/training-rules.md` ·
  **[Y]** your decision ·
  **[S]** written in the coach spec, no source given yet ·
  **[A]** an assumption made while building — must be confirmed or replaced

---

## 1. What we want to achieve

A private desktop app for a runner who also trains in the gym. Your data stays on
your machine: no accounts, no subscriptions, no cloud.

- **Specialist in running + gym**, plus the foundations under every sport:
  strength, stretching, mobility, meditation.
- **Not for beginners or the unmotivated.** The value is: knowing where to go
  next, answering exercise doubts, and insights about your running.
- **Built for you first, others later.** No onboarding or packaging work yet,
  but nothing personal is hard-coded, so it can be shared one day.
- **Training advice must be backed by research.** See §2 and §4.

## 2. Principles (apply to every feature)

| Rule | Source |
|---|---|
| Training advice needs a rule from the research file [R]; your own preferences are fine labelled [Y]; assumptions [A] never ship as advice | [Y] |
| Research rule parameters are config with ranges, not hard-coded constants | [R] research file, "How to read" |
| Data stays local; the only network call allowed is the AI provider you choose | [Y] |
| The AI never computes numbers — code calculates, the AI only explains | [Y] |
| You own the plan: nothing changes without your confirmation | [S] |
| No pressure: no streaks on coach screens, no red "missed" states | [S] |
| Numbers show at most 2 decimals, everywhere | [Y] |
| Every blocking action shows a loading state | [Y] |
| HR zones in five distinct colours | [Y] |
| Test first, then code (TDD) | [Y] |
| Build order: M1 → M2 → M3, then the coach (M4) | [Y] |
| Personal facts (sex, birth year) are set only by you. Your training profile (runs per week, gym days, split, goal, experience) can be set by you or created and changed by the AI coach — with your confirmation | [Y] 2026-10-20 |

## 3. Roadmap

Milestones are the ones you set on GitHub on Oct 9. Rule ids (RULE-…) point to
`research/training-rules.md`. #N is the GitHub issue for that row
(Fernando12filho/distrava); every open row has one.

### M1 — Trust the data
_Your imports are complete and every date, time and distance is right._

| Status | Feature | Notes |
|---|---|---|
| ✅ | Apple Health, GPX and CSV import | Phase 1 |
| ✅ | Duplicate detection; a second watch doesn't double distance | Phase 1 |
| ✅ | Regression net: alarms if any existing number changes | 2026-10-18 |
| ✅ | Activities shown and counted in local time, not UTC | 2026-10-19 |
| ✅ | Activity list date filter in local time | 2026-10-20; end date now inclusive, bad dates give a clear error |
| ✅ | Re-import guide on the Import page | 2026-10-20; page no longer claims .fit support it doesn't have; time-zone wording corrected |
| ✅ | Find why ~half of runs have almost no heart-rate samples | 2026-10-20: Apple's export itself lacks per-second samples for those workouts; the importer was right |
| ✅ | Average/max HR from the watch's own workout summary; re-import corrects existing activities | 2026-10-20; on your data: 27 activities off by 10+ bpm |
| ✅ | Runs without per-second heart rate: zones, HR chart and split HR hidden, with a note; gaps and jumps noted | 2026-10-20; your runs: 66 hidden, 5 with a gaps note, 46 clean |
| ✅ | Spot-check against Apple Fitness for a few known runs | 2026-10-20: all match |
| ⬜ | Winter-time and travel start times are 1–2 h off | low impact: 308 activities show 1 h late, 1 on the wrong day. Apple's export writes all dates in the export-time offset; each workout's own `HKTimeZone` tag fixes it. Needs `ai-jail --map /var/db/timezone` to verify · #16 |
| 🔬 | Research: get data from devices into Distrava without a manual export | Shortcuts, Health Auto Export, a small iOS companion; incremental vs full re-import; what leaves the device · #7 |

### M2 — Records & dashboard
_What Strava charges for, correct by the research and explained so you can trust it._

| Status | Feature | Notes |
|---|---|---|
| ✅ | Best efforts (400 m → marathon), splits, HR zones | Phase 1 |
| ✅ | Training load (TRIMP / CTL / ATL), race predictions, VO2max estimate | Phase 1 |
| ✅ | Check every metric against research | 2026-10-20 — findings below |
| ✅ | Sex in Settings, used for training load | 2026-10-20; the training profile moved to M4 (you or the coach set it) |
| ✅ | Max HR: Tanaka 208 − 0.7 × age, replaced by your observed max | 2026-10-20; yours: 194 → 190 (observed 178 is lower) |
| ✅ | Resting HR from Apple Health (7-day median) instead of the default 60 | 2026-10-20; yours: 54 after your next re-import |
| ✅ | Training load with sex-specific TRIMP constants, shown as a personal trend | 2026-10-20; RULE-METRIC-03 |
| ✅ | Race predictions: marathon flagged as likely too fast | 2026-10-20; RULE-METRIC-04 (no slower adjustment: the research gives no formula) |
| ✅ | "VO2max" relabelled as a race-equivalent score (VDOT); zones labelled as estimates | 2026-10-20; RULE-METRIC-05, METRIC-01 |
| ✅ | Grade-adjusted pace: removed (D6) — it used an unsupported 3.3 % per 1 % rule and was never shown | 2026-10-20; revisit with Minetti 2002 if wanted |
| ✅ | "What does this number mean?" for each metric, with its rule id | 2026-10-20: training load, race predictions, VDOT, HR zones; a test rejects any source not in the research file |
| ✅ | PR history: Records page with every improvement per distance | 2026-10-20; linked from Recent PRs · #8 |
| ✅ | Impossible best efforts removed (distance logged in chunks read as sprints) | 2026-10-20; e.g. 400 m 0:18 → 1:34, 1K 3:02 → 4:30; your PR table needs a one-time recompute · #6 |
| ⬜ | Dashboard: agree the 3–5 questions it answers at a glance, then redesign around them | e.g. load this week, recent PRs, run vs gym balance; follows the design handoff · #9 |

### M3 — Gym & foundations
_The gym side gets the same depth as running._

| Status | Feature | Notes |
|---|---|---|
| ✅ | Exercise catalog: 40 exercises, muscle groups, equipment | built for the coach |
| ⬜ | Log a gym session: sets, reps, weight, reps in reserve | RULE-LOAD-03; Apple Health only gives duration + HR · #18 |
| ⬜ | Session effort (sRPE) after every run and lift | RULE-LOAD-01 · #19 |
| ⬜ | Retire the catalog's easy/moderate/hard labels: effort comes from what you did | RULE-LOAD-04 · #20 |
| ⬜ | Weekly hard sets per muscle group | RULE-WEEK-02/03 · #21 |
| ⬜ | Review session templates: 2 strength days with heavy legs for runners | RULE-WEEK-04 · #22 |
| ⬜ | Strength progress per exercise and muscle group | #23 |
| ⬜ | Mobility, stretching and meditation sessions, with honest claims only | RULE-MOB-01/02/03 · #11 |

### M4 — Coach & trainer
_Spec: `Distrava Coach — Use Cases, Decisions & Test Plan.md`. Paused after step 4
until M1–M3 are done._

| Status | Feature | Notes |
|---|---|---|
| ✅ | 1. Regression net | listed under M1 |
| ✅ | 2. Data model | weeks → sessions → exercises, check-ins, notes |
| ✅ | 3. Weekly board | Coach page: 7 day columns, add / move / remove sessions, Done / Partial / Skip, edit volumes |
| ✅ | 4. Auto check-in | imported runs/rides offered as "Import matches · Confirm" |
| ⬜ | 5. Rebalancer | RULE-REC-01/02/04, PROG-01/02, WEEK-01; decisions D1, D4, D7 · #25 |
| ⬜ | Training profile: runs per week, gym days, split, goal, experience | set by you or created/changed by the coach (with your confirmation); feeds RULE-WEEK-01/02, LOAD-03 · #26 |
| ⬜ | 6. Connect an AI provider | your own API key, stored in the OS keychain · #27 |
| ⬜ | 7. Coach tools, preview, undo | the AI proposes, you accept or undo · #28 |
| ⬜ | 8. Plan a week from scratch or from past weeks | RULE-WEEK-01..04 · #29 |
| ⬜ | 9. Import a trainer's PDF plan | #30 |
| ⬜ | 10. Post-workout check-in + trainer export | RULE-CHECK-01/02; decision D8 · #31 |
| ⬜ | 11. Exercise Q&A and fact check | answer + confidence + basis · #32 |
| ⬜ | 12. Connect your own AI agent (MCP) | #33 |

## 4. Rules the app uses today, and where they come from

| Rule | Used in | Source |
|---|---|---|
| HR zones as % of heart-rate reserve (Karvonen), labelled as estimates | zones, time in zone | [R] RULE-METRIC-01 |
| Max HR: your setting, else the higher of 208 − 0.7 × age and the highest HR held ≥ 5 s | settings, zones, load | [R] RULE-METRIC-02 (Tanaka 2001) |
| Training load = TRIMP with constants for your sex (male ones while not set) | dashboard | [R] RULE-METRIC-03 (constants are expert opinion) |
| Resting HR: your setting, else the median of Apple Health's last 7 daily readings, else 60 | zones, load | [R] RULE-METRIC-01 |
| Fitness / fatigue as 42 / 7-day averages | dashboard | [R] RULE-METRIC-03 — convention; fine as a personal trend |
| Race prediction: Riegel, exponent 1.06; marathon shown with a "likely too fast" caution | dashboard | [R] RULE-METRIC-04 |
| VDOT shown as a race-equivalent score, not VO2max | dashboard | [R] RULE-METRIC-05 |
| Heart-rate gaps over 30 s and jumps over 15 bpm/s are flagged | activity detail | [R] RULE-METRIC-07 (thresholds are expert opinion) |
| Under 50 % of a workout with heart rate: zones, HR chart and split HR hidden; under 90 %: a gaps note | activity detail | [Y] D10; thresholds from your data, which clusters above 90 % or below 50 % |
| Average / max HR come from the watch's own workout summary | everywhere | [Y] fix for Apple's sparse exports, 2026-10-20 |
| Best-effort distances mirror Strava | records | [Y] |
| A best effort can't include a gap over 15 s that covers more than 2× the run's typical speed | records, PRs | [A] from your data, pending your OK |
| Match an import to a session: same type, same day, ±25 % | coach | [Y] proposed by me, you approved |
| A run one day off asks instead of matching | coach | [Y] proposed by me, you approved |
| Exercise intensity easy / moderate / hard | catalog | [R] RULE-LOAD-04 says effort must come from what you did — retire (M3) |
| Session templates (one leg day in the gym split) | coach | [R] RULE-WEEK-04 — runners need 2 strength days with heavy legs — review (M3) |
| Default volumes (e.g. running day = 8 km) | coach | [A] no source — derive from your recent weeks (M4) |

## 5. Research

Received 2026-10-20: `research/training-rules.md` — 30 rules, from the prompt in
`research/PROMPT.md`. Your profile block was blank, so rules marked
"depends_on" wait for the profile (M2).

| Status | Topic | What it decides |
|---|---|---|
| ✅ | A. What makes a session "hard" — RULE-LOAD-01..04 | effort tracking (M3), rebalancer |
| ✅ | B. Recovery and spacing — RULE-REC-01..04 | rebalancer, planner |
| ✅ | C. A sensible week — RULE-WEEK-01..05 | planner, templates (M3) |
| ✅ | D. Skipped sessions and progression — RULE-PROG-01..04 | rebalancer, dashboard |
| ✅ | E. Metrics already shown — RULE-METRIC-01..07 | M2 fixes |
| ✅ | F. Mobility, stretching, meditation — RULE-MOB-01..03 | M3 |
| ✅ | G. Post-workout check-in — RULE-CHECK-01..02 | M4 step 10 |
| ⬜ | ACSM 2026 resistance-training update (replaces the 2009 stand) | check before M3 · #24 |

## 6. Decisions needed

From the research file's open questions. Each is asked when its milestone starts.

| Status | Decision | Needed for |
|---|---|---|
| ⬜ | D1. "Hard run" without a lab test: effort rating, heart rate, or either? | M3, M4 rebalancer |
| ⬜ | D2. Show the 80/20 easy/hard split by time or by number of runs? | M4 planner |
| ⬜ | D3. Keep your gym split, or nudge toward 2 leg days a week for running? | M3 templates |
| ⬜ | D4. Gap after hard legs before a hard run: 24 h or 48 h? | M4 rebalancer |
| ⬜ | D5. Training-load constants: keep 42/7 days, or fit your own later? | M2 · #17 |
| ✅ | D6. Grade-adjusted pace model (decided: remove it for now) | M2 |
| ⬜ | D7. Coming back after a break: 14-day threshold, 80 % first week? | M4 rebalancer |
| ⬜ | D8. When a check-in disagrees with the watch, does the check-in win? | M4 step 10 |
| ✅ | D9. Choose your sex in Settings (the rest of the profile is set by you or the coach later) | M2 training load |
| ✅ | D10. Runs without per-second heart rate: hide time-in-zones and HR chart (decided: hide) | M1 HR flags |

## 7. Log

| Date | What happened |
|---|---|
| 2026-09-07 | Phase 1 frozen; work moved to a native iOS app |
| 2026-10-09 | Freeze reversed: this Flask app is Distrava again; iOS is a separate project. Milestones M1–M4 set |
| 2026-10-18 | Coach spec written. CLAUDE.md rewritten. Regression net, data model |
| 2026-10-18 | Coach board built (sessions, not exercises, after your mockup feedback) |
| 2026-10-19 | Auto check-in; volume editing; local-time fix |
| 2026-10-20 | Coach paused. Decided: order M1 → M2 → M3 → M4, research-backed advice, built for you first. Research prompt written. This plan and the roadmap page created |
| 2026-10-20 | M1: activity list date filter uses local time; "to" date includes that day |
| 2026-10-20 | Research received. Five metrics on the dashboard conflict with it; fixes added to M2. Coach rules now have sources |
| 2026-10-20 | M1: re-import guide on the Import page; removed the false ".fit" claim |
| 2026-10-20 | M1: checking heart-rate gaps on real data found ~half of runs with almost no in-run samples. Cause unknown (export or importer); investigating |
| 2026-10-20 | M1: cause found in your export — Apple omits per-second samples for some workouts. Importer now uses the watch's own HR summary; re-import fixes existing data |
| 2026-10-20 | M1: runs without per-second heart rate hide their zones and HR chart (D10); gaps and jumps get a note. Rule parameters now live in `app/training_rules.py` |
| 2026-10-20 | You re-imported. Found that Apple's export writes every date in the export-time offset, so the claim "exact time zone from the watch" was wrong; winter/travel hour offset parked as low impact. Spot-check list sent |
| 2026-10-20 | Spot-check: all match — M1 done. M2 started: max HR now Tanaka + observed max (yours 194 → 190); 7-day load 22.51 → 24.01 |
| 2026-10-20 | Observed max repaired (127 → 178, backup kept). Resting HR now read from Apple Health (yours 54). Decided: the training profile is set by you or the coach |
| 2026-10-20 | You re-imported (resting HR 54) and set sex. M2: marathon prediction cautioned, VO2max relabelled VDOT, zones labelled as estimates |
| 2026-10-20 | M2: "What is this?" explanations with rule ids and sources on training load, predictions, VDOT and HR zones |
| 2026-10-20 | D6: unused grade-adjusted pace removed. PR history: Records page with progression chosen |
| 2026-10-20 | Records page built. Found impossible PRs (400 m in 18 s) from chunked distance in 2020–21 exports; a teleport rule removes them and keeps real pauses |
| 2026-10-20 | GitHub synced with this plan: 18 issues created (#16–#33) for every open row; #8, #12, #14 closed as done; #6 moved to M2 |
| 2026-10-20 | Added #7 (device sync research, M1) and #9 (dashboard questions, M2) to this plan |

## 8. Waiting on

| Status | Item | Who |
|---|---|---|
| ✅ | Run the research prompt, save `research/training-rules.md` | you |
| ✅ | Point me to your Apple Health `export.zip` (read-only check of one sparse run) | you |
| ✅ | Re-import `mydata/export 3.zip` on the Import page (about a minute) — fixes HR and times on all activities | you |
| ✅ | Compare the spot-check list with the Fitness app | you |
| ✅ | OK to repair your observed max HR in `data/fitness.db` (127 → 178, after a backup)? | you — done |
| ✅ | Re-import `mydata/export 3.zip` once more, to pick up your resting HR (54) | you |
| ⏭ | Decision D9: your profile, before M2 starts | you |
| ⏭ | OK the teleport rule, and a one-time recompute of your PR table (backup first)? | you |
| ✅ | Sync the GitHub issues with this plan | done 2026-10-20 |
| ⬜ | Board columns (Projects kanban): the token has no `project` scope — run `gh auth refresh -s project` outside the jail, then I can move cards | you |
| ✅ | Issues #7 and #9: add them to this plan | you — added to M1 and M2 |
| ✅ | Push branch `coach-board` — already merged into `main`, which is pushed | — |
