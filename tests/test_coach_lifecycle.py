"""Real sequences of actions, where single-rule tests can't see the bug.

Each rule has its own tests elsewhere. These replay the order things happen in
actual use: a session marked done by hand before the import exists, a workout
on the edge of two weeks, a status changed twice.
"""

import json
import re
from datetime import datetime, timedelta

import pytest

from app.coach import routes as coach_routes
from app.coach import set_log, volume
from app.models import ActivityStream, CoachSession, CoachSetLog

WEEK = "2026-10-19"
NEXT_WEEK = "2026-10-26"


class FrozenWednesday(coach_routes.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


@pytest.fixture()
def workout(make_activity):
    def _workout(day, activity_type="Run", distance=8040.0, duration=2712, hour=7, offset=0):
        start = datetime(day.year, day.month, day.day, hour, 6)
        return make_activity(
            activity_type=activity_type,
            start_time=start,
            end_time=start + timedelta(seconds=duration),
            duration_seconds=duration,
            distance_meters=distance,
            utc_offset_minutes=offset,
            dedup_key=f"{activity_type}|{start.isoformat()}|{duration}",
        )

    return _workout


def _add(client, db_session, template, day_index, week=WEEK):
    client.post("/coach/sessions", data={"template": template, "day_index": str(day_index), "week_start": week})
    db_session.expire_all()
    return db_session.query(CoachSession).order_by(CoachSession.id.desc()).first()


def _board(client, week=WEEK, session=None):
    query = f"week={week}" + (f"&session={session}" if session else "")
    return client.get(f"/coach/?{query}").get_data(as_text=True)


def _offers(db_session, week):
    db_session.expire_all()
    return coach_routes._week_matches(db_session, coach_routes.date.fromisoformat(week))[0]


def _start_log(client, session):
    client.post(f"/coach/sessions/{session.id}/log")


def _status(client, session, status):
    client.post(f"/coach/sessions/{session.id}/status", data={"status": status})


def _reload(db_session, session_id):
    db_session.expire_all()
    return db_session.get(CoachSession, session_id)


TEMPLATES = {
    "gym": ("chest_triceps", "back_biceps", {"activity_type": "TraditionalStrengthTraining", "distance": 0.0}),
    "run": ("running_day", "running_day", {}),
}


# --- AC-06: which session does an import belong to? ------------------------------


@pytest.mark.parametrize("status", ["done", "partial"])
@pytest.mark.parametrize("kind", ["gym", "run"])
def test_ac06_an_import_on_a_day_already_ticked_off_is_not_offered_to_the_next_day(
    client, db_session, workout, kind, status
):
    first, second, shape = TEMPLATES[kind]
    monday = _add(client, db_session, first, 0)
    tuesday = _add(client, db_session, second, 1)
    _status(client, monday, status)

    # The import lands after the tick, which is the normal order: you train,
    # tick it off, and export from the watch days later.
    workout(datetime(2026, 10, 19), **shape)

    assert tuesday.id not in _offers(db_session, WEEK)


def test_ac06_a_sunday_run_that_fits_sunday_is_not_offered_to_the_next_monday(client, db_session, workout):
    _add(client, db_session, "running_day", 6, WEEK)
    monday = _add(client, db_session, "running_day", 0, NEXT_WEEK)
    workout(datetime(2026, 10, 25))

    assert monday.id not in _offers(db_session, NEXT_WEEK)


def test_ac06_a_monday_run_that_fits_monday_is_not_offered_to_the_previous_sunday(client, db_session, workout):
    sunday = _add(client, db_session, "running_day", 6, WEEK)
    _add(client, db_session, "running_day", 0, NEXT_WEEK)
    workout(datetime(2026, 10, 26))

    assert sunday.id not in _offers(db_session, WEEK)


def test_ac06_a_late_evening_workout_counts_on_its_local_day(client, db_session, workout):
    wednesday = _add(client, db_session, "running_day", 2)
    # 02:06 UTC Thursday is 21:06 Wednesday at UTC-5.
    workout(datetime(2026, 10, 22), hour=2, offset=-300)

    assert "Import matches" in _board(client, session=wednesday.id)


def test_skipping_a_confirmed_session_releases_its_import(client, db_session, workout):
    session = _add(client, db_session, "running_day", 2)
    run = workout(datetime(2026, 10, 21))
    client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(run.id)})

    _status(client, session, "skipped")

    assert _reload(db_session, session.id).matched_activity_id is None


