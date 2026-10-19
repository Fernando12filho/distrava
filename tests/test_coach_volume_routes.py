import re
from datetime import date, datetime, timedelta

import pytest

from app.coach import routes as coach_routes
from app.models import CoachSession, CoachSessionItem, UserSettings


class FrozenWednesday(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


def _add(client, template, day_index=2):
    client.post("/coach/sessions", data={"template": template, "day_index": str(day_index), "week_start": "2026-10-19"})


def _items(db_session):
    db_session.expire_all()
    return db_session.query(CoachSession).one().items


def test_editing_sets_and_reps_saves_them(client, db_session):
    _add(client, "chest_triceps")
    bench = _items(db_session)[0]

    response = client.post(f"/coach/items/{bench.id}/volume", data={"sets": "5", "reps": "5"})

    assert response.status_code == 303
    assert f"session={bench.session_id}" in response.headers["Location"]
    edited = _items(db_session)[0]
    assert (edited.sets, edited.reps) == (5, 5)


def test_editing_a_distance_in_miles_stores_metres(client, db_session):
    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    _add(client, "running_day")
    run = _items(db_session)[0]

    client.post(f"/coach/items/{run.id}/volume", data={"distance": "3.1"})

    assert _items(db_session)[0].distance_meters == pytest.approx(4988.97)


def test_editing_minutes_on_a_timed_exercise(client, db_session):
    _add(client, "mobility")
    flow = _items(db_session)[0]

    client.post(f"/coach/items/{flow.id}/volume", data={"minutes": "15"})

    assert _items(db_session)[0].duration_seconds == 900


def test_an_impossible_volume_is_rejected_and_nothing_changes(client, db_session):
    _add(client, "chest_triceps")
    bench = _items(db_session)[0]

    response = client.post(f"/coach/items/{bench.id}/volume", data={"sets": "0", "reps": "5"})

    assert response.status_code == 400
    assert (_items(db_session)[0].sets, _items(db_session)[0].reps) == (4, 6)


def test_editing_an_unknown_exercise_is_404(client):
    assert client.post("/coach/items/999/volume", data={"sets": "3", "reps": "8"}).status_code == 404


def test_detail_prefills_each_exercise_in_its_own_shape(client, db_session):
    _add(client, "shoulders_abs")
    session = db_session.query(CoachSession).one()

    html = client.get(f"/coach/?session={session.id}").get_data(as_text=True)

    assert re.search(r'name="sets"[^>]*value="4"', html)
    assert re.search(r'name="reps"[^>]*value="6"', html)
    assert re.search(r'name="seconds"[^>]*value="45"', html)


def test_detail_prefills_distance_in_the_users_units(client, db_session):
    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    _add(client, "running_day")
    session = db_session.query(CoachSession).one()

    html = client.get(f"/coach/?session={session.id}").get_data(as_text=True)

    assert re.search(r'name="distance"[^>]*value="5.0"', html)
    assert ">mi<" in html


def test_the_week_card_shows_the_edited_volume(client, db_session):
    _add(client, "running_day")
    run = _items(db_session)[0]

    client.post(f"/coach/items/{run.id}/volume", data={"distance": "5"})

    assert "5.0 km" in client.get("/coach/").get_data(as_text=True)


def test_editing_the_planned_distance_lets_a_real_run_match(client, db_session, make_activity):
    _add(client, "running_day")
    run = _items(db_session)[0]
    start = datetime(2026, 10, 21, 7, 0)
    make_activity(
        start_time=start,
        end_time=start + timedelta(seconds=1922),
        duration_seconds=1922,
        distance_meters=5080.0,
        dedup_key="real-5k",
    )
    assert "Import matches" not in client.get("/coach/").get_data(as_text=True)

    client.post(f"/coach/items/{run.id}/volume", data={"distance": "5"})

    assert "Import matches" in client.get("/coach/").get_data(as_text=True)


def test_volume_page_carries_no_long_decimals(client, db_session):
    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    _add(client, "running_day")
    run = _items(db_session)[0]
    client.post(f"/coach/items/{run.id}/volume", data={"distance": "3.1"})

    html = client.get(f"/coach/?session={run.session_id}").get_data(as_text=True)

    assert not re.search(r"\d+\.\d{3,}", html)
