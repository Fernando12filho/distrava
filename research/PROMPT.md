# Research prompt — training rules for Distrava

Copy everything below the line into a new Claude chat (with web search / research
turned on). Fill in the "About me" block first. Save the answer as
`research/training-rules.md` in this repo.

Topics A–G were run on 2026-10-20. Topic H (goals) was added later and has its
own follow-up prompt at the end of this file. Run only that one.

---

I'm building Distrava, a private desktop training app for a recreational runner
who also trains in the gym. The app must only give training advice that is backed
by evidence. I need you to research the rules below and write one Markdown file I
can drop into the project.

## About me (the user the rules are for)
- Age: ___ · Sex: ___
- Running: ___ runs/week, usually ___ km, mostly at ___ (time of day)
- Gym: ___ sessions/week, split like ___ (e.g. Chest & Triceps / Back & Biceps / Legs / Shoulders & Abs)
- Goal for the next months: ___
- Experience: ___ years running, ___ years lifting
- Devices: Apple Watch (heart rate, GPS)

## How to research
- Prefer, in order: systematic reviews and meta-analyses; position stands from
  professional bodies (ACSM, NSCA, IOC, etc.); randomized controlled trials;
  large observational studies. Expert opinion only when nothing else exists, and
  say so.
- **Only cite sources you actually found and checked.** Give authors, year,
  title, journal and a DOI or URL for each. If you can't verify a citation, leave
  it out. Never invent one.
- Say who was studied (elite vs recreational, novice vs trained, age, sex). Point
  out when evidence comes from athletes and may not apply to a recreational adult.
- If the evidence is weak, mixed, or missing, say exactly that. "No good evidence"
  is a useful answer.
- Turn findings into numbers where the evidence allows (hours, percentages,
  thresholds), with a range, not a single magic number.

## Questions

### A. What makes a session "hard"?
1. Session RPE (Foster et al. 2001): validity for running and for resistance
   training. What session-RPE value separates easy / moderate / hard?
2. Heart-rate-based load (TRIMP, time in zones): thresholds that define a hard run.
3. For lifting: reps in reserve (RIR) / RPE per set — what counts as a hard set?
4. Should "hard" be judged from the exercise type, from the planned effort, or
   from what was actually done? What does the evidence support?

### B. Recovery and spacing
1. Minimum time before training the same muscle group hard again (e.g. ACSM 2009
   position stand on resistance training progression). Does it differ by muscle
   group or by training age?
2. Spacing hard running sessions (hard/easy principle): evidence vs tradition.
3. Concurrent training (running + lifting): interference effect (e.g. Wilson et
   al. 2012 meta-analysis), and practical rules — order within a day, hours
   between sessions, hard leg day vs hard run on consecutive days.

### C. A sensible week (the "targets")
1. Running: weekly frequency and intensity distribution for recreational runners
   (polarized / pyramidal / threshold; Seiler and colleagues; Stöggl & Sperlich
   2014). Does 80/20 apply to someone running 3–4 times a week?
