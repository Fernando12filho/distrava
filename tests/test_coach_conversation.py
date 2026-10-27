"""One coach conversation across weeks (#43): the chat is the same on every
week's page, each message remembers the week it was asked from, and "New chat"
starts fresh.
"""

from app.models import CoachConversation, CoachProposal

from tests.test_preview_undo import WEEK, _ask, _latest, client, fake, frozen_today, keystore, week  # noqa: F401

NEXT = "2026-10-26"


def _thread(client, week_start):
    html = client.get(f"/coach/?week={week_start}").get_data(as_text=True)
    return html.split('<div class="coach-thread">', 1)[1].split("</aside>", 1)[0] if 'class="coach-thread"' in html else ""


def test_a_message_asked_on_one_week_shows_on_every_week(client, fake, week):
    fake.replies.append({"text": "Saturday is free."})

    _ask(client, "Can I move my run?")

    for week_start in (WEEK, NEXT):
        thread = _thread(client, week_start)
        assert "Can I move my run?" in thread and "Saturday is free." in thread


def test_a_message_from_another_week_is_labelled_with_its_week(client, fake, week):
    fake.replies.append({"text": "Saturday is free."})

    _ask(client, "Can I move my run?")

    assert "Week of Oct 19" in _thread(client, NEXT)
    assert "Week of Oct 19" not in _thread(client, WEEK)


def test_the_coach_hears_turns_asked_from_other_weeks(client, fake, week):
    fake.replies.extend([{"text": "Two options: easy or rest."}, {"text": "OK."}])

    _ask(client, "What should next week look like?")
    client.post(f"/coach/weeks/{NEXT}/ask", data={"message": "Go with the first option"})

    messages = fake.calls[1]["messages"]
    assert messages[0]["content"] == "(Asked while viewing the week of 2026-10-19.)\n\nWhat should next week look like?"
    assert messages[1]["content"] == "Two options: easy or rest."
    assert '"week_start": "2026-10-26"' in messages[-1]["content"]


def test_new_chat_starts_empty_and_the_coach_hears_none_of_the_old_one(client, db_session, fake, week):
    fake.replies.extend([{"text": "Saturday is free."}, {"text": "Hello again."}])
    _ask(client, "Can I move my run?")

    response = client.post("/coach/conversations", data={"week": NEXT})

    assert response.status_code == 303 and response.headers["Location"].endswith(f"week={NEXT}")
    assert "Can I move my run?" not in _thread(client, WEEK)
    _ask(client, "Hi")
    assert len(fake.calls[1]["messages"]) == 1
    db_session.expire_all()
    assert db_session.query(CoachConversation).count() == 2


def test_new_chat_drops_a_preview_still_waiting(client, db_session, fake, week):
    fake.replies.extend(
        [{"tool_calls": [{"name": "move_session", "input": {"session_id": week["run"], "day": 5, "reason": "Saturday is free."}}]}, {}]
    )
    _ask(client)
    assert _latest(db_session).status == "pending"

    client.post("/coach/conversations", data={"week": WEEK})

    db_session.expire_all()
    assert db_session.query(CoachProposal).filter_by(status="pending").count() == 0


def test_the_first_message_starts_a_conversation(client, db_session, fake, week):
    fake.replies.append({"text": "Hi."})

    _ask(client, "Hello")

    db_session.expire_all()
    conversation = db_session.query(CoachConversation).one()
    assert [p.request for p in conversation.proposals] == ["Hello"]


def test_new_chat_needs_a_valid_week_to_return_to(client):
    assert client.post("/coach/conversations", data={"week": "2026-10-21"}).status_code == 400


def test_the_panel_is_only_chat_and_the_week_info_sits_above_the_board(client, week):
    # #43, option B: Today, Hard sets and Week check describe the board, so they sit on it.
    html = client.get(f"/coach/?week={WEEK}").get_data(as_text=True)
    board, panel = html.split('<aside class="coach-panel"', 1)
    strip = board.split('<div class="week-strip">', 1)[1].split('<div class="week-grid"', 1)[0]

    for card in ("today-card", "hard-sets-card", "week-check-card"):
        assert f'class="{card}"' in strip
        assert card not in panel
