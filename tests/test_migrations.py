from datetime import date

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import create_app, drop_coach_tables
from app.models import (
    Base,
    BestEffort,
    CoachCheckin,
    CoachExercise,
    CoachNote,
    CoachSession,
    CoachSessionItem,
    CoachWeek,
    Exercise,
    HRZone,
    UserSettings,
)
from regression_fixtures import seed_best_effort_runs, seed_load_schedule

# Every table that existed before the coach work began. Coach tables may be
# added next to these; none of these may change shape or lose a row.
PRE_COACH_TABLES = {
    "activities",
    "activity_streams",
    "best_efforts",
    "hr_zones",
    "exercises",
    "user_settings",
}


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _populate(engine):
    session = sessionmaker(bind=engine)()
    seed_load_schedule(session)
    seed_best_effort_runs(session)
    session.add(UserSettings(resting_hr=55, max_hr=188, birth_year=1990, weight_kg=70.0, units="metric"))
    session.add(HRZone(zone_number=1, label="Recovery", min_bpm=0, max_bpm=135))
    session.add(Exercise(name="Back Squat", muscle_group="legs", category="strength"))
    session.commit()
    session.close()


def _dump(engine):
    inspector = inspect(engine)
    dump = {}
    with engine.connect() as conn:
        for table in PRE_COACH_TABLES:
            columns = [(c["name"], str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)]
            rows = conn.execute(text(f"SELECT * FROM {table} ORDER BY id")).fetchall()
            dump[table] = (columns, [tuple(r) for r in rows])
    return dump


def test_fresh_database_has_every_pre_coach_table():
    app = create_app({"TESTING": True, "ENGINE": _engine()})

    assert PRE_COACH_TABLES <= set(inspect(app.engine).get_table_names())


def test_restart_on_populated_database_leaves_existing_tables_untouched():
    engine = _engine()
    create_app({"TESTING": True, "ENGINE": engine})
    _populate(engine)
    before = _dump(engine)

    create_app({"TESTING": True, "ENGINE": engine})

    after = _dump(engine)
    assert after == before
    assert all(rows for _columns, rows in before.values())


COACH_TABLES = {
    "coach_exercises",
    "coach_weeks",
    "coach_sessions",
    "coach_session_items",
    "coach_checkins",
    "coach_notes",
}


def _populate_coach(engine):
    session = sessionmaker(bind=engine)()
    exercise = session.query(CoachExercise).first()
    week = CoachWeek(week_start=date(2026, 10, 19))
    gym = CoachSession(week=week, day_index=1, kind="gym", focus="Chest & Triceps")
    gym.items.append(CoachSessionItem(exercise=exercise, sets=4, reps=6))
    gym.checkins.append(CoachCheckin(energy=3))
    session.add_all([week, CoachNote(text="note")])
    session.commit()
    session.close()


def test_create_app_migrates_coach_tables_up():
    app = create_app({"TESTING": True, "ENGINE": _engine()})

    assert COACH_TABLES <= set(inspect(app.engine).get_table_names())


def test_every_coach_table_uses_the_coach_prefix():
    coach_tables = {name for name in Base.metadata.tables if name not in PRE_COACH_TABLES}

    assert coach_tables == COACH_TABLES


def test_coach_down_drops_only_coach_tables():
    engine = _engine()
    create_app({"TESTING": True, "ENGINE": engine})
    _populate(engine)
    _populate_coach(engine)
    before = _dump(engine)

    drop_coach_tables(engine)

    assert set(inspect(engine).get_table_names()) == PRE_COACH_TABLES
    assert _dump(engine) == before


def test_coach_up_down_up_round_trip_leaves_existing_tables_untouched():
    engine = _engine()
    create_app({"TESTING": True, "ENGINE": engine})
    _populate(engine)
    before = _dump(engine)

    drop_coach_tables(engine)
    create_app({"TESTING": True, "ENGINE": engine})

    assert COACH_TABLES <= set(inspect(engine).get_table_names())
    assert _dump(engine) == before


def test_restart_keeps_coach_rows():
    engine = _engine()
    create_app({"TESTING": True, "ENGINE": engine})
    _populate_coach(engine)

    create_app({"TESTING": True, "ENGINE": engine})

    session = sessionmaker(bind=engine)()
    assert session.query(CoachSession).count() == 1
    assert session.query(CoachSessionItem).count() == 1
    assert session.query(CoachCheckin).count() == 1
    session.close()


def test_restart_keeps_best_efforts_rows():
    engine = _engine()
    create_app({"TESTING": True, "ENGINE": engine})
    _populate(engine)

    create_app({"TESTING": True, "ENGINE": engine})

    session = sessionmaker(bind=engine)()
    assert session.query(BestEffort).count() == 10
    session.close()
