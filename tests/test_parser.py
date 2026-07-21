import zipfile
from datetime import datetime

import pytest

from app import parser
from app.models import Activity, ActivityStream, BestEffort

DUPLICATE_WORKOUT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30.0" durationUnit="min" totalDistance="5.0" totalDistanceUnit="km" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:30:00 -0700"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30.0" durationUnit="min" totalDistance="5.0" totalDistanceUnit="km" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:30:00 -0700"/>
</HealthData>"""

BILLION_LAUGHS_XML = b"""<?xml version="1.0"?>
<!DOCTYPE HealthData [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<HealthData>&lol2;</HealthData>"""

WORKOUT_STATISTICS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30.0" durationUnit="min" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:30:00 -0700" sourceName="Fernando&#8217;s Apple Watch">
  <WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" sum="300" unit="Cal"/>
  <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" sum="5.2" unit="km"/>
 </Workout>
</HealthData>"""

CYCLING_DISTANCE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Workout workoutActivityType="HKWorkoutActivityTypeCycling" duration="30.0" durationUnit="min" totalDistance="10.0" totalDistanceUnit="km" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:30:00 -0700"/>
 <Record type="HKQuantityTypeIdentifierDistanceCycling" sourceName="Apple Watch" unit="km" creationDate="2026-07-01 08:10:00 -0700" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:10:00 -0700" value="3.0"/>
</HealthData>"""

ROUTE_LINKED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30.0" durationUnit="min" totalDistance="5.0" totalDistanceUnit="km" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:30:00 -0700">
  <WorkoutRoute><FileReference path="/workout-routes/route_2026-07-01_8.00am.gpx"/></WorkoutRoute>
 </Workout>
</HealthData>"""

ME_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Me HKCharacteristicTypeIdentifierDateOfBirth="2000-04-02" HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexMale"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30.0" durationUnit="min" totalDistance="5.0" totalDistanceUnit="km" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:30:00 -0700"/>
</HealthData>"""


def test_apple_health_xml_produces_correct_activity(fixtures_dir):
    xml_bytes = (fixtures_dir / "sample_export.xml").read_bytes()

    workouts = parser.parse_apple_health_xml(xml_bytes)

    assert len(workouts) == 1
    w = workouts[0]
    assert w["activity_type"] == "Run"
    assert w["start_time"] == datetime(2026, 7, 1, 15, 0, 0)
    assert w["end_time"] == datetime(2026, 7, 1, 15, 30, 0)
    assert w["duration_seconds"] == 1800
    assert w["distance_meters"] == 5000.0


def test_two_pass_buckets_records_into_correct_workout_window(fixtures_dir):
    xml_bytes = (fixtures_dir / "sample_export.xml").read_bytes()

    workouts = parser.parse_apple_health_xml(xml_bytes)

    stream = workouts[0]["stream_data"]
    assert stream["time"] == [0, 300, 900]
    assert stream["hr"] == [None, 145.0, 152.0]
    assert stream["distance"] == [1500.0, None, None]


def test_records_outside_all_workout_windows_are_discarded_no_crash(fixtures_dir):
    xml_bytes = (fixtures_dir / "sample_export.xml").read_bytes()

    workouts = parser.parse_apple_health_xml(xml_bytes)

    stream = workouts[0]["stream_data"]
    assert len(stream["time"]) == 3
    assert all(v != 70.0 for v in stream["hr"])


def test_dedup_within_one_parse_overlapping_workouts_keeps_one():
    workouts = parser.parse_apple_health_xml(DUPLICATE_WORKOUT_XML)

    assert len(workouts) == 1


def test_distance_falls_back_to_workout_statistics_when_attribute_missing():
    workouts = parser.parse_apple_health_xml(WORKOUT_STATISTICS_XML)

    assert len(workouts) == 1
    assert workouts[0]["distance_meters"] == pytest.approx(5200.0)


def test_source_device_captured_from_workout_source_name():
    workouts = parser.parse_apple_health_xml(WORKOUT_STATISTICS_XML)

    assert workouts[0]["source_device"] == "Fernando’s Apple Watch"


def test_cycling_distance_records_bucketed_into_stream():
    workouts = parser.parse_apple_health_xml(CYCLING_DISTANCE_XML)

    stream = workouts[0]["stream_data"]
    assert stream["distance"] == [3000.0]


def test_route_file_reference_captured_on_workout():
    workouts = parser.parse_apple_health_xml(ROUTE_LINKED_XML)

    assert workouts[0]["route_file"] == "workout-routes/route_2026-07-01_8.00am.gpx"


def test_route_file_is_none_when_no_route():
    workouts = parser.parse_apple_health_xml(DUPLICATE_WORKOUT_XML)

    assert workouts[0]["route_file"] is None


def test_collect_workout_windows_captures_me_birth_year():
    windows, me_attrs = parser._collect_workout_windows(ME_XML)

    assert me_attrs.get("birth_year") == 2000


def test_collect_workout_windows_me_attrs_empty_when_absent():
    windows, me_attrs = parser._collect_workout_windows(DUPLICATE_WORKOUT_XML)

    assert me_attrs.get("birth_year") is None


ROUTE_GPX_BYTES = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Apple Health Export" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lon="-81.365080" lat="28.560426"><ele>34.6</ele><time>2026-07-01T15:00:00Z</time></trkpt>
    <trkpt lon="-81.365085" lat="28.560427"><ele>34.8</ele><time>2026-07-01T15:00:10Z</time></trkpt>
  </trkseg></trk>
</gpx>"""


def test_parse_route_gpx_returns_points_relative_to_window_start():
    window_start = datetime(2026, 7, 1, 15, 0, 0)

    points = parser._parse_route_gpx(ROUTE_GPX_BYTES, window_start)

    assert len(points) == 2
    assert points[0] == {"elapsed": 0, "lat": 28.560426, "lon": -81.365080, "elevation": 34.6}
    assert points[1]["elapsed"] == 10


def test_bucket_records_merges_route_points_into_stream():
    xml_bytes = b"<HealthData></HealthData>"
    windows = [{"start_time": datetime(2026, 7, 1, 15, 0, 0), "end_time": datetime(2026, 7, 1, 15, 1, 0)}]
    route_points_by_index = {
        0: [
            {"elapsed": 0, "lat": 28.56, "lon": -81.36, "elevation": 34.6},
            {"elapsed": 10, "lat": 28.561, "lon": -81.361, "elevation": 35.0},
        ]
    }

    streams = parser._bucket_records(xml_bytes, windows, route_points_by_index)

    assert streams[0]["time"] == [0, 10]
    assert streams[0]["lat"] == [28.56, 28.561]
    assert streams[0]["lon"] == [-81.36, -81.361]
    assert streams[0]["elevation"] == [34.6, 35.0]


def _build_zip_with_route(tmp_path, name="export_with_route.zip"):
    export_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Me HKCharacteristicTypeIdentifierDateOfBirth="1995-06-15"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="1.0" durationUnit="min" totalDistance="1.0" totalDistanceUnit="km" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:01:00 -0700" sourceName="Test Watch">
  <WorkoutRoute><FileReference path="/workout-routes/route_test.gpx"/></WorkoutRoute>
 </Workout>
</HealthData>"""
    route_gpx = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lon="-81.0" lat="28.0"><ele>10.0</ele><time>2026-07-01T15:00:00Z</time></trkpt>
    <trkpt lon="-81.001" lat="28.001"><ele>15.0</ele><time>2026-07-01T15:00:30Z</time></trkpt>
  </trkseg></trk>
</gpx>"""
    zip_path = tmp_path / name
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("apple_health_export/export.xml", export_xml)
        zf.writestr("apple_health_export/workout-routes/route_test.gpx", route_gpx)
    return zip_path


def test_import_zip_captures_route_points_and_elevation_gain(tmp_path, db_session):
    from app.models import ActivityStream

    zip_path = _build_zip_with_route(tmp_path)

    parser.import_apple_health_zip(zip_path, db_session)

    activity = db_session.query(Activity).one()
    stream = db_session.query(ActivityStream).filter_by(activity_id=activity.id).one()
    assert 28.0 in stream.stream_data["lat"]
    assert -81.0 in stream.stream_data["lon"]
    assert activity.elevation_gain_meters == pytest.approx(5.0)


def test_import_zip_persists_source_device(tmp_path, db_session):
    zip_path = _build_zip_with_route(tmp_path)

    parser.import_apple_health_zip(zip_path, db_session)

    activity = db_session.query(Activity).one()
    assert activity.source_device == "Test Watch"


def test_import_zip_auto_fills_birth_year_when_unset(tmp_path, db_session):
    from app.models import UserSettings

    zip_path = _build_zip_with_route(tmp_path)

    parser.import_apple_health_zip(zip_path, db_session)

    settings = db_session.query(UserSettings).one()
    assert settings.birth_year == 1995


MULTI_DISTANCE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30.0" durationUnit="min" totalDistance="5.0" totalDistanceUnit="km" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:30:00 -0700"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" unit="km" creationDate="2026-07-01 08:05:00 -0700" startDate="2026-07-01 08:05:00 -0700" endDate="2026-07-01 08:05:00 -0700" value="0.5"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" unit="km" creationDate="2026-07-01 08:10:00 -0700" startDate="2026-07-01 08:10:00 -0700" endDate="2026-07-01 08:10:00 -0700" value="0.3"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" unit="km" creationDate="2026-07-01 08:15:00 -0700" startDate="2026-07-01 08:15:00 -0700" endDate="2026-07-01 08:15:00 -0700" value="0.2"/>
</HealthData>"""


def test_apple_health_distance_records_accumulate_into_running_total():
    workouts = parser.parse_apple_health_xml(MULTI_DISTANCE_XML)

    stream = workouts[0]["stream_data"]
    assert stream["distance"] == pytest.approx([500.0, 800.0, 1000.0])


def test_import_zip_does_not_overwrite_existing_birth_year(tmp_path, db_session):
    from app.models import UserSettings

    db_session.add(UserSettings(birth_year=1988))
    db_session.commit()
    zip_path = _build_zip_with_route(tmp_path)

    parser.import_apple_health_zip(zip_path, db_session)

    settings = db_session.query(UserSettings).one()
    assert settings.birth_year == 1988


def test_dedup_across_reimports_same_zip_twice_no_duplicate_rows(fixtures_dir, db_session):
    zip_path = fixtures_dir / "sample_export.zip"

    result1 = parser.import_apple_health_zip(zip_path, db_session)
    assert result1 == {"imported": 1, "skipped": 0}

    result2 = parser.import_apple_health_zip(zip_path, db_session)
    assert result2 == {"imported": 0, "skipped": 1}

    assert db_session.query(Activity).count() == 1


def test_gpx_import_creates_activity_and_stream(fixtures_dir, db_session):
    gpx_path = fixtures_dir / "sample.gpx"

    result = parser.import_gpx(gpx_path, db_session)

    assert result == {"imported": 1, "skipped": 0}
    activity = db_session.query(Activity).one()
    assert activity.activity_type == "Run"
    assert activity.source == "gpx"
    assert activity.duration_seconds == 600
    assert activity.avg_hr == pytest.approx(147.6667, abs=0.001)
    assert activity.max_hr == 155.0
    assert activity.elevation_gain_meters == pytest.approx(5.0, abs=0.001)
    assert activity.distance_meters == pytest.approx(146.28, abs=0.5)

    stream = db_session.query(ActivityStream).filter_by(activity_id=activity.id).one()
    assert stream.stream_data["hr"] == [140.0, 148.0, 155.0]
    assert len(stream.stream_data["time"]) == 3
    assert stream.stream_data["lat"] == [37.7749, 37.7755, 37.7760]
    assert stream.stream_data["lon"] == [-122.4194, -122.4190, -122.4185]


def test_csv_import_creates_activity_without_stream(fixtures_dir, db_session):
    csv_path = fixtures_dir / "sample.csv"

    result = parser.import_csv(csv_path, db_session)

    assert result == {"imported": 1, "skipped": 0}
    activity = db_session.query(Activity).one()
    assert activity.activity_type == "Run"
    assert activity.duration_seconds == 1800
    assert activity.distance_meters == 5000.0
    assert activity.avg_hr == 148.0
    assert activity.max_hr == 165.0
    assert activity.elevation_gain_meters == 42.0
    assert activity.source == "csv"
    assert db_session.query(ActivityStream).count() == 0


def test_zip_path_traversal_entry_raises_and_writes_nothing(tmp_path, db_session):
    evil_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil_zip, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")

    with pytest.raises(ValueError):
        parser.import_apple_health_zip(evil_zip, db_session)

    assert db_session.query(Activity).count() == 0
    assert not (tmp_path.parent.parent / "evil.txt").exists()


def test_zip_missing_export_xml_raises_clean_error(tmp_path, db_session):
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("apple_health_export/readme.txt", "no export here")

    with pytest.raises(ValueError, match="export.xml"):
        parser.import_apple_health_zip(bad_zip, db_session)


def test_entity_expansion_attempt_is_caught():
    with pytest.raises(Exception):
        parser.parse_apple_health_xml(BILLION_LAUGHS_XML)


def test_update_best_efforts_creates_pr_row(db_session, make_activity):
    activity = make_activity(distance_meters=10000.0, duration_seconds=3000, dedup_key="be-1")
    times = [i * 300 for i in range(11)]
    distances = [i * 1000.0 for i in range(11)]
    stream_data = {"time": times, "hr": [None] * 11, "distance": distances, "elevation": [], "pace": []}

    parser.update_best_efforts(db_session, activity, stream_data)

    five_k = db_session.query(BestEffort).filter_by(distance_label="5K").one()
    assert five_k.duration_seconds == pytest.approx(1500.0, abs=0.01)
    assert five_k.activity_id == activity.id


def test_update_best_efforts_pr_replaces_old(db_session, make_activity):
    slow_activity = make_activity(dedup_key="slow")
    fast_activity = make_activity(dedup_key="fast")
    slow_stream = {"time": [0, 1800], "hr": [None, None], "distance": [0, 5000.0], "elevation": [], "pace": []}
    fast_stream = {"time": [0, 1400], "hr": [None, None], "distance": [0, 5000.0], "elevation": [], "pace": []}

    parser.update_best_efforts(db_session, slow_activity, slow_stream)
    parser.update_best_efforts(db_session, fast_activity, fast_stream)

    five_k = db_session.query(BestEffort).filter_by(distance_label="5K").one()
    assert five_k.activity_id == fast_activity.id
    assert five_k.duration_seconds == pytest.approx(1400.0, abs=0.01)


def test_update_best_efforts_non_pr_does_not_overwrite(db_session, make_activity):
    fast_activity = make_activity(dedup_key="fast")
    slow_activity = make_activity(dedup_key="slow")
    fast_stream = {"time": [0, 1400], "hr": [None, None], "distance": [0, 5000.0], "elevation": [], "pace": []}
    slow_stream = {"time": [0, 1800], "hr": [None, None], "distance": [0, 5000.0], "elevation": [], "pace": []}

    parser.update_best_efforts(db_session, fast_activity, fast_stream)
    parser.update_best_efforts(db_session, slow_activity, slow_stream)

    five_k = db_session.query(BestEffort).filter_by(distance_label="5K").one()
    assert five_k.activity_id == fast_activity.id
    assert five_k.duration_seconds == pytest.approx(1400.0, abs=0.01)


DUAL_SOURCE_DISTANCE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="10.0" durationUnit="min" totalDistance="1.2" totalDistanceUnit="km" startDate="2026-07-01 08:00:00 -0700" endDate="2026-07-01 08:10:00 -0700"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" sourceName="Watch" unit="m" value="200" startDate="2026-07-01 08:01:00 -0700" endDate="2026-07-01 08:01:03 -0700"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" sourceName="Watch" unit="m" value="200" startDate="2026-07-01 08:03:00 -0700" endDate="2026-07-01 08:03:03 -0700"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" sourceName="Watch" unit="m" value="200" startDate="2026-07-01 08:05:00 -0700" endDate="2026-07-01 08:05:03 -0700"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" sourceName="Watch" unit="m" value="200" startDate="2026-07-01 08:07:00 -0700" endDate="2026-07-01 08:07:03 -0700"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" sourceName="Watch" unit="m" value="200" startDate="2026-07-01 08:09:00 -0700" endDate="2026-07-01 08:09:03 -0700"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" sourceName="iPhone" unit="m" value="600" startDate="2026-07-01 08:04:00 -0700" endDate="2026-07-01 08:04:01 -0700"/>
</HealthData>"""


def test_overlapping_second_source_does_not_inflate_distance():
    windows = parser.parse_apple_health_xml(DUAL_SOURCE_DISTANCE_XML)
    distances = [d for d in windows[0]["stream_data"]["distance"] if d is not None]

    assert distances[-1] == pytest.approx(1000.0, abs=1.0)


def test_overlapping_second_source_does_not_create_distance_spike():
    windows = parser.parse_apple_health_xml(DUAL_SOURCE_DISTANCE_XML)
    stream = windows[0]["stream_data"]
    pairs = [(t, d) for t, d in zip(stream["time"], stream["distance"]) if d is not None]

    for (t0, d0), (t1, d1) in zip(pairs, pairs[1:]):
        speed = (d1 - d0) / (t1 - t0)
        assert speed < 8.0, f"implausible {speed:.1f} m/s between t={t0} and t={t1}"


def test_update_best_efforts_ignores_cycling(db_session, make_activity):
    ride = make_activity(activity_type="Cycle", dedup_key="ride-1")
    stream_data = {"time": [0, 489], "hr": [None, None], "distance": [0, 5000.0], "elevation": [], "pace": []}

    parser.update_best_efforts(db_session, ride, stream_data)

    assert db_session.query(BestEffort).count() == 0


def test_update_best_efforts_ignores_strength_training(db_session, make_activity):
    gym = make_activity(activity_type="TraditionalStrengthTraining", dedup_key="gym-1")
    stream_data = {"time": [0, 120], "hr": [None, None], "distance": [0, 3218.0], "elevation": [], "pace": []}

    parser.update_best_efforts(db_session, gym, stream_data)

    assert db_session.query(BestEffort).count() == 0


def test_recompute_best_efforts_drops_stale_non_run_prs(db_session, make_activity):
    ride = make_activity(activity_type="Cycle", dedup_key="ride-2")
    run = make_activity(activity_type="Run", dedup_key="run-2")
    ride_stream = {"time": [0, 489], "hr": [None, None], "distance": [0, 5000.0], "elevation": [], "pace": []}
    run_stream = {"time": [0, 1500], "hr": [None, None], "distance": [0, 5000.0], "elevation": [], "pace": []}
    db_session.add(ActivityStream(activity_id=ride.id, stream_data=ride_stream))
    db_session.add(ActivityStream(activity_id=run.id, stream_data=run_stream))
    db_session.add(
        BestEffort(
            distance_label="5K",
            distance_meters=5000.0,
            activity_id=ride.id,
            duration_seconds=489.0,
            pace_per_km_seconds=97.8,
            achieved_at=ride.start_time,
        )
    )
    db_session.commit()

    parser.recompute_best_efforts(db_session)

    five_k = db_session.query(BestEffort).filter_by(distance_label="5K").one()
    assert five_k.activity_id == run.id
    assert five_k.duration_seconds == pytest.approx(1500.0, abs=0.01)