2. Strength: weekly sets per muscle group and sessions per muscle per week
   (Schoenfeld and colleagues' frequency and volume meta-analyses). Minimum dose
   to maintain vs to improve.
3. Strength training for runners: effect on running economy and injury
   (e.g. Balsalobre-Fernández 2016; Blagrove 2018).

### D. Skipped sessions and progression
1. Should a skipped session be made up, moved, or dropped? Any evidence?
2. Weekly load increases and injury: Nielsen et al. 2014 (novice runners), the
   "10 % rule" RCT (Buist et al. 2008), the acute:chronic workload ratio and its
   critique (Impellizzeri et al. 2020). What can a recreational app safely say?
3. Detraining: how many days or weeks off before fitness measurably drops
   (e.g. Mujika & Padilla)?

### E. Metrics the app already shows — are they defensible?
1. Karvonen heart-rate-reserve zones vs %HRmax vs other models.
2. Max HR estimate: 220 − age vs Tanaka 2001 (208 − 0.7 × age) vs others.
3. Banister TRIMP and the 42-day / 7-day fitness/fatigue model; sex-specific
   TRIMP constants.
4. Riegel race prediction (exponent 1.06): accuracy for recreational runners;
   alternatives (e.g. Vickers & Vertosick 2016).
5. Daniels VDOT as a VO2max estimate from race times.
6. Grade-adjusted pace: is ~3.3 % slower per 1 % uphill grade supported
   (e.g. Minetti 2002 energy cost of running on slopes)?
7. Apple Watch heart-rate accuracy during running and lifting.

### F. Mobility, stretching, meditation
1. Stretching before/after running: performance and injury evidence.
2. Mobility work: what's supported, what isn't.
3. Meditation or breathing for recovery or performance: any solid evidence?

### G. Post-workout check-in
1. Short subjective questions (energy, effort, soreness, pain): validity
   (e.g. Saw et al. 2016 on subjective vs objective monitoring).
2. Pain: which answers should make an app say "see a professional" instead of
   giving advice? (Avoid medical claims.)

## Output format (important)

Write a single Markdown file named `training-rules.md` with:

1. **Summary table:** rule id · one-line rule · evidence strength
   (strong / moderate / weak / expert opinion / none) · applies to
   (rebalancer / planner / check-in / dashboard / matcher).
2. **One section per rule**, exactly in this shape:

```
### RULE-<AREA>-<NN>: <short name>
- Rule: <plain sentence the app can follow>
- Parameters: <numbers with units and a range, e.g. min_hours_same_muscle_hard: 48 (range 48–72)>
- Applies to: <feature>
- Evidence strength: <strong | moderate | weak | expert opinion | none>
- Population studied: <who>
- Sources:
  - <Authors, Year. Title. Journal. DOI/URL>
- Caveats: <limits, when it doesn't apply>
- Confidence for a recreational adult: <high | medium | low> — <why>
```

3. **"Not supported"**: popular rules the evidence does *not* back, so the app
   avoids them.
4. **Open questions** where research couldn't decide and I have to choose.

---

## Follow-up prompt — topic H (goals the first round didn't cover)

Copy everything below the line into a new chat (with web search / research turned
on). Fill in the "About me" block first. Save the answer as
`research/training-rules-H.md`. I'll merge it into `training-rules.md` after you
check it.

---

I'm building Distrava, a private desktop training app for a recreational runner
who also trains in the gym. The app only gives training advice that is backed by
evidence. A first research round already produced rules on session hardness,
recovery, weekly volume, progression, metrics, mobility and check-ins. This round
covers goals that first round didn't.

The example goal the app has to handle: **"Run a marathon, with no hurry on the
date, and gain a little weight at the same time."**

## About me (the user the rules are for)
- Age: ___ · Sex: ___ · Height: ___ cm · Weight: ___ kg
- Running: ___ runs/week, usually ___ km; longest recent run ___ km
- Gym: ___ sessions/week
- Goal: marathon (no fixed date) + gain about ___ kg over ___ months
- Experience: ___ years running, ___ years lifting; marathons finished: ___

## How to research
Same standard as before:
- Prefer, in order: systematic reviews and meta-analyses; position stands
  (ACSM, ISSN, IOC, NSCA, etc.); randomized controlled trials; large
  observational studies. Use expert opinion only when nothing else exists, and
  say so.
- **Only cite sources you actually found and checked.** Give authors, year,
  title, journal and a DOI or URL for each. Never invent one.
- Say who was studied, and point out when evidence comes from elite athletes or
  bodybuilders rather than recreational adults.
- "No good evidence" is a useful answer. Give ranges, not magic numbers.
- **No medical or diet-prescription claims.** The app is not a dietitian. Say
  where it should stop and refer to a professional (e.g. signs of disordered
  eating, low energy availability / RED-S).

## Questions

### H. Goals: gaining weight, marathon + muscle together, body inputs
1. **Gaining weight as lean mass.** What energy surplus, and what rate of weight
   gain (% of body weight per week or month), favours muscle over fat in trained
   recreational adults? How much protein per kg per day, and does timing matter?
   Can an app give these as ranges without becoming diet advice?
2. **Marathon training and muscle gain at the same time.** Does endurance
   training reduce hypertrophy or strength gains (the interference effect), and
   does that depend on running volume, intensity, or how sessions are spaced?
   Is "build muscle and train for a marathon" realistic, or should one goal lead
   in phases? What does the evidence say about energy needs when both run
   together?
3. **A marathon build with no deadline.** For a recreational runner, how long
   should a build be, how should the weekly long run and total volume
   progress, and what peak weekly volume is reasonable? Which parts are
   evidence and which are coaching tradition?
4. **Height, weight and age as inputs.** Which rules actually need them (e.g.
   estimating energy expenditure with an equation such as Mifflin–St Jeor, and
   how accurate that is)? Which popular uses should the app avoid (e.g. BMI
   targets for athletes)?
5. **Tracking body weight.** How often to weigh in, and how to smooth daily
   noise (water, glycogen) before deciding a trend is real.
6. **ACSM 2026 resistance-training update** (Med Sci Sports Exerc, DOI
   10.1249/MSS.0000000000003897), which replaces the 2009 position stand. Do its
   recommendations change weekly sets per muscle (≥ 10 hard sets to grow), rest
   between sessions for the same muscle (48 h), or reps in reserve? List each
   change against those three numbers.

## Output format
Use exactly the same shape as the first round:

1. A summary table: rule id · one-line rule · evidence strength · applies to
   (planner / rebalancer / dashboard / check-in / profile).
2. One section per rule, ids `RULE-GOAL-<NN>` for questions 1–5 and
   `RULE-ACSM26-<NN>` for question 6:

```
### RULE-GOAL-<NN>: <short name>
- Rule: <plain sentence the app can follow>
- Parameters: <numbers with units and a range>
- Applies to: <feature>
- Evidence strength: <strong | moderate | weak | expert opinion | none>
- Population studied: <who>
- Sources:
  - <Authors, Year. Title. Journal. DOI/URL>
- Caveats: <limits, when it doesn't apply>
- Confidence for a recreational adult: <high | medium | low> — <why>
```

3. "Not supported": popular rules the evidence does not back.
4. "Refer out": answers that should make the app stop advising and suggest a
   professional.
5. Open questions where I have to choose.
