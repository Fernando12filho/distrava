"""The coach's read tools: they answer from what the app already knows and
never write (AC-15). Pure: the request's drafts answer through functions passed
in, and results go back as compact JSON.
"""

import json
from datetime import date

from app.coach import rules
from app.coach.catalog import CATEGORIES, EQUIPMENT, MUSCLE_GROUPS
from app.coach.tools import ToolError

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


def run(call, view_week, check, research=None, catalog=None):
    """The result text for one read call; a bad argument raises ToolError.
    view_week(week_start) and check() answer from the request's drafts;
    research is rules.parse() of the research file (None: not available)."""
    if call["name"] == "search_exercises":
        return json.dumps(exercises(call["input"], catalog or {}), ensure_ascii=False, sort_keys=True)
    if call["name"] == "search_rules":
        found = rules.search(research or rules.parse(""), call["input"].get("topic") or "")
        return json.dumps(found, ensure_ascii=False, sort_keys=True)
    if call["name"] == "check_plan":
        return json.dumps(check(), ensure_ascii=False, sort_keys=True)
    if call["name"] == "get_week":
        return json.dumps(view_week(monday(call["input"].get("week_start"))), ensure_ascii=False, sort_keys=True)
    raise ToolError(f"Unknown tool {call['name']}.")
