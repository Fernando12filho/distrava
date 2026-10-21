"""Parameters of the research rules the app applies, in one place.

Each value cites its rule id in research/training-rules.md, with the range the
research gives, so it can be tuned without hunting through the code.
"""

# RULE-METRIC-07: flag heart-rate dropouts and implausible jumps.
# Both thresholds are expert opinion in the research.
HR_GAP_FLAG_SECONDS = 30  # range 15–60
HR_JUMP_FLAG_BPM_PER_S = 15  # range 10–20

# RULE-METRIC-03: Banister TRIMP weighting (a, b) in a * exp(b * HR-reserve
# fraction). Widely used; the research could not verify the primary source,
# so treat them as expert opinion. Unset sex keeps the male pair.
TRIMP_WEIGHTING = {"male": (0.64, 1.92), "female": (0.86, 1.67)}

# RULE-METRIC-04: Riegel (exponent 1.06) is well calibrated up to the half
# marathon for recreational runners; beyond it, predictions run too fast.
RIEGEL_RELIABLE_UP_TO_METERS = 21097.0
RIEGEL_LONG_CAUTION = "likely too fast — Riegel underestimates marathon times for most recreational runners"

# Not a research rule: a data-quality check (plan.md, pending your OK). A best
# effort can't include a "teleport": a gap of more than 15 s between distance
# samples covering more than twice the run's typical speed. Old exports log
# distance in such chunks (9.7–17.5 m/s against a run's ~1.2 m/s, giving a
# "400 m in 18 s"), while pauses in real runs cover little distance (0–0.9 m/s
# against 2.8 m/s in the 2026-09-27 10K).
EFFORT_MAX_SAMPLE_GAP_SECONDS = 15
EFFORT_GAP_SPEED_RATIO = 2.0

# RULE-METRIC-01: resting HR is the median of the watch's daily readings over
# this many days (resting_hr_source: 7_day_median).
RESTING_HR_WINDOW_DAYS = 7

# RULE-METRIC-02: an observed max HR replaces the age estimate once it is
# higher, but only if held this long, to filter out sensor artefacts.
HR_MAX_OBSERVED_MIN_SECONDS = 5  # range 5–30

# Decision D10 (plan.md): below this share of the workout covered by
# second-by-second heart rate, time-in-zones, the HR chart and per-split HR are
# hidden rather than computed from a few samples. Real data clusters above 90 %
# or below 50 %, with almost nothing between.
HR_DETAIL_MIN_COVERAGE = 0.5

# Between the two, the detail is shown with a note that heart rate has gaps.
HR_GAPS_NOTE_BELOW = 0.9

# RULE-LOAD-03: a working set is "hard" when it ends with at most this many
# reps in reserve. The research range is 2–4; 3 is the convention hypertrophy
# studies approximate. Only the user's own reps-in-reserve entry decides it
# (RULE-LOAD-04), so a set without one is neither hard nor easy.
HARD_SET_MAX_RIR = 3  # range 2–4

# RULE-LOAD-01: session effort (sRPE) on Foster's CR-10 scale, load = rating ×
# minutes. Validity is strong; the easy/moderate/hard cut-offs come from the
# scale's verbal anchors, so they are expert opinion.
SRPE_EASY_MAX = 2  # range 2–3
SRPE_HARD_MIN = 5  # range 5–6
SRPE_DELAY_MIN = 30  # range 10–30: rate about this long after finishing
SRPE_ANCHORS = {2: "Easy", 3: "Moderate", 4: "Somewhat hard", 5: "Hard", 7: "Very hard"}

# RULE-WEEK-02: hard sets per muscle group per week. 10+ is the growth band
# (Schoenfeld 2017 compared < 5, 5–9 and 10+; no upper limit found); about 3 is
# enough to maintain in young adults. Pending the ACSM 2026 check (#24).
SETS_PER_MUSCLE_IMPROVE_MIN = 10  # range 10–20
SETS_PER_MUSCLE_MAINTAIN_MIN = 3  # range 1–4
