"""Step 8a, slice 4 (#42): the coach keeps a short to-do list with update_plan.
It shows live while the coach works (the loading state), never touches the
draft, and is held to the same number rule as everything the coach says.
"""

import pytest

from app.coach import agent

from tests.test_add_session import _add
from tests.test_agent_stream import _run
from app.coach.providers import FakeProvider


def _plan(*items):
    return {"name": "update_plan", "input": {"steps": [{"text": t, "done": d} for t, d in items]}}


def _plans(events):
    return [e["steps"] for e in events if e["type"] == "plan"]


def test_update_plan_is_offered_to_the_coach():
    names = [t["name"] for t in agent.tool_definitions()]

    assert "update_plan" in names


def test_the_plan_streams_as_the_coach_updates_it():
    fake = FakeProvider(
        [
            {"tool_calls": [_plan(("Read last week", False), ("Add a Friday run", False))]},
            {"tool_calls": [_add(day=4), _plan(("Read last week", True), ("Add a Friday run", True))]},
            {"text": "Added an easy run on Friday."},
        ]
    )

    result, events = _run(fake, request="Add an easy run on Friday")

    assert _plans(events) == [
        [{"text": "Read last week", "done": False}, {"text": "Add a Friday run", "done": False}],
        [{"text": "Read last week", "done": True}, {"text": "Add a Friday run", "done": True}],
    ]
    assert result["status"] == "pending"
    # The plan is the coach's own words, so it never shows as a code-written step.
    assert [e["text"] for e in events if e["type"] == "step"] == ["Easy run on Fri: added (8.0 km)"]


def test_the_plan_never_reaches_the_draft():
    fake = FakeProvider([{"tool_calls": [_plan(("Look at the week", False))]}, {"text": "Thursday is fine."}])

    result, _ = _run(fake)

    assert result["status"] == "answer" and result["calls"] == []
    assert fake.calls[1]["messages"][-1]["content"][0]["content"] == "OK"


def test_a_plan_with_an_invented_number_is_refused_and_never_shown():
    fake = FakeProvider([{"tool_calls": [_plan(("Run 17 km on Sunday", False))]}, {"text": "Thursday is fine."}])

    result, events = _run(fake)

    assert _plans(events) == []
    refused = fake.calls[1]["messages"][-1]["content"][0]
    assert refused["is_error"] and "17" in refused["content"]
    assert result["reply"] == "Thursday is fine."


@pytest.mark.parametrize(
    "steps",
    [[], [{"text": "", "done": False}], [{"text": "x" * (agent.MAX_PLAN_TEXT + 1), "done": False}],
     [{"text": "Step", "done": False}] * (agent.MAX_PLAN_STEPS + 1)],
)
def test_a_plan_must_be_short(steps):
    fake = FakeProvider([{"tool_calls": [{"name": "update_plan", "input": {"steps": steps}}]}, {"text": "Fine."}])

    result, events = _run(fake)

    assert _plans(events) == []
    assert fake.calls[1]["messages"][-1]["content"][0]["is_error"]
    # A bad plan is a slip in the loading state, not a bad change: it uses up no retries.
    assert result["reply"] == "Fine."


def test_without_a_listener_the_plan_is_still_answered():
    fake = FakeProvider([{"tool_calls": [_plan(("Look at the week", False))]}, {"text": "Fine."}])

    def complete(system, messages, tools):
        return fake.complete("coach", system=system, messages=messages, tools=tools)

    from tests.test_agent_stream import CAT, TODAY, WEEK_START, _week

    result = agent.propose(
        complete, week=_week(), catalog=CAT, rebalancer_sessions=[], request="Hi",
        context={"week_start": WEEK_START, "today": TODAY, "units": "metric", "profile": {}, "week_check": []},
    )

    assert result["reply"] == "Fine."
