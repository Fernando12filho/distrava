"""Streaming the coach (#43): the answer goes out sentence by sentence, each one
checked for invented numbers before it is sent, and the coach's steps go out as
code-written lines. Nothing a check would refuse ever reaches the screen.
"""

from datetime import date

from app.coach import agent
from app.coach.catalog import CATALOG
from app.coach.providers import FakeProvider

from tests.test_add_session import _add
from tests.test_coach_contract import TODAY, WEEK_START, _week

CAT = {e["slug"]: e for e in CATALOG}


def _run(fake, request="Is Thursday OK?"):
    events = []

    def complete(system, messages, tools, on_text=None):
        return fake.complete("coach", system=system, messages=messages, tools=tools, on_text=on_text)

    def load_week(week_start):
        return {"state": {"today_index": 7, "sessions": []}, "rebalancer": []}

    result = agent.propose(
        complete, week=_week(), catalog=CAT, rebalancer_sessions=[], request=request,
        context={"week_start": WEEK_START, "today": TODAY, "units": "metric", "profile": {}, "week_check": []},
        readers={"load_week": load_week}, on_event=events.append,
    )
    return result, events


def _texts(events):
    return [e["text"] for e in events if e["type"] == "text"]


def test_an_answer_goes_out_sentence_by_sentence():
    fake = FakeProvider([{"text": "Thursday is fine. Your run fits there."}])

    result, events = _run(fake)

    assert _texts(events) == ["Thursday is fine.", " Your run fits there."]
    assert "".join(_texts(events)) == result["reply"]


def test_a_decimal_point_does_not_end_a_sentence():
    fake = FakeProvider([{"text": "Keep it at 8.0 km. That's plenty."}])

    _, events = _run(fake)

    assert _texts(events)[0] == "Keep it at 8.0 km."


def test_a_sentence_with_an_invented_number_never_goes_out():
    fake = FakeProvider([{"text": "Thursday is fine. Run 12 km instead."}, {"text": "Thursday is fine."}])

    result, events = _run(fake)

    assert not any("12" in t for t in _texts(events))
    kinds = [e["type"] for e in events]
    # The checked first sentence went out, the round was sent back, the screen was told to clear.
    assert kinds == ["text", "reset", "text"]
    assert result["reply"] == "Thursday is fine."


def test_each_step_goes_out_as_a_code_written_line():
    fake = FakeProvider(
        [
            {"tool_calls": [{"name": "get_week", "input": {"week_start": "2026-10-12"}}]},
            {"tool_calls": [_add(day=4), {"name": "check_plan", "input": {}}]},
            {"text": "Added an easy run on Friday."},
        ]
    )

    _, events = _run(fake, request="Add an easy run on Friday")

    steps = [e["text"] for e in events if e["type"] == "step"]
    assert steps == ["Read the week of Oct 12", "Easy run on Fri: added (8.0 km)", "Checked the draft against the Week check"]


def test_a_refused_change_says_so_without_the_coachs_numbers():
    bad = _add(day=4, items=[{"exercise": "easy_run", "sets": None, "reps": None, "duration_seconds": None, "distance_meters": 12345.0}])
    fake = FakeProvider([{"tool_calls": [bad]}, {"text": "OK."}])

    _, events = _run(fake)

    steps = [e["text"] for e in events if e["type"] == "step"]
    assert steps == ["The app refused one change; the coach is adjusting"]
    assert not any("12345" in e.get("text", "") for e in events)


def test_without_a_listener_nothing_streams():
    calls = []

    def complete(system, messages, tools):
        calls.append(messages)
        return FakeProvider([{"text": "Fine."}]).complete("coach", system=system, messages=messages, tools=tools)

    result = agent.propose(
        complete, week=_week(), catalog=CAT, rebalancer_sessions=[], request="Hi",
        context={"week_start": WEEK_START, "today": TODAY, "units": "metric", "profile": {}, "week_check": []},
    )

    assert result["reply"] == "Fine." and len(calls) == 1


def test_steps_name_the_week_in_plain_words():
    assert agent.step_label({"name": "get_week", "input": {"week_start": "2026-11-02"}}, []) == "Read the week of Nov 02"
    assert date(2026, 11, 2).weekday() == 0
