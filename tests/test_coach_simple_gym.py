"""The gym plan stays simple: pick the exercises, see suggested reps, log only if you want."""

import re
from datetime import date, datetime, timedelta

import pytest

from app.coach import routes as coach_routes
from app.models import CoachExercise, CoachProposal, CoachSession, CoachSetLog

WEEK = "2026-10-19"


class FrozenWednesday(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


@pytest.fixture(autouse=True)
def catalog(db_session):
    from app.coach.catalog import seed_catalog

    seed_catalog(db_session)


def _add(client, db_session, template="back_biceps", day_index=3):
    client.post("/coach/sessions", data={"template": template, "day_index": str(day_index), "week_start": WEEK})
    db_session.expire_all()
    return db_session.query(CoachSession).order_by(CoachSession.id.desc()).first()


def _page(client, session):
    return client.get(f"/coach/?week={WEEK}&session={session.id}").get_data(as_text=True)


def _slug(db_session, session_id, position=0):
    db_session.expire_all()
    return db_session.get(CoachSession, session_id).items[position].exercise.slug


# --- reps are a suggestion, the exercise is the choice ---------------------------


def test_a_gym_exercise_shows_its_reps_without_inputs(client, db_session):
    session = _add(client, db_session)

    page = _page(client, session)

    assert "4 × 5" in page
    assert 'name="sets"' not in page and 'name="reps"' not in page


def test_a_run_keeps_its_editable_distance(client, db_session):
    session = _add(client, db_session, "running_day")

    assert 'name="distance"' in _page(client, session)


def test_swapping_an_exercise_keeps_its_reps(client, db_session):
    session = _add(client, db_session)
    item = session.items[0]

    response = client.post(f"/coach/items/{item.id}/swap", data={"exercise": "bench_press"})

    assert response.status_code == 303
    assert _slug(db_session, session.id) == "bench_press"
    db_session.expire_all()
    assert (db_session.get(CoachSession, session.id).items[0].sets, db_session.get(CoachSession, session.id).items[0].reps) == (4, 5)


def test_the_swap_list_offers_only_exercises_of_the_same_kind(client, db_session):
    session = _add(client, db_session)

    form = re.search(r'action="/coach/items/%d/swap".*?</form>' % session.items[0].id, _page(client, session), re.S).group(0)

    assert "Bench press" in form
    assert "Easy run" not in form and "Pull-up</option>" not in form


@pytest.mark.parametrize("slug", ["easy_run", "not_a_real_exercise", ""])
def test_a_swap_to_a_different_kind_or_unknown_exercise_is_refused(client, db_session, slug):
    session = _add(client, db_session)

    assert client.post(f"/coach/items/{session.items[0].id}/swap", data={"exercise": slug}).status_code == 400
    assert _slug(db_session, session.id) == "pull_up"


def test_a_finished_session_cannot_be_swapped(client, db_session):
    session = _add(client, db_session)
    item_id = session.items[0].id
    client.post(f"/coach/sessions/{session.id}/status", data={"status": "done"})

    assert client.post(f"/coach/items/{item_id}/swap", data={"exercise": "barbell_row"}).status_code == 400


def test_an_added_exercise_goes_last_with_no_invented_volume(client, db_session):
    session = _add(client, db_session)

    response = client.post(f"/coach/sessions/{session.id}/items", data={"exercise": "face_pull"})

    assert response.status_code == 303
    db_session.expire_all()
    added = db_session.get(CoachSession, session.id).items[-1]
    assert (added.exercise.slug, added.sets, added.reps) == ("face_pull", None, None)


def test_adding_a_run_to_a_gym_session_is_refused(client, db_session):
    session = _add(client, db_session)

    assert client.post(f"/coach/sessions/{session.id}/items", data={"exercise": "easy_run"}).status_code == 400


# --- tracking sets and weight is optional ----------------------------------------


def test_finishing_a_gym_session_logs_nothing_by_itself(client, db_session):
    session = _add(client, db_session)

    client.post(f"/coach/sessions/{session.id}/status", data={"status": "done"})

    db_session.expire_all()
    assert db_session.query(CoachSetLog).count() == 0


def test_set_tracking_is_folded_away_and_starts_only_when_asked(client, db_session):
    session = _add(client, db_session)
    client.post(f"/coach/sessions/{session.id}/status", data={"status": "done"})

    page = _page(client, session)
    assert "Track sets and weight" in page and "<details" in page[page.index("session-detail") :]

    client.post(f"/coach/sessions/{session.id}/log")

    db_session.expire_all()
    assert db_session.query(CoachSetLog).count() == 4 + 4 + 3


def test_a_planned_session_offers_no_set_tracking(client, db_session):
    session = _add(client, db_session)

    assert "Track sets and weight" not in _page(client, session)
    assert client.post(f"/coach/sessions/{session.id}/log").status_code == 400


# --- the coach's card stays out of the way (DS-10) -------------------------------


def _proposal(db_session, session, status="accepted", reply="A long explanation the chat already shows."):
    from app.models import CoachConversation

    conversation = db_session.query(CoachConversation).first() or CoachConversation()
    db_session.add(conversation)
    proposal = CoachProposal(
        week=session.week,
        conversation=conversation,
        request="move it",
        reply=reply,
        status=status,
        calls=1,
        changes=["Back & Biceps: Thu → Fri"],
        before={},
        after={},
    )
    db_session.add(proposal)
    db_session.commit()
    return proposal


def test_a_pending_card_lists_changes_but_not_the_whole_reply(client, db_session):
    session = _add(client, db_session)
    _proposal(db_session, session, status="pending")

    page = _page(client, session)
    bar = re.search(r'<div class="proposal-bar.*?</form>\s*</div>\s*</div>', page, re.S).group(0)

    assert "Back &amp; Biceps: Thu → Fri" in bar
    assert "A long explanation" not in bar
    assert page.count("A long explanation") == 1


def test_an_accepted_change_leaves_no_card_and_undo_moves_to_the_chat(client, db_session):
    session = _add(client, db_session)
    proposal = _proposal(db_session, session)

    page = _page(client, session)

    assert "proposal-bar" not in page
    thread = page[page.index("coach-thread") :]
    assert f"/coach/proposals/{proposal.id}/undo" in thread


def test_a_refused_change_leaves_only_its_note_in_the_chat(client, db_session):
    session = _add(client, db_session)
    _proposal(db_session, session, status="stale")

    page = _page(client, session)

    assert "proposal-bar" not in page
    assert "Not applied: the week changed" in page


# --- moving through activities ---------------------------------------------------


@pytest.fixture()
def three_runs(make_activity):
    made = []
    for n, day in enumerate((5, 7, 9)):
        start = datetime(2026, 10, day, 8, 0)
        made.append(
            make_activity(
                start_time=start,
                end_time=start + timedelta(minutes=30),
                dedup_key=f"run-{n}",
                utc_offset_minutes=0,
            )
        )
    return made


def _nav(client, activity):
    html = client.get(f"/activities/{activity.id}").get_data(as_text=True)
    return re.search(r'<nav class="activity-nav".*?</nav>', html, re.S).group(0)


def test_an_activity_links_to_the_next_newer_and_older_ones(client, three_runs):
    older, middle, newer = three_runs

    nav = _nav(client, middle)

    assert f'href="/activities/{newer.id}"' in nav and f'href="/activities/{older.id}"' in nav


def test_the_newest_activity_has_nothing_newer(client, three_runs):
    older, middle, newest = three_runs

    nav = _nav(client, newest)

    assert 'data-nav="newer"' not in nav and f'href="/activities/{middle.id}"' in nav


def test_the_oldest_activity_has_nothing_older(client, three_runs):
    oldest, middle, _newer = three_runs

    assert 'data-nav="older"' not in _nav(client, oldest)


def test_two_activities_starting_together_can_still_be_walked_through(client, make_activity):
    start = datetime(2026, 10, 5, 8, 0)
    end = start + timedelta(minutes=30)
    first = make_activity(start_time=start, end_time=end, dedup_key="a", utc_offset_minutes=0)
    second = make_activity(start_time=start, end_time=end, activity_type="Walk", dedup_key="b", utc_offset_minutes=0)

    assert f'href="/activities/{second.id}"' in _nav(client, first)
    assert f'href="/activities/{first.id}"' in _nav(client, second)


def test_same_day_activities_have_titles_you_can_tell_apart(client, make_activity):
    start = datetime(2026, 10, 5, 8, 0)
    make_activity(start_time=start, end_time=start + timedelta(minutes=30), dedup_key="a", utc_offset_minutes=0)
    evening = start + timedelta(hours=10)
    later = make_activity(start_time=evening, end_time=evening + timedelta(minutes=30), dedup_key="b", utc_offset_minutes=0)

    assert "Oct 05, 2026 · 18:00" in client.get(f"/activities/{later.id}").get_data(as_text=True).split("page-title", 1)[1][:80]


@pytest.mark.parametrize("activity_type", ["Run", "TraditionalStrengthTraining", "Walk"])
def test_the_arrow_keys_are_available_on_every_type_of_activity(client, make_activity, activity_type):
    activity = make_activity(activity_type=activity_type)

    assert "activity-nav.js" in client.get(f"/activities/{activity.id}").get_data(as_text=True)


# --- leftovers from a session ticked and unticked -----------------------------------


def _ticked_then_unticked(client, db_session):
    session = _add(client, db_session)
    client.post(f"/coach/sessions/{session.id}/status", data={"status": "done"})
    client.post(f"/coach/sessions/{session.id}/log")
    client.post(f"/coach/sessions/{session.id}/status", data={"status": "planned"})
    db_session.expire_all()
    return db_session.get(CoachSession, session.id)


def test_untouched_copies_of_the_plan_do_not_lock_a_planned_exercise(client, db_session):
    session = _ticked_then_unticked(client, db_session)
    item_id = session.items[0].id

    assert f'action="/coach/items/{item_id}/swap"' in _page(client, session)
    assert client.post(f"/coach/items/{item_id}/swap", data={"exercise": "bench_press"}).status_code == 303

    db_session.expire_all()
    assert db_session.get(CoachSession, session.id).items[0].logged_sets == []


def test_sets_you_entered_still_lock_a_planned_exercise(client, db_session):
    session = _ticked_then_unticked(client, db_session)
    item = session.items[0]
    client.post(f"/coach/sets/{item.logged_sets[0].id}", data={"reps": "5", "weight": "20", "rir": ""})

    assert client.post(f"/coach/items/{item.id}/swap", data={"exercise": "bench_press"}).status_code == 400
    assert client.post(f"/coach/items/{item.id}/delete").status_code == 400
