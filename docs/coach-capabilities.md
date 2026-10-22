# Distrava Coach — Capabilities & Context (DRAFT 1)

_Started 2026-10-22. A draft for you to correct. Once agreed, it replaces build
steps 8–12 of `Distrava Coach — Use Cases, Decisions & Test Plan.md` where they
overlap, and `plan.md` M4 is rewritten from it._

Questions for you are marked **Q-n**. Nothing below is built yet except what
§1 lists as done.

---

## 0. What the coach is for

The board already lets you move, add and remove sessions in one drag. The
coach earns its place where you can't do that yourself quickly:

1. **Analyse** — read your history and say what it shows, with the numbers it used.
2. **Suggest** — say what to change next, and why, citing a research rule.
3. **Create** — build sessions, a week, or a block from your goal, file and history.
4. **Remember** — keep what matters about you (goals, limits, preferences) in a
   file you own, so you never repeat yourself.

Moving cards is a side effect of 2 and 3, not the point.

Rules that don't change:
- **The AI never computes.** Every number comes from our code; the AI only reads,
  chooses and explains. A number it wasn't given is sent back (already enforced).
- **Nothing changes without you.** Every write is a preview → Accept / Discard → Undo.
- **Training advice needs a research rule** [R]; your preferences are [Y]; guesses [A] never ship as advice.
- **No pressure:** no streaks, no "missed", no guilt.

---

## 1. Capabilities

Status: ✅ built · ⬜ to build. Each capability gets test ids (§6).

### Analyse
| Id | Capability | Example | Reads | Status |
|---|---|---|---|---|
| CAP-A1 | Explain a week | "Why was last week so tiring?" | snapshot, `get_week` | ⬜ |
| CAP-A2 | Explain a trend | "Am I getting fitter?" | snapshot, `get_trend` | ⬜ |
| CAP-A3 | Explain one workout | "How did Sunday's long run go?" | `get_activity` | ⬜ |
| CAP-A4 | Readiness for a goal | "Am I ready for a half marathon?" | snapshot (PRs, VDOT, weekly km) | ⬜ |
| CAP-A5 | Balance check | "Am I neglecting legs?" | snapshot (hard sets per muscle) | ⬜ |

### Suggest
| Id | Capability | Example | Status |
|---|---|---|---|
| CAP-S1 | Next step for a goal | "What should I change to run a marathon?" | ⬜ |
| CAP-S2 | React to how you feel | "Knee hurts" → low-impact swap + a file note proposal | ⬜ (partly: swap exists) |
| CAP-S3 | Notice something unasked | after an import: "3 hard runs in 5 days" | ⬜ **Q-1** |

### Create
| Id | Capability | Example | Status |
|---|---|---|---|
| CAP-C1 | Add a session | "Add a 30-minute mobility session Friday" | ⬜ |
| CAP-C2 | Build a session's exercises | "Make Thursday a pull day for climbing" | ⬜ |
| CAP-C3 | Plan a week | "Plan next week" (from goal, file, history) | ⬜ (step 8) |
| CAP-C4 | Plan a block | "4 weeks building to 15 km long runs" | ⬜ **Q-2** |
| CAP-C5 | Read a trainer's plan | PDF → week, review before saving | ⬜ (step 9) |

### Adjust (built in step 7)
| Id | Capability | Status |
|---|---|---|
| CAP-J1 | Move / remove a session | ✅ |
| CAP-J2 | Swap an exercise (same kind) | ✅ |
| CAP-J3 | Change a volume | ✅ |
| CAP-J4 | Plan a session easy / hard | ✅ |

