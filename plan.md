# Plan — Distrava

_Living document. Updated at the end of every piece of work. Last update: 2026-10-20._

**See it visually:** open `docs/roadmap.html` in a browser. It is generated from
this file (`python scripts/build_roadmap.py`), so the two never disagree.

How to read this file:
- **Status:** ✅ done · 🔨 in progress · ⏭ next · ⬜ not started · 🔬 needs research first
- **Source** (for every rule the app follows):
  **[R]** research — a study or guideline is named ·
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
- **Training advice must be backed by research.** See §2.

## 2. Principles (apply to every feature)

| Rule | Source |
|---|---|
| Training advice needs a named study or guideline [R]; your own preferences are fine labelled [Y]; assumptions [A] never ship as advice | [Y] |
| Data stays local; the only network call allowed is the AI provider you choose | [Y] |
| The AI never computes numbers — code calculates, the AI only explains | [Y] |
| You own the plan: nothing changes without your confirmation | [S] |
| No pressure: no streaks on coach screens, no red "missed" states | [S] |
| Numbers show at most 2 decimals, everywhere | [Y] |
| Every blocking action shows a loading state | [Y] |
| HR zones in five distinct colours | [Y] |
| Test first, then code (TDD) | [Y] |
| Build order: M1 → M2 → M3, then the coach (M4) | [Y] |

## 3. Roadmap

Milestones are the ones you set on GitHub on Oct 9. The features inside M1–M3
are my proposal — tell me what to add or remove.

### M1 — Trust the data
_Your imports are complete and every date, time and distance is right._

| Status | Feature | Notes |
|---|---|---|
| ✅ | Apple Health, GPX and CSV import | Phase 1 |
| ✅ | Duplicate detection; a second watch doesn't double distance | Phase 1 |
| ✅ | Regression net: alarms if any existing number changes | 2026-10-18 |
| ✅ | Activities shown and counted in local time, not UTC | 2026-10-19 |
| ⏭ | Activity list date filter in local time | small follow-up |
| ⬜ | Re-import guide: how to refresh your Apple Health export | also fixes time offsets exactly |
| ⬜ | Spot-check against Apple Fitness for a few known runs | proves the numbers; needs you |

### M2 — Records & dashboard
_What Strava charges for, explained so you can trust it._

| Status | Feature | Notes |
|---|---|---|
| ✅ | Best efforts (400 m → marathon), splits, HR zones | Phase 1 |
| ✅ | Training load (TRIMP / CTL / ATL), race predictions, VO2max estimate | Phase 1 |
| 🔬 | Check every metric against the research file | research §E |
| ⬜ | "What does this number mean?" for each metric, with its source | |
| ⬜ | PR history over time (not only the current best) | |

### M3 — Gym & foundations
_The gym side gets the same depth as running._

| Status | Feature | Notes |
|---|---|---|
| ✅ | Exercise catalog: 40 exercises, muscle groups, equipment | built for the coach |
| 🔬 | Replace the catalog's easy/moderate/hard labels with a researched measure of effort | research §A |
| ⬜ | Log a gym session: sets, reps, weight | Apple Health only gives duration + HR |
| ⬜ | Strength progress per exercise and muscle group | |
| 🔬 | Mobility, stretching and meditation sessions | research §F |

### M4 — Coach & trainer
_Spec: `Distrava Coach — Use Cases, Decisions & Test Plan.md`. Paused after step 4
until M1–M3 are done and the research is back._

