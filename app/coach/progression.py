"""How the week compares with the weeks before it — pure code, no advice text.

Distance jumps (RULE-PROG-02), easing back in after a break (RULE-PROG-04 with
decision D7: you choose, the app only offers), and the easy/hard balance of the
week's runs (RULE-WEEK-01).
"""

from math import floor

from app.training_rules import (
    DISTANCE_INCREASE_BIG_PCT,
    DISTANCE_INCREASE_NOTE_PCT,
    EASY_SHARE_TARGET,
    HARD_RUNS_PER_WEEK,
    RETURN_BREAK_MIN_DAYS,
    RETURN_WEEK_FACTORS,
)


# RULE-PROG-02
def distance_change(this_week_meters, previous_weeks_meters):
    if not previous_weeks_meters:
        return None
    baseline = sum(previous_weeks_meters) / len(previous_weeks_meters)
    if baseline <= 0:
        return None
    pct = round((this_week_meters - baseline) / baseline * 100, 2)
    if pct > DISTANCE_INCREASE_BIG_PCT:
        level = "big"
    elif pct > DISTANCE_INCREASE_NOTE_PCT:
        level = "jump"
    else:
        level = None
    return {"this_week_meters": this_week_meters, "baseline_meters": round(baseline, 2), "pct": pct, "level": level}


def break_days(last_workout_date, today):
    if last_workout_date is None:
        return None
    return (today - last_workout_date).days


# RULE-PROG-04 + D7
def return_options(days_off):
    if days_off is None or days_off < RETURN_BREAK_MIN_DAYS:
        return []
    return [{"factor": f, "percent": round(f * 100)} for f in RETURN_WEEK_FACTORS]


def scale_item(item, factor):
    """The planned volume to change on one item; reps and weights stay as they are."""
    if item["sets"]:
        return {"sets": max(1, floor(item["sets"] * factor))}
    if item["distance_meters"]:
        return {"distance_meters": round(item["distance_meters"] * factor, 2)}
    if item["duration_seconds"]:
        return {"duration_seconds": round(item["duration_seconds"] * factor)}
    return {}


# RULE-WEEK-01: hard_flags holds True / False / None (unknown) per run.
def run_balance(hard_flags):
    known = [flag for flag in hard_flags if flag is not None]
    if not known:
        return None
    hard = sum(known)
    # round() first: 5 × 0.2 is 1.0000000000000002 in floating point.
    suggested = max(HARD_RUNS_PER_WEEK, floor(round(len(known) * (1 - EASY_SHARE_TARGET), 6)))
    return {"runs": len(known), "hard": hard, "suggested_hard": suggested, "note": hard > suggested}
