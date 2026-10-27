"""One coach request, worked in steps (spec "Agent loop", step 8a): each round
the model reads with read tools or changes a draft with write tools; code runs
and checks every call, and the request ends when the model replies without a
tool, gives up after two bad rounds, or reaches its step or cost cap.

Pure: the provider call and the readers come in as functions, and nothing here
touches the database — a result is only a proposal for the user to accept.
"""

import copy
import json
import re
from datetime import date, timedelta

from app.coach import board, llm_config, progression, read_tools, rebalancer, tools
from app.coach.usage import call_cost

# A bad round is a rejected write or a finish that fails the final check: the
# old "at most one retry" (spec "Token budget" §7), now counted per request.
MAX_BAD_ROUNDS = 2
# Enough to follow up on a review and its options without resending a long week of chat.
MAX_HISTORY_TURNS = 10
# How far ahead one request may plan: a bound on the draft, not training advice.
MAX_WEEKS_AHEAD = 4

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
STOPPED = "The coach reached its limit for one request before finishing. The board is unchanged; try a smaller request."
STOPPED_WITH_DRAFT = "(The coach reached its limit for one request; this is what it had.)"

_INSTRUCTIONS = f"""You are the coach inside Distrava, a private training app for a runner who also lifts.
The user's week arrives as JSON in <week> tags, followed by their request.
Earlier messages are this week's conversation so far; when the user refers to something you offered, follow it, but the <week> in the latest message is the current state.

How you work:
- Work in steps. Read tools (like get_week) answer from the app; write tools change a draft of this week. Each write is checked by the app, and your draft builds up across steps.
- Before you finish a change, call check_plan and fix every clash marked "new"; clashes already on the board are the user's to decide.
- When you're done, reply without calling a tool: one or two plain sentences for the user. The user then sees the whole draft as one preview they accept or undo; nothing changes without them.
- Only sessions with "can_change": true can change. Days are 0 = Monday … 6 = Sunday.
- Make the smallest change that does what the user asked. Don't redesign the week unless they ask you to plan it.
- To plan or fill a week, add sessions with add_session. Take volumes from the user's past weeks (read them with get_week) or from their request; if neither has them, ask the user instead of choosing numbers.
- You can plan up to {MAX_WEEKS_AHEAD} weeks ahead: read each week with get_week first, then add to it with add_session and its week_start. The user accepts or undoes the whole draft at once.
- Every tool takes a "reason": one short sentence for the user, in plain words.
- If the request needs something the tools can't do, or it's a question, answer in two or three sentences without tools.

Numbers: never calculate. Use only numbers that appear in the week JSON, in tool results or in the user's request. The app shows the exact before → after values itself.

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
    defined = copy.deepcopy(read_tools.READ_TOOLS + tools.TOOLS)
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


def _label(session):
    day = board.DOW_LABELS[session["day_index"]].title() if 0 <= session["day_index"] < len(board.DOW_LABELS) else "Last week"
    return f"{day} {session['focus']} (session {session['id']})"


def plan_check(draft, catalog, rebalancer_sessions, context):
    """check_plan (AC-16): the Week check's three parts, computed on the draft."""
    rebuilt = tools.rebuild(rebalancer_sessions, draft, catalog)
    by_id, is_new = {s["id"]: s for s in rebuilt}, tools.is_new_conflict(rebalancer_sessions)
    clashes = [
        {"rule": c["rule"], "reason": c["reason"], "sessions": [_label(by_id[i]) for i in c["session_ids"]], "groups": c["groups"], "new": is_new(c)}
        for c in rebalancer.check_week(rebuilt)
    ]
    # RULE-WEEK-01, by session count, as on the Week check.
    hard_runs = progression.run_balance(
        [rebalancer.effort(s)["hard"] for s in rebuilt if s["kind"] == "run" and s["day_index"] >= 0 and s["status"] != "skipped"]
    )
    # RULE-PROG-02: imported so far plus the draft's runs still to come.
    distance = None
    if context.get("distance"):
        ahead = sum(
            item["distance_meters"] or 0.0
            for s in draft["sessions"]
            if s["kind"] == "run" and s["status"] == "planned" and s["day_index"] >= draft["today_index"]
            for item in s["items"]
        )
        # Standing rule: at most 2 decimals, in what the coach sees too.
        this_week = round(context["distance"]["so_far_meters"] + ahead, 2)
        distance = progression.distance_change(this_week, [round(m, 2) for m in context["distance"]["previous_weeks_meters"]])
    return {"clashes": clashes, "hard_runs": hard_runs, "distance": distance}


