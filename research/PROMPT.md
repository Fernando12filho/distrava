# Research prompt — training rules for Distrava

Copy everything below the line into a new Claude chat (with web search / research
turned on). Fill in the "About me" block first. Save the answer as
`research/training-rules.md` in this repo.

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