| Status | Feature | Notes |
|---|---|---|
| ✅ | 1. Regression net | listed under M1 |
| ✅ | 2. Data model | weeks → sessions → exercises, check-ins, notes |
| ✅ | 3. Weekly board | Coach page: 7 day columns, add / move / remove sessions, Done / Partial / Skip, edit volumes |
| ✅ | 4. Auto check-in | imported runs/rides offered as "Import matches · Confirm" |
| 🔬 | 5. Rebalancer | rules need sources — research §A–§D |
| ⬜ | 6. Connect an AI provider | your own API key, stored in the OS keychain |
| ⬜ | 7. Coach tools, preview, undo | the AI proposes, you accept or undo |
| ⬜ | 8. Plan a week from scratch or from past weeks | |
| ⬜ | 9. Import a trainer's PDF plan | |
| 🔬 | 10. Post-workout check-in + trainer export | research §G |
| ⬜ | 11. Exercise Q&A and fact check | answer + confidence + basis |
| ⬜ | 12. Connect your own AI agent (MCP) | |

## 4. Rules the app uses today, and where they come from

| Rule | Used in | Source |
|---|---|---|
| HR zones as % of heart-rate reserve (Karvonen) | zones, time in zone | [R] Karvonen 1957; Apple Watch default — to verify (research §E1) |
| Max HR fallback 220 − age | settings | [R] widely used, known to be imprecise — to verify (§E2) |
| Training load = TRIMP; fitness/fatigue = 42/7-day averages | dashboard | [R] Banister impulse-response model — to verify (§E3) |
| Race prediction: Riegel, exponent 1.06 | dashboard | [R] Riegel 1981 — to verify (§E4) |
| VO2max estimate (Daniels VDOT formula) | dashboard | [R] Daniels & Gilbert — to verify (§E5) |
| Grade-adjusted pace: +3.3 % per 1 % grade | activity detail | [A] no source recorded — to verify (§E6) |
| Best-effort distances mirror Strava | records | [Y] |
| Match an import to a session: same type, same day, ±25 % | coach | [Y] proposed by me, you approved |
| A run one day off asks instead of matching | coach | [Y] proposed by me, you approved |
| Exercise intensity easy / moderate / hard | catalog | [A] my judgement — to replace (§A) |
| Session templates (e.g. "Chest & Triceps" = bench, incline, dips, pushdown) | coach | [A] my choice — to review |
| Default volumes (e.g. running day = 8 km) | coach | [A] my choice — to review |

## 5. Research

**You:** run the prompt in `research/PROMPT.md` in a normal Claude chat with
research turned on, and save the answer as `research/training-rules.md`.
**Then I:** turn each rule into [R] entries in §4, replace every [A] that the
research answers, and only then build the rebalancer.

| Status | Topic | What it decides |
|---|---|---|
| ⏭ | A. What makes a session "hard" | effort labels, rebalancer, check-ins |
| ⏭ | B. Recovery and spacing | rebalancer |
| ⏭ | C. A sensible week (targets) | planner, rebalancer |
| ⏭ | D. Skipped sessions and progression | rebalancer |
| ⏭ | E. Metrics already shown | M2 dashboard |
| ⏭ | F. Mobility, stretching, meditation | M3 |
| ⏭ | G. Post-workout check-in | M4 step 10 |

## 6. Log

| Date | What happened |
|---|---|
| 2026-09-07 | Phase 1 frozen; work moved to a native iOS app |
| 2026-10-09 | Freeze reversed: this Flask app is Distrava again; iOS is a separate project. Milestones M1–M4 set |
| 2026-10-18 | Coach spec written. CLAUDE.md rewritten. Regression net, data model |
| 2026-10-18 | Coach board built (sessions, not exercises, after your mockup feedback) |
| 2026-10-19 | Auto check-in; volume editing; local-time fix |
| 2026-10-20 | Coach paused. Decided: order M1 → M2 → M3 → M4, research-backed advice, built for you first. Research prompt written. This plan and the roadmap page created |

## 7. Waiting on

| Status | Item | Who |
|---|---|---|
| ⏭ | Run the research prompt, save `research/training-rules.md` | you |
| ⬜ | Sync the GitHub board with this plan — start a session with `ai-jail --github --allow-host github.com --allow-host api.github.com claude` | you start it, I sync |
| ⬜ | Push branch `coach-board` (7 commits, local only) | you, or me in the session above |
