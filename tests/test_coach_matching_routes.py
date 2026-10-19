from datetime import date, datetime, timedelta

import pytest

from app.coach import routes as coach_routes
from app.models import Activity, CoachSession

WEDNESDAY = date(2026, 10, 21)


class FrozenWednesday(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


@pytest.fixture()
def run_on(make_activity):
    def _run_on(day, hour=7, minute=6, distance=8040.0, duration=2712, activity_type="Run"):
        start = datetime(day.year, day.month, day.day, hour, minute)
        return make_activity(
            activity_type=activity_type,
            start_time=start,
            end_time=start + timedelta(seconds=duration),
            duration_seconds=duration,
            distance_meters=distance,
            dedup_key=f"{activity_type}|{start.isoformat()}|{duration}",
        )

    return _run_on


def _add(client, template, day_index):
    client.post("/coach/sessions", data={"template": template, "day_index": str(day_index), "week_start": "2026-10-19"})


def _session(db_session, focus="Running day"):
    db_session.expire_all()
    return db_session.query(CoachSession).filter_by(focus=focus).one()


def _board(client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/coach/?{query}").get_data(as_text=True)


def test_ac06_board_offers_the_matching_import_for_confirmation(client, db_session, run_on):
    _add(client, "running_day", 2)
    run = run_on(WEDNESDAY)

    html = _board(client)

    assert "Import matches" in html
    assert "Run · 8.04 km · 45:12 · 07:06" in html
    assert f'name="activity_id" value="{run.id}"' in html
    assert _session(db_session).status == "planned"


def test_confirming_marks_the_session_done_and_links_the_activity(client, db_session, run_on):
    _add(client, "running_day", 2)
    run = run_on(WEDNESDAY)
    session = _session(db_session)

    response = client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(run.id)})

    assert response.status_code == 303
    confirmed = _session(db_session)
    assert (confirmed.status, confirmed.matched_activity_id) == ("done", run.id)


def test_a_confirmed_session_shows_its_activity_and_no_more_suggestion(client, db_session, run_on):
    _add(client, "running_day", 2)
    run = run_on(WEDNESDAY)
    session = _session(db_session)
    client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(run.id)})

    html = _board(client)

    assert "Import matches" not in html
    assert f'href="/activities/{run.id}"' in html


def test_confirming_an_activity_that_does_not_fit_is_rejected(client, db_session, run_on):
    _add(client, "running_day", 2)
    too_short = run_on(WEDNESDAY, distance=3000.0)
    session = _session(db_session)

    response = client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(too_short.id)})

    assert response.status_code == 400
    assert _session(db_session).status == "planned"


@pytest.mark.parametrize("activity_id", ["999", "", "run"])
def test_confirming_an_unknown_activity_is_rejected(client, db_session, activity_id):
    _add(client, "running_day", 2)
    session = _session(db_session)

    assert client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": activity_id}).status_code == 400


def test_ac06_a_run_logged_the_next_day_asks_with_the_day_shown(client, run_on):
    _add(client, "running_day", 2)
    run_on(date(2026, 10, 22))

    html = _board(client)

    assert "Import matches" not in html
    assert "Was this import this session?" in html
    assert "Thu 22 · Run · 8.04 km" in html


def test_a_run_on_the_previous_sunday_is_offered_to_monday(client, run_on):
    _add(client, "running_day", 0)
    run_on(date(2026, 10, 18))

    assert "Sun 18 · Run · 8.04 km" in _board(client)


def test_ac06_two_fitting_runs_ask_which_one(client, run_on):
    _add(client, "running_day", 2)
    morning = run_on(WEDNESDAY, hour=7)
    evening = run_on(WEDNESDAY, hour=18, distance=7900.0)

    html = _board(client)

    assert "Which import was this?" in html
    assert html.index(f'value="{morning.id}"') < html.index(f'value="{evening.id}"')


def test_choosing_one_of_two_candidates_confirms_it(client, db_session, run_on):
    _add(client, "running_day", 2)
    run_on(WEDNESDAY, hour=7)
    evening = run_on(WEDNESDAY, hour=18, distance=7900.0)
    session = _session(db_session)

    response = client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(evening.id)})

    assert response.status_code == 303
    assert _session(db_session).matched_activity_id == evening.id


def test_gym_sessions_never_get_suggestions(client, run_on):
    _add(client, "legs_glutes", 2)
    run_on(WEDNESDAY)

    html = _board(client)

    assert "Import matches" not in html
    assert "Was this import" not in html


def test_ride_session_matches_an_imported_ride(client, db_session, run_on):
    _add(client, "easy_ride", 2)
    run_on(WEDNESDAY, activity_type="Cycle", distance=21000.0, duration=2900)

    assert "Ride · 21.00 km · 48:20 · 07:06" in _board(client)


def test_resetting_to_planned_releases_the_activity(client, db_session, run_on):
    _add(client, "running_day", 2)
    run = run_on(WEDNESDAY)
    session = _session(db_session)
    client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(run.id)})

    client.post(f"/coach/sessions/{session.id}/status", data={"status": "planned"})

    reset = _session(db_session)
    assert (reset.status, reset.matched_activity_id) == ("planned", None)
    assert "Import matches" in _board(client)


def test_board_survives_a_matched_activity_being_wiped(client, db_session, run_on):
    _add(client, "running_day", 2)
    run = run_on(WEDNESDAY)
    session = _session(db_session)
    client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(run.id)})

    client.post("/settings/wipe")

    assert db_session.query(Activity).count() == 0
    assert client.get("/coach/").status_code == 200


def test_an_activity_confirmed_last_week_is_not_offered_again(client, db_session, run_on):
    client.post("/coach/sessions", data={"template": "running_day", "day_index": "6", "week_start": "2026-10-12"})
    sunday_run = run_on(date(2026, 10, 18))
    last_week = _session(db_session)
    client.post(f"/coach/sessions/{last_week.id}/confirm", data={"activity_id": str(sunday_run.id)})
    _add(client, "running_day", 0)

    html = _board(client, week="2026-10-19")

    assert "Sun 18 · Run" not in html
