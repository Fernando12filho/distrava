"""What was actually lifted — pure parsing, defaults and the hard-set rule.

A logged gym session starts as a copy of its plan (one row per planned set)
and the user corrects whatever went differently. Nothing here estimates
effort: a set is hard only when the user says how many reps were left.
"""

from math import isfinite

from app import analytics
from app.coach.volume import item_shape
from app.training_rules import HARD_SET_MAX_RIR

LIMITS = {
    "reps": (0, 100),
    "seconds": (1, 3600),
    "rir": (0, 10),
}
MAX_WEIGHT = 1000.0


def planned_sets(item):
    shape = item_shape(item)
    if shape not in ("sets_reps", "sets_seconds"):
        return []
    reps = item["reps"] if shape == "sets_reps" else None
    seconds = item["duration_seconds"] if shape == "sets_seconds" else None
    return [{"set_number": n, "reps": reps, "duration_seconds": seconds} for n in range(1, item["sets"] + 1)]


def _raw(form, field):
    return (form.get(field) or "").strip()


def _integer(form, field):
    raw = _raw(form, field)
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{field} must be a whole number") from None
    low, high = LIMITS[field]
    if not low <= value <= high:
        raise ValueError(f"{field} must be between {low} and {high}")
    return value


def _weight_kg(form, units):
    raw = _raw(form, "weight").replace(",", ".")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ValueError("weight must be a number") from None
    if not isfinite(value) or not 0 < value <= MAX_WEIGHT:
        raise ValueError(f"weight must be more than zero and at most {MAX_WEIGHT:g}")
    return round(analytics.weight_to_kg(value, units), 2)


def parse_set(kind, form, units):
    """kind is "reps" or "seconds": a set keeps the shape it was planned with."""
    parsed = {"reps": _integer(form, "reps")} if kind == "reps" else {"duration_seconds": _integer(form, "seconds")}
    parsed["weight_kg"] = _weight_kg(form, units)
    parsed["rir"] = _integer(form, "rir")
    return parsed


# RULE-LOAD-03, RULE-LOAD-04
def is_hard(rir):
    if rir is None:
        return None
    return rir <= HARD_SET_MAX_RIR


def weight_value(kg, units):
    if kg is None:
        return ""
    value, _unit = analytics.convert_weight(kg, units)
    return f"{value:.2f}".rstrip("0").rstrip(".")
