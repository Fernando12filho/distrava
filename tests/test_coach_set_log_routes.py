import re
from datetime import date, datetime, timedelta

import pytest

from app.coach import routes as coach_routes
from app.models import CoachSession, CoachSetLog, UserSettings

WEDNESDAY = date(2026, 10, 21)


class FrozenWednesday(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


@pytest.fixture()
def strength_on(make_activity):
    def _strength_on(day, activity_type="TraditionalStrengthTraining"):
        start = datetime(day.year, day.month, day.day, 18, 0)
        return make_activity(
            activity_type=activity_type,
            start_time=start,
            end_time=start + timedelta(minutes=55),
            duration_seconds=3300,
            distance_meters=0.0,
            dedup_key=f"{activity_type}|{start.isoformat()}|3300",
        )

    return _strength_on


def _add(client, template="legs_glutes", day_index=2):
    client.post("/coach/sessions", data={"template": template, "day_index": str(day_index), "week_start": "2026-10-19"})


def _session(db_session, focus="Legs & Glutes"):
    db_session.expire_all()
    return db_session.query(CoachSession).filter_by(focus=focus).one()


def _logged(db_session, focus="Legs & Glutes"):
    """{exercise name: [(set_number, reps, seconds, weight_kg, rir), ...]}"""
    return {
        item.exercise.name: [
            (s.set_number, s.reps, s.duration_seconds, s.weight_kg, s.rir) for s in item.logged_sets
        ]
        for item in _session(db_session, focus).items
    }


def _done(client, session_id, status="done"):
    return client.post(f"/coach/sessions/{session_id}/status", data={"status": status})


def _board(client, session_id):
    return client.get(f"/coach/?week=2026-10-19&session={session_id}").get_data(as_text=True)


def test_confirming_a_strength_import_fills_the_sets_from_the_plan(client, db_session, strength_on):
    _add(client)
    workout = strength_on(WEDNESDAY)
    session = _session(db_session)

    assert "Import matches" in _board(client, session.id)
    client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(workout.id)})

    logged = _logged(db_session)
    assert logged["Back squat"] == [(n, 6, None, None, None) for n in range(1, 5)]
    assert logged["Calf raise"] == [(n, 15, None, None, None) for n in range(1, 4)]
    assert _session(db_session).matched_activity_id == workout.id


@pytest.mark.parametrize("status", ["done", "partial"])
def test_marking_a_gym_session_done_or_partial_fills_the_sets(client, db_session, status):
    _add(client)
    _done(client, _session(db_session).id, status)

    assert len(_logged(db_session)["Back squat"]) == 4


def test_timed_sets_are_filled_with_their_planned_seconds(client, db_session):
    _add(client, "shoulders_abs")
    _done(client, _session(db_session, "Shoulders & Abs").id)

    assert _logged(db_session, "Shoulders & Abs")["Plank"] == [(n, None, 45, None, None) for n in range(1, 4)]


def test_a_planned_or_skipped_session_has_no_logged_sets(client, db_session):
    _add(client)
    session_id = _session(db_session).id
    _done(client, session_id, "skipped")

    assert all(sets == [] for sets in _logged(db_session).values())


def test_a_run_session_gets_no_set_rows(client, db_session):
    _add(client, "running_day")
    _done(client, _session(db_session, "Running day").id)

    assert _logged(db_session, "Running day") == {"Easy run": []}


def test_what_you_logged_survives_going_back_to_planned_and_done_again(client, db_session):
    _add(client)
    session_id = _session(db_session).id
    _done(client, session_id)
    first = _session(db_session).items[0].logged_sets[0]
    client.post(f"/coach/sets/{first.id}", data={"reps": "5", "weight": "100", "rir": "1"})

    _done(client, session_id, "planned")
    _done(client, session_id)

    squat = _logged(db_session)["Back squat"]
    assert len(squat) == 4
    assert squat[0] == (1, 5, None, 100.0, 1)


def test_editing_a_set_saves_reps_weight_and_reps_in_reserve(client, db_session):
    _add(client)
    _done(client, _session(db_session).id)
    first = _session(db_session).items[0].logged_sets[0]

    response = client.post(f"/coach/sets/{first.id}", data={"reps": "7", "weight": "92.5", "rir": "2"})

    assert response.status_code == 303
    assert _logged(db_session)["Back squat"][0] == (1, 7, None, 92.5, 2)


