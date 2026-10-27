"""The coach can add a session to its draft (spec step 8b, moved up on
2026-10-27): checked like a manual add, volumes only from numbers it was given,
and new sessions count in the spacing check.
"""

import pytest

from app.coach import agent, tools
from app.coach.catalog import CATALOG
from app.coach.providers import FakeProvider

from tests.test_coach_contract import TODAY, WEEK_START, _week

CAT = {e["slug"]: e for e in CATALOG}


def _item(exercise, sets=None, reps=None, duration_seconds=None, distance_meters=None):
    return {"exercise": exercise, "sets": sets, "reps": reps, "duration_seconds": duration_seconds, "distance_meters": distance_meters}


def _add(day=4, kind="run", focus="Easy run", items=None, effort=None, week_start="2026-10-19", reason="A second easy run."):
    return {
        "name": "add_session",
        "input": {
            "week_start": week_start,
            "day": day,
            "kind": kind,
            "focus": focus,
            "planned_effort": effort,
            "items": [_item("easy_run", distance_meters=8000.0)] if items is None else items,
            "reason": reason,
        },
    }


def test_a_new_session_goes_last_on_its_day_with_new_ids():
    after = tools.apply(_week(), _add(day=3), CAT)

    new = [s for s in after["sessions"] if s["id"] < 0]
    assert new == [
        {
            "id": -1, "day_index": 3, "position": 1, "kind": "run", "focus": "Easy run", "status": "planned",
            "planned_effort": None, "locked": False,
            "items": [{"id": -1, "position": 0, "exercise": "easy_run", "sets": None, "reps": None, "duration_seconds": None, "distance_meters": 8000.0}],
        }
    ]


def test_two_new_sessions_never_share_an_id():
    week = tools.apply(_week(), _add(day=4), CAT)
    week = tools.apply(week, _add(day=5, kind="gym", focus="Legs", items=[_item("back_squat", sets=4, reps=6)]), CAT)

    ids = [s["id"] for s in week["sessions"] if s["id"] < 0]
    item_ids = [i["id"] for s in week["sessions"] if s["id"] < 0 for i in s["items"]]
    assert ids == [-1, -2] and item_ids == [-1, -2]


@pytest.mark.parametrize(
    "call, message",
    [
        (_add(day=1), "already past"),
        (_add(day=7), "0–6"),
        (_add(kind="swim"), "kind"),
        (_add(focus="  "), "focus"),
        (_add(focus="x" * 41), "focus"),
        (_add(items=[_item("no_such_move", sets=3, reps=10)]), "not in the catalog"),
        (_add(kind="gym", items=[_item("easy_run", distance_meters=8000.0)]), "doesn't fit a gym session"),
        (_add(kind="run", items=[_item("back_squat", sets=4, reps=6)]), "doesn't fit a run session"),
        (_add(items=[]), "at least one exercise"),
        (_add(kind="rest", focus="Rest", items=[_item("easy_run", distance_meters=8000.0)]), "no exercises"),
        (_add(items=[_item("easy_run")]), "needs a volume"),
        (_add(items=[_item("easy_run", sets=3, distance_meters=8000.0)]), "only one"),
        (_add(kind="gym", items=[_item("back_squat", sets=40, reps=6)]), "sets must be"),
        (_add(effort="brutal"), "effort"),
    ],
)
def test_add_session_is_checked_like_a_manual_add(call, message):
    with pytest.raises(tools.ToolError, match=message):
        tools.apply(_week(), call, CAT)


def test_a_rest_day_has_no_exercises():
    after = tools.apply(_week(), _add(kind="rest", focus="Rest", items=[]), CAT)

    assert [s["kind"] for s in after["sessions"] if s["id"] < 0] == ["rest"]


def test_an_added_session_reads_as_added():
    after = tools.apply(_week(), _add(day=4), CAT)

    assert tools.change_lines(_week(), after, CAT, "metric") == ["Easy run on Fri: added (8.0 km)"]


def test_an_added_hard_leg_day_counts_in_the_spacing_check():
    rb = [
        {
            "id": 2, "day_index": 3, "position": 0, "kind": "run", "status": "planned", "focus": "Running day", "planned_effort": "hard",
            "srpe": None, "z3_minutes": None, "muscle_groups": set(), "hard_set_groups": set(), "rated_set_groups": set(),
        }
    ]
    week = _week()
    week["sessions"][0]["planned_effort"] = "hard"
    legs = _add(day=2, kind="gym", focus="Legs", effort="hard", items=[_item("back_squat", sets=4, reps=6)])

    after = tools.apply(week, legs, CAT)

    # RULE-REC-04 + D4: hard legs the day before a hard run.
    assert [c["rule"] for c in tools.new_conflicts(rb, after, CAT)] == ["RULE-REC-04"]


# --- in the agent: volumes come from what the coach was given ---------------------------


def _run(fake, request="Add an easy run on Friday"):
    def complete(system, messages, tools_):
        return fake.complete("coach", system=system, messages=messages, tools=tools_)

    return agent.propose(
        complete, week=_week(), catalog=CAT, rebalancer_sessions=[], request=request,
        context={"week_start": WEEK_START, "today": TODAY, "units": "metric", "profile": {}, "week_check": []}, readers={},
    )


def test_a_volume_from_the_week_is_accepted():
    # 8000.0 m is Thursday's planned run in the payload.
    fake = FakeProvider([{"tool_calls": [_add(day=4)]}, {}])

    result = _run(fake)

    assert result["status"] == "pending"
    assert result["changes"] == ["Easy run on Fri: added (8.0 km)"]


def test_an_invented_volume_is_sent_back():
    fake = FakeProvider([{"tool_calls": [_add(day=4, items=[_item("easy_run", distance_meters=12000.0)])]}, {"text": "OK."}])

    _run(fake)

    error = fake.calls[1]["messages"][-1]["content"][0]
    assert error["is_error"] is True
    assert "12000" in error["content"] and "get_week" in error["content"]


def test_a_volume_the_user_gave_is_accepted():
    fake = FakeProvider([{"tool_calls": [_add(day=4, items=[_item("easy_run", distance_meters=12000.0)])]}, {}])

    result = _run(fake, request="Add a 12000 m easy run on Friday")

    assert result["status"] == "pending"
