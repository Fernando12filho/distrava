# Distrava — Evidence-Based Training Rules

Version 1 · researched October 2026 · for a recreational adult who runs and lifts (Apple Watch HR + GPS).

**How to read this file**

- Every number is a **default with a range**. Store them as config, not constants, so they can be tuned per user.
- "Evidence strength" describes the research behind the rule. "Confidence for a recreational adult" describes how well it transfers to *this* user, which is often lower because much of the literature is on athletes.
- Only sources I located and checked (title, authors, journal, DOI/URL) are cited. Where something is commonly quoted but I could not verify the primary source, the rule says so and cites nothing.
- **User profile fields in the brief were blank** (age, sex, runs/week, split, goal, experience). Rules that depend on them are marked `depends_on:`; the app should read these from the user profile rather than hard-coding.
- Distrava's architecture rule applies throughout: deterministic code evaluates these rules; the LLM only narrates the result and cites the rule id.

---

## 1. Summary table

| Rule id | One-line rule | Evidence strength | Applies to |
|---|---|---|---|
| RULE-LOAD-01 | Use session-RPE (CR-10 × minutes) as the common load unit for runs and lifts | strong (validity) / expert opinion (cut-offs) | check-in, dashboard, rebalancer |
| RULE-LOAD-02 | A run is "hard" if enough time is spent above the upper HR threshold, or sRPE ≥ 5 | weak | matcher, rebalancer |
| RULE-LOAD-03 | A lifting set is "hard" if it ends ≤ 3 reps in reserve | moderate | matcher, planner |
| RULE-LOAD-04 | Classify hardness from what was actually done, not from the plan or exercise type | moderate | matcher, rebalancer |
| RULE-REC-01 | Leave ~48 h before training the same muscle group hard again | expert opinion | planner, rebalancer |
| RULE-REC-02 | At most 2 hard runs per week, never on consecutive days | weak | planner, rebalancer |
| RULE-REC-03 | Same-day run + lift: lift first if lower-body strength is the priority; separate by ≥ 3 h when possible | moderate | planner |
| RULE-REC-04 | Don't place a hard leg session within 24 h before a hard run | expert opinion | planner, rebalancer |
| RULE-WEEK-01 | Most running is easy: ~75–80 % of runs/time easy, 1 (max 2) hard runs a week | moderate (athletes) / weak (recreational) | planner, dashboard |
| RULE-WEEK-02 | ≥ 10 hard sets per muscle per week to improve size; much less maintains | moderate | planner, dashboard |
| RULE-WEEK-03 | Per-muscle frequency is a free choice when weekly volume is equal | strong | planner, rebalancer |
| RULE-WEEK-04 | Runners should keep 2 strength sessions per week (heavy + plyometric) | moderate | planner |
| RULE-WEEK-05 | Present strength training as the best-supported injury-reduction tool | moderate | dashboard |
| RULE-PROG-01 | A skipped session is dropped or moved, never stacked on top of another | none | rebalancer |
| RULE-PROG-02 | Warn when weekly running distance rises > 20–30 % vs the recent baseline | weak–moderate | rebalancer, dashboard |
| RULE-PROG-03 | Do not use the acute:chronic workload ratio (ACWR) to predict injury | moderate | dashboard |
| RULE-PROG-04 | Breaks under ~2 weeks need no detraining warning; maintain with intensity | weak | rebalancer, dashboard |
| RULE-METRIC-01 | HR zones: use %HR-reserve (Karvonen) when resting HR is known; label as estimates | moderate | dashboard |
| RULE-METRIC-02 | HRmax: default Tanaka (208 − 0.7·age); replace with observed max when available | strong (population) | dashboard |
| RULE-METRIC-03 | TRIMP / CTL / ATL / TSB: show as personal trends, not absolute truths | weak | dashboard |
| RULE-METRIC-04 | Riegel predictions: fine up to half marathon; flag marathon as optimistic | moderate | dashboard |
| RULE-METRIC-05 | VDOT: label as an estimate, not a measured VO2max | none (peer-reviewed) | dashboard |
| RULE-METRIC-06 | Grade-adjusted pace: cost rises non-linearly with grade; don't hard-code 3.3 %/1 % | weak | dashboard |
| RULE-METRIC-07 | Trust Apple Watch HR for zones; never show calories as precise | moderate | dashboard |
| RULE-MOB-01 | Stretching: no injury-prevention claim; keep pre-run static holds < 60 s and follow with dynamic work | moderate | planner, check-in |
| RULE-MOB-02 | Foam rolling: optional warm-up tool, tiny recovery effect | moderate (small effect) | planner |
| RULE-MOB-03 | Meditation/breathing: no claim for physical recovery or running performance | weak / none | planner |
| RULE-CHECK-01 | Short subjective check-ins are valid inputs and may override device data | moderate | check-in, rebalancer |
| RULE-CHECK-02 | Pain ≥ 5/10, worsening pain, or red-flag answers → stop advice and refer | weak / expert opinion | check-in |

---

## 2. Rules

### A. What makes a session "hard"

