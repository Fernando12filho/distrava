import re
from datetime import date

import pytest

from app.coach import catalog
from app.coach import routes as coach_routes
from app.models import CoachExercise, CoachSession, CoachSessionItem, CoachWeek, UserSettings

MONDAY = date(2026, 10, 19)
DAY_COLUMN = r'class="day-col((?: [a-z]+)*)"'


class FrozenWednesday(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


def _add(client, template, day_index=0, week_start="2026-10-19", **headers):
    return client.post(
        "/coach/sessions",
        data={"template": template, "day_index": str(day_index), "week_start": week_start},
        headers=headers,
    )


def _only_session(db_session):
    db_session.expire_all()
    return db_session.query(CoachSession).one()


# ---------------------------------------------------------------- board page


def test_board_renders_seven_day_columns_for_the_current_week(client):
    response = client.get("/coach/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert len(re.findall(DAY_COLUMN, html)) == 7
    assert "Oct 19 – Oct 25, 2026" in html


def test_board_highlights_today_and_dims_past_days(client):
    html = client.get("/coach/").get_data(as_text=True)

    columns = re.findall(DAY_COLUMN, html)
    assert [("today" in c, "past" in c) for c in columns] == [
        (False, True),
        (False, True),
        (True, False),
        (False, False),
        (False, False),
        (False, False),
        (False, False),
    ]


def test_board_get_never_creates_a_week(client, db_session):
    client.get("/coach/")

    assert db_session.query(CoachWeek).count() == 0


def test_board_week_param_snaps_to_monday(client):
    html = client.get("/coach/?week=2026-10-30").get_data(as_text=True)

    assert "Oct 26 – Nov 01, 2026" in html


def test_board_rejects_a_garbage_week(client):
    assert client.get("/coach/?week=soon").status_code == 400


def test_board_shows_sessions_by_focus_not_exercises(client):
    _add(client, "chest_triceps", day_index=3)

    html = client.get("/coach/").get_data(as_text=True)

    assert "Chest &amp; Triceps" in html
    assert "4 exercises" in html
    assert "Bench press" not in html


def test_selecting_a_session_lists_its_exercises(client, db_session):
    _add(client, "chest_triceps", day_index=3)
    session = _only_session(db_session)

    html = client.get(f"/coach/?session={session.id}").get_data(as_text=True)

    for name in ["Bench press", "Incline dumbbell press", "Dips", "Triceps pushdown"]:
        assert name in html
    assert re.search(r'name="sets"[^>]*value="4"', html)
    assert re.search(r'name="reps"[^>]*value="6"', html)


def test_ac_rule_load_04_exercise_rows_show_no_intensity_bars(client, db_session):
    _add(client, "legs_glutes", day_index=1)
    session = _only_session(db_session)

    html = client.get(f"/coach/?session={session.id}").get_data(as_text=True)

    assert "Back squat" in html
    assert "intensity-bars" not in html


def test_selecting_a_session_from_another_week_is_ignored(client, db_session):
    _add(client, "chest_triceps", day_index=3)
    session = _only_session(db_session)

    html = client.get(f"/coach/?week=2026-10-26&session={session.id}").get_data(as_text=True)

    assert "Bench press" not in html


def test_board_shows_run_distance_in_the_users_units(client, db_session):
    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    _add(client, "running_day", day_index=2)

    html = client.get("/coach/").get_data(as_text=True)

    assert "5.0 mi" in html


# ---------------------------------------------------------------- add session (UC-05)


def test_adding_a_session_creates_the_week_and_copies_the_template(client, db_session):
    response = _add(client, "shoulders_abs", day_index=6)

    assert response.status_code == 303
    session = _only_session(db_session)
    assert session.week.week_start == MONDAY
    assert (session.day_index, session.kind, session.focus, session.status) == (6, "gym", "Shoulders & Abs", "planned")
    template = catalog.SESSION_TEMPLATES["shoulders_abs"]["items"]
    assert [i.exercise.slug for i in session.items] == [t["slug"] for t in template]
    assert f"session={session.id}" in response.headers["Location"]


def test_adding_a_second_session_to_a_day_goes_below_the_first(client, db_session):
    _add(client, "shoulders_abs", day_index=6)
    _add(client, "mobility", day_index=6)

    db_session.expire_all()
    positions = [(s.focus, s.position) for s in db_session.query(CoachSession).order_by(CoachSession.position)]
    assert positions == [("Shoulders & Abs", 0), ("Mobility & stretch", 1)]


def test_adding_a_rest_day_has_no_exercises(client, db_session):
    _add(client, "rest", day_index=4)

    assert _only_session(db_session).items == []


@pytest.mark.parametrize(
    "data",
    [
        {"template": "crossfit", "day_index": "0", "week_start": "2026-10-19"},
        {"template": "rest", "day_index": "7", "week_start": "2026-10-19"},
        {"template": "rest", "day_index": "monday", "week_start": "2026-10-19"},
        {"template": "rest", "day_index": "0", "week_start": "later"},
    ],
)
def test_adding_a_session_rejects_bad_input(client, db_session, data):
    assert client.post("/coach/sessions", data=data).status_code == 400
    assert db_session.query(CoachSession).count() == 0


# ---------------------------------------------------------------- move (drag)


def test_moving_a_session_puts_it_at_the_end_of_the_target_day(client, db_session):
    _add(client, "running_day", day_index=5)
    _add(client, "legs_glutes", day_index=1)
    legs = db_session.query(CoachSession).filter_by(focus="Legs & Glutes").one()

    response = client.post(f"/coach/sessions/{legs.id}/move", data={"day_index": "5"}, headers={"X-Requested-With": "fetch"})

    assert response.status_code == 204
    db_session.expire_all()
    moved = db_session.get(CoachSession, legs.id)
    assert (moved.day_index, moved.position) == (5, 1)


def test_moving_a_session_without_fetch_redirects_to_the_board(client, db_session):
    _add(client, "running_day", day_index=5)
    session = _only_session(db_session)

    response = client.post(f"/coach/sessions/{session.id}/move", data={"day_index": "4"})

    assert response.status_code == 303


def test_moving_a_session_keeps_its_status_and_exercises(client, db_session):
    _add(client, "chest_triceps", day_index=3)
    session = _only_session(db_session)
    client.post(f"/coach/sessions/{session.id}/status", data={"status": "done"})

    client.post(f"/coach/sessions/{session.id}/move", data={"day_index": "6"})

    moved = _only_session(db_session)
    assert moved.status == "done"
    assert len(moved.items) == 4


@pytest.mark.parametrize("day_index", ["-1", "7", "x"])
def test_moving_rejects_a_day_outside_the_week(client, db_session, day_index):
    _add(client, "running_day", day_index=5)
    session = _only_session(db_session)

    assert client.post(f"/coach/sessions/{session.id}/move", data={"day_index": day_index}).status_code == 400


def test_moving_an_unknown_session_is_404(client):
    assert client.post("/coach/sessions/999/move", data={"day_index": "1"}).status_code == 404


# ---------------------------------------------------------------- status (UC-10)


@pytest.mark.parametrize("status", ["done", "partial", "skipped", "planned"])
def test_setting_a_status_saves_it(client, db_session, status):
    _add(client, "legs_glutes", day_index=1)
    session = _only_session(db_session)

    response = client.post(f"/coach/sessions/{session.id}/status", data={"status": status})

    assert response.status_code == 303
    assert _only_session(db_session).status == status


@pytest.mark.parametrize("status", ["moved", "missed", ""])
def test_setting_a_status_rejects_anything_else(client, db_session, status):
    _add(client, "legs_glutes", day_index=1)
    session = _only_session(db_session)

    assert client.post(f"/coach/sessions/{session.id}/status", data={"status": status}).status_code == 400


def test_ac07_skipped_session_reads_neutral(client, db_session):
    _add(client, "legs_glutes", day_index=1)
    session = _only_session(db_session)
    client.post(f"/coach/sessions/{session.id}/status", data={"status": "skipped"})

    html = client.get("/coach/").get_data(as_text=True)

    assert "st-skipped" in html
    assert not re.search(r"missed|failed|streak", html, re.IGNORECASE)


# ---------------------------------------------------------------- remove (UC-05)


def test_removing_a_session_deletes_it_and_its_exercises(client, db_session):
    _add(client, "legs_glutes", day_index=1)
    session = _only_session(db_session)

    response = client.post(f"/coach/sessions/{session.id}/delete")

    assert response.status_code == 303
    assert db_session.query(CoachSession).count() == 0
    assert db_session.query(CoachSessionItem).count() == 0
    assert db_session.query(CoachExercise).count() == len(catalog.CATALOG)


def test_removing_an_exercise_keeps_the_session(client, db_session):
    _add(client, "legs_glutes", day_index=1)
    session = _only_session(db_session)
    first = session.items[0]

    response = client.post(f"/coach/items/{first.id}/delete")

    assert response.status_code == 303
    assert f"session={session.id}" in response.headers["Location"]
    assert [i.exercise.slug for i in _only_session(db_session).items] == [
        "romanian_deadlift",
        "walking_lunge",
        "calf_raise",
    ]


def test_removing_an_unknown_exercise_is_404(client):
    assert client.post("/coach/items/999/delete").status_code == 404


# ---------------------------------------------------------------- coach panel (UC-15)


def test_ac11_with_no_provider_the_coach_panel_shows_a_setup_hint(client):
    html = client.get("/coach/").get_data(as_text=True)

    assert "Coach not connected" in html
    assert 'href="/settings"' in html


def test_the_today_card_shows_todays_session(client):
    _add(client, "running_day", day_index=2)

    html = client.get("/coach/").get_data(as_text=True)

    # #43 (DS-06): the Today card moved from the Coach panel to the strip above the board.
    today = html.split('<div class="today-card">', 1)[1].split('<div class="hard-sets-card">', 1)[0]
    assert "Running day" in today
    assert "8.0 km" in today


def test_coach_panel_without_a_session_today_says_so_calmly(client):
    html = client.get("/coach/").get_data(as_text=True)

    assert "Nothing planned today" in html


# ---------------------------------------------------------------- shell + standing rules


def test_coach_nav_item_is_live_and_active_on_the_board(client):
    html = client.get("/coach/").get_data(as_text=True)

    assert re.search(r'<a href="/coach/"\s+class="nav-item active', html)
    assert ">Coach</span><span class=\"soon-pill\">" not in html


def test_board_page_carries_no_long_decimals(client, db_session):
    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    for template, day in [("running_day", 0), ("legs_glutes", 1), ("easy_ride", 2), ("mobility", 6)]:
        _add(client, template, day_index=day)
    session = db_session.query(CoachSession).first()

    html = client.get(f"/coach/?session={session.id}").get_data(as_text=True)

    assert not re.search(r"\d+\.\d{3,}", html)


def test_board_never_uses_the_negative_red(client, db_session):
    _add(client, "legs_glutes", day_index=1)
    session = _only_session(db_session)

    html = client.get(f"/coach/?session={session.id}").get_data(as_text=True)

    assert "btn-danger" not in html
    assert "negative" not in html
