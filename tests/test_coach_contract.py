"""The coach loop against a fake provider: valid output → a proposal; invalid →
one retry with the reasons → otherwise it says so and changes nothing.
"""

import json
from datetime import date

from app.coach import agent
from app.coach.catalog import CATALOG
from app.coach.providers import FakeProvider

CAT = {e["slug"]: e for e in CATALOG}
WEEK_START = date(2026, 10, 19)
TODAY = date(2026, 10, 21)


def _week():
    return {
        "today_index": 2,
        "sessions": [
            {
                "id": 2,
                "day_index": 3,
                "position": 0,
                "kind": "run",
                "focus": "Running day",
                "status": "planned",
                "planned_effort": None,
                "locked": False,
                "items": [
                    {"id": 20, "position": 0, "exercise": "easy_run", "sets": None, "reps": None, "duration_seconds": None, "distance_meters": 8000.0}
                ],
            },
            {
                "id": 1,
                "day_index": 0,
                "position": 0,
                "kind": "run",
                "focus": "Running day",
                "status": "done",
                "planned_effort": None,
                "locked": True,
                "items": [
                    {"id": 10, "position": 0, "exercise": "easy_run", "sets": None, "reps": None, "duration_seconds": None, "distance_meters": 5000.0}
                ],
            },
        ],
    }


def _run(fake, request="Move Thursday's run to Friday", rebalancer_sessions=(), week=None, history=(), readers=None):
    def complete(system, messages, tools):
        return fake.complete("coach", system=system, messages=messages, tools=tools)

    return agent.propose(
        complete,
        week=week or _week(),
        catalog=CAT,
        rebalancer_sessions=list(rebalancer_sessions),
        request=request,
        context={"week_start": WEEK_START, "today": TODAY, "units": "metric", "profile": {}, "week_check": []},
        history=list(history),
        readers=readers or {},
    )


# --- conversation memory ---------------------------------------------------------

_REVIEW = {"request": "Review my week", "reply": "Two options: move the run to Friday, or plan it easy.", "status": "answer"}


def test_earlier_turns_come_before_the_request_and_the_week_only_once():
    fake = FakeProvider([{"text": "Done."}])

    _run(fake, request="Do the first option", history=[_REVIEW])

    messages = fake.calls[0]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[0]["content"] == "Review my week"
    assert messages[1]["content"] == "Two options: move the run to Friday, or plan it easy."
    # Old turns carry no week: only the current one is true now.
    assert "<week>" not in messages[0]["content"]
    assert messages[2]["content"].startswith("<week>") and messages[2]["content"].endswith("Do the first option")


def test_what_the_user_did_with_a_proposal_is_told_to_the_coach():
    move = {"request": "Move the run", "reply": "Friday is free.", "status": "accepted"}
    fake = FakeProvider([{"text": "Done."}])

    _run(fake, request="Now plan it easy", history=[move])

    assert fake.calls[0]["messages"][2]["content"].startswith("(You proposed that change and the user accepted it.)")


def test_failed_turns_are_left_out_and_only_the_latest_turns_are_kept():
    failed = {"request": "hello", "reply": "The request was not accepted.", "status": "failed"}
    turns = [{"request": f"Question {i}", "reply": f"Answer {i}", "status": "answer"} for i in range(agent.MAX_HISTORY_TURNS + 3)]
    fake = FakeProvider([{"text": "Done."}])

    _run(fake, request="Next", history=[failed, *turns])

    sent = [m["content"] for m in fake.calls[0]["messages"][:-1]]
    assert "hello" not in sent
    assert len(sent) == 2 * agent.MAX_HISTORY_TURNS
    assert sent[-1] == f"Answer {agent.MAX_HISTORY_TURNS + 2}"


def test_a_number_from_an_earlier_turn_is_not_an_invented_number():
    earlier = {"request": "How far should Friday be?", "reply": "Keep it at 6 km, as you said.", "status": "answer"}
    fake = FakeProvider([{"text": "Friday stays at 6 km."}])

    result = _run(fake, request="Remind me about Friday", history=[earlier])

    assert result["status"] == "answer"
    assert len(fake.calls) == 1


def _move(day=4, reason="Friday is free."):
    return {"name": "move_session", "input": {"session_id": 2, "day": day, "reason": reason}}


def test_a_valid_tool_call_becomes_a_pending_proposal():
    fake = FakeProvider([{"tool_calls": [_move()]}, {}])

    result = _run(fake)

    assert result["status"] == "pending"
    assert result["reply"] == "Friday is free."
    assert result["changes"] == ["Running day: Thu → Fri"]
    assert result["after"]["sessions"][0]["day_index"] == 4
    assert result["calls"] == [_move()]
    assert len(fake.calls) == 2  # the change, then the coach finishing


def test_an_answer_without_tools_is_just_an_answer():
    fake = FakeProvider([{"text": "Your Thursday run is an easy run."}])

    result = _run(fake, request="What is Thursday?")

    assert result == {"status": "answer", "reply": "Your Thursday run is an easy run.", "calls": [], "after": None, "changes": []}


