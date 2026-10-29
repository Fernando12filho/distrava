"""Drafts over several weeks (spec step 8b, AC-20): one request may plan this
week and the next ones; the draft is shown, accepted and undone as one.
"""

import json
from datetime import date

import pytest

from app.coach import agent
from app.coach.catalog import CATALOG
from app.coach.providers import FakeProvider

from tests.test_add_session import _add, _item
from tests.test_coach_contract import TODAY, WEEK_START, _week

CAT = {e["slug"]: e for e in CATALOG}
NEXT = date(2026, 10, 26)


def _next_week_state():
    return {
        "today_index": 0,
        "sessions": [
            {
                "id": 30, "day_index": 1, "position": 0, "kind": "gym", "focus": "Legs & Glutes", "status": "planned",
                "planned_effort": None, "locked": False,
                "items": [{"id": 300, "position": 0, "exercise": "back_squat", "sets": 4, "reps": 6, "duration_seconds": None, "distance_meters": None}],
            }
        ],
    }


def _run(fake, request="Plan my next 2 weeks"):
    loaded = []

    def load_week(week_start):
        loaded.append(week_start)
        state = _next_week_state() if week_start == NEXT else {"today_index": 0, "sessions": []}
        return {"state": state, "rebalancer": []}

    def complete(system, messages, tools):
        return fake.complete("coach", system=system, messages=messages, tools=tools)

    result = agent.propose(
        complete, week=_week(), catalog=CAT, rebalancer_sessions=[], request=request,
        context={"week_start": WEEK_START, "today": TODAY, "units": "metric", "profile": {}, "week_check": []},
        readers={"load_week": load_week},
    )
    return result, loaded


def test_ac_20_one_request_plans_this_week_and_the_next():
    fake = FakeProvider([{"tool_calls": [_add(day=4), _add(day=3, week_start="2026-10-26")]}, {}])

    result, loaded = _run(fake)

    assert loaded == [NEXT]
    assert result["status"] == "pending"
    assert set(result["weeks"]) == {"2026-10-19", "2026-10-26"}
    assert result["weeks"]["2026-10-26"]["before"] == {"-2": None}
    assert result["weeks"]["2026-10-26"]["after"]["-2"]["day_index"] == 3
    assert result["changes"] == ["Week of Oct 19 · Easy run on Fri: added (8.0 km)", "Week of Oct 26 · Easy run on Thu: added (8.0 km)"]


def test_new_sessions_never_share_an_id_across_weeks():
    fake = FakeProvider([{"tool_calls": [_add(day=4), _add(day=3, week_start="2026-10-26"), _add(day=5, week_start="2026-10-26")]}, {}])

    result, _ = _run(fake)

    ids = [int(k) for part in result["weeks"].values() for k in part["after"]]
    assert sorted(ids) == [-3, -2, -1]


def test_only_next_weeks_changed_still_reads_as_that_week():
    fake = FakeProvider([{"tool_calls": [_add(day=3, week_start="2026-10-26")]}, {}])

    result, _ = _run(fake)

    assert set(result["weeks"]) == {"2026-10-26"}
    assert result["changes"] == ["Week of Oct 26 · Easy run on Thu: added (8.0 km)"]


def test_a_session_read_in_another_week_can_be_changed_there():
    adjust = {
        "name": "adjust_item",
        "input": {"item_id": 300, "sets": 4, "reps": 8, "duration_seconds": None, "distance_meters": None, "reason": "As you asked."},
    }
    fake = FakeProvider([{"tool_calls": [{"name": "get_week", "input": {"week_start": "2026-10-26"}}]}, {"tool_calls": [adjust]}, {}])

    result, _ = _run(fake, request="Make next week's squats 4 x 8")

    assert result["weeks"]["2026-10-26"]["after"]["30"]["items"][0]["reps"] == 8
    assert "2026-10-19" not in result["weeks"]


@pytest.mark.parametrize("week_start, message", [("2026-10-12", "past"), ("2026-11-23", "weeks ahead"), ("2026-10-27", "Monday")])
def test_planning_stays_between_this_week_and_the_horizon(week_start, message):
    fake = FakeProvider([{"tool_calls": [_add(day=3, week_start=week_start)]}, {"text": "OK."}])

    _run(fake)

    error = fake.calls[1]["messages"][-1]["content"][0]
    assert error["is_error"] is True and message in error["content"]


def test_reading_next_week_after_adding_shows_the_draft():
    fake = FakeProvider([{"tool_calls": [_add(day=3, week_start="2026-10-26")]}, {"tool_calls": [{"name": "get_week", "input": {"week_start": "2026-10-26"}}]}, {}])

    _run(fake)

    seen = json.loads(fake.calls[2]["messages"][-1]["content"][0]["content"])
    assert sorted(s["focus"] for s in seen["sessions"]) == ["Easy run", "Legs & Glutes"]


def test_check_plan_covers_every_week_the_draft_changes():
    legs = _add(day=0, week_start="2026-10-26", kind="gym", focus="Legs", effort="hard", items=[_item("back_squat", sets=4, reps=6)])
    tempo = _add(day=1, week_start="2026-10-26", effort="hard")
    fake = FakeProvider([{"tool_calls": [legs, tempo, {"name": "check_plan", "input": {}}]}, {"text": "OK."}, {"text": "OK."}])

    _run(fake, request="Next week: squats 4 x 6 on Monday, a tempo on Tuesday")

    checked = json.loads(fake.calls[1]["messages"][-1]["content"][-1]["content"])
    # RULE-REC-04 + D4: hard legs on Monday, then a hard run on Tuesday.
    assert [c["rule"] for c in checked["other_weeks"]["2026-10-26"]["clashes"]] == ["RULE-REC-04"]


def test_a_new_clash_in_another_week_blocks_the_finish():
    legs = _add(day=0, week_start="2026-10-26", kind="gym", focus="Legs", effort="hard", items=[_item("back_squat", sets=4, reps=6)])
    tempo = _add(day=1, week_start="2026-10-26", effort="hard")
    fake = FakeProvider([{"tool_calls": [legs, tempo]}, {}, {}])

    result, _ = _run(fake, request="Next week: squats 4 x 6 on Monday, a tempo on Tuesday")

    assert result["status"] == "failed"
    assert "RULE-REC-04" in json.dumps(fake.calls[2]["messages"][-1]["content"])
