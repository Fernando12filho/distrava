"""Import a simulated watch export through the real route, then check what the app shows.

The scenarios copy shapes found in real exports: a lift then a run the same
afternoon, a run with a cooldown walk, a workout restarted minutes later, an
export that simply has more in it next time.
"""

from datetime import datetime

import pytest

from app.coach import routes as coach_routes
from app.models import Activity, CoachSession
from simulated_export import Workout, upload

WEEK = "2026-11-09"
MONDAY = datetime(2026, 11, 9)


class FrozenFriday(coach_routes.date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 13)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenFriday)


def at(day_offset, hour, minute=0):
    return MONDAY.replace(day=9 + day_offset, hour=hour, minute=minute)


LIFT = {"kind": "Strength", "minutes": 34.0}
RUN = {"kind": "Run", "minutes": 42.0, "km": 8.0}


def _add(client, db_session, template, day_index, week=WEEK):
    client.post("/coach/sessions", data={"template": template, "day_index": str(day_index), "week_start": week})
    db_session.expire_all()
    return db_session.query(CoachSession).order_by(CoachSession.id.desc()).first()


def _activities(db_session):
    db_session.expire_all()
    return db_session.query(Activity).order_by(Activity.start_time).all()


def _matches(db_session, week=WEEK):
    db_session.expire_all()
    return coach_routes._week_matches(db_session, coach_routes.date.fromisoformat(week))[0]


def _board(client, week=WEEK):
    return client.get(f"/coach/?week={week}").get_data(as_text=True)


def _confirm(client, session, activity):
    return client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(activity.id)})


# --- what lands in the database --------------------------------------------------


def test_a_lift_and_a_run_on_the_same_day_are_two_activities(client, db_session):
    response = upload(client, [Workout(start=at(0, 16, 36), **LIFT), Workout(start=at(0, 17, 44), **RUN)])

    assert response.status_code == 200
    assert [a.activity_type for a in _activities(db_session)] == ["TraditionalStrengthTraining", "Run"]


def test_two_runs_minutes_apart_stay_two_activities(client, db_session):
    upload(
        client,
        [
            Workout(kind="Run", start=at(0, 16, 6), minutes=10.0, km=1.8),
            Workout(kind="Run", start=at(0, 16, 20), minutes=7.0, km=1.2),
        ],
    )

    assert [round(a.distance_meters) for a in _activities(db_session)] == [1800, 1200]


def test_a_run_and_its_cooldown_walk_keep_their_own_data(client, db_session):
    upload(
        client,
        [
            Workout(kind="Run", start=at(0, 10, 45), minutes=48.0, km=8.03, avg_hr=151.0),
            Workout(kind="Walk", start=at(0, 11, 34), minutes=6.0, km=0.53, avg_hr=118.0),
        ],
    )

    run, walk = _activities(db_session)
    assert (round(run.distance_meters), run.avg_hr) == (8030, 151.0)
    assert (round(walk.distance_meters), walk.avg_hr) == (530, 118.0)


def test_watch_and_phone_logging_one_run_is_one_activity_at_watch_distance(client, db_session):
    upload(client, [Workout(start=at(0, 8), phone_km=8.2, **RUN), Workout(start=at(0, 8), device="Runner’s iPhone", samples=False, **RUN)])

    activities = _activities(db_session)
    assert len(activities) == 1
    assert activities[0].distance_meters == 8000.0
    assert activities[0].streams[0].stream_data["distance"][-1] == pytest.approx(8000.0, abs=1.0)


def test_a_type_the_app_has_no_session_for_still_imports(client, db_session):
    upload(client, [Workout(kind="Cooldown", start=at(0, 15, 13), minutes=35.0)])

    assert _activities(db_session)[0].activity_type == "Cooldown"


def test_a_watch_summary_without_samples_still_gives_heart_rate(client, db_session):
    upload(client, [Workout(start=at(0, 8), samples=False, avg_hr=151.0, **{k: v for k, v in RUN.items()})])

    assert _activities(db_session)[0].avg_hr == 151.0


def test_an_evening_workout_keeps_its_local_day(client, db_session):
    # 21:30 at UTC-5 is already the next day in UTC.
    upload(client, [Workout(start=at(1, 21, 30), **RUN)])

    assert _activities(db_session)[0].local_start_time.date() == at(1, 0).date()


# --- importing again --------------------------------------------------------------


def test_importing_the_same_export_twice_adds_nothing(client, db_session):
    export = [Workout(start=at(0, 16, 36), **LIFT), Workout(start=at(0, 17, 44), **RUN)]
    upload(client, export)

    second = upload(client, export).get_json()

    assert (second["imported"], second["skipped"]) == (0, 2)
    assert len(_activities(db_session)) == 2


