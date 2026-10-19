import os
from pathlib import Path

from flask import Flask, g
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app import analytics
from app.models import Base

# Base.metadata.create_all() only creates tables that don't exist yet — it never
# alters an existing table. data/fitness.db predates these columns, so on an
# existing table we add whatever's missing by hand instead of wiping the file.
_SCHEMA_UPGRADES = {
    "activities": ["source_device", "utc_offset_minutes"],
    "user_settings": ["weight_kg", "units"],
    "coach_sessions": ["matched_activity_id"],
}


def _apply_schema_upgrades(engine):
    added = set()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table_name, required_columns in _SCHEMA_UPGRADES.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
            for column_name in required_columns:
                if column_name in existing_columns:
                    continue
                column = Base.metadata.tables[table_name].columns[column_name]
                column_type = column.type.compile(engine.dialect)
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
                added.add((table_name, column_name))
    return added


# Activities imported before offsets were recorded only know their UTC start.
# Runs once, when the column is first added: Apple Health and GPX rows get the
# offset of the given timezone (the computer's own when tz is None) at that
# instant; CSV rows were stored as local time, so theirs is 0. Re-importing an
# Apple Health export later replaces these estimates with the exact offsets.
def _backfill_activity_offsets(engine, tz):
    activities = Base.metadata.tables["activities"]
    with engine.begin() as conn:
        rows = conn.execute(
            select(activities.c.id, activities.c.source, activities.c.start_time).where(
                activities.c.utc_offset_minutes.is_(None)
            )
        ).fetchall()
        for activity_id, source, start_time in rows:
            offset = 0 if source == "csv" else analytics.local_offset_minutes(start_time, tz)
            conn.execute(
                activities.update().where(activities.c.id == activity_id).values(utc_offset_minutes=offset)
            )


# The first coach model put exercises straight on the day ("cards"); it was
# replaced by sessions before anything wrote check-ins. Databases opened during
# that window still carry its tables, which create_all() would never fix. Only
# empty tables are dropped, so no data can be lost here.
def _retire_card_era_coach_tables(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "coach_cards" in tables:
            conn.execute(text("DROP TABLE coach_cards"))
        if "coach_checkins" in tables:
            columns = {c["name"] for c in inspector.get_columns("coach_checkins")}
            empty = conn.execute(text("SELECT COUNT(*) FROM coach_checkins")).scalar() == 0
            if "card_id" in columns and empty:
                conn.execute(text("DROP TABLE coach_checkins"))


COACH_TABLE_PREFIX = "coach_"


# The "down" migration for the coach feature. Reversed sorted_tables drops
# children before parents, and the prefix filter guarantees no pre-coach table
# (or its rows) can be touched.
def drop_coach_tables(engine):
    coach_tables = [t for t in Base.metadata.sorted_tables if t.name.startswith(COACH_TABLE_PREFIX)]
    Base.metadata.drop_all(engine, tables=list(reversed(coach_tables)))


# Deliberately minimal .env support instead of a python-dotenv dependency:
# real shell environment always wins over the file.
def load_env_file(path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def create_app(config=None):
    load_env_file(Path(".env"))
    app = Flask(__name__)
    app.config.setdefault(
        "DATABASE_URL", os.environ.get("DISTRAVA_DATABASE_URL", "sqlite:///./data/fitness.db")
    )
    if config:
        app.config.update(config)

    engine = app.config.get("ENGINE")
    if engine is None:
        database_url = app.config["DATABASE_URL"]
        if database_url.startswith("sqlite:///./"):
            db_path = Path(database_url.replace("sqlite:///./", "", 1))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(database_url, connect_args={"check_same_thread": False})

    _retire_card_era_coach_tables(engine)
    Base.metadata.create_all(engine)
    added_columns = _apply_schema_upgrades(engine)
    if ("activities", "utc_offset_minutes") in added_columns:
        _backfill_activity_offsets(engine, app.config.get("LOCAL_TIMEZONE"))
    app.engine = engine
    app.session_factory = sessionmaker(bind=engine)

    from app.coach.catalog import seed_catalog

    seed_session = app.session_factory()
    try:
        seed_catalog(seed_session)
    finally:
        seed_session.close()

    app.jinja_env.filters["format_duration"] = analytics.format_duration
    app.jinja_env.filters["format_pace"] = analytics.format_pace

    from app.routes import bp

    app.register_blueprint(bp)

    from app.coach.routes import bp as coach_bp

    app.register_blueprint(coach_bp)

    @app.teardown_appcontext
    def close_session(exception=None):
        session = g.pop("db_session", None)
        if session is not None:
            session.close()

    return app
