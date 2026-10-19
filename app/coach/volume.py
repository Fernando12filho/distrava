"""Editing an exercise's planned volume — pure parsing and validation.

An exercise keeps the shape it was planned with (sets × reps stays sets × reps),
so the form only offers, and the parser only reads, that shape's fields.
"""

from math import isfinite

from app import analytics

LIMITS = {
    "sets": (1, 20),
    "reps": (1, 100),
    "seconds": (1, 3600),
}
MAX_MINUTES = 600
MAX_DISTANCE_METERS = 100_000.0


def item_shape(item):
    if item.get("sets") and item.get("reps"):
        return "sets_reps"
    if item.get("sets") and item.get("duration_seconds"):
        return "sets_seconds"
    if item.get("distance_meters"):
        return "distance"
    if item.get("duration_seconds"):
        return "duration"
    return "none"


def _integer(form, field):
    raw = (form.get(field) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{field} must be a whole number") from None
    low, high = LIMITS[field]
    if not low <= value <= high:
        raise ValueError(f"{field} must be between {low} and {high}")
    return value


def _number(form, field):
    raw = (form.get(field) or "").strip().replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{field} must be a number") from None
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be more than zero")
    return value


def parse_volume(shape, form, units):
    if shape == "sets_reps":
        return {"sets": _integer(form, "sets"), "reps": _integer(form, "reps")}
    if shape == "sets_seconds":
        return {"sets": _integer(form, "sets"), "duration_seconds": _integer(form, "seconds")}
    if shape == "distance":
        meters_per_unit = analytics.METERS_PER_MILE if units == "imperial" else 1000.0
        meters = round(_number(form, "distance") * meters_per_unit, 2)
        if meters > MAX_DISTANCE_METERS:
            raise ValueError("distance is longer than any planned session")
        return {"distance_meters": meters}
    if shape == "duration":
        minutes = _number(form, "minutes")
        if minutes > MAX_MINUTES:
            raise ValueError(f"minutes must be at most {MAX_MINUTES}")
        return {"duration_seconds": round(minutes * 60)}
    raise ValueError("this exercise has no volume to edit")


def _trim(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def form_values(item, units):
    shape = item_shape(item)
    if shape == "sets_reps":
        return {"sets": str(item["sets"]), "reps": str(item["reps"])}
    if shape == "sets_seconds":
        return {"sets": str(item["sets"]), "seconds": str(item["duration_seconds"])}
    if shape == "distance":
        value, _unit = analytics.convert_distance(item["distance_meters"], units)
        return {"distance": f"{value:.1f}"}
    if shape == "duration":
        return {"minutes": _trim(item["duration_seconds"] / 60)}
    return {}
