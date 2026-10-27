"""One coach request: the model reads the week and proposes changes with tools;
code validates them, at most one retry, otherwise it says so (spec "Token
budget" §7). Pure: the provider call comes in as a function, and nothing here
touches the database — a result is only a proposal for the user to accept.
"""

import copy
import json
from datetime import timedelta

from app.coach import board, tools

MAX_ATTEMPTS = 2
# Enough to follow up on a review and its options without resending a long week of chat.
MAX_HISTORY_TURNS = 10

_OUTCOMES = {
    "accepted": "(You proposed that change and the user accepted it.)",
    "discarded": "(You proposed that change and the user discarded it.)",
    "undone": "(You proposed that change; the user accepted it, then undid it.)",
    "stale": "(You proposed that change, but the user edited the week first, so it wasn't applied.)",
}

GAVE_UP = (
    "The coach couldn't turn that into a change that fits your week. "
    "Try saying it another way, or change the board directly."
)
DECLINED = "The coach couldn't answer that one. The board is unchanged."
TOO_LONG = "The coach's answer was cut off. The board is unchanged; try a shorter request."

_INSTRUCTIONS = """You are the coach inside Distrava, a private training app for a runner who also lifts.
The user's week arrives as JSON in <week> tags, followed by their request.
Earlier messages are this week's conversation so far; when the user refers to something you offered, follow it, but the <week> in the latest message is the current state.

How you work:
- To change the week, call the tools. Each call is checked by the app and shown to the user as a preview they accept or undo; nothing changes without them.
- Only sessions with "can_change": true can change. Days are 0 = Monday … 6 = Sunday.
- Make the smallest change that does what the user asked. Don't redesign the week.
- Every tool takes a "reason": one short sentence for the user, in plain words.
- If the request needs something the tools can't do, or it's a question, answer in two or three sentences without tools.

Numbers: never calculate. Use only numbers that appear in the week JSON or in the user's request. The app shows the exact before → after values itself.

Tone: calm and neutral. A skipped session is not a failure: no streaks, no guilt, no "missed".

Exercise catalog (slug — name · category · muscle group · equipment · workout type):
"""


def _catalog_lines(catalog):
    return "\n".join(
        f"{slug} — {e['name']} · {e['category']} · {e['muscle_group']} · {e['equipment']}"
        + (f" · {e['activity_type']}" if e.get("activity_type") else "")
        for slug, e in sorted(catalog.items())
    )


# Stable across requests (prompt caching, spec "Token budget" §3): the catalog
# and instructions in the system prompt, the tool list as defined; the week
# and the request go last, in the user message.
def system_prompt(catalog):
    return [{"type": "text", "text": _INSTRUCTIONS + _catalog_lines(catalog), "cache_control": {"type": "ephemeral"}}]


def tool_definitions():
    defined = copy.deepcopy(tools.TOOLS)
    defined[-1]["cache_control"] = {"type": "ephemeral"}
    return defined


def _can_change(week, session):
    return session["status"] == "planned" and session["day_index"] >= week["today_index"] and not session["locked"]


def payload(week, context):
    week_start, units = context["week_start"], context["units"]

    def day(index):
        return f"{board.DOW_LABELS[index].title()} {(week_start + timedelta(days=index)).isoformat()}"

    sessions = []
    for s in sorted(week["sessions"], key=lambda s: (s["day_index"], s["position"])):
        items = []
        for item in s["items"]:
            entry = {"id": item["id"], "exercise": item["exercise"], "volume": board.item_volume(item, units)}
            # Standing rule: at most 2 decimals, in the payload too.
            entry.update({f: round(item[f], 2) for f in ("sets", "reps", "duration_seconds", "distance_meters") if item[f] is not None})
            items.append(entry)
        sessions.append(
            {
                "id": s["id"],
                "day": day(s["day_index"]),
                "kind": s["kind"],
                "focus": s["focus"],
                "status": s["status"],
                "planned_effort": s["planned_effort"],
                "can_change": _can_change(week, s),
                "items": items,
            }
        )
    return {
        "today": context["today"].isoformat(),
        "week_start": week_start.isoformat(),
        "units": units,
        "profile": context["profile"],
        "week_check": context["week_check"],
        "sessions": sessions,
    }


