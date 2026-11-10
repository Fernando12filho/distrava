"""Check-in matcher (UC-09): pair imported activities with planned sessions.

Pure code — no tokens, no guessing. A session gets a "match" only when exactly
one activity fits it and that activity fits nothing else; any doubt (two
candidates, one activity fitting two sessions, a run logged a day off) becomes
an "ask" and the user picks. A session ticked off by hand before its import
arrived gets a "link". Nothing changes without a confirm tap.
"""

from collections import Counter

TOLERANCE = 0.25
TICKED_STATUSES = ("done", "partial")

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
    """Return {session_id: {"kind": "match" | "ask" | "link", "activity_ids": [...]}}.

    Pass the neighbouring weeks' sessions too: an activity on a Sunday belongs to
    that Sunday's session, and only the sessions given here can claim it.
    """
    claimed = {s["matched_activity_id"] for s in sessions if s.get("matched_activity_id")}
    free = [a for a in activities if a["id"] not in claimed]
    matchable = [s for s in sessions if s["kind"] in SESSION_ACTIVITY_TYPES and not s.get("matched_activity_id")]
    open_sessions = [s for s in matchable if s["status"] == "planned"]
    ticked_sessions = [s for s in matchable if s["status"] in TICKED_STATUSES]

    def on_day(session, days_off):
        return [
            a
            for a in free
            if abs((a["start_time"].date() - session["date"]).days) == days_off and _fits(session, a, tolerance)
        ]

    same_day = {s["id"]: on_day(s, 0) for s in open_sessions}
    near_day = {s["id"]: on_day(s, 1) for s in open_sessions}
    ticked_day = {s["id"]: on_day(s, 0) for s in ticked_sessions}

    claims = Counter(a["id"] for candidates in same_day.values() for a in candidates)
    # The workout behind a session you already ticked off is not a stray.
    ticked_ids = {a["id"] for candidates in ticked_day.values() for a in candidates}

    results = {}
    for session in open_sessions:
        exact = same_day[session["id"]]
        if len(exact) == 1 and claims[exact[0]["id"]] == 1:
            results[session["id"]] = {"kind": "match", "activity_ids": [exact[0]["id"]]}
        elif exact:
            results[session["id"]] = {"kind": "ask", "activity_ids": _by_start(exact)}
        else:
            # An activity that lines up with its own day's session belongs there.
            neighbours = [a for a in near_day[session["id"]] if claims[a["id"]] == 0 and a["id"] not in ticked_ids]
            if neighbours:
                results[session["id"]] = {"kind": "ask", "activity_ids": _by_start(neighbours)}

    for session in ticked_sessions:
        candidates = [a for a in ticked_day[session["id"]] if claims[a["id"]] == 0]
        if candidates:
            results[session["id"]] = {"kind": "link", "activity_ids": _by_start(candidates)}
    return results
