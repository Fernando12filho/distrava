"""Activities keep start_time in UTC (dedup, sorting and the regression net rely
on it) and carry the offset to their local wall clock. Everything a person
reads — dates, times, which day a run counts toward — uses local time."""

import re
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import analytics, create_app, parser
from app import routes as main_routes
from app.models import Activity
from regression_fixtures import captured_context

BRASILIA = timezone(timedelta(hours=-3))
PACIFIC_SUMMER = timezone(timedelta(hours=-7))

EVENING_RUN_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30.0" durationUnit="min" totalDistance="5.0" totalDistanceUnit="km" startDate="2026-10-16 22:15:00 -0300" endDate="2026-10-16 22:45:00 -0300"/>
</HealthData>"""


# ---------------------------------------------------------------- pure helpers


def test_to_local_without_an_offset_is_unchanged():
    start = datetime(2026, 10, 17, 1, 15)

    assert analytics.to_local(start, None) == start


def test_to_local_applies_the_offset():
    assert analytics.to_local(datetime(2026, 10, 17, 1, 15), -180) == datetime(2026, 10, 16, 22, 15)


@pytest.mark.parametrize(
    "tz, expected",
    [(BRASILIA, -180), (PACIFIC_SUMMER, -420), (timezone(timedelta(hours=5, minutes=30)), 330)],
)
def test_local_offset_minutes_for_a_timezone(tz, expected):
    assert analytics.local_offset_minutes(datetime(2026, 10, 17, 1, 15), tz) == expected


def test_local_offset_minutes_defaults_to_the_computers_timezone():
    utc = datetime(2026, 10, 17, 1, 15)
    expected = utc.replace(tzinfo=timezone.utc).astimezone().utcoffset()

    assert analytics.local_offset_minutes(utc) == int(expected.total_seconds() // 60)


# ---------------------------------------------------------------- imports


def test_apple_health_workout_keeps_its_exact_offset(fixtures_dir):
    windows = parser.parse_apple_health_xml((fixtures_dir / "sample_export.xml").read_bytes())

    assert windows[0]["start_time"] == datetime(2026, 7, 1, 15, 0)
    assert windows[0]["utc_offset_minutes"] == -420


def test_apple_health_import_stores_the_offset(fixtures_dir, db_session):
    parser.import_apple_health_zip(fixtures_dir / "sample_export.zip", db_session)

    activity = db_session.query(Activity).one()
    assert activity.utc_offset_minutes == -420
    assert activity.local_start_time == datetime(2026, 7, 1, 8, 0)


def test_gpx_import_uses_the_given_timezone(fixtures_dir, db_session):
    parser.import_gpx(fixtures_dir / "sample.gpx", db_session, tz=BRASILIA)

    activity = db_session.query(Activity).one()
    assert activity.start_time == datetime(2026, 7, 1, 8, 0)
    assert activity.local_start_time == datetime(2026, 7, 1, 5, 0)


def test_csv_times_are_already_local(fixtures_dir, db_session):
    parser.import_csv(fixtures_dir / "sample.csv", db_session)

    activity = db_session.query(Activity).one()
    assert activity.utc_offset_minutes == 0
    assert activity.local_start_time == datetime(2026, 7, 1, 8, 0)


def _zip_with(tmp_path, xml_bytes):
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("apple_health_export/export.xml", xml_bytes)
    return path


def test_reimporting_an_export_corrects_offsets_without_duplicating(tmp_path, db_session):
    export = _zip_with(tmp_path, EVENING_RUN_XML)
    parser.import_apple_health_zip(export, db_session)
    activity = db_session.query(Activity).one()
    activity.utc_offset_minutes = 0
    db_session.commit()

    summary = parser.import_apple_health_zip(export, db_session)

    assert summary == {"imported": 0, "skipped": 1}
    db_session.expire_all()
    activity = db_session.query(Activity).one()
    assert activity.utc_offset_minutes == -180
    assert activity.local_start_time == datetime(2026, 10, 16, 22, 15)


def test_reimporting_a_gpx_never_overwrites_a_known_offset(fixtures_dir, db_session):
    parser.import_gpx(fixtures_dir / "sample.gpx", db_session, tz=BRASILIA)

    parser.import_gpx(fixtures_dir / "sample.gpx", db_session, tz=PACIFIC_SUMMER)

    assert db_session.query(Activity).one().utc_offset_minutes == -180


# ---------------------------------------------------------------- existing databases


def _legacy_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE activities (
                    id INTEGER PRIMARY KEY, activity_type VARCHAR NOT NULL,
                    start_time DATETIME NOT NULL, end_time DATETIME NOT NULL,
                    duration_seconds INTEGER NOT NULL, distance_meters FLOAT NOT NULL,
                    avg_hr FLOAT, max_hr FLOAT, elevation_gain_meters FLOAT,
                    source VARCHAR NOT NULL, source_id VARCHAR,
                    dedup_key VARCHAR NOT NULL UNIQUE, created_at DATETIME, source_device VARCHAR
                )
                """
            )
        )
        rows = [
            ("apple_health", "2026-10-17 01:15:00.000000", "k1"),
            ("gpx", "2026-10-17 12:00:00.000000", "k2"),
            ("csv", "2026-10-17 08:00:00.000000", "k3"),
        ]
        for source, start, key in rows:
            conn.execute(
                text(
                    "INSERT INTO activities (activity_type, start_time, end_time, duration_seconds, "
                    "distance_meters, source, dedup_key) VALUES ('Run', :s, :s, 1800, 5000.0, :src, :k)"
                ),
                {"s": start, "src": source, "k": key},
            )
    return engine


