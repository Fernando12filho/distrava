"""Parameters of the research rules the app applies, in one place.

Each value cites its rule id in research/training-rules.md, with the range the
research gives, so it can be tuned without hunting through the code.
"""

# RULE-METRIC-07: flag heart-rate dropouts and implausible jumps.
# Both thresholds are expert opinion in the research.
HR_GAP_FLAG_SECONDS = 30  # range 15–60
HR_JUMP_FLAG_BPM_PER_S = 15  # range 10–20

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
