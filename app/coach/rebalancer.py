"""The week's spacing rules, in pure code. The coach may explain the result but
never changes it.

Sessions only have a day, not a clock time, so gaps are whole days: two
sessions a day apart are 24 h apart. "In the 24 h before a hard run" (RULE-REC-04)
therefore includes the day before, and an earlier session on the same day.

Session dicts: id, day_index (negative = the end of last week, used only for
spacing), position, kind, status, planned_effort ("easy" / "hard" / None),
srpe, z3_minutes, muscle_groups, hard_set_groups, rated_set_groups.
"""

from itertools import combinations

from app.training_rules import (
    MAX_HARD_RUNS_PER_WEEK,
    MIN_HOURS_BETWEEN_HARD_RUNS,
    MIN_HOURS_HARD_LEGS_BEFORE_HARD_RUN,
    MIN_HOURS_SAME_MUSCLE_HARD,
    SRPE_HARD_MIN,
    Z3_MIN_MINUTES_HARD,
)

DAYS_PER_WEEK = 7
# full_body trains every group, so it overlaps all of them, legs included.
FULL_BODY = "full_body"
LEG_GROUPS = {"legs", "glutes", FULL_BODY}
_NEVER_HARD_KINDS = ("rest", "mobility")
_UNKNOWN = {"hard": None, "groups": set(), "source": None}


def _planned(session, groups):
    hard = session["planned_effort"] == "hard"
    return {"hard": hard, "groups": set(groups) if hard else set(), "source": "plan"}


# RULE-LOAD-04: what was done decides; the plan only when nothing was recorded.
def effort(session):
    if session["status"] == "skipped" or session["kind"] in _NEVER_HARD_KINDS:
        return {"hard": False, "groups": set(), "source": None}

    if session["kind"] == "gym":
        if session["srpe"] is not None:
            hard = session["srpe"] >= SRPE_HARD_MIN
            groups = (session["hard_set_groups"] or session["muscle_groups"]) if hard else set()
            return {"hard": hard, "groups": set(groups), "source": "done"}
        if session["rated_set_groups"]:
            # RULE-LOAD-03: hard for exactly the groups that got hard sets.
            groups = set(session["hard_set_groups"])
            return {"hard": bool(groups), "groups": groups, "source": "done"}
        if session["planned_effort"]:
            return _planned(session, session["muscle_groups"])
        return dict(_UNKNOWN)

    # RULE-LOAD-02 + D1: either signal makes a run hard.
    signals = []
    if session["srpe"] is not None:
        signals.append(session["srpe"] >= SRPE_HARD_MIN)
    if session["z3_minutes"] is not None:
        signals.append(session["z3_minutes"] >= Z3_MIN_MINUTES_HARD)
    if signals:
        return {"hard": any(signals), "groups": set(), "source": "done"}
    if session["planned_effort"]:
        return _planned(session, ())
    return dict(_UNKNOWN)


def _overlap(a, b):
    shared = a & b
    if FULL_BODY in a:
        shared |= b
    if FULL_BODY in b:
        shared |= a
    return shared - {FULL_BODY} or shared


def _too_close(first, second, hours):
    return abs(second["day_index"] - first["day_index"]) * 24 < hours


def _legs_too_close_before(legs, run):
    gap = run["day_index"] - legs["day_index"]
    if gap == 0:
        return legs["position"] < run["position"]
    return 0 < gap and gap * 24 <= MIN_HOURS_HARD_LEGS_BEFORE_HARD_RUN


def _in_week(*sessions):
    return any(s["day_index"] >= 0 for s in sessions)


def check_week(sessions):
    rated = [(s, effort(s)) for s in sessions]
    hard_runs = sorted((s for s, e in rated if s["kind"] == "run" and e["hard"]), key=lambda s: (s["day_index"], s["position"]))
    hard_gym = [(s, e["groups"]) for s, e in rated if s["kind"] == "gym" and e["hard"]]
    conflicts = []

    # RULE-REC-02: a weekly cap, and never two hard runs too close together.
    this_week = [s for s in hard_runs if 0 <= s["day_index"] < DAYS_PER_WEEK]
    if len(this_week) > MAX_HARD_RUNS_PER_WEEK:
        conflicts.append({"rule": "RULE-REC-02", "reason": "cap", "session_ids": [s["id"] for s in this_week], "groups": []})
    for first, second in zip(hard_runs, hard_runs[1:]):
        if _in_week(first, second) and _too_close(first, second, MIN_HOURS_BETWEEN_HARD_RUNS):
            conflicts.append({"rule": "RULE-REC-02", "reason": "close", "session_ids": [first["id"], second["id"]], "groups": []})

    # RULE-REC-01: the same muscle group trained hard again too soon.
    for (first, a), (second, b) in combinations(hard_gym, 2):
        shared = _overlap(a, b)
        if shared and _in_week(first, second) and _too_close(first, second, MIN_HOURS_SAME_MUSCLE_HARD):
            ordered = sorted((first, second), key=lambda s: (s["day_index"], s["position"]))
            conflicts.append(
                {"rule": "RULE-REC-01", "reason": "close", "session_ids": [s["id"] for s in ordered], "groups": sorted(shared)}
            )

    # RULE-REC-04 + D4: hard legs shortly before a hard run.
    for legs, groups in hard_gym:
        if not groups & LEG_GROUPS:
            continue
        for run in hard_runs:
            if _in_week(legs, run) and _legs_too_close_before(legs, run):
                conflicts.append(
                    {"rule": "RULE-REC-04", "reason": "close", "session_ids": [legs["id"], run["id"]], "groups": sorted(groups & LEG_GROUPS)}
                )
    return conflicts


def _occupied(sessions, day, moving_id):
    return any(
        s["day_index"] == day and s["id"] != moving_id and s["kind"] != "rest" and s["status"] != "skipped"
        for s in sessions
    )


# RULE-PROG-01: a skipped session is dropped by default. It may move only to a
# later free day where it breaks no spacing rule — never stacked on another.
def move_options(sessions, session_id, today_index):
    moving = next(s for s in sessions if s["id"] == session_id)
    others = [s for s in sessions if s["id"] != session_id]
    options = []
    for day in range(max(today_index + 1, 0), DAYS_PER_WEEK):
        # Its own day is no move: un-skipping is the status buttons' job.
        if day == moving["day_index"] or _occupied(sessions, day, session_id):
            continue
        last = max((s["position"] for s in others if s["day_index"] == day), default=-1)
        moved = {**moving, "day_index": day, "position": last + 1, "status": "planned"}
        if not any(moved["id"] in c["session_ids"] for c in check_week(others + [moved])):
            options.append(day)
    return options