STRAYS = "Your words used numbers that aren't in the week, a tool result or the request: {}. Don't calculate; use only numbers you were given. The app shows exact values itself."


def _strays(text, allowed):
    found = tools.stray_numbers(text, allowed)
    return STRAYS.format(", ".join(dict.fromkeys(found))) if found else None


def _new_volumes(call, allowed):
    """add_session's volumes, held to "never computes": a plan's numbers come from the
    user's own weeks or words, never from the model (default volumes are [A])."""
    if call["name"] != "add_session":
        return
    numbers = " ".join(str(item[f]) for item in call["input"]["items"] for f in tools.VOLUME_FIELDS if item[f] is not None)
    found = tools.stray_numbers(numbers, allowed)
    if found:
        raise tools.ToolError(
            f"These volumes aren't in anything you were given: {', '.join(dict.fromkeys(found))}. "
            "Use volumes from the user's weeks (read them with get_week) or from their request; "
            "a distance or time they gave in km, miles, minutes or hours counts in metres or seconds (12 km = 12000)."
        )


class _Weeks:
    """The request's drafts: one per week it has read or changed, by week start.
    Other weeks come from load_week(week_start) -> {"state", "rebalancer"}."""

    def __init__(self, week, rebalancer_sessions, context, load_week):
        self.current = context["week_start"]
        self.original = {self.current: week}
        self.draft = {self.current: copy.deepcopy(week)}
        self.rebalancer = {self.current: rebalancer_sessions}
        self.context = {self.current: context}
        self._load_week = load_week

    def load(self, week_start):
        if week_start not in self.draft:
            if self._load_week is None:
                raise tools.ToolError("Other weeks can't be read here.")
            loaded = self._load_week(week_start)
            self.original[week_start] = loaded["state"]
            self.draft[week_start] = copy.deepcopy(loaded["state"])
            self.rebalancer[week_start] = loaded["rebalancer"]
            # The distance check needs imported runs, which only the asked-from week carries.
            self.context[week_start] = {**self.context[self.current], "week_start": week_start, "week_check": [], "distance": None}
        return self.draft[week_start]

    def view(self, week_start):
        return payload(self.load(week_start), self.context[week_start])

    def owner(self, call):
        """The week holding the session or exercise a call names (this week if none does)."""
        session_id, item_id = call["input"].get("session_id"), call["input"].get("item_id")
        for week_start, draft in self.draft.items():
            for session in draft["sessions"]:
                if session["id"] == session_id or any(i["id"] == item_id for i in session["items"]):
                    return week_start
        return self.current

    def floors(self):
        sessions = [s for d in self.draft.values() for s in d["sessions"]]
        return min([0, *(s["id"] for s in sessions)]), min([0, *(i["id"] for s in sessions for i in s["items"])])

    def changed(self):
        return [w for w in sorted(self.draft) if self.draft[w] != self.original[w]]

    def new_conflicts(self, catalog):
        return {w: tools.new_conflicts(self.rebalancer[w], self.draft[w], catalog) for w in self.changed()}

    def check(self, catalog):
        result = plan_check(self.draft[self.current], catalog, self.rebalancer[self.current], self.context[self.current])
        others = [w for w in self.changed() if w != self.current]
        if others:
            result["other_weeks"] = {
                w.isoformat(): {k: v for k, v in plan_check(self.draft[w], catalog, self.rebalancer[w], self.context[w]).items() if k != "distance"}
                for w in others
            }
        return result

    def change_lines(self, catalog, units):
        changed = self.changed()
        lines = []
        for w in changed:
            week_lines = tools.change_lines(self.original[w], self.draft[w], catalog, units)
            # One week asked about and changed reads as before; anything else names its week.
            label = "" if changed == [self.current] else f"Week of {w:%b %d} · "
            lines += [label + line for line in week_lines]
        return lines


# A sentence ends at . ! or ? followed by whitespace, or at a line break, so "8.0 km"
# is never cut at its decimal point.
_SENTENCE = re.compile(r".*?(?:[.!?](?=\s)|\n)", re.DOTALL)