### RULE-LOAD-01: Session-RPE as the common load unit
- Rule: After every session (run or lift), ask "How hard was the whole session?" on Foster's CR-10 scale ~30 min after finishing; load = sRPE × duration (min). Classify sessions by sRPE: easy ≤ 2, moderate 3–4, hard ≥ 5.
- Parameters: `srpe_easy_max: 2` (range 2–3) · `srpe_hard_min: 5` (range 5–6) · `srpe_delay_min: 30` (range 10–30) · `load_au = srpe * minutes`
- Applies to: check-in, dashboard, rebalancer
- Evidence strength: strong (for validity of sRPE as a load measure); expert opinion (for the easy/moderate/hard cut-offs, which come from the scale's verbal anchors: 2 = Easy, 3 = Moderate, 4 = Somewhat Hard, 5 = Hard, 7 = Very Hard)
- Population studied: Foster 2001 — small samples of young adults (cycling, basketball). Haddad 2017 review — 36 validation studies across sports, men and women, children to adults, mixed levels, mostly athletes. Resistance-training validation studies are small (≈10–20 people each).
- Sources:
  - Foster C, Florhaug JA, Franklin J, Gottschall L, Hrovatin LA, Parker S, Doleshal P, Dodge C, 2001. A new approach to monitoring exercise training. Journal of Strength and Conditioning Research 15(1):109–115. https://paulogentil.com/pdf/A%20New%20Approach%20to%20Monitoring%20Exercise%20Training.pdf
  - Haddad M, Stylianides G, Djaoui L, Dellal A, Chamari K, 2017. Session-RPE method for training load monitoring: validity, ecological usefulness, and influencing factors. Frontiers in Neuroscience 11:612. https://doi.org/10.3389/fnins.2017.00612
- Caveats: sRPE is a single number for the whole session, so a 10-min interval block inside an easy hour can rate "moderate". Correlation with HR-based load is weaker for resistance sessions (Haddad Table 2 reports r ≈ 0.25–0.52 vs TRIMP in one soccer cohort's gym sessions) because HR under-represents lifting effort — that is a reason to *prefer* sRPE for lifts, not to drop it.
- Confidence for a recreational adult: high — validated across ages and levels; only the cut-offs are convention.

### RULE-LOAD-02: Heart-rate definition of a hard run
- Rule: Mark a run "hard" if time spent above the user's upper threshold (zone 3 of a 3-zone model, i.e. above the second ventilatory/lactate threshold) reaches the minimum, OR if its sRPE is ≥ 5. If no lab thresholds exist, estimate the zone-3 boundary from HR reserve and label it an estimate.
- Parameters: `z3_min_minutes_hard: 10` (range 5–20) · `z3_boundary_pct_hrr_default: 85` (range 80–90, estimate only) · fallback `srpe_hard_min` from RULE-LOAD-01
- Applies to: matcher, rebalancer
- Evidence strength: weak (the 3-zone model is well established; the specific minutes-above-threshold cut-off and %HRR proxy are expert opinion)
- Population studied: 3-zone model built on elite and well-trained endurance athletes (Seiler & Kjerland: 11 junior cross-country skiers) and trained recreational runners (Esteve-Lanao: sub-elite runners with lab-measured thresholds).
- Sources:
  - Seiler KS, Kjerland GØ, 2006. Quantifying training intensity distribution in elite endurance athletes: is there evidence for an "optimal" distribution? Scandinavian Journal of Medicine & Science in Sports. https://doi.org/10.1111/j.1600-0838.2004.00418.x
  - Esteve-Lanao J, Foster C, Seiler S, Lucía A, 2007. Impact of training intensity distribution on performance in endurance athletes. Journal of Strength and Conditioning Research. https://doi.org/10.1519/R-19725.1
- Caveats: Seiler & Kjerland found HR-based and sRPE-based zone distributions agreed closely (≈75/8/17 % vs 76/6/18 %), which supports using sRPE as the fallback. Thresholds estimated from formulas can be off by a full zone; cardiac drift in heat (Florida) pushes HR up at constant effort.
- Confidence for a recreational adult: medium — concept is sound; numeric cut-offs are app defaults.

### RULE-LOAD-03: What counts as a hard lifting set
- Rule: A working set is "hard" if the user reports ending it with ≤ 3 reps in reserve (RIR), equivalent to set-RPE ≥ 7 on the RIR-based scale (RPE 10 = 0 RIR, 9 = 1 RIR, …). Only hard sets count toward weekly volume (RULE-WEEK-02).
- Parameters: `hard_set_max_rir: 3` (range 2–4) · `hard_set_min_rpe: 7` (range 6–8)
- Applies to: matcher, planner, dashboard
- Evidence strength: moderate
- Population studied: Zourdos/Helms 2016 — 15 experienced (≈5 yr) and 14 novice squatters, young adults. Volume meta-analyses (RULE-WEEK-02) count sets taken close to failure.
- Sources:
  - Zourdos MC, Klemp A, Dolan C, Quiles JM, … Helms E, 2016. Novel resistance training-specific rating of perceived exertion scale measuring repetitions in reserve. Journal of Strength and Conditioning Research 30(1):267–275. https://doi.org/10.1519/JSC.0000000000001049
  - Helms ER, et al., 2016. Application of the repetitions in reserve-based rating of perceived exertion scale for resistance training. Strength and Conditioning Journal 38(4):42–49. https://doi.org/10.1519/SSC.0000000000000218
- Caveats: Experienced lifters rated RPE more accurately at max loads than novices; novices tend to under-estimate how close they are to failure. The "≤ 3 RIR" boundary is the convention most hypertrophy studies approximate, not a measured threshold.
- Confidence for a recreational adult: medium — depends_on: years lifting (lower if < 1 year).

### RULE-LOAD-04: Judge "hard" from what was done
- Rule: The matcher classifies a session from logged reality (sRPE, HR zone time, set RIR). Use the planned intensity only when no actual data exist, and never infer hardness from the exercise type alone ("leg day" ≠ hard).
- Parameters: `hardness_source_priority: [actual_srpe, actual_hr_zones, actual_set_rir, planned_intensity]`
- Applies to: matcher, rebalancer
- Evidence strength: moderate
- Population studied: coach-vs-athlete studies summarised by Haddad 2017 (swimmers, judo, tennis, soccer, volleyball).
- Sources:
  - Haddad M, Stylianides G, Djaoui L, Dellal A, Chamari K, 2017. Session-RPE method for training load monitoring: validity, ecological usefulness, and influencing factors. Frontiers in Neuroscience 11:612. https://doi.org/10.3389/fnins.2017.00612
- Caveats: The review reports weak agreement between the intensity a coach planned and what athletes perceived — athletes found hard sessions harder and easy sessions easier than planned. That is exactly the gap the matcher must avoid.
- Confidence for a recreational adult: high.

### B. Recovery and spacing

### RULE-REC-01: Spacing hard sessions for the same muscle group
- Rule: Don't schedule a hard session (RULE-LOAD-03) for a muscle group within 48 h of the previous hard session for that group. Allow sooner if the earlier session was not hard or the check-in reports low soreness.
- Parameters: `min_hours_same_muscle_hard: 48` (range 48–72) · `soreness_block_threshold: 6/10` (range 5–7, expert opinion)
- Applies to: planner, rebalancer
- Evidence strength: expert opinion
- Population studied: ACSM guidance for healthy adults; frequency meta-analysis covered untrained and trained adults, upper and lower body.
- Sources:
  - American College of Sports Medicine (Ratamess NA et al.), 2009. Progression models in resistance training for healthy adults. Medicine & Science in Sports & Exercise 41(3):687–708. https://doi.org/10.1249/MSS.0b013e3181915670
  - Schoenfeld BJ, Grgic J, Krieger J, 2019. How many times per week should a muscle be trained to maximize muscle hypertrophy? A systematic review and meta-analysis of studies examining the effects of resistance training frequency. Journal of Sports Sciences 37(11):1286–1295. https://doi.org/10.1080/02640414.2018.1555906
- Caveats: The 48 h figure is widely attributed to ACSM guidance, but it is a practical recommendation, not a measured recovery time. Schoenfeld 2019 found frequency doesn't change hypertrophy when volume is equal, so spacing is about fatigue and session quality, not about growth. ACSM 2009's recommended frequencies are 2–3 d/wk (novice), 3–4 (intermediate), 4–5 (advanced) — full-body vs split changes how this maps to muscles. ACSM published an updated umbrella review (2026, DOI 10.1249/MSS.0000000000003897) replacing the 2009 stand; check it before shipping. No good evidence that the rest interval differs by muscle group.
- Confidence for a recreational adult: medium — depends_on: split (a body-part split already gives ~7 days per muscle).

### RULE-REC-02: Spacing hard runs (hard/easy)
- Rule: Schedule at most 2 hard runs per week, never on consecutive days; at least one easy day or rest day between them.
- Parameters: `max_hard_runs_per_week: 2` (range 1–2 at 3–4 runs/wk; up to 3 above 5 runs/wk) · `min_hours_between_hard_runs: 48` (range 48–72)
- Applies to: planner, rebalancer
- Evidence strength: weak
- Population studied: descriptive studies of national/international endurance athletes training 10–13 times/week.
- Sources:
  - Seiler S, 2010. What is best practice for training intensity and duration distribution in endurance athletes? International Journal of Sports Physiology and Performance 5(3):276–291. https://doi.org/10.1123/ijspp.5.3.276
  - Stöggl TL, Sperlich B, 2015. The training intensity distribution among well-trained and elite endurance athletes. Frontiers in Physiology 6:295. https://doi.org/10.3389/fphys.2015.00295
- Caveats: Stöggl & Sperlich summarise the elite literature as: about 80 % low intensity, and two high-intensity sessions per week suffice to drive adaptation. The "not back-to-back" part is tradition; I found no RCT testing it in recreational runners.
- Confidence for a recreational adult: medium — the cap is sensible and low-risk; the spacing is convention.

### RULE-REC-03: Order and gap for running + lifting on the same day
- Rule: When a run and a lift fall on the same day, separate them by ≥ 3 h if the schedule allows. If done back-to-back and lower-body strength is the priority, lift first; if running fitness is the priority, order doesn't matter for aerobic gains.
- Parameters: `min_hours_between_run_and_lift: 3` (range 3–6; 0 allowed with ordering rule) · `order_if_strength_priority: lift_then_run`
- Applies to: planner
- Evidence strength: moderate
- Population studied: Schumann 2022 — 43 studies, healthy adults of any sex/age, supervised ≥ 4 weeks, untrained and trained. Murlasits 2018 — chronic trials comparing same-session order. Wilson 2012 — 21 studies.
- Sources:
  - Schumann M, Feuerbacher JF, Sünkeler M, Freitag N, Rønnestad BR, Doma K, Lundberg TR, 2022. Compatibility of concurrent aerobic and strength training for skeletal muscle size and function: an updated systematic review and meta-analysis. Sports Medicine 52:601–612. https://doi.org/10.1007/s40279-021-01587-7
  - Murlasits Z, Kneffel Z, Thalib L, 2018. The physiological effects of concurrent strength and endurance training sequence: a systematic review and meta-analysis. Journal of Sports Sciences 36(11):1212–1219. https://doi.org/10.1080/02640414.2017.1364405
  - Wilson JM, Marin PJ, Rhea MR, Wilson SMC, Loenneke JP, Anderson JC, 2012. Concurrent training: a meta-analysis examining interference of aerobic and resistance exercises. Journal of Strength and Conditioning Research 26(8):2293–2307. https://doi.org/10.1519/JSC.0b013e31823a3e2d
- Caveats: Schumann found no interference with hypertrophy or maximal strength, but explosive-strength gains were blunted, mainly when both were done in the same session (vs ≥ 3 h apart). Murlasits found lifting first gave ~4 kg more lower-body 1RM with no effect on VO2max. Wilson's older analysis found running (not cycling) interfered with strength and size, scaling with running frequency and duration — so the effect may be larger for higher-mileage users.
- Confidence for a recreational adult: high for "interference is small"; medium for exact hours.

### RULE-REC-04: Hard legs vs hard run on consecutive days
- Rule: Don't place a hard leg session (squat/deadlift/lunge sets at ≤ 3 RIR) in the 24 h before a hard run. A hard run before a leg day is acceptable. Easy runs may follow leg day.
- Parameters: `min_hours_hard_legs_before_hard_run: 24` (range 24–48)
- Applies to: planner, rebalancer
- Evidence strength: expert opinion
- Population studied: none directly; inferred from concurrent-training reviews above.
- Sources: none directly testing this; context from Schumann 2022 and Wilson 2012 (RULE-REC-03).
- Caveats: I found no trial comparing "hard legs → hard run next day" with other orders in recreational runners. The rule protects run quality; it is not an injury rule.
- Confidence for a recreational adult: low — reasonable default, user-overridable.

### C. A sensible week (targets)

### RULE-WEEK-01: Running intensity distribution
- Rule: Target most running at easy intensity. With 3–4 runs per week, plan 1 hard run (2 at most) and make the rest clearly easy (zone 1 / sRPE ≤ 2). Track the distribution by time-in-zone and by session count.
- Parameters: `easy_share_target: 0.80` (range 0.70–0.90 of time or sessions) · `hard_runs_per_week: 1` (range 1–2 at 3–4 runs/wk) · `moderate_zone_share_max: 0.20` (range 0.10–0.35)
- Applies to: planner, dashboard
- Evidence strength: moderate for trained athletes; weak for recreational runners at 3–4 runs/week
- Population studied: Stöggl & Sperlich 2014 — 48 well-trained endurance athletes (VO2peak ≈ 63), 9 weeks. Rosenblat 2019 — 3–4 RCTs, athletes with > 2 yr training and VO2max > 50. Oliveira 2024 — 17–18 studies, mostly trained. Muñoz 2014 — 30 recreational runners, 10 weeks, 10 km.
- Sources:
  - Stöggl T, Sperlich B, 2014. Polarized training has greater impact on key endurance variables than threshold, high intensity, or high volume training. Frontiers in Physiology 5:33. https://doi.org/10.3389/fphys.2014.00033
  - Rosenblat MA, Perrotta AS, Vicenzino B, 2019. Polarized vs. threshold training intensity distribution on endurance sport performance: a systematic review and meta-analysis of randomized controlled trials. Journal of Strength and Conditioning Research 33(12):3491–3500. https://doi.org/10.1519/JSC.0000000000002618
  - Oliveira PS, Boppre G, Fonseca H, 2024. Comparison of polarized versus other types of endurance training intensity distribution on athletes' endurance performance: a systematic review with meta-analysis. Sports Medicine 54(8):2071–2095. https://doi.org/10.1007/s40279-024-02034-z
  - Muñoz I, Seiler S, Bautista J, España J, Larumbe E, Esteve-Lanao J, 2014. Does polarized training improve performance in recreational runners? International Journal of Sports Physiology and Performance 9(2):265–272. https://doi.org/10.1123/ijspp.2012-0350
  - Esteve-Lanao J, Foster C, Seiler S, Lucía A, 2007 (see RULE-LOAD-02).
- Caveats: The newest meta-analysis (Oliveira 2024) found polarized training better only for VO2peak, mainly in short (< 12 wk) interventions and highly trained athletes; time-trial and threshold outcomes were the same across distributions. In the only recreational RCT found (Muñoz), the 10 km difference (5.0 % vs 3.6 %) was **not statistically significant** overall. So: "mostly easy" is well supported; "polarized beats pyramidal" is not. At 3 runs/week, 80/20 by session count means < 1 hard run — use time share, not session count, at low frequencies.
- Confidence for a recreational adult: medium — depends_on: runs/week, goal.

### RULE-WEEK-02: Weekly strength volume per muscle
- Rule: To improve muscle size, target ≥ 10 hard sets per muscle group per week. To merely maintain (busy weeks, race block), allow as little as 1 session/week with ~1 hard set per exercise, provided load (intensity) stays the same.
- Parameters: `sets_per_muscle_improve_min: 10` (range 10–20) · `sets_per_muscle_maintain_min: 3` (range 1–4, young adults) · `maintain_requires_same_relative_load: true`
- Applies to: planner, dashboard
- Evidence strength: moderate
- Population studied: Schoenfeld 2017 — 15 studies, mostly untrained young adults (only two with lifting experience, per a co-author). Bickel 2011 — 70 adults; young 20–35 vs older 60–75, 32-week maintenance RCT. Spiering 2021 — narrative review.
- Sources:
  - Schoenfeld BJ, Ogborn D, Krieger JW, 2017. Dose-response relationship between weekly resistance training volume and increases in muscle mass: a systematic review and meta-analysis. Journal of Sports Sciences 35(11):1073–1082. https://doi.org/10.1080/02640414.2016.1210197
  - Bickel CS, Cross JM, Bamman MM, 2011. Exercise dosing to retain resistance training adaptations in young and older adults. Medicine & Science in Sports & Exercise 43(7):1177–1187. https://doi.org/10.1249/MSS.0b013e318207c15d
  - Spiering BA, Mujika I, Sharp MA, Foulis SA, 2021. Maintaining physical performance: the minimal dose of exercise needed to preserve endurance and strength over time. Journal of Strength and Conditioning Research 35(5):1449–1458. https://doi.org/10.1519/JSC.0000000000003964
- Caveats: Schoenfeld 2017 compared < 5, 5–9 and 10+ sets/week; it could not define an upper limit. In Bickel, one-ninth of the training dose kept hypertrophy in young adults but not older adults; Spiering notes older adults may need ~2 sessions/week and 2–3 sets/exercise. Strength (not size) was maintained well in both ages. The upper range (20) is a practical ceiling, not evidence of harm above it.
- Confidence for a recreational adult: medium — depends_on: age (raise maintenance floor after ~60), goal.

### RULE-WEEK-03: Sessions per muscle per week
- Rule: Don't penalise the user's split. Any weekly frequency per muscle (1–3+) is acceptable as long as weekly hard-set volume (RULE-WEEK-02) is met. When volume is high, prefer splitting it across ≥ 2 sessions for session quality.
- Parameters: `freq_per_muscle_min: 1` (range 1–3) · `max_hard_sets_per_muscle_per_session_soft_cap: 10` (range 8–12, expert opinion)
- Applies to: planner, rebalancer
- Evidence strength: strong (for the volume-equated finding)
- Population studied: 25 studies, trained and untrained, upper and lower body.
- Sources:
  - Schoenfeld BJ, Grgic J, Krieger J, 2019. How many times per week should a muscle be trained to maximize muscle hypertrophy? Journal of Sports Sciences 37(11):1286–1295. https://doi.org/10.1080/02640414.2018.1555906
- Caveats: When volume was *not* equated, higher frequency had a modest advantage — because it usually means more total sets. The per-session cap is expert opinion.
- Confidence for a recreational adult: high.

### RULE-WEEK-04: Strength training for runners
- Rule: Keep 2 strength sessions per week that include heavy lower-body work and some plyometrics; protect these when rebalancing a busy week.
- Parameters: `strength_sessions_per_week_for_runners: 2` (range 2–3) · `program_length_weeks_for_effect: 8` (range 8–12)
- Applies to: planner
- Evidence strength: moderate
- Population studied: Balsalobre-Fernández 2016 — 5 studies, 93 highly trained middle/long-distance runners. Blagrove 2018 — runners with ≥ 6 months experience, all abilities.
- Sources:
  - Balsalobre-Fernández C, Santos-Concejero J, Grivas GV, 2016. Effects of strength training on running economy in highly trained runners: a systematic review with meta-analysis of controlled trials. Journal of Strength and Conditioning Research 30(8):2361–2368. https://doi.org/10.1519/JSC.0000000000001316
  - Blagrove RC, Howatson G, Hayes PR, 2018. Effects of strength training on the physiological determinants of middle- and long-distance running performance: a systematic review. Sports Medicine 48(5):1117–1149. https://doi.org/10.1007/s40279-017-0835-7
- Caveats: Balsalobre found a large benefit to running economy (SMD −1.42) from 2–3 sessions/week over 8–12 weeks, but only in highly trained runners. Blagrove extends benefits (economy, time-trial, sprint speed) to runners of all abilities, with no effect on VO2max or body composition. A bodybuilding-style split (Chest & Triceps / Back & Biceps / …) may contain only one leg day; the planner should check that leg + plyometric work actually occurs ≥ 2×/week.
- Confidence for a recreational adult: medium–high.

### RULE-WEEK-05: Strength training and injury (dashboard messaging)
- Rule: When the app explains *why* strength work matters, it may state that strength training is the best-supported exercise intervention for reducing sports injuries; it must not promise injury prevention for any individual.
- Parameters: none (messaging rule)
- Applies to: dashboard
- Evidence strength: moderate
- Population studied: 25 RCTs, 26,610 participants, mixed sports and ages (not runner-specific).
- Sources:
  - Lauersen JB, Bertelsen DM, Andersen LB, 2014. The effectiveness of exercise interventions to prevent sports injuries: a systematic review and meta-analysis of randomised controlled trials. British Journal of Sports Medicine 48(11):871–877. https://doi.org/10.1136/bjsports-2013-092538
- Caveats: Strength training reduced injuries to under a third (RR 0.315); stretching showed no effect. Few included trials were in recreational runners, and estimates were heterogeneous.
- Confidence for a recreational adult: medium.

### D. Skipped sessions and progression

### RULE-PROG-01: Handling a skipped session
- Rule: A skipped session is **dropped** by default. It may be **moved** only if the new slot satisfies all spacing rules (RULE-REC-01/02/04) and the week's hard-session cap. Never "make it up" by doubling a later session or adding an extra hard day.
- Parameters: `skip_policy: drop` · `allow_move_if_spacing_ok: true` · `max_extra_hard_sessions_from_makeup: 0`
- Applies to: rebalancer
- Evidence strength: none
- Population studied: —
- Sources: none found. No study I located compared make-up, move, or drop strategies.
- Caveats: Indirect support only: maintenance research (Spiering 2021, RULE-WEEK-02) shows a missed session or two barely affects fitness, so dropping costs little, while spikes in load are the more plausible risk (RULE-PROG-02).
- Confidence for a recreational adult: medium — low downside; the app should tell the user this is a design choice, not a finding.

### RULE-PROG-02: Weekly running-distance increases
- Rule: Compare this week's planned/actual distance to the recent baseline. Show a caution when the increase exceeds ~20 %, and a stronger warning above ~30 % (sustained over 2 weeks). Do not enforce a strict 10 % cap.
- Parameters: `distance_increase_caution_pct: 20` (range 20–30) · `distance_increase_warn_pct: 30` (range 30–40) · `baseline_window_weeks: 2` (range 2–4)
- Applies to: rebalancer, dashboard
- Evidence strength: weak–moderate (observational cohorts; one null RCT on the 10 % rule)
- Population studied: Nielsen 2014 — 874 healthy novice runners with GPS watches. Damsted 2019 — 261 recreational runners preparing for a half marathon. Buist 2008 — 532 novice runners in an RCT (mean age ≈ 40, 57 % women), 6.7 km event.
- Sources:
  - Nielsen RO, Parner ET, Nohr EA, Sørensen H, Lind M, Rasmussen S, 2014. Excessive progression in weekly running distance and risk of running-related injuries: an association which varies according to type of injury. Journal of Orthopaedic & Sports Physical Therapy 44(10):739–747. https://doi.org/10.2519/jospt.2014.5164
  - Damsted C, Parner ET, Sørensen H, Malisoux L, Hulme A, Nielsen RO, 2019. The association between changes in weekly running distance and running-related injury: preparing for a half marathon. Journal of Orthopaedic & Sports Physical Therapy. https://doi.org/10.2519/jospt.2019.8541
  - Buist I, Bredeweg SW, van Mechelen W, Lemmink KA, Pepping GJ, Diercks RL, 2008. No effect of a graded training program on the number of running-related injuries in novice runners: a randomized controlled trial. American Journal of Sports Medicine 36(1):33–39. https://doi.org/10.1177/0363546507307505
- Caveats: Nielsen's > 30 % group had more distance-related injuries (HR 1.59) but the confidence interval crossed 1 (p = 0.07). Damsted found more injuries when weekly distance rose 20–60 % vs < 20 %. Buist found the 10 %-rule program gave the same injury rate (≈ 20 %) as a faster program. All are novice/recreational, so they transfer well — but none prove a safe threshold.
- Confidence for a recreational adult: medium.

### RULE-PROG-03: No ACWR-based injury predictions
- Rule: The dashboard may show acute (7-day) and chronic (28/42-day) load as trends, but must not compute an acute:chronic ratio "sweet spot" or tell the user their injury risk from it.
- Parameters: `show_acwr: false` · `show_acute_and_chronic_load: true`
- Applies to: dashboard
- Evidence strength: moderate (methodological critique)
- Population studied: re-analyses of published team-sport data.
- Sources:
  - Impellizzeri FM, Tenan MS, Kempton T, Novak A, Coutts AJ, 2020. Acute:chronic workload ratio: conceptual issues and fundamental pitfalls. International Journal of Sports Physiology and Performance 15(6):907–913. https://doi.org/10.1123/ijspp.2019-0864
  - Impellizzeri FM, McCall A, Ward P, Bornn L, Coutts AJ, 2020. Training load and its role in injury prevention, part 2: conceptual and methodologic pitfalls. Journal of Athletic Training 55(9):893–901. https://doi.org/10.4085/1062-6050-501-19
- Caveats: Impellizzeri et al. conclude there is no evidence supporting ACWR for training-load management or injury-risk recommendations, and that ratio statistics make it inaccurate. Supporters still exist (team sport literature), so this is contested, but the burden of proof is not met.
- Confidence for a recreational adult: high (for *not* using it).

### RULE-PROG-04: Detraining after time off
- Rule: For breaks shorter than ~2 weeks, don't show "fitness lost" messages and resume the previous plan with a slightly lower first week. For longer breaks, rebuild distance gradually (RULE-PROG-02 baseline resets). During busy periods, keep intensity and cut frequency/volume first.
- Parameters: `no_detraining_message_days: 14` (range 10–21) · `return_week_volume_factor: 0.8` (range 0.6–0.9, expert opinion) · `maintenance_runs_per_week_min: 2` (range 2–3)
- Applies to: rebalancer, dashboard
- Evidence strength: weak
- Population studied: Mujika & Padilla — review mostly of highly trained athletes; < 4 weeks = short-term. Bosquet 2013 — 103 studies on strength after training cessation. Spiering 2021 — general and military populations.
- Sources:
  - Mujika I, Padilla S, 2000. Detraining: loss of training-induced physiological and performance adaptations. Part I: short term insufficient training stimulus. Sports Medicine 30(2):79–87. https://doi.org/10.2165/00007256-200030020-00002
  - Bosquet L, Berryman N, Dupuy O, Mekary S, Arvisais D, Bherer L, Mujika I, 2013. Effect of training cessation on muscular performance: a meta-analysis. Scandinavian Journal of Medicine & Science in Sports 23(3). https://doi.org/10.1111/sms.12047
  - Spiering BA, Mujika I, Sharp MA, Foulis SA, 2021 (see RULE-WEEK-02).
- Caveats: Mujika & Padilla describe a rapid VO2max fall in highly trained athletes but more moderate changes in recently trained people, and limited strength loss in the short term. Bosquet found a dose-response with time off and larger losses in older and inactive people. Spiering reports endurance maintained up to ~15 weeks with 2 sessions/week if intensity is kept. None give a precise "day X" threshold for a recreational adult — the 14-day default is a judgement call.
- Confidence for a recreational adult: medium.

### E. Metrics the app already shows

### RULE-METRIC-01: Heart-rate zone model
- Rule: When resting HR is known (Apple Watch provides it), compute zones as % of HR reserve (Karvonen). Otherwise use %HRmax. Always label zones "estimated" unless set from a lab or field threshold test, and let the user override boundaries.
- Parameters: `zone_model_default: pct_hrr` · `zone_model_fallback: pct_hrmax` · `resting_hr_source: 7_day_median`
- Applies to: dashboard
- Evidence strength: moderate
- Population studied: Swain & Leutholtz 1997 — 63 adults, incremental cycling to max.
- Sources:
  - Swain DP, Leutholtz BC, 1997. Heart rate reserve is equivalent to %VO2 reserve, not to %VO2max. Medicine & Science in Sports & Exercise 29(3):410–414. https://pubmed.ncbi.nlm.nih.gov/9139182/
- Caveats: Swain found %HRR tracks %VO2-reserve almost exactly (slope 1.00), while %HRR overstates %VO2max, especially in less fit people. Some later studies in other populations disagree, and the relationship drifts during long steady exercise. Any formula-based zone is still an estimate of the user's real thresholds.
- Confidence for a recreational adult: medium.

### RULE-METRIC-02: Estimating maximum heart rate
- Rule: Default HRmax = 208 − 0.7 × age (Tanaka). As soon as the user records a higher HR in a hard effort (artifact-filtered), replace the estimate with the observed max. Never use 220 − age.
- Parameters: `hrmax_formula: 208 - 0.7*age` · `observed_max_override: true` · `observed_max_min_duration_s: 5` (range 5–30, artifact filter)
- Applies to: dashboard
- Evidence strength: strong (population-level)
- Population studied: meta-analysis of 351 studies (18,712 subjects) plus a lab study of 514 healthy adults; not different by sex or activity level.
- Sources:
  - Tanaka H, Monahan KD, Seals DR, 2001. Age-predicted maximal heart rate revisited. Journal of the American College of Cardiology 37(1):153–156. https://doi.org/10.1016/s0735-1097(00)01054-8
- Caveats: Good on average but large individual error; any one person can be well above or below. depends_on: age.
- Confidence for a recreational adult: medium (formula) / high (observed max).

### RULE-METRIC-03: TRIMP and the fitness–fatigue (CTL/ATL/TSB) model
- Rule: Keep Banister TRIMP and the 42-day/7-day exponentially weighted fitness/fatigue curves, but present them as *personal trend lines*. Don't compare values between people, don't treat TSB thresholds as rules, and don't drive the rebalancer from TSB alone.
- Parameters: `ctl_time_constant_days: 42` (range 28–50) · `atl_time_constant_days: 7` (range 5–10) · `trimp_k_men: 1.92` · `trimp_k_women: 1.67`
- Applies to: dashboard
- Evidence strength: weak
- Population studied: Morton 1990 — small numbers of athletes and non-athletes, running.
- Sources:
  - Morton RH, Fitz-Clarke JR, Banister EW, 1990. Modeling human performance in running. Journal of Applied Physiology 69(3):1171–1177. https://doi.org/10.1152/jappl.1990.69.3.1171
- Caveats: Morton et al. fitted fitness and fatigue parameters **individually**; the 42/7 days used by most apps are convention, not the fitted values. The sex-specific weighting constants (1.92 / 1.67) are widely used and attributed to Banister's early work; I could not access the primary source to verify them, so treat them as expert opinion. Impellizzeri 2020 (RULE-PROG-03) notes ACWR derives from this model and inherits its assumptions. TRIMP under-counts resistance training (low HR for high effort) — use sRPE load for lifts (RULE-LOAD-01).
- Confidence for a recreational adult: low.

### RULE-METRIC-04: Riegel race prediction
- Rule: Show Riegel predictions (exponent 1.06) as a range for 5 km → half marathon. For marathon predictions, show a warning that the estimate is likely too fast and add a slower adjustment or a Vickers-style model that includes weekly mileage.
- Parameters: `riegel_exponent: 1.06` · `riegel_max_target_distance_km: 21.1` · `marathon_warning: true`
- Applies to: dashboard
- Evidence strength: moderate
- Population studied: 2,303 recreational runners (internet survey, self-reported).
- Sources:
  - Vickers AJ, Vertosick EA, 2016. An empirical study of race times in recreational endurance runners. BMC Sports Science, Medicine and Rehabilitation 8:26. https://doi.org/10.1186/s13102-016-0052-y
- Caveats: Riegel was well calibrated up to the half marathon but underestimated marathon time by ≥ 10 min for half the runners. Vickers & Vertosick found typical weekly mileage plus a previous race time predicted best. Self-reported data.
- Confidence for a recreational adult: high (≤ half marathon), low (marathon).

### RULE-METRIC-05: Daniels VDOT
- Rule: Show VDOT as a "race-equivalent performance score", not as the user's VO2max. Don't use it to set physiological thresholds.
- Parameters: `label: "VDOT (estimate from race time)"`
- Applies to: dashboard
- Evidence strength: none (peer-reviewed validation not found)
- Population studied: —
- Sources: none verified. VDOT comes from Daniels & Gilbert's tables (book form); I found no peer-reviewed validation against measured VO2max in recreational runners.
- Caveats: Useful for pace equivalence between distances; not a measurement.
- Confidence for a recreational adult: low.

### RULE-METRIC-06: Grade-adjusted pace
- Rule: Don't use a fixed linear "3.3 % slower per 1 % grade". Implement the energy-cost-of-running vs gradient relationship from Minetti 2002 (cost rises steeply and non-linearly uphill; is lowest around −20 % and rises again on steeper descents), and label GAP as an estimate.
- Parameters: `gap_model: minetti_2002_polynomial` · `gap_valid_grade_range: [-0.45, 0.45]` · `cr_level_J_per_kg_m: 3.40`
- Applies to: dashboard
- Evidence strength: weak
- Population studied: 10 runners on a treadmill, grades −45 % to +45 %.
- Sources:
  - Minetti AE, Moia C, Roi GS, Susta D, Ferretti G, 2002. Energy cost of walking and running at extreme uphill and downhill slopes. Journal of Applied Physiology 93(3):1039–1046. https://doi.org/10.1152/japplphysiol.01177.2001
- Caveats: I could not verify that "~3.3 % per 1 %" comes from any primary source. Take the polynomial coefficients from the paper itself, not from secondary sites. Small trained sample, treadmill not trail; GPS altitude noise on short segments can dominate the correction — smooth elevation first.
- Confidence for a recreational adult: low–medium.

### RULE-METRIC-07: Apple Watch heart-rate data
- Rule: Use Apple Watch HR for zones, TRIMP and lifting HR summaries. Flag runs with dropouts or implausible jumps rather than silently using them. Never present watch calories as accurate.
- Parameters: `hr_gap_flag_seconds: 30` (range 15–60) · `hr_jump_flag_bpm_per_s: 15` (range 10–20, expert opinion) · `show_calories: false` (or "rough estimate" label)
- Applies to: dashboard
- Evidence strength: moderate
- Population studied: Khushhal 2017 — 21 recreationally active men, treadmill. Dooley 2017 — 62 students (58 % women). Lee 2026 — 62 healthy young men, endurance and resistance protocols vs ECG.
- Sources:
  - Khushhal A, Nichols S, Evans W, Gleadall-Siddall DO, Page R, O'Doherty AF, Carroll S, Ingle L, Abt G, 2017. Validity and reliability of the Apple Watch for measuring heart rate during exercise. Sports Medicine International Open 1(6):E206–E211. https://doi.org/10.1055/s-0043-120195
  - Dooley EE, Golaszewski NM, Bartholomew JB, 2017. Estimating accuracy at exercise intensities: a comparative study of self-monitoring heart rate and physical activity wearable devices. JMIR mHealth and uHealth 5(3):e34. https://doi.org/10.2196/mhealth.7043
  - Lee TH, Jun DU, Bae JY, Roh HT, Cho SY, 2026. Comparative validity of smartwatch-derived heart rate and energy expenditure during endurance and resistance exercise. Sensors 26(8):2526. https://doi.org/10.3390/s26082526
- Caveats: Older models (Khushhal 2017) were very accurate walking but weaker jogging/running. Newer data (Apple Watch Series 7, Lee 2026) show mean bias about −1 bpm in endurance and −0.5 bpm in resistance exercise with ±6–7 bpm limits of agreement; Apple was the only watch not different from ECG during lifting. Calories were poor in every study (resistance-exercise EE badly wrong). Lee 2026 tested only men; Dooley's sample was mixed.
- Confidence for a recreational adult: high (HR), low (calories).

### F. Mobility, stretching, meditation

### RULE-MOB-01: Stretching
- Rule: Don't tell users stretching prevents injury. Stretching is fine for range of motion. If static stretching is done before a run, keep it under 60 s per muscle and follow it with dynamic warm-up drills/easy running.
- Parameters: `pre_run_static_max_s_per_muscle: 60` (range 30–60) · `require_dynamic_after_static: true`
- Applies to: planner, check-in
- Evidence strength: moderate
- Population studied: Behm 2016 — healthy active individuals (systematic review behind the Canadian Society for Exercise Physiology position stand). Lauersen 2014 — 25 RCTs, mixed sports.
- Sources:
  - Behm DG, Blazevich AJ, Kay AD, McHugh M, 2016. Acute effects of muscle stretching on physical performance, range of motion, and injury incidence in healthy active individuals: a systematic review. Applied Physiology, Nutrition, and Metabolism 41(1):1–11. https://doi.org/10.1139/apnm-2015-0235
  - Lauersen JB, Bertelsen DM, Andersen LB, 2014 (see RULE-WEEK-05).
- Caveats: Static stretching ≥ 60 s per muscle reduced immediate performance (~4.6 %), < 60 s barely (~1.1 %), and the effect largely disappears when dynamic activity follows. Static/PNF stretching had no clear effect on injuries; Lauersen found no protective effect of stretching. No good evidence about stretching *after* running for recovery.
- Confidence for a recreational adult: high.

### RULE-MOB-02: Mobility / foam rolling
- Rule: Offer foam rolling or mobility drills as an optional part of the warm-up. Don't present them as a recovery accelerator or injury preventer.
- Parameters: `foam_roll_optional: true` · `foam_roll_duration_min: 2–5` (expert opinion)
- Applies to: planner
- Evidence strength: moderate (for "the effect is small")
- Population studied: 21 studies (14 pre-rolling, 7 post-rolling), mostly young active adults.
- Sources:
  - Wiewelhove T, Döweling A, Schneider C, Hottenrott L, Meyer T, Kellmann M, Pfeiffer M, Ferrauti A, 2019. A meta-analysis of the effects of foam rolling on performance and recovery. Frontiers in Physiology 10:376. https://doi.org/10.3389/fphys.2019.00376
- Caveats: Effects on performance and recovery were minor to negligible, with possible small benefits for sprint, flexibility and perceived soreness; the authors favour foam rolling as warm-up rather than recovery. For "mobility work" more broadly, I found no strong evidence for specific routines in runners.
- Confidence for a recreational adult: medium.

### RULE-MOB-03: Meditation and breathing
- Rule: The app may offer meditation/breathing for stress and wellbeing, but must not claim it speeds physical recovery or improves running/lifting performance.
- Parameters: `meditation_claims_allowed: [wellbeing, focus]` · `meditation_claims_blocked: [recovery, endurance_performance, strength]`
- Applies to: planner
- Evidence strength: weak (mindfulness → precision-sport performance and psychological outcomes); none (for recovery or endurance performance in recreational adults)
- Population studied: athletes > 15 years, mostly precision sports (shooting, darts).
- Sources:
  - Bühlmayer L, Birrer D, Röthlin P, Faude O, Donath L, 2017. Effects of mindfulness practice on performance-relevant parameters and performance outcomes in sports: a meta-analytical review. Sports Medicine 47(11):2309–2321. https://doi.org/10.1007/s40279-017-0752-9
- Caveats: Physiological outcomes had wide confidence limits and very large heterogeneity; performance gains were seen in shooting and dart throwing, not endurance sports. I found no solid evidence for specific breathing protocols improving recovery.
- Confidence for a recreational adult: low.

### G. Post-workout check-in

### RULE-CHECK-01: Subjective check-in questions
- Rule: After each session, ask 3–4 one-tap questions (session effort/sRPE, energy/fatigue, muscle soreness, pain yes/no). Treat sustained poor answers as a valid reason to make the next hard session easier, even if device metrics look fine.
- Parameters: `checkin_items: [srpe_0_10, energy_1_5, soreness_0_10, pain_yes_no]` · `downgrade_if_low_energy_days: 2` (range 2–3, expert opinion) · `downgrade_if_soreness_ge: 6` (range 5–7, expert opinion)
- Applies to: check-in, rebalancer
- Evidence strength: moderate
- Population studied: 56 studies of athletes reporting both subjective and objective well-being measures.
- Sources:
  - Saw AE, Main LC, Gastin PB, 2016. Monitoring the athlete training response: subjective self-reported measures trump commonly used objective measures: a systematic review. British Journal of Sports Medicine 50(5):281–291. https://doi.org/10.1136/bjsports-2015-094758
- Caveats: Subjective measures responded to acute and chronic load more sensitively and consistently than objective markers, and the two usually did not correlate. Saw et al. reviewed *established* questionnaires; very short custom items haven't been validated to the same degree. Athletes, not recreational adults.
- Confidence for a recreational adult: medium.

### RULE-CHECK-02: When to stop advising and refer
- Rule: If the user reports pain, ask for a 0–10 rating and two follow-ups. The app stops giving training advice for that body area and shows "consider seeing a physiotherapist or doctor" when any of these is true: pain ≥ 5/10 during or after activity; pain that is worse the next morning or worse week over week; pain lasting > 1–2 weeks; pain that changes how they run or lift (limping, can't bear weight). For chest pain, fainting, unusual shortness of breath, or numbness/weakness, the app says to stop exercising and seek medical care promptly. Below 5/10 and stable, the app may continue but must suggest reducing load in that area.
- Parameters: `pain_refer_threshold: 5` (range 4–5, 0–10 scale) · `pain_persist_days_refer: 10` (range 7–14, expert opinion) · `red_flags: [chest_pain, fainting, unusual_breathlessness, numbness_or_weakness, cannot_bear_weight, sudden_sharp_pain_with_swelling]`
- Applies to: check-in
- Evidence strength: weak (pain threshold) / expert opinion (red flags and durations)
- Population studied: Silbernagel 2007 — 38 patients with Achilles tendinopathy, RCT.
- Sources:
  - Silbernagel KG, Thomeé R, Eriksson BI, Karlsson J, 2007. Continued sports activity, using a pain-monitoring model, during rehabilitation in patients with Achilles tendinopathy: a randomized controlled study. American Journal of Sports Medicine 35(6):897–906. https://doi.org/10.1177/0363546506298279
- Caveats: In Silbernagel's trial, continuing running/jumping while keeping pain below 5/10 gave no worse outcome than rest. That supports the 5/10 line for tendon-type pain only; it is not a diagnostic tool, and the app must not name conditions. The red-flag list is standard clinical caution, not from a cited trial.
- Confidence for a recreational adult: medium — safe-side defaults.

---

## 3. Not supported (avoid these rules)

| Popular rule | What the evidence says | Source |
|---|---|---|
| "Never increase weekly mileage by more than 10 %" | An RCT found a 10 %-rule program gave the same injury rate as a faster one. Large jumps (> 20–30 %) are the concern, not 10 %. | Buist 2008; Nielsen 2014; Damsted 2019 |
| "Keep ACWR between 0.8 and 1.3 to avoid injury" | No evidence supports ACWR for injury-risk management; ratio artefacts. | Impellizzeri 2020 (×2) |
| "Stretch before running to prevent injury" | No clear injury effect; long static holds reduce immediate performance. | Behm 2016; Lauersen 2014 |
| "220 − age is your max HR" | Superseded; Tanaka fits better, especially for older adults. Both carry large individual error. | Tanaka 2001 |
| "Cardio kills gains" | Concurrent training doesn't blunt hypertrophy or max strength on average; only explosive strength is affected. | Schumann 2022 |
| "Train each muscle 2×/week or you won't grow" | Frequency doesn't matter when weekly volume is equal. | Schoenfeld 2019 |
| "Muscles need 72 h or they won't grow" | No growth penalty from higher frequency at equal volume; spacing is about fatigue. | Schoenfeld 2019 |
| "Make up missed workouts" | No evidence of benefit; a missed session costs little. | Spiering 2021 (indirect) |
| "Polarized 80/20 is proven best for everyone" | Polarized ≈ other distributions for time-trial and threshold outcomes; edge only for VO2peak in short programs in trained athletes. | Oliveira 2024; Muñoz 2014 |
| "Watch calories are accurate" | Errors large, worst during lifting. | Lee 2026; Dooley 2017 |
| "Foam rolling speeds recovery" | Effects minor to negligible. | Wiewelhove 2019 |
| "Riegel predicts your marathon" | Systematically too fast for most recreational runners. | Vickers & Vertosick 2016 |

---

## 4. Open questions (you have to choose)

1. **Hard-run definition when no threshold test exists.** Choose between sRPE-only, HR-zone-only, or "either" (this file uses *either*). The minutes-above-threshold cut-off (default 10) is unvalidated.
2. **Session-count vs time-share for 80/20.** At 3 runs/week, session counts can't express 80/20; this file uses time-share. Decide which the dashboard shows.
3. **Spacing for split routines.** With a once-per-week body-part split, RULE-REC-01 rarely triggers. Decide whether the planner should nudge toward ≥ 2 leg exposures/week for running benefit (RULE-WEEK-04) at the cost of the user's preferred split.
4. **Hard legs → hard run gap.** 24 h is a default with no direct evidence; you might prefer 48 h if run quality is the main goal.
5. **TRIMP sex constants and CTL/ATL time constants.** Keep the conventional 1.92/1.67 and 42/7 days, or fit personal constants once enough data exist (Morton 1990 fitted them individually)?
6. **Grade-adjusted pace model.** Minetti's polynomial is from 10 treadmill runners; Strava-style empirical models from large GPS datasets exist but I didn't find peer-reviewed versions. Pick one and label it.
7. **Return after a break.** The 14-day "no message" and 0.8 first-week factor are judgement calls.
8. **How much to trust the check-in over device data** when they disagree (RULE-CHECK-01 says check-in wins; you may want a confirmation prompt instead).
9. **Profile-dependent parameters.** Fill in age, sex, runs/week, split, goal, experience; then revisit RULE-LOAD-03 (lifting experience), RULE-WEEK-01 (runs/week, goal), RULE-WEEK-02 (age), RULE-METRIC-02/03 (age, sex).
10. **ACSM 2026 update.** ACSM's new resistance-training umbrella review (Med Sci Sports Exerc, DOI 10.1249/MSS.0000000000003897) replaces the 2009 stand. I verified it exists but didn't extract its recommendations; worth checking before locking RULE-REC-01 and RULE-WEEK-02.
