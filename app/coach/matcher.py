"""Check-in matcher (UC-09): pair imported activities with planned sessions.

Pure code — no tokens, no guessing. A session gets a "match" only when exactly
one activity fits it and that activity fits nothing else; any doubt (two
candidates, one activity fitting two sessions, a run logged a day off) becomes
an "ask" and the user picks. Nothing is marked done without a confirm tap.
"""

from collections import Counter

TOLERANCE = 0.25

# Apple Health records a gym session as either strength type, depending on
# which the user picked on the watch.
SESSION_ACTIVITY_TYPES = {
    "run": ("Run",),
    "ride": ("Cycle",),
    "gym": ("TraditionalStrengthTraining", "FunctionalStrengthTraining"),
}


def _within(planned, actual, tolerance):
    if not actual:
        return False
    return abs(actual - planned) / planned <= tolerance


def _fits(session, activity, tolerance):
    if activity["activity_type"] not in SESSION_ACTIVITY_TYPES[session["kind"]]:
        return False
    # A gym plan lists exercises, not the length of the visit, so there is no
    # volume to compare against.
    if session["kind"] == "gym":
        return True
    if session["distance_meters"]:
        return _within(session["distance_meters"], activity["distance_meters"], tolerance)
    if session["duration_seconds"]:
        return _within(session["duration_seconds"], activity["duration_seconds"], tolerance)
    return True


def _by_start(activities):
    return [a["id"] for a in sorted(activities, key=lambda a: a["start_time"])]


def match_sessions(sessions, activities, tolerance=TOLERANCE):
    """Return {session_id: {"kind": "match" | "ask", "activity_ids": [...]}}."""
    claimed = {s["matched_activity_id"] for s in sessions if s.get("matched_activity_id")}
    free = [a for a in activities if a["id"] not in claimed]
    open_sessions = [s for s in sessions if s["status"] == "planned" and s["kind"] in SESSION_ACTIVITY_TYPES]

    same_day, near_day = {}, {}
    for session in open_sessions:
        fitting = [a for a in free if _fits(session, a, tolerance)]
        offsets = {a["id"]: (a["start_time"].date() - session["date"]).days for a in fitting}
        same_day[session["id"]] = [a for a in fitting if offsets[a["id"]] == 0]
        near_day[session["id"]] = [a for a in fitting if abs(offsets[a["id"]]) == 1]

    claims = Counter(a["id"] for candidates in same_day.values() for a in candidates)

    results = {}
    for session in open_sessions:
        exact = same_day[session["id"]]
        if len(exact) == 1 and claims[exact[0]["id"]] == 1:
            results[session["id"]] = {"kind": "match", "activity_ids": [exact[0]["id"]]}
        elif exact:
            results[session["id"]] = {"kind": "ask", "activity_ids": _by_start(exact)}
        else:
            # An activity that lines up with its own day's session belongs there.
            neighbours = [a for a in near_day[session["id"]] if claims[a["id"]] == 0]
            if neighbours:
                results[session["id"]] = {"kind": "ask", "activity_ids": _by_start(neighbours)}
    return results
