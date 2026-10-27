"""The coach's read tools: they answer from what the app already knows and
never write (AC-15). Pure: anything that needs the database comes in as a
reader function from the route, and results go back as compact JSON.
"""

import json
from datetime import date

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
]

NAMES = {tool["name"] for tool in READ_TOOLS}


def _monday(value):
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ToolError("week_start must be a Monday date, YYYY-MM-DD.") from None
    if day.weekday() != 0:
        raise ToolError(f"{day.isoformat()} is not a Monday; weeks start on Monday.")
    return day


def run(call, readers, week_start, draft_view):
    """The result text for one read call; a bad argument raises ToolError."""
    if call["name"] == "get_week":
        wanted = _monday(call["input"].get("week_start"))
        if wanted == week_start:
            data = draft_view()
        elif "get_week" in readers:
            data = readers["get_week"](wanted)
        else:
            raise ToolError("Other weeks can't be read here.")
        return json.dumps(data, ensure_ascii=False, sort_keys=True)
    raise ToolError(f"Unknown tool {call['name']}.")
