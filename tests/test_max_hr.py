"""RULE-METRIC-02: max HR defaults to Tanaka (208 - 0.7 x age) and is replaced by
the highest heart rate actually held in a workout, once that is higher. A value
typed into Settings always wins."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import analytics, create_app, parser, training_rules
from app.models import Base, UserSettings
from app.routes import _resolve_hr_profile

TODAY = date(2026, 10, 20)


def _dense(values, step=5):
    return list(range(0, step * len(values), step)), values


# ---------------------------------------------------------------- sustained max


def test_a_one_reading_spike_is_not_a_max():
    times, hr = _dense([150.0] * 12)
    hr[3] = 205.0

    assert analytics.sustained_max_hr(times, hr, 5, 30) == 150.0


def test_a_peak_held_for_five_seconds_counts():
    times, hr = _dense([150.0] * 6 + [178.0, 178.0] + [160.0] * 4)

    assert analytics.sustained_max_hr(times, hr, 5, 30) == 178.0


def test_readings_too_far_apart_never_count():
    times, hr = _dense([180.0] * 5, step=60)

    assert analytics.sustained_max_hr(times, hr, 5, 30) is None


@pytest.mark.parametrize("times, hr", [([], []), ([0], [170.0]), ([0, 5], [None, 170.0])])
def test_too_few_readings_give_no_max(times, hr):
    assert analytics.sustained_max_hr(times, hr, 5, 30) is None


def test_the_hold_time_sits_inside_the_researched_range():
    assert 5 <= training_rules.HR_MAX_OBSERVED_MIN_SECONDS <= 30


# ---------------------------------------------------------------- which max HR is used


@pytest.mark.parametrize(
    "settings, expected_max",
    [
        (None, 190),
        (UserSettings(birth_year=2000), 190),
        (UserSettings(birth_year=2000, observed_max_hr=178), 190),
        (UserSettings(birth_year=2000, observed_max_hr=196), 196),
        (UserSettings(observed_max_hr=195), 195),
        (UserSettings(birth_year=2000, observed_max_hr=196, max_hr=185), 185),
    ],
)
def test_max_hr_resolution(settings, expected_max):
    assert _resolve_hr_profile(settings, TODAY)[1] == expected_max


# ---------------------------------------------------------------- learning it from workouts


def _persist(db_session, start, hr_values):
    times, hr = _dense(hr_values)
    parser._persist_activity(
        db_session,
        activity_type="Run",
        start_time=start,
        end_time=start,
        duration_seconds=times[-1],
        distance_meters=5000.0,
        avg_hr=None,
        max_hr=None,
        elevation_gain_meters=None,
        source="gpx",
        source_id=None,
        stream_data={"time": times, "hr": hr, "distance": [None] * len(times), "elevation": [], "pace": []},
    )


def test_importing_a_workout_records_the_held_max(db_session):
    _persist(db_session, datetime(2026, 10, 1, 7), [150.0] * 5 + [181.0, 182.0] + [150.0] * 5)

    assert db_session.query(UserSettings).one().observed_max_hr == 181


def test_a_lower_workout_never_lowers_the_observed_max(db_session):
    _persist(db_session, datetime(2026, 10, 1, 7), [181.0, 181.0, 150.0])
    _persist(db_session, datetime(2026, 10, 2, 7), [170.0, 170.0, 150.0])

    assert db_session.query(UserSettings).one().observed_max_hr == 181


def test_a_higher_workout_raises_it(db_session):
    _persist(db_session, datetime(2026, 10, 1, 7), [181.0, 181.0, 150.0])
    _persist(db_session, datetime(2026, 10, 2, 7), [188.0, 189.0, 150.0])

    assert db_session.query(UserSettings).one().observed_max_hr == 188


def test_the_scan_works_on_a_database_file(tmp_path):
    # An in-memory database shares one connection; a file does not, and writing
    # while still streaming the workouts locked it (found on real data).
    engine = create_engine(f"sqlite:///{tmp_path / 'fitness.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(UserSettings(birth_year=2000))
    session.commit()
    # More workouts than one fetch batch, each peaking higher than the last.
    for day in range(60):
        peak = 120.0 + day
        _persist(session, datetime(2026, 8, 1, 7) + timedelta(days=day), [110.0, peak, peak, 110.0])
    session.close()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE user_settings DROP COLUMN observed_max_hr"))

    create_app({"TESTING": True, "ENGINE": engine})

    with engine.connect() as conn:
        assert conn.execute(text("SELECT observed_max_hr FROM user_settings")).scalar() == 179


def test_existing_workouts_are_scanned_once_when_the_column_arrives():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(UserSettings(birth_year=2000))
    session.commit()
    _persist(session, datetime(2026, 10, 1, 7), [150.0, 177.0, 178.0, 178.0, 150.0])
    session.close()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE user_settings DROP COLUMN observed_max_hr"))

    create_app({"TESTING": True, "ENGINE": engine})

    with engine.connect() as conn:
        assert conn.execute(text("SELECT observed_max_hr FROM user_settings")).scalar() == 178


# ---------------------------------------------------------------- settings page


def test_settings_page_names_the_new_estimate(client):
    html = client.get("/settings").get_data(as_text=True)

    assert "208 − 0.7 × age" in html
    assert "220−age" not in html and "220 − age" not in html
