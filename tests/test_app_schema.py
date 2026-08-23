import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import create_app


def _old_schema_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE activities (
                    id INTEGER PRIMARY KEY,
                    activity_type VARCHAR NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    distance_meters FLOAT NOT NULL,
                    avg_hr FLOAT,
                    max_hr FLOAT,
                    elevation_gain_meters FLOAT,
                    source VARCHAR NOT NULL,
                    source_id VARCHAR,
                    dedup_key VARCHAR NOT NULL UNIQUE,
                    created_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO activities
                    (activity_type, start_time, end_time, duration_seconds, distance_meters,
                     source, dedup_key)
                VALUES ('Run', '2026-01-01 08:00:00', '2026-01-01 08:30:00', 1800, 5000.0,
                        'apple_health', 'old-row-key')
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE user_settings (
                    id INTEGER PRIMARY KEY,
                    resting_hr INTEGER,
                    max_hr INTEGER,
                    birth_year INTEGER
                )
                """
            )
        )
    return engine


def test_create_app_upgrades_existing_activities_table_without_losing_data():
    engine = _old_schema_engine()

    app = create_app({"TESTING": True, "ENGINE": engine})

    session = sessionmaker(bind=app.engine)()
    from app.models import Activity

    stored = session.query(Activity).one()
    assert stored.dedup_key == "old-row-key"
    assert stored.source_device is None
    session.close()


def test_create_app_upgrades_existing_user_settings_table_without_losing_data():
    engine = _old_schema_engine()

    app = create_app({"TESTING": True, "ENGINE": engine})

    session = sessionmaker(bind=app.engine)()
    from app.models import UserSettings

    session.add(UserSettings(resting_hr=55, max_hr=185, birth_year=1990))
    session.commit()
    stored = session.query(UserSettings).one()
    assert stored.weight_kg is None
    assert stored.units is None
    session.close()


def test_database_url_defaults_from_env_var(monkeypatch):
    monkeypatch.setenv("DISTRAVA_DATABASE_URL", "sqlite:///./data/scratch-env-test.db")

    app = create_app({"TESTING": True, "ENGINE": create_engine("sqlite:///:memory:")})

    assert app.config["DATABASE_URL"] == "sqlite:///./data/scratch-env-test.db"
