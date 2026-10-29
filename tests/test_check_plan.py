"""Step 8a, slice 2: check_plan runs the Week check on the coach's own draft
(AC-16) — spacing clashes marked new or already there, the hard-run balance
and the distance change — so it can fix problems before it finishes.
"""

import json

from app.coach import agent
from app.coach.catalog import CATALOG
from app.coach.providers import FakeProvider

from tests.test_coach_contract import TODAY, WEEK_START, _week

CAT = {e["slug"]: e for e in CATALOG}
CHECK = {"name": "check_plan", "input": {}}
HARD = {"name": "set_planned_effort", "input": {"session_id": 2, "effort": "hard", "reason": "Make it a tempo."}}


def _rb(session_id, day_index, planned_effort):
    return {
        "id": session_id, "day_index": day_index, "position": 0, "kind": "run", "status": "planned", "focus": "Running day",
        "planned_effort": planned_effort, "srpe": None, "z3_minutes": None,
        "muscle_groups": set(), "hard_set_groups": set(), "rated_set_groups": set(),
    }


def _two_runs_week():
    week = _week()
    friday = json.loads(json.dumps(week["sessions"][0]))
    friday.update(id=9, day_index=4, planned_effort="hard")
    friday["items"][0]["id"] = 90
    week["sessions"].append(friday)
    return week, [_rb(2, 3, None), _rb(9, 4, "hard")]


def _run(fake, week=None, rebalancer_sessions=(), distance=None):
    def complete(system, messages, tools):
        return fake.complete("coach", system=system, messages=messages, tools=tools)

    context = {"week_start": WEEK_START, "today": TODAY, "units": "metric", "profile": {}, "week_check": []}
    if distance:
        context["distance"] = distance
    return agent.propose(
        complete, week=week or _week(), catalog=CAT, rebalancer_sessions=list(rebalancer_sessions),
        request="Check my week", context=context, readers={},
    )


def _checked(fake, call_index):
    block = fake.calls[call_index]["messages"][-1]["content"][-1]
    assert block["type"] == "tool_result" and not block.get("is_error")
    return json.loads(block["content"])


def test_ac_16_check_plan_reports_a_clash_the_draft_adds():
    week, rb = _two_runs_week()
    fake = FakeProvider([{"tool_calls": [HARD, CHECK]}, {"text": "OK."}, {"text": "OK."}])

    _run(fake, week=week, rebalancer_sessions=rb)

    checked = _checked(fake, 1)
    assert checked["clashes"] == [
        {"rule": "RULE-REC-02", "reason": "close", "sessions": ["Thu Running day (session 2)", "Fri Running day (session 9)"], "groups": [], "new": True}
    ]


def test_a_clash_already_on_the_board_is_listed_but_not_new():
    week, rb = _two_runs_week()
    rb[0]["planned_effort"] = "hard"
    week["sessions"][0]["planned_effort"] = "hard"
    fake = FakeProvider([{"tool_calls": [CHECK]}, {"text": "OK."}])

    _run(fake, week=week, rebalancer_sessions=rb)

    assert [c["new"] for c in _checked(fake, 1)["clashes"]] == [False]


def test_check_plan_counts_hard_runs_in_the_draft():
    week, rb = _two_runs_week()
    fake = FakeProvider([{"tool_calls": [HARD, CHECK]}, {"text": "OK."}, {"text": "OK."}])

    _run(fake, week=week, rebalancer_sessions=rb)

    # RULE-WEEK-01: both runs hard against a suggested 1.
    assert _checked(fake, 1)["hard_runs"] == {"runs": 2, "hard": 2, "suggested_hard": 1, "note": True}


def test_check_plan_compares_the_drafts_running_distance_with_recent_weeks():
    # RULE-PROG-02: 2 km run so far + the 8 km planned Thursday against a 5 km average.
    fake = FakeProvider([{"tool_calls": [CHECK]}, {"text": "OK."}])

    _run(fake, distance={"so_far_meters": 2000.0, "previous_weeks_meters": [5000.0, 5000.0]})

    assert _checked(fake, 1)["distance"] == {"this_week_meters": 10000.0, "baseline_meters": 5000.0, "pct": 100.0, "level": "big"}


def test_without_recent_weeks_there_is_no_distance_change():
    fake = FakeProvider([{"tool_calls": [CHECK]}, {"text": "OK."}])

    _run(fake)

    assert _checked(fake, 1)["distance"] is None


def test_numbers_from_check_plan_may_be_used_in_the_answer():
    fake = FakeProvider([{"tool_calls": [CHECK]}, {"text": "This week is 100.0 % above your recent average."}])

    result = _run(fake, distance={"so_far_meters": 2000.0, "previous_weeks_meters": [5000.0, 5000.0]})

    assert result["status"] == "answer"


def test_check_plan_is_offered_and_the_prompt_asks_for_it():
    fake = FakeProvider([{"text": "OK."}])

    _run(fake)

    names = [t["name"] for t in fake.calls[0]["tools"]]
    assert "check_plan" in names
    assert "check_plan" in fake.calls[0]["system"][0]["text"]