def test_a_rejected_call_is_retried_once_with_the_reason():
    fake = FakeProvider([{"tool_calls": [_move(day=1)]}, {"tool_calls": [_move(day=4)]}, {}])

    result = _run(fake)

    assert result["status"] == "pending"
    retry = fake.calls[1]["messages"]
    assert retry[1]["role"] == "assistant"
    assert retry[1]["content"] == [{"type": "tool_use", "id": "toolu_fake_1", "name": "move_session", "input": _move(day=1)["input"]}]
    tool_result = retry[2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_fake_1"
    assert tool_result["is_error"] is True
    assert "already past" in tool_result["content"]


def test_two_bad_answers_give_up_and_change_nothing():
    fake = FakeProvider([{"tool_calls": [_move(day=1)]}, {"tool_calls": [_move(day=0)]}])

    result = _run(fake)

    assert result["status"] == "failed"
    assert result["after"] is None
    assert result["changes"] == []
    assert "couldn't" in result["reply"]
    assert len(fake.calls) == 2  # at most one retry


def test_every_tool_call_in_a_reply_gets_a_result_on_retry():
    good = {"name": "set_planned_effort", "input": {"session_id": 2, "effort": "easy", "reason": "Keep it easy."}}
    fake = FakeProvider([{"tool_calls": [good, _move(day=1)]}, {}])

    _run(fake)

    results = [b for b in fake.calls[1]["messages"][2]["content"] if b["type"] == "tool_result"]
    assert [r.get("is_error", False) for r in results] == [False, True]


def test_ac_never_computes_a_number_not_given_is_sent_back():
    fake = FakeProvider([{"tool_calls": [_move(reason="Friday leaves you 36 hours to recover.")]}, {"tool_calls": [_move()]}, {}])

    result = _run(fake)

    assert result["status"] == "pending"
    feedback = fake.calls[1]["messages"][2]["content"][0]
    assert feedback["is_error"] is True and "36" in feedback["content"]
    assert result["calls"] == [_move()]  # the call with the invented number was never applied


def test_an_answer_with_an_invented_number_is_retried_too():
    fake = FakeProvider([{"text": "Run about 12 km."}, {"text": "Keep it to the 8.0 km planned."}])

    result = _run(fake, request="How far on Thursday?")

    assert result["status"] == "answer"
    assert result["reply"] == "Keep it to the 8.0 km planned."
    assert fake.calls[1]["messages"][1] == {"role": "assistant", "content": [{"type": "text", "text": "Run about 12 km."}]}


def test_a_change_that_adds_a_spacing_clash_is_refused():
    rb = [
        {
            "id": 2, "day_index": 3, "position": 0, "kind": "run", "status": "planned", "focus": "", "planned_effort": "hard",
            "srpe": None, "z3_minutes": None, "muscle_groups": set(), "hard_set_groups": set(), "rated_set_groups": set(),
        },
        {
            "id": 9, "day_index": 4, "position": 0, "kind": "run", "status": "planned", "focus": "", "planned_effort": "hard",
            "srpe": None, "z3_minutes": None, "muscle_groups": set(), "hard_set_groups": set(), "rated_set_groups": set(),
        },
    ]
    hard = {"name": "set_planned_effort", "input": {"session_id": 2, "effort": "hard", "reason": "Make it a tempo."}}
    # The coach makes the change, finishes, is told about the clash, and finishes again unchanged.
    fake = FakeProvider([{"tool_calls": [hard]}, {}, {}])

    week = _week()
    friday = json.loads(json.dumps(week["sessions"][0]))
    friday.update(id=9, day_index=4, planned_effort="hard")
    friday["items"][0]["id"] = 90
    week["sessions"].append(friday)

    # Thursday isn't planned hard yet, so two hard runs a day apart is a new clash.
    result = _run(fake, rebalancer_sessions=[{**rb[0], "planned_effort": None}, rb[1]], week=week)

    assert result["status"] == "failed"
    assert "RULE-REC-02" in json.dumps(fake.calls[2]["messages"][-1]["content"])


def test_a_refusal_is_reported_without_a_retry():
    fake = FakeProvider([{"text": "", "stop_reason": "refusal"}])

    result = _run(fake)

    assert result["status"] == "failed"
    assert len(fake.calls) == 1


def test_the_payload_lists_the_week_compactly_and_marks_what_can_change():
    fake = FakeProvider([{"text": "OK."}])

    _run(fake)

    first = fake.calls[0]["messages"][0]["content"]
    payload = json.loads(first.split("<week>")[1].split("</week>")[0])
    assert payload["today"] == "2026-10-21"
    by_id = {s["id"]: s for s in payload["sessions"]}
    assert by_id[2]["can_change"] is True and by_id[1]["can_change"] is False
    assert by_id[2]["day"] == "Thu 2026-10-22"
    assert by_id[2]["items"] == [{"id": 20, "exercise": "easy_run", "volume": "8.0 km", "distance_meters": 8000.0}]
    assert first.rstrip().endswith("Move Thursday's run to Friday")


def test_the_system_prompt_and_tools_are_stable_and_cached():
    fake = FakeProvider([{"text": "OK."}, {"text": "OK."}])
    _run(fake)
    _run(fake, request="Something else")

    first, second = fake.calls
    assert first["system"] == second["system"]
    assert first["tools"] == second["tools"]
    assert first["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert first["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "dumbbell_bench_press" in first["system"][0]["text"]  # the catalog rides in the cached prefix


def test_payload_numbers_have_at_most_two_decimals():
    week = _week()
    week["sessions"][0]["items"][0]["distance_meters"] = 5600.000000001
    fake = FakeProvider([{"text": "OK."}])

    _run(fake, week=week)

    first = fake.calls[0]["messages"][0]["content"]
    assert "5600.000000001" not in first
    assert '"distance_meters": 5600.0' in first