def test_wiping_activities_does_not_link_old_sessions_to_new_imports(client, db_session, workout):
    session = _add(client, db_session, "running_day", 2)
    run = workout(datetime(2026, 10, 21))
    client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(run.id)})

    client.post("/settings/wipe")
    # SQLite hands an emptied table's ids out again, so this can be the same id.
    unrelated = workout(datetime(2026, 10, 5), distance=3000.0, duration=900)

    assert _reload(db_session, session.id).matched_activity_id != unrelated.id


# --- logged sets follow what actually happened -----------------------------------


@pytest.mark.parametrize("new_status", ["planned", "skipped"])
def test_sets_of_a_session_that_is_no_longer_done_do_not_count_for_the_week(client, db_session, new_status):
    session = _add(client, db_session, "legs_glutes", 2)
    _status(client, session, "done")
    _start_log(client, session)
    db_session.expire_all()
    assert db_session.query(CoachSetLog).count() > 0

    _status(client, session, new_status)
    db_session.expire_all()

    assert coach_routes._week_logged_sets(db_session, FrozenWednesday(2026, 10, 19)) == []


def test_removing_an_exercise_from_the_plan_keeps_what_you_logged(client, db_session):
    # plan.md §4: "editing the plan later never changes" a finished session.
    session = _add(client, db_session, "legs_glutes", 2)
    _status(client, session, "done")
    _start_log(client, session)
    session = _reload(db_session, session.id)
    item_id = session.items[0].id
    before = db_session.query(CoachSetLog).count()

    client.post(f"/coach/items/{item_id}/delete")

    db_session.expire_all()
    assert db_session.query(CoachSetLog).count() == before


# --- what you type is what you get back ------------------------------------------


@pytest.mark.parametrize("units", ["metric", "imperial"])
@pytest.mark.parametrize("typed", ["5.25", "8.25", "10.05"])
def test_a_planned_distance_shows_back_exactly_as_typed(units, typed):
    # The form reposts what it shows, so a rounded display silently rewrites
    # the plan the next time Save is pressed.
    stored = volume.parse_volume("distance", {"distance": typed}, units)

    assert volume.form_values(stored, units)["distance"] == typed


@pytest.mark.parametrize("units", ["metric", "imperial"])
@pytest.mark.parametrize("typed", ["45", "102.5", "135", "225"])
def test_a_logged_weight_shows_back_exactly_as_typed(units, typed):
    stored = set_log.parse_set("reps", {"reps": "5", "weight": typed}, units)

    assert set_log.weight_value(stored["weight_kg"], units) == typed


def test_undoing_the_easing_keeps_an_edit_made_since(client, db_session, workout):
    # D7: undo restores what easing changed, not what you changed afterwards.
    workout(datetime(2026, 10, 7))
    session = _add(client, db_session, "running_day", 4)
    assert client.post(f"/coach/weeks/{WEEK}/ease", data={"factor": "0.8"}).status_code == 303
    item_id = _reload(db_session, session.id).items[0].id

    client.post(f"/coach/items/{item_id}/volume", data={"distance": "6.5"})
    client.post(f"/coach/weeks/{WEEK}/ease/undo")

    assert _reload(db_session, session.id).items[0].distance_meters == 6500.0


# --- odd input and the 2-decimal rule --------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["/activities?page=abc", "/coach/?week=0001-01-01", "/coach/?week=9999-12-27"],
)
def test_a_bad_url_never_crashes(client, url):
    assert client.get(url).status_code < 500


def test_the_stream_payload_has_at_most_two_decimals(client, db_session, make_activity):
    activity = make_activity()
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={
                "time": [0, 10],
                "hr": [140.123, 141.456],
                "pace": [5.12345, 5.6789],
                "elevation": [10.2685, 11.1111],
                "distance": [0.0, 28.3333],
            },
        )
    )
    db_session.commit()

    payload = json.dumps(client.get(f"/activities/{activity.id}/stream.json").get_json())

    assert not re.search(r"\d\.\d{3,}", payload)
