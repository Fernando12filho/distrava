"""The coach's write tools, in pure code: plain week dicts in, a new week out.

The model only names a tool and its arguments. Everything that decides whether
a change is allowed, and what the week looks like after it, lives here — so a
bad call is rejected with a reason the model can correct, and nothing reaches
the database until the user accepts the preview.

Week dict: today_index (first day that may change; 7 for a past week) and
sessions, each with id, day_index, position, kind, focus, status,
planned_effort, locked (logged sets, a matched import or a check-in) and items
(id, position, exercise slug, sets, reps, duration_seconds, distance_meters).
"""

import copy
import re

from app.coach import board, rebalancer, volume

# Mirrors app.models.PLANNED_EFFORTS; kept here so this module stays free of SQLAlchemy.
PLANNED_EFFORTS = ("easy", "hard")

_DAY = {"type": "integer", "description": "0 = Monday … 6 = Sunday"}
_NULLABLE_INT = {"type": ["integer", "null"]}


# Every call carries its own one-line reason for the user, so the explanation
# arrives with the change instead of needing a second round trip.
_REASON = {"type": "string", "description": "One short sentence for the user, without numbers you calculated."}


def _tool(name, description, properties):
    properties = {**properties, "reason": _REASON}
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOLS = [
    _tool(
        "move_session",
        "Move a planned session to another day of this week, today or later. It goes last on that day.",
        {"session_id": {"type": "integer"}, "day": _DAY},
    ),
    _tool(
        "remove_session",
        "Take a planned session off the week (for rest). Nothing is made up elsewhere.",
        {"session_id": {"type": "integer"}},
    ),
    _tool(
        "swap_exercise",
        "Replace one exercise in a planned session with another catalog exercise of the same category; "
        "runs swap only to runs and rides to rides. Its volume stays.",
        {"item_id": {"type": "integer"}, "exercise": {"type": "string", "description": "catalog slug"}},
    ),
    _tool(
        "adjust_item",
        "Change one exercise's planned volume. Give only the fields its current volume uses "
        "(sets+reps, sets+duration_seconds, distance_meters, or duration_seconds); the rest null. "
        "Use only numbers the user gave or that appear in the week.",
        {
            "item_id": {"type": "integer"},
            "sets": _NULLABLE_INT,
            "reps": _NULLABLE_INT,
            "duration_seconds": _NULLABLE_INT,
            "distance_meters": {"type": ["number", "null"]},
        },
    ),
    _tool(
        "set_planned_effort",
        "Plan a session as easy or hard, or clear it with null. Only used until the session is done.",
        # anyOf, not a type list: the strict-schema check rejects an enum beside ["string", "null"].
        {"session_id": {"type": "integer"}, "effort": {"anyOf": [{"type": "string", "enum": list(PLANNED_EFFORTS)}, {"type": "null"}]}},
    ),
]


class ToolError(ValueError):
    pass


def _day_name(day_index):
    return board.DOW_LABELS[day_index].title()


def _session(week, session_id):
    for session in week["sessions"]:
        if session["id"] == session_id:
            return session
    raise ToolError(f"No session {session_id} this week.")


def _item(week, item_id):
    for session in week["sessions"]:
        for item in session["items"]:
            if item["id"] == item_id:
                return session, item
    raise ToolError(f"No exercise {item_id} this week.")


# History stays as it was: past days, finished sessions and anything with
# logged work are the user's record, not the coach's to rearrange.
def _editable(week, session):
    label = f"{_day_name(session['day_index'])}'s {session['focus']}"
    if session["status"] != "planned":
        raise ToolError(f"{label} is {session['status']}; only planned sessions can change.")
    if session["day_index"] < week["today_index"]:
        raise ToolError(f"{label} is already past.")
    if session["locked"]:
        raise ToolError(f"{label} has logged work; it can't change.")


def _move(week, args, _catalog):
    session = _session(week, args["session_id"])
    day = args["day"]
    if not isinstance(day, int) or not 0 <= day <= 6:
        raise ToolError("day must be 0–6 (Monday–Sunday).")
    _editable(week, session)
    if day < week["today_index"]:
        raise ToolError(f"{_day_name(day)} is already past.")
    if day == session["day_index"]:
        raise ToolError(f"{session['focus']} is already on {_day_name(day)}.")
    last = max((s["position"] for s in week["sessions"] if s["day_index"] == day), default=-1)
    session["day_index"] = day
    session["position"] = last + 1


