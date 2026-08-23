from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Activity, ActivityStream, BestEffort, Exercise, HRZone, UserSettings


def test_activity_created_with_all_fields(db_session):
    activity = Activity(
        activity_type="Run",
        start_time=datetime(2026, 7, 1, 8, 0, 0),
        end_time=datetime(2026, 7, 1, 8, 30, 0),
        duration_seconds=1800,
        distance_meters=5000.0,
        avg_hr=148.0,
        max_hr=165.0,
        elevation_gain_meters=42.0,
        source="apple_health",
        source_id="uuid-1",
        dedup_key="Run|2026-07-01T08:00:00|1800",
    )
    db_session.add(activity)
    db_session.commit()

    stored = db_session.query(Activity).one()
    assert stored.id is not None
    assert stored.activity_type == "Run"
    assert stored.distance_meters == 5000.0
    assert stored.avg_hr == 148.0
    assert stored.max_hr == 165.0
    assert stored.elevation_gain_meters == 42.0
    assert stored.source == "apple_health"
    assert stored.source_id == "uuid-1"
    assert stored.dedup_key == "Run|2026-07-01T08:00:00|1800"
    assert stored.created_at is not None


def test_activity_stream_fk_and_cascade_delete(db_session, make_activity):
    activity = make_activity()
    stream = ActivityStream(
        activity_id=activity.id,
        stream_data={"hr": [140, 150], "pace": [300, 310], "elevation": [10, 12], "distance": [0, 100], "time": [0, 10]},
    )
    db_session.add(stream)
    db_session.commit()

    assert db_session.query(ActivityStream).count() == 1

    db_session.delete(activity)
    db_session.commit()

    assert db_session.query(ActivityStream).count() == 0


def test_dedup_key_unique_constraint_prevents_duplicate(db_session, make_activity):
    make_activity(dedup_key="Run|2026-07-01T08:00:00|1800")

    with pytest.raises(IntegrityError):
        make_activity(dedup_key="Run|2026-07-01T08:00:00|1800")


def test_best_effort_fk_to_activity(db_session, make_activity):
    activity = make_activity()
    best_effort = BestEffort(
        distance_label="5K",
        distance_meters=5000.0,
        activity_id=activity.id,
        duration_seconds=1500.0,
        pace_per_km_seconds=300.0,
        achieved_at=activity.start_time,
    )
    db_session.add(best_effort)
    db_session.commit()

    stored = db_session.query(BestEffort).one()
    assert stored.activity_id == activity.id
    assert stored.distance_label == "5K"


def test_hr_zone_fields(db_session):
    zone = HRZone(zone_number=1, label="Zone 1 (Recovery)", min_bpm=90, max_bpm=120)
    db_session.add(zone)
    db_session.commit()

    stored = db_session.query(HRZone).one()
    assert stored.zone_number == 1
    assert stored.label == "Zone 1 (Recovery)"
    assert stored.min_bpm == 90
    assert stored.max_bpm == 120


def test_exercise_fields(db_session):
    exercise = Exercise(name="Squat", muscle_group="Legs", category="Strength")
    db_session.add(exercise)
    db_session.commit()

    stored = db_session.query(Exercise).one()
    assert stored.name == "Squat"
    assert stored.muscle_group == "Legs"
    assert stored.category == "Strength"


def test_user_settings_fields(db_session):
    settings = UserSettings(resting_hr=55, max_hr=185, birth_year=1990)
    db_session.add(settings)
    db_session.commit()

    stored = db_session.query(UserSettings).one()
    assert stored.resting_hr == 55
    assert stored.max_hr == 185
    assert stored.birth_year == 1990


def test_activity_source_device_optional_field(db_session, make_activity):
    make_activity(source_device="Garmin Forerunner 265")

    stored = db_session.query(Activity).one()
    assert stored.source_device == "Garmin Forerunner 265"


def test_activity_source_device_defaults_to_none(db_session, make_activity):
    make_activity()

    stored = db_session.query(Activity).one()
    assert stored.source_device is None


def test_activity_has_no_title_column(db_session):
    assert "title" not in Activity.__table__.columns


def test_user_settings_weight_and_units_fields(db_session):
    settings = UserSettings(resting_hr=55, max_hr=185, birth_year=1990, weight_kg=72.0, units="metric")
    db_session.add(settings)
    db_session.commit()

    stored = db_session.query(UserSettings).one()
    assert stored.weight_kg == 72.0
    assert stored.units == "metric"