def test_an_invalid_set_edit_is_rejected_and_nothing_changes(client, db_session):
    _add(client)
    _done(client, _session(db_session).id)
    first = _session(db_session).items[0].logged_sets[0]

    response = client.post(f"/coach/sets/{first.id}", data={"reps": "7", "weight": "-3", "rir": "2"})

    assert response.status_code == 400
    assert _logged(db_session)["Back squat"][0] == (1, 6, None, None, None)


def test_weight_typed_in_pounds_is_stored_in_kg(client, db_session):
    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    _add(client)
    _done(client, _session(db_session).id)
    first = _session(db_session).items[0].logged_sets[0]

    client.post(f"/coach/sets/{first.id}", data={"reps": "6", "weight": "225", "rir": ""})

    assert _logged(db_session)["Back squat"][0][3] == 102.06


def test_adding_a_set_copies_the_last_sets_reps_and_weight_but_not_its_effort(client, db_session):
    _add(client)
    _done(client, _session(db_session).id)
    item = _session(db_session).items[0]
    client.post(f"/coach/sets/{item.logged_sets[-1].id}", data={"reps": "5", "weight": "100", "rir": "0"})

    response = client.post(f"/coach/items/{item.id}/sets")

    assert response.status_code == 303
    assert _logged(db_session)["Back squat"][-1] == (5, 5, None, 100.0, None)


def test_adding_a_set_to_an_exercise_without_sets_is_rejected(client, db_session):
    _add(client, "running_day")
    item = _session(db_session, "Running day").items[0]

    assert client.post(f"/coach/items/{item.id}/sets").status_code == 400


def test_removing_a_set_renumbers_the_rest(client, db_session):
    _add(client)
    _done(client, _session(db_session).id)
    second = _session(db_session).items[0].logged_sets[1]

    response = client.post(f"/coach/sets/{second.id}/delete")

    assert response.status_code == 303
    assert [s[0] for s in _logged(db_session)["Back squat"]] == [1, 2, 3]


@pytest.mark.parametrize("path", ["/coach/sets/999", "/coach/sets/999/delete", "/coach/items/999/sets"])
def test_unknown_ids_are_not_found(client, path):
    assert client.post(path).status_code == 404


def test_changing_the_plan_after_logging_leaves_what_was_done_alone(client, db_session):
    _add(client)
    _done(client, _session(db_session).id)
    item = _session(db_session).items[0]

    client.post(f"/coach/items/{item.id}/volume", data={"sets": "5", "reps": "3"})

    assert _logged(db_session)["Back squat"] == [(n, 6, None, None, None) for n in range(1, 5)]


def test_removing_the_session_removes_its_logged_sets(client, db_session):
    _add(client)
    session_id = _session(db_session).id
    _done(client, session_id)

    client.post(f"/coach/sessions/{session_id}/delete")

    db_session.expire_all()
    assert db_session.query(CoachSetLog).count() == 0


def test_the_board_shows_each_logged_set_with_its_values(client, db_session):
    _add(client)
    session_id = _session(db_session).id
    _done(client, session_id)
    first = _session(db_session).items[0].logged_sets[0]
    client.post(f"/coach/sets/{first.id}", data={"reps": "6", "weight": "102.5", "rir": "2"})

    html = _board(client, session_id)

    assert "Reps in reserve" in html
    form = re.search(rf'action="/coach/sets/{first.id}".*?</form>', html, re.S).group(0)
    assert 'name="reps"' in form and 'value="6"' in form
    assert 'name="weight"' in form and 'value="102.5"' in form
    assert 'name="rir"' in form and 'value="2"' in form
    assert "kg" in html


def test_rule_load_03_only_sets_you_rated_three_or_fewer_in_reserve_are_tagged_hard(client, db_session):
    _add(client)
    session_id = _session(db_session).id
    _done(client, session_id)
    sets = _session(db_session).items[0].logged_sets
    client.post(f"/coach/sets/{sets[0].id}", data={"reps": "6", "rir": "3"})
    client.post(f"/coach/sets/{sets[1].id}", data={"reps": "6", "rir": "4"})

    html = _board(client, session_id)

    assert html.count(">Hard set<") == 1
    assert "RULE-LOAD-03" in html


def test_a_planned_gym_session_shows_no_set_log(client, db_session):
    _add(client)

    assert "Reps in reserve" not in _board(client, _session(db_session).id)


def test_set_logging_copy_has_no_pressure_words(client, db_session):
    _add(client)
    session_id = _session(db_session).id
    _done(client, session_id, "partial")

    html = _board(client, session_id).lower()

    for word in ("missed", "failed", "streak"):
        assert word not in html