def test_a_longer_export_adds_only_what_is_new_and_keeps_links(client, db_session):
    first = [Workout(start=at(0, 8), **RUN)]
    session = _add(client, db_session, "running_day", 0)
    upload(client, first)
    run = _activities(db_session)[0]
    _confirm(client, session, run)
    run_id = run.id

    upload(client, first + [Workout(start=at(2, 8), **RUN)])

    assert len(_activities(db_session)) == 2
    assert db_session.get(CoachSession, session.id).matched_activity_id == run_id


# --- what the board does with it --------------------------------------------------


def test_a_lift_and_a_run_each_match_their_own_session(client, db_session):
    lift = _add(client, db_session, "chest_triceps", 0)
    run = _add(client, db_session, "running_day", 0)
    upload(client, [Workout(start=at(0, 16, 36), **LIFT), Workout(start=at(0, 17, 44), **RUN)])

    matches = _matches(db_session)
    activities = _activities(db_session)

    assert matches[lift.id] == {"kind": "match", "activity_ids": [activities[0].id]}
    assert matches[run.id] == {"kind": "match", "activity_ids": [activities[1].id]}


def test_a_workout_with_no_session_still_shows_on_its_day(client, db_session):
    _add(client, db_session, "chest_triceps", 0)
    upload(client, [Workout(start=at(0, 16, 36), **LIFT), Workout(kind="Run", start=at(0, 17, 44), minutes=39.0, km=5.02)])

    assert "Run · 5.02 km · 39:00 · 17:44" in _board(client)


def test_a_workout_already_offered_is_not_listed_twice(client, db_session):
    _add(client, db_session, "chest_triceps", 0)
    upload(client, [Workout(start=at(0, 16, 36), **LIFT)])

    assert _board(client).count("· 16:36") == 1


def test_a_strength_workout_is_not_labelled_with_zero_distance(client, db_session):
    _add(client, db_session, "chest_triceps", 0)
    upload(client, [Workout(start=at(0, 16, 36), **LIFT)])

    assert "0.00 km" not in _board(client)


def test_two_runs_with_different_plans_separate_by_distance(client, db_session):
    short = _add(client, db_session, "running_day", 0)
    db_session.get(CoachSession, short.id).items[0].distance_meters = 3000.0
    db_session.commit()
    long_run = _add(client, db_session, "running_day", 0)
    upload(client, [Workout(kind="Run", start=at(0, 7), minutes=16.0, km=3.0), Workout(start=at(0, 18), **RUN)])

    matches = _matches(db_session)
    morning, evening = _activities(db_session)

    assert matches[short.id] == {"kind": "match", "activity_ids": [morning.id]}
    assert matches[long_run.id] == {"kind": "match", "activity_ids": [evening.id]}


def test_two_identical_sessions_ask_then_narrow_after_the_first_answer(client, db_session):
    first = _add(client, db_session, "chest_triceps", 0)
    second = _add(client, db_session, "back_biceps", 0)
    upload(client, [Workout(start=at(0, 10, 34), **LIFT), Workout(start=at(0, 11, 17), **LIFT)])
    morning, later = _activities(db_session)

    assert _matches(db_session)[first.id]["kind"] == "ask"
    _confirm(client, first, later)

    assert _matches(db_session)[second.id] == {"kind": "match", "activity_ids": [morning.id]}


def test_a_session_ticked_off_by_hand_can_be_linked_after_the_import(client, db_session):
    session = _add(client, db_session, "chest_triceps", 0)
    client.post(f"/coach/sessions/{session.id}/status", data={"status": "partial"})
    upload(client, [Workout(start=at(0, 16, 36), **LIFT)])
    lift = _activities(db_session)[0]

    assert _matches(db_session)[session.id] == {"kind": "link", "activity_ids": [lift.id]}
    _confirm(client, session, lift)

    db_session.expire_all()
    linked = db_session.get(CoachSession, session.id)
    assert (linked.matched_activity_id, linked.status) == (lift.id, "partial")


def test_a_whole_week_replayed_links_every_workout_once(client, db_session):
    plan = [("chest_triceps", 0), ("back_biceps", 1), ("running_day", 2), ("legs_glutes", 4), ("running_day", 5)]
    sessions = [_add(client, db_session, template, day) for template, day in plan]
    upload(
        client,
        [
            Workout(start=at(0, 16), **LIFT),
            Workout(start=at(1, 16), **LIFT),
            Workout(start=at(2, 17), **RUN),
            Workout(start=at(4, 16), **LIFT),
            Workout(start=at(5, 9), **RUN),
        ],
    )

    for session in sessions:
        result = _matches(db_session)[session.id]
        assert result["kind"] == "match"
        client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(result["activity_ids"][0])})

    db_session.expire_all()
    linked = [db_session.get(CoachSession, s.id).matched_activity_id for s in sessions]
    assert len(set(linked)) == 5
    assert _matches(db_session) == {}