def _remove(week, args, _catalog):
    session = _session(week, args["session_id"])
    _editable(week, session)
    week["sessions"].remove(session)


def _swap(week, args, catalog):
    session, item = _item(week, args["item_id"])
    _editable(week, session)
    new = catalog.get(args["exercise"])
    if new is None:
        raise ToolError(f"{args['exercise']} is not in the catalog.")
    if item["exercise"] == args["exercise"]:
        raise ToolError(f"Exercise {item['id']} is already {new['name']}.")
    old = catalog.get(item["exercise"]) or {"category": None, "activity_type": None}
    if new["category"] != old["category"]:
        raise ToolError(f"Exercise {item['id']} needs a {old['category']} exercise; {new['name']} is {new['category']}.")
    # The import matcher pairs a session with a workout by type.
    if old["activity_type"] != new["activity_type"]:
        raise ToolError(f"Exercise {item['id']} is a {old['activity_type']}; {new['name']} is a {new['activity_type']}.")
    item["exercise"] = args["exercise"]


_SHAPE_FIELDS = {
    "sets_reps": ("sets", "reps"),
    "sets_seconds": ("sets", "duration_seconds"),
    "distance": ("distance_meters",),
    "duration": ("duration_seconds",),
}
_FIELD_WORDS = {"sets": "sets", "reps": "reps", "duration_seconds": "duration", "distance_meters": "distance"}
_VOLUME_FIELDS = ("sets", "reps", "duration_seconds", "distance_meters")


def _limits(shape):
    """(low, high, what, unit) per field — the same limits as editing by hand."""
    if shape == "sets_seconds":
        seconds = (*volume.LIMITS["seconds"], "seconds", "")
    else:
        seconds = (1, volume.MAX_MINUTES * 60, "duration", " seconds")
    return {
        "sets": (*volume.LIMITS["sets"], "sets", ""),
        "reps": (*volume.LIMITS["reps"], "reps", ""),
        "duration_seconds": seconds,
        "distance_meters": (1, volume.MAX_DISTANCE_METERS, "distance", " meters"),
    }


def _adjust(week, args, _catalog):
    session, item = _item(week, args["item_id"])
    _editable(week, session)
    shape = volume.item_shape(item)
    fields = _SHAPE_FIELDS.get(shape)
    if fields is None:
        raise ToolError(f"Exercise {item['id']} has no volume to adjust.")
    words = " and ".join(_FIELD_WORDS[f] for f in fields)
    if any(args[f] is None for f in fields):
        raise ToolError(f"Exercise {item['id']} needs {words}.")
    if any(args[f] is not None for f in _VOLUME_FIELDS if f not in fields):
        raise ToolError(f"Exercise {item['id']} only takes {words}.")
    limits = _limits(shape)
    for field in fields:
        low, high, what, unit = limits[field]
        if not low <= args[field] <= high:
            raise ToolError(f"{what} must be {low:g}–{high:g}{unit}.")
    if all(args[f] == item[f] for f in fields):
        raise ToolError(f"Exercise {item['id']} already has that volume.")
    for field in fields:
        item[field] = args[field]


def _effort(week, args, _catalog):
    session = _session(week, args["session_id"])
    if args["effort"] is not None and args["effort"] not in PLANNED_EFFORTS:
        raise ToolError("effort must be easy, hard or null.")
    _editable(week, session)
    session["planned_effort"] = args["effort"]


_APPLY = {
    "move_session": _move,
    "remove_session": _remove,
    "swap_exercise": _swap,
    "adjust_item": _adjust,
    "set_planned_effort": _effort,
}


def apply(week, call, catalog):
    handler = _APPLY.get(call["name"])
    if handler is None:
        raise ToolError(f"Unknown tool {call['name']}.")
    after = copy.deepcopy(week)
    try:
        handler(after, call["input"], catalog)
    except (KeyError, TypeError) as err:
        raise ToolError(f"Bad arguments for {call['name']}: {err}.") from None
    return after


