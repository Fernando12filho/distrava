"""Step 8a, slice 1: the coach works in steps. Writes build up in one draft
across rounds, read tools answer without writing, and every request stops
within its step and cost caps (AC-14, AC-15).
"""

import json
from datetime import date

import pytest

from app.coach import agent, llm_config
from app.coach.catalog import CATALOG
from app.coach.providers import FakeProvider

from tests.test_coach_contract import TODAY, WEEK_START, _move, _week

CAT = {e["slug"]: e for e in CATALOG}
LAST_WEEK = date(2026, 10, 12)
EASY = {"name": "set_planned_effort", "input": {"session_id": 2, "effort": "easy", "reason": "Keep it easy."}}


def _last_week_state():
    return {
        "today_index": 7,
        "sessions": [
            {
                "id": 7, "day_index": 1, "position": 0, "kind": "run", "focus": "Running day", "status": "done",
                "planned_effort": None, "locked": True,
                "items": [{"id": 70, "position": 0, "exercise": "easy_run", "sets": None, "reps": None, "duration_seconds": None, "distance_meters": 6000.0}],
            }
        ],
    }


def _run(fake, request="Move Thursday's run to Friday", readers=None):
    asked = []

    def load_week(week_start):
        asked.append(week_start)
        return {"state": _last_week_state(), "rebalancer": []}

    def complete(system, messages, tools):
        return fake.complete("coach", system=system, messages=messages, tools=tools)

    result = agent.propose(
        complete,
        week=_week(),
        catalog=CAT,
        rebalancer_sessions=[],
        request=request,
        context={"week_start": WEEK_START, "today": TODAY, "units": "metric", "profile": {}, "week_check": []},
        readers=readers or {"load_week": load_week},
    )
    return result, asked


def _get_week(week_start):
    return {"name": "get_week", "input": {"week_start": week_start}}


def _tool_results(call):
    return [b for b in call["messages"][-1]["content"] if b["type"] == "tool_result"]


def test_ac_15_writes_build_up_in_one_draft_across_steps():
    fake = FakeProvider([{"tool_calls": [_move()]}, {"tool_calls": [EASY]}, {"text": "Moved it to Friday and kept it easy."}])

    result, _ = _run(fake)

    assert result["status"] == "pending"
    assert result["after"]["sessions"][0]["day_index"] == 4
    assert result["after"]["sessions"][0]["planned_effort"] == "easy"
    assert result["calls"] == [_move(), EASY]
    assert result["reply"] == "Moved it to Friday and kept it easy."
    assert len(fake.calls) == 3


def test_a_finished_draft_without_a_summary_uses_the_reasons():
    fake = FakeProvider([{"tool_calls": [_move()]}, {}])

    result, _ = _run(fake)

    assert result["reply"] == "Friday is free."


def test_ac_15_reading_another_week_answers_without_writing():
    fake = FakeProvider([{"tool_calls": [_get_week("2026-10-12")]}, {"text": "Last week you ran 6.0 km on Tuesday."}])

    result, asked = _run(fake, request="What did I do last week?")

    assert asked == [LAST_WEEK]
    seen = json.loads(_tool_results(fake.calls[1])[0]["content"])
    assert seen["week_start"] == "2026-10-12"
    assert [(s["day"], s["can_change"], s["items"][0]["volume"]) for s in seen["sessions"]] == [("Tue 2026-10-13", False, "6.0 km")]
    # 6.0 came from a tool result, so it isn't an invented number.
    assert result == {"status": "answer", "reply": "Last week you ran 6.0 km on Tuesday.", "calls": [], "after": None, "changes": []}


def test_reading_this_week_shows_the_draft_so_far():
    fake = FakeProvider([{"tool_calls": [_move()]}, {"tool_calls": [_get_week("2026-10-19")]}, {}])

    _, asked = _run(fake)

    assert asked == []
    seen = json.loads(_tool_results(fake.calls[2])[0]["content"])
    assert [s["day"] for s in seen["sessions"] if s["id"] == 2] == ["Fri 2026-10-23"]


@pytest.mark.parametrize("bad", ["2026-10-14", "next week"])
def test_get_week_wants_a_monday_date(bad):
    fake = FakeProvider([{"tool_calls": [_get_week(bad)]}, {"text": "OK."}])

    _, asked = _run(fake)

    result = _tool_results(fake.calls[1])[0]
    assert result["is_error"] is True
    assert "Monday" in result["content"]
    assert asked == []


def test_ac_14_a_request_stops_at_the_step_cap(monkeypatch):
    monkeypatch.setitem(llm_config.TASKS["coach"], "max_steps", 3)
    fake = FakeProvider([{"tool_calls": [_get_week("2026-10-12")]}] * 5)

    result, _ = _run(fake)

    assert len(fake.calls) == 3
    assert result["status"] == "failed"
    assert result["reply"] == agent.STOPPED
    assert result["after"] is None


def test_ac_14_a_stop_shows_the_draft_it_has(monkeypatch):
    monkeypatch.setitem(llm_config.TASKS["coach"], "max_steps", 2)
    fake = FakeProvider([{"tool_calls": [_move()]}, {"tool_calls": [_get_week("2026-10-12")]}])

    result, _ = _run(fake)

    assert result["status"] == "pending"
    assert result["changes"] == ["Running day: Thu → Fri"]
    assert result["reply"] == "Friday is free. " + agent.STOPPED_WITH_DRAFT


def test_ac_14_a_request_stops_at_the_cost_cap(monkeypatch):
    monkeypatch.setitem(llm_config.TASKS["coach"], "max_cost_usd", 0.25)
    # 100k Opus input tokens is about $0.40: over the cap after one round.
    fake = FakeProvider([{"tool_calls": [_get_week("2026-10-12")], "usage": {"input_tokens": 100_000}}, {"text": "OK."}])

    result, _ = _run(fake)

    assert len(fake.calls) == 1
    assert result["reply"] == agent.STOPPED


def test_caps_live_in_config():
    coach = llm_config.TASKS["coach"]
    assert coach["max_steps"] >= 4
    assert 0 < coach["max_cost_usd"] <= 1


def test_read_tools_are_offered_beside_the_write_tools():
    fake = FakeProvider([{"text": "OK."}])

    _run(fake)

    names = [t["name"] for t in fake.calls[0]["tools"]]
    assert "get_week" in names and "move_session" in names
    get_week = next(t for t in fake.calls[0]["tools"] if t["name"] == "get_week")
    assert get_week["strict"] is True


def test_a_bad_read_is_corrected_without_using_up_the_retries():
    fake = FakeProvider([{"tool_calls": [_get_week("2026-10-14")]}, {"tool_calls": [_get_week("2026-10-15")]}, {"text": "OK."}])

    result, _ = _run(fake)

    # Reading can't harm the week, so only rejected writes count as bad rounds.
    assert result["status"] == "answer"
