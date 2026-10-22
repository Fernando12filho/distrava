from datetime import date

import pytest

from app.coach.week import week_start_for
from app.models import CoachExercise, CoachSession, CoachSessionItem, CoachWeek


@pytest.fixture(autouse=True)
def has_data(make_activity):
    # The dashboard shows only its import prompt until something is imported.
    make_activity()


def _plan_today(db_session, focus="Chest & Triceps", status="planned", exercises=(("Bench press", 4, 8),)):
    today = date.today()
    week = db_session.query(CoachWeek).filter_by(week_start=week_start_for(today)).first()
    if week is None:
        week = CoachWeek(week_start=week_start_for(today))
        db_session.add(week)
    position = len([s for s in week.sessions if s.day_index == today.weekday()])
    session = CoachSession(
        week=week, day_index=today.weekday(), position=position, kind="gym", focus=focus, status=status
    )
    for i, (name, sets, reps) in enumerate(exercises):
        exercise = CoachExercise(name=name, category="strength", muscle_group="chest")
        session.items.append(CoachSessionItem(position=i, exercise=exercise, sets=sets, reps=reps))
    db_session.add(session)
    db_session.commit()
    return session


def _today_panel(client):
    html = client.get("/dashboard").get_data(as_text=True)
    assert 'class="card today-plan"' in html
    return html.split('class="card today-plan"')[1].split("<!-- /today-plan -->")[0]


def test_dashboard_shows_todays_sessions_with_their_exercises(client, db_session):
    session = _plan_today(db_session, exercises=(("Bench press", 4, 8), ("Triceps dip", 3, 12)))

    panel = _today_panel(client)

    assert "Chest &amp; Triceps" in panel
    assert "Bench press" in panel and "4 × 8" in panel
    assert "Triceps dip" in panel and "3 × 12" in panel
    assert f"session={session.id}" in panel


def test_today_panel_shows_status_without_pressure(client, db_session):
    _plan_today(db_session, status="skipped")

    panel = _today_panel(client)

    assert "st-skipped" in panel
    assert "missed" not in panel.lower()


def test_today_panel_ignores_other_days(client, db_session):
    session = _plan_today(db_session, focus="Back & Biceps")
    session.day_index = (date.today().weekday() + 1) % 7
    db_session.commit()

    panel = _today_panel(client)

    assert "Back &amp; Biceps" not in panel
    assert "Nothing planned today" in panel
    assert 'href="/coach/' in panel


def test_today_panel_lists_sessions_in_board_order_like_the_coach_page(client, db_session):
    _plan_today(db_session, focus="Legs & Glutes")
    _plan_today(db_session, focus="Running drills")

    coach = client.get("/coach/").get_data(as_text=True)
    panel = _today_panel(client)

    assert panel.index("Legs &amp; Glutes") < panel.index("Running drills")
    assert coach.index("Legs &amp; Glutes") < coach.index("Running drills")
