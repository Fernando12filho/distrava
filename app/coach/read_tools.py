"""The coach's read tools: they answer from what the app already knows and
never write (AC-15). Pure: the request's drafts answer through functions passed
in, and results go back as compact JSON.
"""

import json
from datetime import date

from app.coach import rules
from app.coach.tools import ToolError

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


def run(call, view_week, check, research=None):
    """The result text for one read call; a bad argument raises ToolError.
    view_week(week_start) and check() answer from the request's drafts;
    research is rules.parse() of the research file (None: not available)."""
    if call["name"] == "search_rules":
        found = rules.search(research or rules.parse(""), call["input"].get("topic") or "")
        return json.dumps(found, ensure_ascii=False, sort_keys=True)
    if call["name"] == "check_plan":
        return json.dumps(check(), ensure_ascii=False, sort_keys=True)
    if call["name"] == "get_week":
        return json.dumps(view_week(monday(call["input"].get("week_start"))), ensure_ascii=False, sort_keys=True)
    raise ToolError(f"Unknown tool {call['name']}.")