def _clash_text(clash):
    groups = f" ({', '.join(clash['groups'])})" if clash["groups"] else ""
    return f"{clash['rule']}: sessions {', '.join(str(i) for i in clash['session_ids'])}{groups}"


def _check(result, week, catalog, rebalancer_sessions, allowed, units):
    """(after, changes, problems by tool-call index, other problems)."""
    calls = result["tool_calls"]
    after, errors = tools.apply_all(week, calls, catalog)
    problems = {i: e for i, e in enumerate(errors) if e}
    other = []
    if calls and not problems:
        clashes = tools.new_conflicts(rebalancer_sessions, after, catalog)
        if clashes:
            other.append(
                "These changes break the week's spacing rules, so they can't be offered: "
                + "; ".join(_clash_text(c) for c in clashes)
                + ". Choose different days or efforts, or explain why it can't be done."
            )
    changes = tools.change_lines(week, after, catalog, units) if not problems else []
    words = result["text"] + " " + " ".join(c["input"].get("reason") or "" for c in calls)
    strays = tools.stray_numbers(words, allowed + "\n" + "\n".join(changes))
    if strays:
        other.append(
            f"Your words used numbers that aren't in the week or the request: {', '.join(dict.fromkeys(strays))}. "
            "Don't calculate; use only numbers you were given. The app shows exact values itself."
        )
    return after, changes, problems, other


def _feedback(result, problems, other):
    blocks = [
        {"type": "tool_result", "tool_use_id": call["id"], "content": problems[i], "is_error": True}
        if i in problems
        else {"type": "tool_result", "tool_use_id": call["id"], "content": "OK"}
        for i, call in enumerate(result["tool_calls"])
    ]
    if other:
        blocks.append({"type": "text", "text": " ".join(other)})
    return blocks


def _reply(result):
    reasons = [c["input"].get("reason", "").strip() for c in result["tool_calls"]]
    return " ".join(dict.fromkeys(r for r in reasons if r)) or result["text"].strip()


def _conversation(history):
    """Earlier turns as plain text, oldest first, so the coach can refer back
    to what it offered. Failed turns were app errors, not the coach speaking."""
    turns = [t for t in history if t["status"] != "failed"][-MAX_HISTORY_TURNS:]
    messages, outcome = [], None
    for turn in turns:
        messages.append({"role": "user", "content": (f"{outcome}\n\n" if outcome else "") + turn["request"]})
        messages.append({"role": "assistant", "content": turn["reply"] or ""})
        outcome = _OUTCOMES.get(turn["status"])
    return messages, outcome


def propose(complete, week, catalog, rebalancer_sessions, request, context, history=()):
    data = payload(week, context)
    week_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
    earlier, outcome = _conversation(history)
    # Only the latest message carries the week: earlier weeks are out of date.
    latest = f"<week>{week_json}</week>\n\n{request}"
    messages = earlier + [{"role": "user", "content": f"{outcome}\n\n{latest}" if outcome else latest}]
    # Numbers already said in this conversation were checked when they were said.
    allowed = "\n".join([week_json, request, *(m["content"] for m in earlier)])
    system, defined = system_prompt(catalog), tool_definitions()

    for attempt in range(MAX_ATTEMPTS):
        result = complete(system, messages, defined)
        if result["stop_reason"] == "refusal":
            return _failed(DECLINED)
        if result["stop_reason"] == "max_tokens":
            return _failed(TOO_LONG)
        after, changes, problems, other = _check(result, week, catalog, rebalancer_sessions, allowed, context["units"])
        if not problems and not other:
            if result["tool_calls"] and changes:
                calls = [{"name": c["name"], "input": c["input"]} for c in result["tool_calls"]]
                return {"status": "pending", "reply": _reply(result), "calls": calls, "after": after, "changes": changes}
            return {"status": "answer", "reply": result["text"].strip(), "calls": [], "after": None, "changes": []}
        messages = messages + [
            {"role": "assistant", "content": result["content"]},
            {"role": "user", "content": _feedback(result, problems, other)},
        ]
    return _failed(GAVE_UP)


def _failed(message):
    return {"status": "failed", "reply": message, "calls": [], "after": None, "changes": []}