def apply_all(week, calls, catalog):
    """Applies each call in turn; a rejected call leaves the week as it was."""
    errors = []
    for call in calls:
        try:
            week = apply(week, call, catalog)
            errors.append(None)
        except ToolError as err:
            errors.append(str(err))
    return week, errors


def touched(before, after):
    """{id: session} before and after for every session that differs (None = absent)."""
    old = {s["id"]: s for s in before["sessions"]}
    new = {s["id"]: s for s in after["sessions"]}
    ids = [i for i in list(old) + [i for i in new if i not in old] if old.get(i) != new.get(i)]
    return {i: old.get(i) for i in ids}, {i: new.get(i) for i in ids}


def _exercise_name(catalog, slug):
    return catalog[slug]["name"] if slug in catalog else "Exercise"


def change_lines(before, after, catalog, units):
    old_sessions, new_sessions = touched(before, after)
    lines = []
    for session_id, old in old_sessions.items():
        new = new_sessions[session_id]
        if old is None:
            continue  # tools never add sessions
        if new is None:
            lines.append(f"{old['focus']} on {_day_name(old['day_index'])}: removed")
            continue
        if new["day_index"] != old["day_index"]:
            lines.append(f"{old['focus']}: {_day_name(old['day_index'])} → {_day_name(new['day_index'])}")
        for was, now in zip(old["items"], new["items"]):
            if now["exercise"] != was["exercise"]:
                lines.append(f"{old['focus']} · {_exercise_name(catalog, was['exercise'])} → {_exercise_name(catalog, now['exercise'])}")
            if any(now[f] != was[f] for f in _VOLUME_FIELDS):
                name = _exercise_name(catalog, now["exercise"])
                lines.append(f"{old['focus']} · {name}: {board.item_volume(was, units)} → {board.item_volume(now, units)}")
        if new["planned_effort"] != old["planned_effort"]:
            lines.append(f"{old['focus']}: " + (f"planned {new['planned_effort']}" if new["planned_effort"] else "no planned effort"))
    return lines


def _conflict_key(conflict):
    return (conflict["rule"], conflict["reason"], frozenset(conflict["session_ids"]))


def rebuild(rebalancer_sessions, after, catalog):
    """The rebalancer's view of a draft: moved days, new efforts and muscle groups."""
    planned = {s["id"]: s for s in after["sessions"]}
    in_week = {s["id"] for s in rebalancer_sessions if s["day_index"] >= 0}
    rebuilt = []
    for session in rebalancer_sessions:
        if session["id"] not in in_week:
            rebuilt.append(session)  # last week's tail, untouched
            continue
        new = planned.get(session["id"])
        if new is None:
            continue
        groups = {catalog[i["exercise"]]["muscle_group"] for i in new["items"] if i["exercise"] in catalog} - {None, "none"}
        rebuilt.append(
            {
                **session,
                "day_index": new["day_index"],
                "position": new["position"],
                "planned_effort": new["planned_effort"],
                "muscle_groups": groups or session["muscle_groups"],
            }
        )
    return rebuilt


def is_new_conflict(rebalancer_sessions):
    existing = {_conflict_key(c) for c in rebalancer.check_week(rebalancer_sessions)}
    return lambda conflict: _conflict_key(conflict) not in existing


# AC-05: a proposal may not add a spacing clash. Clashes already in the week are
# the user's to see on the Week check, not a reason to block every change.
def new_conflicts(rebalancer_sessions, after, catalog):
    is_new = is_new_conflict(rebalancer_sessions)
    return [c for c in rebalancer.check_week(rebuild(rebalancer_sessions, after, catalog)) if is_new(c)]


_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _numbers(text):
    return {round(float(n), 2) for n in _NUMBER.findall(text)}


# "The LLM never computes": any number in the coach's words must already be in
# what it was given or in the code-written change lines.
def stray_numbers(text, allowed_text):
    allowed = _numbers(allowed_text)
    return [n for n in _NUMBER.findall(text) if round(float(n), 2) not in allowed]