def test_existing_activities_get_offsets_from_the_local_timezone_once():
    engine = _legacy_engine()

    create_app({"TESTING": True, "ENGINE": engine, "LOCAL_TIMEZONE": BRASILIA})

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT source, start_time, utc_offset_minutes FROM activities ORDER BY id")).fetchall()
    assert [(r[0], r[2]) for r in rows] == [("apple_health", -180), ("gpx", -180), ("csv", 0)]
    assert rows[0][1].startswith("2026-10-17 01:15:00")


def test_the_backfill_never_runs_again_on_restart():
    engine = _legacy_engine()
    create_app({"TESTING": True, "ENGINE": engine, "LOCAL_TIMEZONE": BRASILIA})
    with engine.begin() as conn:
        conn.execute(text("UPDATE activities SET utc_offset_minutes = 60 WHERE source = 'gpx'"))

    create_app({"TESTING": True, "ENGINE": engine, "LOCAL_TIMEZONE": PACIFIC_SUMMER})

    with engine.connect() as conn:
        assert conn.execute(text("SELECT utc_offset_minutes FROM activities WHERE source = 'gpx'")).scalar() == 60


# ---------------------------------------------------------------- what people see


@pytest.fixture()
def evening_run(make_activity):
    # 22:15 in Brasília on Fri Oct 16 is 01:15 UTC on Sat Oct 17.
    return make_activity(
        start_time=datetime(2026, 10, 17, 1, 15),
        end_time=datetime(2026, 10, 17, 1, 45),
        utc_offset_minutes=-180,
        dedup_key="evening",
    )


def test_activity_detail_shows_the_local_date_and_time(client, evening_run):
    html = client.get(f"/activities/{evening_run.id}").get_data(as_text=True)

    assert "Oct 16, 2026 · 22:15" in html
    assert "Oct 17, 2026" not in html


def test_activity_list_shows_the_local_date(client, evening_run):
    html = client.get("/activities").get_data(as_text=True)

    assert "Oct 16" in html
    assert "Oct 17" not in html


class FrozenFriday(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 16)


def test_dashboard_counts_an_evening_run_on_its_local_day(app, client, evening_run, monkeypatch):
    monkeypatch.setattr(main_routes, "date", FrozenFriday)

    with captured_context(app) as contexts:
        client.get("/dashboard")

    calendar = contexts[-1]["calendar"]
    assert calendar[-1]["date"] == date(2026, 10, 16)
    assert calendar[-1]["level"] > 0
    assert contexts[-1]["weekly_count"] == 1


def test_coach_matches_an_evening_run_on_its_local_day(client, evening_run, monkeypatch):
    from app.coach import routes as coach_routes

    monkeypatch.setattr(coach_routes, "date", FrozenFriday)
    client.post("/coach/sessions", data={"template": "running_day", "day_index": "4", "week_start": "2026-10-12"})
    session_html = client.get("/coach/?week=2026-10-12").get_data(as_text=True)
    item_id = re.search(r"/coach/items/(\d+)/volume", client.get(
        "/coach/?week=2026-10-12&session=" + re.search(r'session=(\d+)"', session_html).group(1)
    ).get_data(as_text=True)).group(1)
    client.post(f"/coach/items/{item_id}/volume", data={"distance": "5"})

    html = client.get("/coach/?week=2026-10-12").get_data(as_text=True)

    assert "Import matches" in html
    assert "Run · 5.00 km · 30:00 · 22:15" in html