class _Sentences:
    """Streams the coach's text one complete sentence at a time (#43). Each sentence
    must pass the number check before it is sent; the first that fails stops the
    stream, so an invented number never reaches the screen."""

    def __init__(self, on_event, passes):
        self._on_event, self._passes = on_event, passes
        self._buffer, self.stopped, self.sent = "", False, False

    def feed(self, piece):
        self._buffer += piece
        while (match := _SENTENCE.match(self._buffer)) is not None:
            self._buffer = self._buffer[match.end() :]
            self._send(match.group(0))

    def flush(self):
        self._send(self._buffer)
        self._buffer = ""

    def _send(self, sentence):
        if self.stopped or not sentence.strip():
            return
        if not self._passes(sentence):
            self.stopped = True
            return
        self.sent = True
        self._on_event({"type": "text", "text": sentence})


REFUSED_STEP = "The app refused one change; the coach is adjusting"


def step_label(call, change_lines):
    """What the coach just did, in code-written words: never the model's own text."""
    if call["name"] == "get_week":
        return f"Read the week of {date.fromisoformat(call['input']['week_start']):%b %d}"
    if call["name"] == "check_plan":
        return "Checked the draft against the Week check"
    return "; ".join(change_lines) or "Changed the draft"


def _add_target(weeks, call):
    week_start = read_tools.monday(call["input"]["week_start"])
    if week_start < weeks.current:
        raise tools.ToolError(f"The week of {week_start.isoformat()} is past.")
    if (week_start - weeks.current).days > 7 * MAX_WEEKS_AHEAD:
        raise tools.ToolError(f"Plan at most {MAX_WEEKS_AHEAD} weeks ahead of this one.")
    return week_start


def _write(weeks, call, catalog, allowed, units, user_units):
    """Applies one write call to the week it belongs to; a rejected call raises ToolError and changes nothing."""
    week_start = _add_target(weeks, call) if call["name"] == "add_session" else weeks.owner(call)
    _new_volumes(call, allowed + "\n" + user_units)
    before = weeks.load(week_start)
    sessions_floor, items_floor = weeks.floors()
    after = tools.apply({**before, "new_id_floor": sessions_floor, "new_item_id_floor": items_floor}, call, catalog)
    after.pop("new_id_floor")
    after.pop("new_item_id_floor")
    # A reason is shown to the user beside the change, so it's held to the same number rule.
    lines = tools.change_lines(before, after, catalog, units)
    stray = _strays(call["input"].get("reason") or "", allowed + "\n" + "\n".join(lines))
    if stray:
        raise tools.ToolError(stray)
    weeks.draft[week_start] = after
    return lines


def _finish_problems(text, weeks, catalog, allowed, units):
    problems = []
    clashes = [c for found in weeks.new_conflicts(catalog).values() for c in found]
    if clashes:
        problems.append(
            "These changes break the week's spacing rules, so they can't be offered: "
            + "; ".join(_clash_text(c) for c in clashes)
            + ". Change the draft with more tool calls, or explain why it can't be done."
        )
    stray = _strays(text, allowed + "\n" + "\n".join(weeks.change_lines(catalog, units)))
    if stray:
        problems.append(stray)
    return problems


def _proposal(text, weeks, catalog, units, applied):
    changed = weeks.changed()
    if not changed:
        return {"status": "answer", "reply": text, "calls": [], "after": None, "changes": []}
    reasons = " ".join(dict.fromkeys(r for r in (c["input"].get("reason", "").strip() for c in applied) if r))
    by_week = {}
    for w in changed:
        old, new = tools.touched(weeks.original[w], weeks.draft[w])
        by_week[w.isoformat()] = {"before": {str(k): v for k, v in old.items()}, "after": {str(k): v for k, v in new.items()}}
    return {
        "status": "pending",
        "reply": text or reasons,
        "calls": [{"name": c["name"], "input": c["input"]} for c in applied],
        "after": weeks.draft[weeks.current],
        "weeks": by_week,
        "changes": weeks.change_lines(catalog, units),
    }


def _stopped(weeks, catalog, units, applied):
    # AC-14: show what it has only if that draft would pass the final check.
    if not weeks.changed() or any(weeks.new_conflicts(catalog).values()):
        return _failed(STOPPED)
    result = _proposal("", weeks, catalog, units, applied)
    result["reply"] = f"{result['reply']} {STOPPED_WITH_DRAFT}".strip()
    return result


