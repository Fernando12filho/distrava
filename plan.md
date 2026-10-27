# Plan — Distrava

_Living document. Updated at the end of every piece of work. Last update: 2026-10-27._

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
| Build order: M1 → M2 → M3 up to #21, then the coach (M4) until it can plan a week with you (8a agent loop, then 8b season planning), then back to the rest of M3 (#22, #23, #11), which needs it to be tested | [Y] 2026-10-21 (was M1 → M2 → M3 → M4) |
| The API key lives only in the OS keychain (macOS now, via the built-in `security` tool; `keyring` for other systems when the app is shared). With no keychain the coach stays off — the key is never saved anywhere else | [Y] 2026-10-21 |
| Every AI call is recorded with its tokens and an estimated cost, and shown in Settings | [Y] 2026-10-21 |
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
| ✅ | Log a gym session: sets, reps, weight, reps in reserve | 2026-10-20: a gym session on the board now matches the day's strength import; once done, each exercise starts as its planned sets × reps and you change anything (reps, weight, reps in reserve, add/remove sets). "Hard set" only when you enter ≤ 3 in reserve (RULE-LOAD-03) · #18 |
| 🔨 | Session effort (sRPE) after every run and lift | Works; **UI to redo later, issue stays open** (2026-10-21). 2026-10-20: a 0–10 "How hard was the whole session?" on every activity page and on a matched coach session (same value); shows easy/moderate/hard and load = rating × minutes; kept on re-import. RULE-LOAD-01 · #19 |
| ✅ | Retire the catalog's easy/moderate/hard labels: effort comes from what you did | 2026-10-21: the 40 exercises no longer carry a fixed label; the board's "Load" bars are gone; your database drops the old column on next start (custom exercises kept). Hard = your session rating or reps in reserve. RULE-LOAD-04 · #20 |
| ✅ | Weekly hard sets per muscle group | 2026-10-21: Coach page, beside the week — hard sets per muscle group, in how many sessions, and "growth" (10+) or "maintenance" (3+) range; sets without reps in reserve are listed as not counted, never guessed. The 10 / 3 bands still need the ACSM 2026 check (#24). RULE-WEEK-02/03 · #21 |
| ⬜ | Session templates become starting points only — no default split | D3 decided: the coach proposes a 2nd heavy-leg day when your goal calls for it (RULE-WEEK-04), you approve · #22 |
| ⬜ | Strength progress: hard sets per muscle group over the weeks | merged into the weekly hard-sets row; logged weights are kept for later · #23 |
| ⬜ | Mobility, stretching and meditation sessions, with honest claims only | RULE-MOB-01/02/03 · #11 |

### M4 — Coach & trainer
_Spec: `Distrava Coach — Use Cases, Decisions & Test Plan.md`. Resumed 2026-10-21
(paused after step 4 on 2026-10-20): the rest of M3 needs a coach that can plan._

| Status | Feature | Notes |
|---|---|---|
| ✅ | 1. Regression net | listed under M1 |
| ✅ | 2. Data model | weeks → sessions → exercises, check-ins, notes |
| ✅ | 3. Weekly board | Coach page: 7 day columns, add / move / remove sessions, Done / Partial / Skip, edit volumes |
| ✅ | 4. Auto check-in | imported runs/rides offered as "Import matches · Confirm" |
| ✅ | 5. Rebalancer | 2026-10-21: "Week check" on the Coach page — hard-run cap and spacing (RULE-REC-02), same-muscle spacing (REC-01), hard legs before a hard run (REC-04, D4); a run is hard on your rating or heart rate (LOAD-02, D1); each session can be planned easy/hard; a skipped session is dropped and can move only to a free later day that fits (PROG-01). Part 2: after 10+ days off it offers easing the rest of the week to 60–90 % of planned volume, your pick, with one-tap undo (PROG-04, D7); notes running distance 20 % / 30 % above your last 2 weeks (PROG-02); notes more hard runs than suggested (WEEK-01, by count) · #25 |
| 🔨 | Training profile: runs per week, gym days, split, goal, experience | 2026-10-21: editable in Settings ("Training profile" card); empty means not said yet, no default split. Coach-proposed changes come with step 7 previews (#28). Feeds RULE-WEEK-01/02, LOAD-03 · #26 |
| ✅ | 6. Connect an AI provider | 2026-10-21: Anthropic, your own API key in the macOS keychain (never SQLite, logs or the page — only "•••• last 4"); Settings card to save, test (loading state) and remove it; every call recorded with its model, tokens and an estimated cost, with this month / all-time totals. Model per task in config (Haiku 5.5 for the connection test, Opus 5.5 default, with Anthropic's refusal fallback). No new dependencies. Tests use a fake provider and can't reach the network or your keychain · #27 |
| ✅ | 7. Coach tools, preview, undo | 2026-10-21: ask the coach on the Coach page; it can move or remove a session, swap an exercise (same kind only), change a volume or plan easy/hard. Code checks every call (only planned sessions from today on with nothing logged, same limits as editing by hand, no new spacing clash) and sends rejected ones back once; otherwise it says it couldn't. The change shows faded on the board with its reason and the exact before → after lines; Accept or Discard, then Undo restores it exactly. If you edit the week first, accept is refused; once you use a changed session, undo is no longer offered. Any number in the coach's words that it wasn't given is sent back. 2026-10-27: remembers this week's conversation (last 10 turns). Not yet: changing a session's kind (run → ride), notes, profile proposals (#26) · #28 |
| 🔨 | 8a. Agent loop: the coach reads what it needs, writes a plan you see live, asks you when something's missing, and checks its own draft before showing it | Like a coding agent, built for training: read tools (any week, history, goals, research rules, exercises by equipment), `check_plan` = the Week check on its draft, `update_plan` (the loading state), `ask_user` with option buttons. Writes still go to one preview you accept or undo. Step and cost caps per request. No web search: advice comes from the research file only. 2026-10-27, slice 1 of 5 done: the coach works in steps — changes build up in one draft, it can read any other week (`get_week`, read-only, never creates a week), and a request stops at 8 steps or $0.25, showing its draft only if it passes the Week check. Next: self-check (`check_plan`) · AC-14..18 · #42 |
| ⬜ | 8b. Plan toward your season goal: main + season goal, situation notes (travel, equipment, little time) with dates, add sessions, drafts over several weeks | Situation is never a fixed setting: you say it or the coach asks. Volumes from your recent weeks replace the 8 km default. RULE-WEEK-01..04, PROG-02, PROG-04; needs D2. AC-19, AC-20 · #29 |
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
| No fixed easy / moderate / hard per exercise: "hard" comes only from your session rating or reps in reserve | catalog, coach | [R] RULE-LOAD-04 (retired 2026-10-21) |
| Session effort: your 0–10 rating; load = rating × minutes; ≤ 2 easy, 3–4 moderate, ≥ 5 hard (cut-offs are the scale's labels, a convention) | activity page, coach | [R] RULE-LOAD-01 |
| A logged set is "hard" only when you enter ≤ 3 reps in reserve; without an entry it is neither | gym log | [R] RULE-LOAD-03, RULE-LOAD-04 |
| A gym session matches a strength workout (traditional or functional) on the same day, whatever its length | coach | [Y] 2026-10-20: the plan, not the import, says what was done |
| A finished gym session starts as a copy of its plan, set by set; editing the plan later never changes it | gym log | [Y] 2026-10-20 |
| Hard sets per muscle per week: 10+ is the growth range, about 3 maintains | coach | [R] RULE-WEEK-02 (Schoenfeld 2017; pending the ACSM 2026 check, #24) |
| Any number of sessions per muscle is fine; only the weekly total is compared | coach | [R] RULE-WEEK-03 (Schoenfeld 2019) |
| Each exercise counts toward its one catalog muscle group (no partial credit for helper muscles) | coach | [A] simplest count; the research gives no rule for it |
| A run is hard on your rating ≥ 5 or 10+ min above 85 % of heart-rate reserve; nothing recorded → its planned easy/hard; neither → never clashes | coach week check | [R] RULE-LOAD-02, RULE-LOAD-04 + D1 (cut-off unvalidated, boundary an estimate) |
| At most 2 hard runs a week, 48 h apart | coach week check | [R] RULE-REC-02 (weak) |
| 48 h before a muscle group is trained hard again (full body overlaps every group) | coach week check | [R] RULE-REC-01 (expert opinion) |
| No hard legs (legs, glutes, full body) in the 24 h before a hard run | coach week check | [R] RULE-REC-04 + D4 (expert opinion, low confidence) |
| Sessions have a day but no time: the day before counts as within 24 h | coach week check | [A] needed to apply the hour rules to day-only sessions |
| A skipped session is dropped; it may move only to a free later day that breaks no spacing rule | coach week check | [R] RULE-PROG-01 — a design choice, no study (said on screen) |
| This week's running distance (imported so far + planned to come) vs the mean of the last 2 weeks: noted above +20 %, "big jump" above +30 %; no 10 % cap | coach week check | [R] RULE-PROG-02 (weak–moderate; Buist 2008 found the 10 % rule changed nothing) |
| After 10+ days without a workout, offer easing the rest of the week to 60 / 70 / 80 / 90 % of planned volume (run distance, ride time, gym sets; never reps); undo restores it | coach week check | [R] RULE-PROG-04 + D7 (you choose; thresholds are judgement calls) |
| More hard runs than max(1, 20 % of the week's runs) gets a note | coach week check | [R] RULE-WEEK-01 (counted by session; D2 still open for the dashboard) |
| Session templates (one leg day in the gym split) | coach | [R] RULE-WEEK-04 — runners need 2 strength days with heavy legs — review (M3) |
| A coach change touches only planned sessions from today on with nothing logged; it may not add a spacing clash (clashes already there are left to the Week check) | coach proposals | [A] my design choice for "you own the plan" — confirm; the spacing check reuses RULE-REC-01/02/04 |
| Default volumes (e.g. running day = 8 km) | coach | [A] no source — derive from your recent weeks (M4). On your data it makes this week's plan 65 % above your last 2 weeks |

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
| ⬜ | ACSM 2026 resistance-training update (replaces the 2009 stand) | check before the weekly hard-sets view · #24 |
| ⏭ | H. Goals the research doesn't cover yet: gaining weight (surplus, rate), marathon training + muscle gain together, a no-deadline marathon build, height/weight as inputs, weigh-in trends; also covers the ACSM 2026 check (#24) | prompt written 2026-10-20, waiting for you to run it; needed before the coach can plan your example goal (M4) |

## 6. Decisions needed

From the research file's open questions. Each is asked when its milestone starts.

| Status | Decision | Needed for |
|---|---|---|
| ✅ | D1. "Hard run" without a lab test (decided 2026-10-21: either — your rating ≥ 5, or 10+ min above the estimated threshold zone; RULE-LOAD-02) | M4 rebalancer |
| ⬜ | D2. Show the 80/20 easy/hard split by time or by number of runs? | M4 planner |
| ✅ | D3. Leg days (decided: no default split — you or the coach manage it; the coach may propose a 2nd leg day, you approve) | M3 templates |
| ✅ | D4. Gap after hard legs before a hard run (decided 2026-10-21: 24 h, RULE-REC-04) | M4 rebalancer |
| ⬜ | D5. Training-load constants: keep 42/7 days, or fit your own later? | M2 · #17 |
| ✅ | D6. Grade-adjusted pace model (decided: remove it for now) | M2 |
| ✅ | D7. Coming back after a break (decided 2026-10-21: no fixed number — the coach shows you the research options, 60–90 % first week, and you choose each time; RULE-PROG-04) | M4 rebalancer |
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
| 2026-10-20 | M3 started. You set the coach's purpose: it keeps, adjusts or builds your week from your goal, profile and trainer's plan, always with your OK; no default split (D3). Gym log built (#18): sets come from the plan, you correct anything |
| 2026-10-20 | Topic H research prompt written (goals + ACSM 2026 check) |
| 2026-10-20 | Session effort (#19): rate any run or lift 0–10; load and easy/moderate/hard shown with their rule. D1 not needed yet — it only matters for the rebalancer |
| 2026-10-21 | #19 kept open: the effort rating works, but its UI will be redone later. #20 done: the catalog's fixed easy/moderate/hard labels and the board's "Load" bars removed (RULE-LOAD-04) |
| 2026-10-21 | #21 done: weekly hard sets per muscle group on the Coach page, with its rule and sources. Your data has no logged sets yet, so it shows empty until you log a gym session |
| 2026-10-21 | Build order changed (your decision): the coach comes next, since the rest of M3 needs it. Training profile (#26) in Settings; next is the rebalancer (#25), which needs D1, D4, D7 |
| 2026-10-21 | D1 (either signal), D4 (24 h) and D7 (coach offers options, you choose) decided |
| 2026-10-21 | AI provider connected (#27): Anthropic key in the macOS keychain, Settings card with test and spend totals; no API call made yet — waiting for your key |
| 2026-10-21 | Rebalancer done (#25): ease back in after a break (your pick, with undo), distance-jump and easy/hard notes. On your data: this week's plan is 21 km against a 12.72 km average (+65.11 %), mostly from the 8 km default per running day |
| 2026-10-22 | UI: the left bar can be hidden. Collapsed, it becomes a slim rail with the "DSV" mark (green S) and a button to bring it back; the choice is remembered |
| 2026-10-22 | Dev: `scripts/screenshots.py` screenshots every page on a throwaway database (Playwright, dev-only via `requirements-dev.txt`), so UI changes are checked by eye before review |
| 2026-10-22 | Your design calls: the collapsed rail shows page icons with tooltips (DS-02); screenshots use a read-only copy of your real database; design decisions live in the Design System file, section 05 (DS-01 DSV mark, DS-02 rail) |
| 2026-10-22 | Sidebar opens and closes smoothly: contents fade, the width glides, contents fade back in (~0.45 s). Instant if macOS "reduce motion" is on |
| 2026-10-22 | Dashboard opens with Today (DS-03): your coach week's sessions for the day, every exercise with sets × reps; a tile opens it on the Coach board. On your data: Thu shows Legs & Glutes (skipped) and Chest & Triceps (planned) |
| 2026-10-22 | Coach page (DS-04): asking the coach no longer reloads the page (your message shows at once, then the reply); the Coach panel closes to a rail like the left bar; day columns stop spilling (the week scrolls sideways below 100px a day); on a narrow window the panel opens over the board instead of below it |
| 2026-10-21 | Rebalancer, part 1 (#25): sessions can be planned easy/hard (your choice over guessing from the exercise); the Coach page checks the week's spacing and offers fitting days for a skipped session. On your data: no clashes; your skipped Thursday legs day has no free later day, so it is dropped |
| 2026-10-27 | Found why the coach never answered: all 6 requests on 10-22 were rejected by Anthropic (HTTP 400) and the reason was thrown away. Rejections now show Anthropic's reason. The reason: the easy/hard tool listed its choices in a form Anthropic's strict check refuses (an enum beside "string or null"); rewritten in the accepted form, with a test so it can't come back. Your call: no change of direction (local-first stays; online database, logins and iPhone are future talk); focus is finishing the MVP and polishing the UI. The coach plans toward a main + season goal; situation (travel, equipment, time, skipped days) comes from you or the coach asks |
| 2026-10-27 | First real coach conversation worked (3 calls, about $0.05). Found it forgot its own options: every message started a new conversation. Now the coach hears this week's last 10 turns (your request, its reply, and whether you accepted, discarded or undid a change); only the latest message carries the week, so it never reasons from an old board. Errors are left out |
| 2026-10-27 | Your call: the coach becomes an agent, like a coding agent but for training. Step 8 split: 8a agent loop (reads, plans live, asks you, checks its own draft; #42), then 8b planning toward your season goal with situation notes and multi-week drafts (#29). Spec updated: UC-16/17, AC-14..20, 4 new test files |
| 2026-10-27 | 8a slice 1: the coach works in steps instead of one shot. Changes collect in a draft across steps; it can read any other week; it finishes by replying without a tool. Limits per request: 8 steps or $0.25 (my default — yours to change); on a limit it shows its draft only if that draft passes the Week check. A simple change now takes 2 calls (the change, then the coach finishing) |

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
| ✅ | OK to add topic H to `research/PROMPT.md` | you — added 2026-10-20 |
| ⏭ | Paste your Anthropic key in Settings → AI coach and press Test connection (costs well under $0.01). Then delete the key from `strava-copy/.env`; optionally create a fresh key and revoke the old one, since it sat in plain text since July | you |
| ⏭ | Try the coach once with your key (Coach page → "Ask your coach…", e.g. "move Thursday's run to Saturday"); each request is one Opus call, recorded in Settings with its cost | you |
| ⏭ | Run the topic H follow-up prompt (end of `research/PROMPT.md`), save it as `research/training-rules-H.md` | you |
| ⬜ | Board columns (Projects kanban): the token has no `project` scope — run `gh auth refresh -s project` outside the jail, then I can move cards | you |
| ✅ | Issues #7 and #9: add them to this plan | you — added to M1 and M2 |
| ✅ | Push branch `coach-board` — already merged into `main`, which is pushed | — |