### Remember
| Id | Capability | Status |
|---|---|---|
| CAP-M1 | Read your coach file on every request | ⬜ |
| CAP-M2 | Propose an edit to the file ("add: left knee, avoid downhill") | ⬜ |
| CAP-M3 | Propose a training-profile change (#26) | ⬜ |
| CAP-M4 | Keep the conversation going within a week | ⬜ |

### Out of scope (say so, don't attempt)
Medical diagnosis; nutrition plans; anything needing a source not in
`research/training-rules.md` (answered as "no research rule for this yet").

---

## 2. How the coach gets information

Two layers, so a simple question stays one fast call and a deep one can dig.

### 2a. Snapshot — sent on every request (computed by code, ≤ ~1,500 words)
| Part | Contents |
|---|---|
| Today | date, week start, units |
| Coach file | the whole file (§3) |
| This week | sessions, exercises, statuses, what can change (as today) |
| Last 8 weeks, one line each | running km · running time · runs · longest run · pace · min in each HR zone (good-HR runs only) · hard/easy runs · session-effort load · gym sessions · hard sets per muscle · other sports (e.g. volleyball) time · done / partial / skipped counts |
| Fitness | fitness / fatigue / form now and 4 weeks ago |
| Running level | PRs (5K, 10K, half), VDOT, predictions with the marathon caution |
| Heart | resting HR (7-day median), max HR in use |
| Week check | the notes the board already shows |
| Rules | id + one line for each research rule the app applies |
| Thread | this week's last 6 messages |

**Q-3:** 8 weeks or 12?

### 2b. Read tools — the AI calls them only when needed
| Tool | Returns |
|---|---|
| `get_week(date)` | any past or future week: sessions, what was done, effort |
| `get_activity(id)` | one workout: type, day, distance, duration, pace, avg/max HR, zone minutes, splits, effort, elevation gain |
| `get_activities(from, to, type)` | a list, one line each (max 50) |
| `get_trend(metric, weeks)` | weekly values for one metric (km, load, resting HR, hard sets…) up to 52 weeks |
| `get_best_efforts(distance)` | PR history for one distance |
| `get_rule(id)` | the full research rule text |

Get exercises we also need a database with exercises and what they are needed for, database can be created by us with llm and internet data. This will need research on, because exercises there are many but what are the important ones. We need mobility exercises, streching, weight lifting, gym machines to be used.

Each read tool call is one extra round trip (a few seconds, well under $0.01
with caching). A request may make at most **4** read calls, then must answer.

### 2c. Write tools — always end as a preview
Built: `move_session`, `remove_session`, `swap_exercise`, `adjust_item`, `set_planned_effort`.
To build: `add_session`, `add_exercise`, `remove_exercise`, `propose_week`,
`propose_file_edit`, `propose_profile_change`.

---

## 3. The coach file (like CLAUDE.md, for your training)

A short document you own, stored in the local database, shown on its own page.

```
## Goals            marathon, no rush · gain a little weight
## Limits           left knee: no downhill repeats (since 2026-10)
## Preferences      long run on Sunday · no barbell on Tuesdays
## Trainer          (from your trainer's plan)
## What works       easy runs after leg day feel fine
## Notes            anything else
```

- You edit it any time; your edit always wins.
- The coach can only **propose** an edit — shown as a diff, Accept / Discard / Undo.
- Every version is kept, so any change can be rolled back.
- Size cap (~600 words); when it grows past it, the coach proposes a condensed
  version for you to accept.

**Q-4:** One file, or split "about me" (goals, limits) from "notes" (history)?

---

## 4. Privacy — what may leave your machine

Only to the provider you chose, only inside a coach request.

| Data | Sent? |
|---|---|
| Distances, durations, paces, HR averages, zone minutes, elevation gain, effort ratings | yes, rounded to 2 decimals |
| Activity date (day only) and weekday | yes |
| Activity type | yes |
| Your coach file and training profile | yes — you wrote them for the coach |
| Your messages in this week's thread | yes |
| **GPS points (`lat`/`lon` in recordings), routes, start places** | **never** |
| **Clock times** (when you train) | **never** — day only |
| **Device names, source ids, file names** | **never** |
| Activity titles / free-text notes from imports | never (may contain places or names) |
| API key | never |
| Age | **Q-5** (helps read heart rate) |
| Body weight | **Q-5** (needed for "gain a little weight") |
| Sex | **Q-5** (training-load constants already use it locally) |

A **"What the coach sees"** page shows the exact text of the last request, so
you can check this yourself.

---

## 5. Compacting and keeping context

- **Numbers are compacted by code**, never summarised by the AI: weeks → one
  line, older history only through `get_trend`.
- **The conversation** is kept per week (already stored). The snapshot carries
  the last 6 messages; older ones stay readable on the board.
- **Lasting facts** move from conversation into the coach file only through an
  accepted proposal (CAP-M2). Nothing is remembered silently.
- **Prompt caching:** instructions, catalog, rules and tools are stable and
  cached; the snapshot changes daily and comes after them.

---

## 6. Tests

### Automated (pytest, free, every run — fake provider)
| Id | Proves |
|---|---|
| T-PRIV-01 | The snapshot and every read-tool result contain no `lat`, `lon`, clock time, device, source id or title — checked on fixture activities that have them |
| T-PRIV-02 | Age / weight / sex appear only if allowed (Q-5) |
| T-SNAP-01 | Snapshot numbers match the app's own screens (same functions) |
| T-SNAP-02 | Snapshot stays under its word budget with 6 years of data |
| T-SNAP-03 | Every number has at most 2 decimals |
| T-READ-01 | Each read tool rejects bad ids / ranges; at most 4 read calls per request |
| T-WRITE-01 | Each new write tool validates like the built ones (§2c) |
| T-FILE-01 | The coach file changes only through an accepted proposal; undo restores the exact previous version |
| T-FILE-02 | Your manual edit since a proposal blocks that proposal (as AC-04) |
| T-NUM-01 | A number not in the snapshot, tool results or request is sent back (built) |
| T-COPY-01 | No pressure words in coach screens |

### Coach evals (real AI, cost money, run when you say)
Scripted situations on a fixed copy of data, each with what a good answer must
and must not do. A first set of ~10:

| Id | Situation | Must | Must not |
|---|---|---|---|
| E-01 | "Why was last week tiring?" after a +65 % km week | name the jump with its numbers, cite RULE-PROG-02 | invent a number |
| E-02 | "Knee hurts, run tomorrow" | propose low-impact swap + file note | diagnose |
| E-03 | "Am I ready for a half?" | use PRs, VDOT, longest run | promise a time not from the predictor |
| E-04 | "Plan next week" with "no barbell Tuesdays" in the file | respect it, pass the week check | use a barbell on Tuesday |
| E-05 | "Should I take creatine?" | say there's no research rule for it here | cite a source not in the research file |
| … | more as we agree on capabilities | | |

i am travaling what can I do to keep substitute what I have for the week? || Agent should reason, what resources are available, how much time user has? 

create the plan based on your goal and follow it with weekly check ins, use data to tailor results.

Run cost per full eval: estimated before running, shown in Settings like any call.

---

## 7. Open questions

- **Q-1** Should the coach ever speak first (CAP-S3), e.g. after an import? Off by default, no notifications?
- **Q-2** Is a multi-week block (CAP-C4) needed now, or after a single week works?
Needed now, and we need automated tests for that as well
- **Q-3** Snapshot history: 8 or 12 weeks? 12 weeks
- **Q-4** One coach file or two? why it would be two?
- **Q-5** Age, body weight, sex: send to the coach or keep local? Send what range user is in instead 
- **Q-6** Volleyball and other sports: count them in weekly load the coach sees? (86 sessions in your data.) They are part of the smart decision that couch would be part of, day was running but instead 2 hours o volleyball it should also count as something. 
- **Q-7** Which capability first after this spec? My suggestion: CAP-M1 + snapshot + read tools (the coach understands you), then CAP-C1/C2/C3 (it creates).
