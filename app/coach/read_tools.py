"""The coach's read tools: they answer from what the app already knows and
never write (AC-15). Pure: the request's drafts answer through functions passed
in, and results go back as compact JSON.
"""

import json
from datetime import date

from app.coach import history, rules
from app.coach.catalog import CATEGORIES, EQUIPMENT, MUSCLE_GROUPS
from app.coach.tools import ToolError

# A bound on how much one read sends the model, not training advice.
MAX_HISTORY_WEEKS = 12

NO_EXERCISE = "No catalog exercise fits. Say so, or ask the user what else they have; don't name exercises outside the catalog."

READ_TOOLS = [
    {
        "name": "get_week",
        "description": "Read any week, past or planned: its sessions, exercises, volumes and status. "
        "For the week being planned you see your changes so far.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"week_start": {"type": "string", "description": "The Monday that starts the week, YYYY-MM-DD"}},
            "required": ["week_start"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_plan",
        "description": "Run the app's Week check on your draft: spacing clashes (new ones are yours to fix), "
        "hard runs against the suggested number, and this week's running distance against recent weeks.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "search_rules",
        "description": "Search the app's research file for training rules on a topic, e.g. \"spacing hard runs\", "
        "\"weekly distance increase\", \"sets per muscle\". Returns up to 3 rules with their id, parameters, sources "
        "and caveats, popular rules the research rejects, or \"not covered\". An empty topic lists every rule's id and title.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "A few words, or a rule id like RULE-REC-01"}},
            "required": ["topic"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_exercises",
        "description": "Find catalog exercises that fit: muscle groups, the equipment the user has on hand "
        "(bodyweight always fits), a category, or stand-ins for one exercise (like). Use it when the user is "
        "travelling, at home or missing equipment. Empty lists mean any.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "muscle_groups": {"type": "array", "items": {"type": "string", "enum": list(MUSCLE_GROUPS)}},
                "equipment": {"type": "array", "items": {"type": "string", "enum": list(EQUIPMENT)}},
                # anyOf, not a type list: the strict-schema check rejects an enum beside ["string", "null"].
                "category": {"anyOf": [{"type": "string", "enum": list(CATEGORIES)}, {"type": "null"}]},
                "like": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": "An exercise slug: find others for its muscle group and category",
                },
            },
            "required": ["muscle_groups", "equipment", "category", "like"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_history",
        "description": "What the user actually did between two dates, up to today: each week's runs, running "
        "distance and time, other workouts, load (effort × minutes, rated workouts only), hard sets per muscle and "
        f"coach sessions by status, then each workout. At most {MAX_HISTORY_WEEKS} weeks. Use it to take volumes "
        "from the user's own weeks.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "from_date": {"type": "string", "description": "First day, YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "Last day, YYYY-MM-DD, today at the latest"},
            },
            "required": ["from_date", "to_date"],
            "additionalProperties": False,
        },
    },
]

NAMES = {tool["name"] for tool in READ_TOOLS}


def monday(value):
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ToolError("week_start must be a Monday date, YYYY-MM-DD.") from None
    if day.weekday() != 0:
        raise ToolError(f"{day.isoformat()} is not a Monday; weeks start on Monday.")
    return day


def _unknown(field, given, known):
    unknown = [v for v in given if v not in known]
    if unknown:
        raise ToolError(f"Unknown {field}: {', '.join(unknown)}. Choose from: {', '.join(known)}.")


def exercises(args, catalog):
    """search_exercises: catalog entries that fit, by muscle group, then name."""
    groups, on_hand = set(args.get("muscle_groups") or []), set(args.get("equipment") or [])
    category, like = args.get("category"), args.get("like")
    _unknown("muscle group", groups, MUSCLE_GROUPS)
    _unknown("equipment", on_hand, EQUIPMENT)
    _unknown("category", [category] if category else [], CATEGORIES)
    if like is not None:
        if like not in catalog:
            raise ToolError(f"Unknown exercise {like}; use a slug from the catalog.")
        # A stand-in works what the original worked, in the same kind of session.
        groups = groups or {catalog[like]["muscle_group"]}
        category = category or catalog[like]["category"]
    if on_hand:
        # Bodyweight needs nothing, so it fits whatever the user has.
        on_hand.add("none")
    found = [
        {"slug": slug, **{k: e[k] for k in ("name", "category", "muscle_group", "equipment")}}
        for slug, e in catalog.items()
        if slug != like
        and (not groups or e["muscle_group"] in groups)
        and (not on_hand or e["equipment"] in on_hand)
        and (category is None or e["category"] == category)
    ]
    found.sort(key=lambda e: (e["muscle_group"], e["name"]))
    return {"exercises": found} if found else {"exercises": [], "note": NO_EXERCISE}


def _day(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ToolError(f"{field} must be a date, YYYY-MM-DD.") from None


def past(args, sources):
    """get_history: the range checked, then summarised from sources["history"](start, end)."""
    start, end = _day(args.get("from_date"), "from_date"), _day(args.get("to_date"), "to_date")
    if end < start:
        raise ToolError("from_date must be on or before to_date.")
    if end > sources["today"]:
        raise ToolError(f"History ends today, {sources['today'].isoformat()}; use get_week for planned weeks.")
    if (end - start).days >= 7 * MAX_HISTORY_WEEKS:
        raise ToolError(f"Ask for at most {MAX_HISTORY_WEEKS} weeks at a time.")
    rows = sources["history"](start, end)
    return history.summary(rows["activities"], rows["sessions"], rows["logged_sets"], start, end, sources["units"])


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def run(call, sources):
    """The result text for one read call; a bad argument raises ToolError.
    sources: view_week(week_start) and check() answer from the request's drafts;
    research is rules.parse() of the research file (None: not available); catalog;
    history(start, end) gives plain rows; today and units."""
    name, args = call["name"], call["input"]
    if name == "get_history":
        if sources.get("history") is None:
            raise ToolError("History can't be read here.")
        return _json(past(args, sources))
    if name == "search_exercises":
        return _json(exercises(args, sources.get("catalog") or {}))
    if name == "search_rules":
        return _json(rules.search(sources.get("research") or rules.parse(""), args.get("topic") or ""))
    if name == "check_plan":
        return _json(sources["check"]())
    if name == "get_week":
        return _json(sources["view_week"](monday(args.get("week_start"))))
    raise ToolError(f"Unknown tool {name}.")
