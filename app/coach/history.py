"""get_history (spec "Agent loop", step 8a): what was actually done in a range,
week by week, so the coach plans from the user's own weeks instead of defaults.
Pure: plain dicts in, every number computed here by existing code and rounded
to 2 decimals before the model sees it.
"""

from collections import Counter
from datetime import timedelta

from app import analytics
from app.coach.hard_sets import weekly_hard_sets
from app.coach.week import DAYS_PER_WEEK, week_start_for


def _round(value):
    value = round(value, 2)
    return int(value) if value == int(value) else value


def _distance_label(meters, units):
    value, unit = analytics.convert_distance(meters, units)
    return f"{_round(value)} {unit}"


def _week(week_start, activities, sessions, logged_sets, units):
    runs = [a for a in activities if a["type"] == "Run"]
    # RULE-LOAD-01: load is rating × minutes, so an unrated workout has none, and is counted as unrated.
    loads = [analytics.session_load(a["session_rpe"], a["duration_seconds"]) for a in activities]
    run_meters = sum(a["distance_meters"] or 0.0 for a in runs)
    return {
        "week_start": week_start.isoformat(),
        "runs": len(runs),
        "run_distance_meters": _round(run_meters),
        "run_distance": _distance_label(run_meters, units),
        "run_minutes": _round(sum(a["duration_seconds"] for a in runs) / 60),
        "other_workouts": len(activities) - len(runs),
        "load": _round(sum(load for load in loads if load is not None)),
        "unrated_workouts": sum(1 for load in loads if load is None),
        "hard_sets": [
            {k: g[k] for k in ("muscle_group", "hard_sets", "unrated")} for g in weekly_hard_sets(logged_sets)["groups"]
        ],
        "coach_sessions": dict(Counter(s["status"] for s in sessions)),
    }


def _workout(activity, units):
    meters = activity["distance_meters"] or 0.0
    return {
        "date": activity["date"].isoformat(),
        "type": activity["type"],
        "distance": _distance_label(meters, units) if meters else None,
        "distance_meters": _round(meters),
        "minutes": _round(activity["duration_seconds"] / 60),
        "effort": activity["session_rpe"],
        "load": analytics.session_load(activity["session_rpe"], activity["duration_seconds"]),
    }


def summary(activities, sessions, logged_sets, start, end, units):
    """activities: [{"date", "type", "distance_meters", "duration_seconds", "session_rpe"}];
    sessions: [{"date", "kind", "focus", "status"}] from the coach board;
    logged_sets: [{"date", "muscle_group", "rir", "session_id"}]. Dates are local, end included."""

    def inside(rows):
        return sorted((r for r in rows if start <= r["date"] <= end), key=lambda r: r["date"])

    activities, sessions, logged_sets = inside(activities), inside(sessions), inside(logged_sets)
    weeks, monday = [], week_start_for(start)
    # Every week, empty ones too: a break shows as weeks with nothing, not as missing weeks.
    while monday <= end:
        in_week = lambda rows, m=monday: [r for r in rows if m <= r["date"] < m + timedelta(days=DAYS_PER_WEEK)]
        weeks.append(_week(monday, in_week(activities), in_week(sessions), in_week(logged_sets), units))
        monday += timedelta(days=DAYS_PER_WEEK)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "units": units,
        "weeks": weeks,
        "workouts": [_workout(a, units) for a in activities],
    }
