"""Pure view helpers for the coach board — plain dicts in, display values out."""

from datetime import date

from app import analytics
from app.coach.week import week_days, week_start_for

DOW_LABELS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
MIN_YEAR, MAX_YEAR = 2000, 2100


def _distance(meters, units):
    value, unit = analytics.convert_distance(meters, units)
    return f"{value:.1f} {unit}"


def item_volume(item, units):
    sets, reps = item.get("sets"), item.get("reps")
    duration, distance = item.get("duration_seconds"), item.get("distance_meters")
    if sets and reps:
        return f"{sets} × {reps}"
    if sets and duration:
        return f"{sets} × {duration} s"
    if distance:
        return _distance(distance, units)
    if duration:
        return analytics.format_duration(duration)
    return "—"


def session_summary(kind, items, units):
    if kind == "rest":
        return ""
    if kind == "gym":
        count = len(items)
        return f"{count} exercise" if count == 1 else f"{count} exercises"
    total_distance = sum(i.get("distance_meters") or 0 for i in items)
    if total_distance:
        return _distance(total_distance, units)
    total_seconds = sum((i.get("duration_seconds") or 0) * (i.get("sets") or 1) for i in items)
    if total_seconds:
        return analytics.format_duration(total_seconds)
    count = len(items)
    return f"{count} exercise" if count == 1 else f"{count} exercises"


def activity_label(activity, units, session_date):
    parts = [analytics.categorize_activity_type(activity["activity_type"])["label"]]
    # A lift has no distance; "0.00 km" only hides what tells two workouts apart.
    if activity["distance_meters"]:
        value, unit = analytics.convert_distance(activity["distance_meters"], units)
        parts.append(f"{value:.2f} {unit}")
    start = activity["start_time"]
    parts += [analytics.format_duration(activity["duration_seconds"]), f"{start:%H:%M}"]
    label = " · ".join(parts)
    if start.date() != session_date:
        label = f"{start:%a %d} · {label}"
    return label


def build_week_view(week_start, today, sessions):
    days = []
    for index, day in enumerate(week_days(week_start)):
        day_sessions = sorted((s for s in sessions if s["day_index"] == index), key=lambda s: s["position"])
        days.append(
            {
                "index": index,
                "date": day,
                "dow": DOW_LABELS[index],
                "num": day.day,
                "is_today": day == today,
                "is_past": day < today,
                "sessions": day_sessions,
            }
        )
    return days


def parse_week_param(raw, today):
    if raw is None:
        return week_start_for(today)
    parsed = date.fromisoformat(raw)
    # The page links to the weeks either side, which overflows at date's limits.
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        raise ValueError("week is out of range")
    return week_start_for(parsed)


def exercise_choices(catalog, categories, activity_type, exclude=()):
    """Catalog entries that may take a slot, grouped by muscle for a picker."""
    groups = {}
    fitting = [
        e for e in catalog if e["category"] in categories and e["activity_type"] == activity_type and e["slug"] not in exclude
    ]
    for entry in sorted(fitting, key=lambda e: e["name"]):
        groups.setdefault(entry["muscle_group"] or "none", []).append(entry)
    return [
        {"label": "Other" if muscle == "none" else muscle.replace("_", " ").capitalize(), "options": groups[muscle]}
        for muscle in sorted(groups)
    ]
