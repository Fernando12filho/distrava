"""AC-04 and AC-10: a coach proposal is only a preview until accepted, a manual
edit is never overwritten by it, and undo puts the board back exactly.
"""

import json
import re
from datetime import date

import pytest
from sqlalchemy import text

from app import create_app
from app.coach import routes as coach_routes
from app.coach.keystore import MemoryKeystore
from app.coach.providers import FakeProvider, ProviderError
from app.models import CoachLlmCall, CoachProposal, CoachSession, CoachSessionItem, CoachWeek

KEY = "sk-ant-api03-Abc_def-123456789"
WEEK = "2026-10-19"


class FrozenWednesday(coach_routes.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


@pytest.fixture()
def fake():
    return FakeProvider([])


@pytest.fixture()
def keystore():
    store = MemoryKeystore()
    store.set(KEY)
    return store


@pytest.fixture()
def client(engine, keystore, fake):
    return create_app({"TESTING": True, "ENGINE": engine, "KEYSTORE": keystore, "PROVIDER_FACTORY": lambda key: fake}).test_client()


def _add(client, db_session, template, day_index):
    client.post("/coach/sessions", data={"template": template, "day_index": str(day_index), "week_start": WEEK})
    db_session.expire_all()
    return db_session.query(CoachSession).order_by(CoachSession.id.desc()).first().id


def _board_rows(db_session):
    """Every column of every board row: what "byte-for-byte" means here."""
    db_session.expire_all()
    rows = {}
    for table in ("coach_weeks", "coach_sessions", "coach_session_items", "coach_set_logs", "coach_checkins"):
        rows[table] = [tuple(r) for r in db_session.execute(text(f"SELECT * FROM {table} ORDER BY id")).fetchall()]
    return rows


def _ask(client, message="Move Thursday's run to Saturday"):
    return client.post(f"/coach/weeks/{WEEK}/ask", data={"message": message})


def _latest(db_session):
    db_session.expire_all()
    return db_session.query(CoachProposal).order_by(CoachProposal.id.desc()).first()


def _call(name, reason="Saturday is free.", **arguments):
    return {"name": name, "input": {**arguments, "reason": reason}}


@pytest.fixture()
def week(client, db_session):
    return {
        "run": _add(client, db_session, "running_day", 3),
        "chest": _add(client, db_session, "chest_triceps", 4),
        "ride": _add(client, db_session, "easy_ride", 6),
    }


# --- asking -----------------------------------------------------------------------


def test_ac_04_a_proposal_writes_nothing_to_the_board(client, db_session, fake, week):
    before = _board_rows(db_session)
    fake.replies.append({"tool_calls": [_call("move_session", session_id=week["run"], day=5)]})
    fake.replies.append({})

    response = _ask(client)

    assert response.status_code == 303
    assert _board_rows(db_session) == before
    proposal = _latest(db_session)
    assert proposal.status == "pending"
    assert proposal.request == "Move Thursday's run to Saturday"
    assert proposal.changes == ["Running day: Thu → Sat"]
    # Every round is recorded: the change, then the coach finishing.
    assert db_session.query(CoachLlmCall).filter_by(task="coach").count() == 2


def test_the_board_shows_the_preview_faded_with_why_accept_and_discard(client, db_session, fake, week):
    fake.replies.append({"tool_calls": [_call("move_session", session_id=week["run"], day=5)]})
    fake.replies.append({})
    _ask(client)
    proposal = _latest(db_session)

    html = client.get(f"/coach/?week={WEEK}").get_data(as_text=True)

    bar = re.search(r'<div class="proposal-bar".*?</div>\s*</div>', html, re.S).group(0)
    assert "Saturday is free." in bar
    assert "Running day: Thu → Sat" in bar
    assert f'action="/coach/proposals/{proposal.id}/accept"' in bar
    assert f'action="/coach/proposals/{proposal.id}/discard"' in bar
    assert html.count("session-card ghost-remove") == 1
    assert html.count("session-card ghost-add") == 1
    assert "PROPOSED" in html
    # The thread keeps the request and the reply.
    assert "Move Thursday&#39;s run to Saturday" in html


def test_asking_without_a_key_changes_nothing_and_calls_nobody(engine, db_session, fake):
    client = create_app({"TESTING": True, "ENGINE": engine, "KEYSTORE": MemoryKeystore(), "PROVIDER_FACTORY": lambda key: fake}).test_client()

    response = _ask(client)

    assert response.status_code == 303
    assert fake.calls == []
    assert db_session.query(CoachProposal).count() == 0


def test_an_empty_message_is_refused(client, fake, week):
    assert client.post(f"/coach/weeks/{WEEK}/ask", data={"message": "  "}).status_code == 400
    assert fake.calls == []


def test_asking_on_a_week_without_a_plan_creates_the_week(client, db_session, fake):
    fake.replies.append({"text": "Nothing is planned yet."})

    _ask(client, "What's planned?")

    proposal = _latest(db_session)
    assert proposal.status == "answer"
    assert proposal.reply == "Nothing is planned yet."


def test_a_provider_error_is_shown_and_nothing_changes(client, db_session, fake, week):
    before = _board_rows(db_session)
    fake.replies.append(ProviderError("rate_limit"))

    _ask(client)

    proposal = _latest(db_session)
    assert proposal.status == "failed"
    assert "Too many requests" in proposal.reply
    assert _board_rows(db_session) == before
    html = client.get(f"/coach/?week={WEEK}").get_data(as_text=True)
    assert "Too many requests" in html


def test_the_coach_hears_this_weeks_earlier_turns(client, db_session, fake, week):
    fake.replies.extend([{"text": "Two options: move the run, or plan it easy."}, {"text": "Done."}])

    _ask(client, "Review my week")
    _ask(client, "Do the first option")

    messages = fake.calls[1]["messages"]
    assert [m["content"] for m in messages[:2]] == ["Review my week", "Two options: move the run, or plan it easy."]
    assert messages[-1]["content"].endswith("Do the first option")


def test_the_coach_can_read_another_week_from_the_board(client, db_session, fake, week):
    client.post("/coach/sessions", data={"template": "easy_ride", "day_index": "1", "week_start": "2026-10-12"})
    fake.replies.extend([{"tool_calls": [{"name": "get_week", "input": {"week_start": "2026-10-12"}}]}, {"text": "Last week had a ride."}])

    _ask(client, "What did I do last week?")

    seen = json.loads(fake.calls[1]["messages"][-1]["content"][0]["content"])
    assert seen["week_start"] == "2026-10-12"
    assert [s["day"] for s in seen["sessions"]] == ["Tue 2026-10-13"]
    assert all(s["can_change"] is False for s in seen["sessions"])  # a past week is history
    assert _latest(db_session).status == "answer"


def test_reading_a_week_with_no_plan_says_it_is_empty(client, db_session, fake, week):
    fake.replies.extend([{"tool_calls": [{"name": "get_week", "input": {"week_start": "2026-11-02"}}]}, {"text": "Nothing planned yet."}])

    _ask(client, "What's planned in two weeks?")

    seen = json.loads(fake.calls[1]["messages"][-1]["content"][0]["content"])
    assert seen["sessions"] == [] and seen["week_start"] == "2026-11-02"
    db_session.expire_all()
    assert db_session.query(CoachWeek).filter_by(week_start=date(2026, 11, 2)).count() == 0  # reading never creates


def test_check_plan_from_the_board_has_the_weeks_distance_inputs(client, db_session, fake, week):
    fake.replies.extend([{"tool_calls": [{"name": "check_plan", "input": {}}]}, {"text": "All clear."}])

    _ask(client, "Is this week OK?")

    checked = json.loads(fake.calls[1]["messages"][-1]["content"][0]["content"])
    assert checked["clashes"] == []
    # No runs in the last two weeks: no baseline, so no distance change to report.
    assert checked["distance"] is None
    assert _latest(db_session).status == "answer"


def test_check_plan_compares_the_draft_with_the_last_two_weeks_of_runs(client, db_session, fake, week, make_activity):
    from datetime import datetime

    for n, day in enumerate((date(2026, 10, 7), date(2026, 10, 14), date(2026, 10, 19))):
        start = datetime.combine(day, datetime.min.time()).replace(hour=8)
        meters = 2000.0 if day.day == 19 else 5000.0
        make_activity(start_time=start, end_time=start, distance_meters=meters, source_id=f"run-{n}", dedup_key=f"Run|{start.isoformat()}|1800")
    fake.replies.extend([{"tool_calls": [{"name": "check_plan", "input": {}}]}, {"text": "All clear."}])

    _ask(client, "Is this week OK?")

    checked = json.loads(fake.calls[1]["messages"][-1]["content"][0]["content"])
    # RULE-PROG-02: Monday's 2 km plus Thursday's planned 8 km against a 5 km average.
    assert checked["distance"] == {"this_week_meters": 10000.0, "baseline_meters": 5000.0, "pct": 100.0, "level": "big"}


def test_a_new_request_replaces_the_pending_preview(client, db_session, fake, week):
    fake.replies.append({"tool_calls": [_call("move_session", session_id=week["run"], day=5)]})
    fake.replies.append({})
    _ask(client)
    first = _latest(db_session).id
    fake.replies.append({"tool_calls": [_call("remove_session", session_id=week["ride"], reason="Rest on Sunday.")]})
    fake.replies.append({})

    _ask(client, "Drop Sunday")

    db_session.expire_all()
    assert db_session.get(CoachProposal, first).status == "discarded"
    assert _latest(db_session).status == "pending"


# --- accept, discard, undo ----------------------------------------------------------


def test_accept_applies_the_change(client, db_session, fake, week):
    fake.replies.append({"tool_calls": [_call("move_session", session_id=week["run"], day=5)]})
    fake.replies.append({})
    _ask(client)
    proposal = _latest(db_session)

    response = client.post(f"/coach/proposals/{proposal.id}/accept")

    assert response.status_code == 303
    db_session.expire_all()
    assert db_session.get(CoachSession, week["run"]).day_index == 5
    assert db_session.get(CoachProposal, proposal.id).status == "accepted"
    html = client.get(f"/coach/?week={WEEK}").get_data(as_text=True)
    assert f'action="/coach/proposals/{proposal.id}/undo"' in html


def test_discard_leaves_the_board_alone(client, db_session, fake, week):
    before = _board_rows(db_session)
    fake.replies.append({"tool_calls": [_call("move_session", session_id=week["run"], day=5)]})
    fake.replies.append({})
    _ask(client)
    proposal = _latest(db_session)

    client.post(f"/coach/proposals/{proposal.id}/discard")

    assert _board_rows(db_session) == before
    assert _latest(db_session).status == "discarded"
    assert "ghost-add" not in client.get(f"/coach/?week={WEEK}").get_data(as_text=True)


def test_ac_10_undo_restores_the_board_byte_for_byte(client, db_session, fake, week):
    db_session.expire_all()
    chest = db_session.get(CoachSession, week["chest"])
    bench, incline = chest.items[0].id, chest.items[1].id
    run_item = db_session.get(CoachSession, week["run"]).items[0].id
    before = _board_rows(db_session)
    fake.replies.append(
        {
            "tool_calls": [
                _call("move_session", session_id=week["run"], day=5),
                _call("adjust_item", item_id=run_item, sets=None, reps=None, duration_seconds=None, distance_meters=6000.0),
                _call("swap_exercise", item_id=bench, exercise="dumbbell_bench_press"),
                _call("adjust_item", item_id=incline, sets=2, reps=10, duration_seconds=None, distance_meters=None),
                _call("set_planned_effort", session_id=week["chest"], effort="hard"),
                _call("remove_session", session_id=week["ride"]),
            ]
        }
    )
    fake.replies.append({})
    _ask(client)
    proposal = _latest(db_session)
    client.post(f"/coach/proposals/{proposal.id}/accept")
    assert _board_rows(db_session) != before
    db_session.expire_all()
    assert db_session.get(CoachSession, week["ride"]) is None

    client.post(f"/coach/proposals/{proposal.id}/undo")

    assert _board_rows(db_session) == before
    assert _latest(db_session).status == "undone"


def test_ac_04_a_manual_edit_after_the_preview_blocks_accept(client, db_session, fake, week):
    fake.replies.append({"tool_calls": [_call("move_session", session_id=week["run"], day=5)]})
    fake.replies.append({})
    _ask(client)
    proposal = _latest(db_session)
    client.post(f"/coach/sessions/{week['run']}/move", data={"day_index": "4"})
    before = _board_rows(db_session)

    client.post(f"/coach/proposals/{proposal.id}/accept")

    assert _board_rows(db_session) == before
    assert _latest(db_session).status == "stale"
    html = client.get(f"/coach/?week={WEEK}").get_data(as_text=True)
    assert "The week changed since" in html


def test_undo_is_refused_once_the_session_was_used(client, db_session, fake, week):
    fake.replies.append({"tool_calls": [_call("move_session", session_id=week["run"], day=2)]})
    fake.replies.append({})
    _ask(client)
    proposal = _latest(db_session)
    client.post(f"/coach/proposals/{proposal.id}/accept")
    client.post(f"/coach/sessions/{week['run']}/status", data={"status": "done"})
    before = _board_rows(db_session)

    client.post(f"/coach/proposals/{proposal.id}/undo")

    assert _board_rows(db_session) == before
    assert _latest(db_session).status == "accepted"
    html = client.get(f"/coach/?week={WEEK}").get_data(as_text=True)
    assert f'action="/coach/proposals/{proposal.id}/undo"' not in html


@pytest.mark.parametrize("action", ["accept", "discard"])
def test_only_a_pending_proposal_can_be_accepted_or_discarded(client, db_session, fake, week, action):
    fake.replies.append({"text": "Just an answer."})
    _ask(client, "What's on Thursday?")
    proposal = _latest(db_session)

    assert client.post(f"/coach/proposals/{proposal.id}/{action}").status_code == 400
    assert client.post("/coach/proposals/999/accept").status_code == 404


def test_only_an_accepted_proposal_can_be_undone(client, db_session, fake, week):
    fake.replies.append({"tool_calls": [_call("move_session", session_id=week["run"], day=5)]})
    fake.replies.append({})
    _ask(client)
    assert client.post(f"/coach/proposals/{_latest(db_session).id}/undo").status_code == 400
