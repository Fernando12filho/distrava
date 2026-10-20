"""Apple Health exports sometimes hold only a handful of heart-rate samples for a
workout, while the workout's own WorkoutStatistics carries the watch's average
and maximum computed from every beat. The summary wins when it exists."""

import zipfile
from datetime import datetime

import pytest

from app import parser
from app.models import Activity, ActivityStream

# Mirrors the real 2026-06-10 run: 12 samples in the export, mostly warm-up,
# while the watch's own summary says the run averaged ~156 bpm.
SPARSE_RUN_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min" startDate="2026-06-10 18:38:05 -0400" endDate="2026-06-10 18:38:05 -0400" value="131"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min" startDate="2026-06-10 18:38:14 -0400" endDate="2026-06-10 18:38:14 -0400" value="104"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="29.33" durationUnit="min" startDate="2026-06-10 18:37:31 -0400" endDate="2026-06-10 19:07:37 -0400">
  <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" startDate="2026-06-10 18:37:31 -0400" endDate="2026-06-10 19:07:37 -0400" sum="5.01365" unit="km"/>
  <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" startDate="2026-06-10 18:37:31 -0400" endDate="2026-06-10 19:07:37 -0400" average="155.867" minimum="93" maximum="166" unit="count/min"/>
 </Workout>
</HealthData>"""

NO_SUMMARY_XML = SPARSE_RUN_XML.replace(
    b'  <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" startDate="2026-06-10 18:37:31 -0400" endDate="2026-06-10 19:07:37 -0400" average="155.867" minimum="93" maximum="166" unit="count/min"/>\n',
    b"",
)


def _zip(tmp_path, xml_bytes, name="export.zip"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("apple_health_export/export.xml", xml_bytes)
    return path


def test_workout_window_carries_the_watch_summary():
    windows = parser.parse_apple_health_xml(SPARSE_RUN_XML)

    assert windows[0]["summary_avg_hr"] == pytest.approx(155.867)
    assert windows[0]["summary_max_hr"] == 166.0


def test_import_uses_the_watch_summary_over_sparse_samples(tmp_path, db_session):
    parser.import_apple_health_zip(_zip(tmp_path, SPARSE_RUN_XML), db_session)

    activity = db_session.query(Activity).one()
    assert activity.avg_hr == pytest.approx(155.867)
    assert activity.max_hr == 166.0


def test_import_keeps_the_samples_themselves_in_the_stream(tmp_path, db_session):
    parser.import_apple_health_zip(_zip(tmp_path, SPARSE_RUN_XML), db_session)

    stream = db_session.query(ActivityStream).one().stream_data
    assert [v for v in stream["hr"] if v is not None] == [131.0, 104.0]


def test_without_a_summary_the_samples_are_averaged_as_before(tmp_path, db_session):
    parser.import_apple_health_zip(_zip(tmp_path, NO_SUMMARY_XML), db_session)

    activity = db_session.query(Activity).one()
    assert activity.avg_hr == pytest.approx(117.5)
    assert activity.max_hr == 131.0


def test_reimporting_corrects_heart_rate_on_existing_activities(tmp_path, db_session):
    parser.import_apple_health_zip(_zip(tmp_path, NO_SUMMARY_XML, "old.zip"), db_session)
    before = db_session.query(Activity).one()
    start, key = before.start_time, before.dedup_key

    summary = parser.import_apple_health_zip(_zip(tmp_path, SPARSE_RUN_XML, "new.zip"), db_session)

    assert summary == {"imported": 0, "skipped": 1}
    db_session.expire_all()
    activity = db_session.query(Activity).one()
    assert activity.avg_hr == pytest.approx(155.867)
    assert activity.max_hr == 166.0
    assert (activity.start_time, activity.dedup_key) == (start, key)


def test_reimporting_without_a_summary_leaves_heart_rate_alone(tmp_path, db_session):
    parser.import_apple_health_zip(_zip(tmp_path, SPARSE_RUN_XML, "new.zip"), db_session)

    parser.import_apple_health_zip(_zip(tmp_path, NO_SUMMARY_XML, "old.zip"), db_session)

    db_session.expire_all()
    assert db_session.query(Activity).one().avg_hr == pytest.approx(155.867)


def test_summary_heart_rate_feeds_training_load(tmp_path, db_session):
    from app import analytics

    parser.import_apple_health_zip(_zip(tmp_path, SPARSE_RUN_XML), db_session)
    activity = db_session.query(Activity).one()

    load = analytics.trimp(activity.duration_seconds / 60, activity.avg_hr, 60, 190)
    sparse_load = analytics.trimp(activity.duration_seconds / 60, 117.5, 60, 190)
    assert load > 2 * sparse_load