def _conversation(history, week_start):
    """Earlier turns as plain text, oldest first, so the coach can refer back
    to what it offered. Failed turns were app errors, not the coach speaking.
    A turn asked while viewing another week says which (#43)."""
    turns = [t for t in history if t["status"] != "failed"][-MAX_HISTORY_TURNS:]
    messages, outcome = [], None
    for turn in turns:
        asked = turn.get("week_start", week_start)
        where = f"(Asked while viewing the week of {asked.isoformat()}.)\n\n" if asked != week_start else ""
        messages.append({"role": "user", "content": (f"{outcome}\n\n" if outcome else "") + where + turn["request"]})
        messages.append({"role": "assistant", "content": turn["reply"] or ""})
        outcome = _OUTCOMES.get(turn["status"])
    return messages, outcome


def propose(complete, week, catalog, rebalancer_sessions, request, context, history=(), readers=None, on_event=None):
    """on_event, when given, streams the request (#43): {"type": "text"} for each
    checked sentence, {"type": "step"} for each tool call, and {"type": "reset"}
    when a finished answer is sent back for correction."""
    data = payload(week, context)
    week_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
    earlier, outcome = _conversation(history, context["week_start"])
    # Only the latest message carries the week: earlier weeks are out of date.
    latest = f"<week>{week_json}</week>\n\n{request}"
    messages = earlier + [{"role": "user", "content": f"{outcome}\n\n{latest}" if outcome else latest}]
    # Numbers already said in this conversation were checked when they were said.
    allowed = "\n".join([week_json, request, *(m["content"] for m in earlier)])
    system, defined = system_prompt(catalog), tool_definitions()
    limits, units = llm_config.TASKS["coach"], context["units"]
    # Only the user's own words: "12 km" in their messages permits 12000 metres.
    user_units = tools.unit_conversions("\n".join([request, *(m["content"] for m in earlier if m["role"] == "user")]))

    weeks = _Weeks(week, rebalancer_sessions, context, (readers or {}).get("load_week"))
    applied, bad_rounds, spent = [], 0, 0.0
    for _step in range(limits["max_steps"]):
        if on_event is None:
            result = complete(system, messages, defined)
        else:
            # `allowed` grows with tool results, so the check reads it when each sentence ends.
            sentences = _Sentences(on_event, lambda s: not _strays(s, allowed + "\n" + "\n".join(weeks.change_lines(catalog, units))))
            result = complete(system, messages, defined, on_text=sentences.feed)
            sentences.flush()
        spent += call_cost(result["model"], result["usage"]) or 0.0
        if result["stop_reason"] == "refusal":
            return _failed(DECLINED)
        if result["stop_reason"] == "max_tokens":
            return _failed(TOO_LONG)

        feedback, bad = [], False
        if result["tool_calls"]:
            for call in result["tool_calls"]:
                try:
                    if call["name"] in read_tools.NAMES:
                        content = read_tools.run(call, weeks.view, lambda: weeks.check(catalog))
                        allowed += "\n" + content
                        lines = []
                    else:
                        lines = _write(weeks, call, catalog, allowed, units, user_units)
                        applied.append(call)
                        content = "OK"
                    feedback.append({"type": "tool_result", "tool_use_id": call["id"], "content": content})
                    if on_event:
                        on_event({"type": "step", "text": step_label(call, lines)})
                except tools.ToolError as err:
                    refused_write = call["name"] not in read_tools.NAMES
                    bad = bad or refused_write
                    feedback.append({"type": "tool_result", "tool_use_id": call["id"], "content": str(err), "is_error": True})
                    if on_event and refused_write:
                        on_event({"type": "step", "text": REFUSED_STEP})
        else:
            text = result["text"].strip()
            problems = _finish_problems(text, weeks, catalog, allowed, units)
            if not problems:
                return _proposal(text, weeks, catalog, units, applied)
            bad = True
            feedback.append({"type": "text", "text": " ".join(problems)})
            if on_event and sentences.sent:
                on_event({"type": "reset"})

        bad_rounds += bad
        if bad_rounds >= MAX_BAD_ROUNDS:
            return _failed(GAVE_UP)
        if spent >= limits["max_cost_usd"]:
            return _stopped(weeks, catalog, units, applied)
        messages = messages + [{"role": "assistant", "content": result["content"]}, {"role": "user", "content": feedback}]
    return _stopped(weeks, catalog, units, applied)


def _failed(message):
    return {"status": "failed", "reply": message, "calls": [], "after": None, "changes": []}
