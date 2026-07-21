import io

import pytest


def test_index_redirects_to_dashboard(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_activity_list_returns_200(client, make_activity):
    make_activity()
    response = client.get("/activities")
    assert response.status_code == 200


def test_activity_list_shows_miles_when_units_imperial(client, make_activity, db_session):
    from app.models import UserSettings

    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    make_activity(distance_meters=5000.0, duration_seconds=1500)

    response = client.get("/activities")

    body = response.data.decode()
    assert "3.1 mi" in body
    assert "8:03" in body


def test_activity_list_shows_km_when_units_metric_default(client, make_activity):
    make_activity(distance_meters=5000.0, duration_seconds=1500)

    response = client.get("/activities")

    body = response.data.decode()
    assert "5.0 km" in body
    assert "5:00" in body


def test_activity_list_filtered_by_type(client, make_activity):
    run = make_activity(activity_type="Run", dedup_key="run-key")
    walk = make_activity(activity_type="Walk", dedup_key="walk-key")

    response = client.get("/activities?type=Run")

    body = response.data.decode()
    assert f'data-activity-id="{run.id}"' in body
    assert f'data-activity-id="{walk.id}"' not in body


def test_activity_list_filtered_by_date_range(client, make_activity):
    from datetime import datetime

    early = make_activity(
        start_time=datetime(2026, 1, 1, 8, 0, 0),
        end_time=datetime(2026, 1, 1, 8, 30, 0),
        dedup_key="early-key",
    )
    late = make_activity(
        start_time=datetime(2026, 6, 1, 8, 0, 0),
        end_time=datetime(2026, 6, 1, 8, 30, 0),
        dedup_key="late-key",
    )

    response = client.get("/activities?from=2026-05-01&to=2026-07-01")

    body = response.data.decode()
    assert f'data-activity-id="{late.id}"' in body
    assert f'data-activity-id="{early.id}"' not in body


def test_activity_list_sorted_by_distance_ascending(client, make_activity):
    far = make_activity(distance_meters=10000.0, dedup_key="far-key")
    near = make_activity(distance_meters=2000.0, dedup_key="near-key")

    response = client.get("/activities?sort=dist&dir=asc")

    body = response.data.decode()
    assert body.index(f'data-activity-id="{near.id}"') < body.index(f'data-activity-id="{far.id}"')


def test_activity_list_paginates_ten_per_page(client, make_activity):
    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1, 8, 0, 0)
    activities = [
        make_activity(start_time=base + timedelta(days=i), end_time=base + timedelta(days=i, minutes=30), dedup_key=f"page-key-{i}")
        for i in range(12)
    ]

    page1 = client.get("/activities?page=1").data.decode()
    page2 = client.get("/activities?page=2").data.decode()

    assert sum(f'data-activity-id="{a.id}"' in page1 for a in activities) == 10
    assert sum(f'data-activity-id="{a.id}"' in page2 for a in activities) == 2


def test_activity_list_range_filters_last_30_days(client, make_activity):
    from datetime import datetime, timedelta

    now = datetime.now()
    recent = make_activity(start_time=now - timedelta(days=5), end_time=now - timedelta(days=5) + timedelta(minutes=30), dedup_key="recent-key")
    old = make_activity(start_time=now - timedelta(days=90), end_time=now - timedelta(days=90) + timedelta(minutes=30), dedup_key="old-key")

    response = client.get("/activities?range=30")

    body = response.data.decode()
    assert f'data-activity-id="{recent.id}"' in body
    assert f'data-activity-id="{old.id}"' not in body


def test_activity_detail_shows_imperial_units_in_summary(client, make_activity, db_session):
    from app.models import UserSettings

    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    activity = make_activity(distance_meters=5000.0, duration_seconds=1500, elevation_gain_meters=100.0)

    response = client.get(f"/activities/{activity.id}")

    body = response.data.decode()
    assert "3.1" in body
    assert "mi" in body
    assert "328" in body
    assert "ft" in body


def test_activity_detail_splits_header_says_per_mile_when_imperial(client, make_activity, db_session):
    from app.models import ActivityStream, UserSettings

    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    times = [i * 300 for i in range(6)]
    distances = [i * 1000.0 for i in range(6)]
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": [None] * 6, "distance": distances, "elevation": [], "pace": []},
        )
    )
    db_session.commit()

    response = client.get(f"/activities/{activity.id}")

    assert "per mile" in response.data.decode()


def test_activity_detail_returns_200_for_existing(client, make_activity):
    activity = make_activity()
    response = client.get(f"/activities/{activity.id}")
    assert response.status_code == 200


def test_activity_detail_computes_splits_from_stream(client, make_activity, db_session):
    from app.models import ActivityStream

    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    times = [i * 300 for i in range(6)]
    distances = [i * 1000.0 for i in range(6)]
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": [None] * 6, "distance": distances, "elevation": [], "pace": []},
        )
    )
    db_session.commit()

    response = client.get(f"/activities/{activity.id}")

    assert response.status_code == 200
    body = response.data.decode()
    assert body.count("data-split-index") == 5


def test_activity_detail_returns_404_for_missing(client):
    response = client.get("/activities/999")
    assert response.status_code == 404


def test_activity_detail_falls_back_to_synthesized_title_when_none(client, make_activity):
    from datetime import datetime

    activity = make_activity(activity_type="Run", start_time=datetime(2026, 7, 11, 6, 42, 0), title=None)

    response = client.get(f"/activities/{activity.id}")

    body = response.data.decode()
    assert "Run · Jul 11, 2026" in body


def test_activity_detail_shows_real_title_when_set(client, make_activity):
    activity = make_activity(title="Morning tempo along the river")

    response = client.get(f"/activities/{activity.id}")

    assert "Morning tempo along the river" in response.data.decode()


def test_activity_detail_omits_device_when_none(client, make_activity):
    activity = make_activity(source_device=None)

    response = client.get(f"/activities/{activity.id}")

    assert response.status_code == 200


def test_activity_detail_shows_device_when_set(client, make_activity):
    activity = make_activity(source_device="Garmin Forerunner 265")

    response = client.get(f"/activities/{activity.id}")

    assert "Garmin Forerunner 265" in response.data.decode()


def test_activity_detail_marks_season_best_for_own_pr(client, make_activity, db_session):
    from app.models import ActivityStream, BestEffort

    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    times = [i * 300 for i in range(6)]
    distances = [i * 1000.0 for i in range(6)]
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": [None] * 6, "distance": distances, "elevation": [], "pace": []},
        )
    )
    db_session.add(
        BestEffort(
            distance_label="1K",
            distance_meters=1000.0,
            activity_id=activity.id,
            duration_seconds=300.0,
            pace_per_km_seconds=300.0,
            achieved_at=activity.start_time,
        )
    )
    db_session.commit()

    response = client.get(f"/activities/{activity.id}")

    assert "SEASON BEST" in response.data.decode()


def test_activity_detail_shows_time_in_hr_zones(client, make_activity, db_session):
    from app.models import ActivityStream

    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    times = [i * 300 for i in range(6)]
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": [150.0] * 6, "distance": [None] * 6, "elevation": [], "pace": []},
        )
    )
    db_session.commit()

    body = client.get(f"/activities/{activity.id}").data.decode()

    assert "Heart rate zones" in body
    zone2_index = body.index("Zone 2 — Aerobic")
    assert zone2_index < body.index("25:00", zone2_index) < body.index("Zone 3 — Tempo")


def test_activity_detail_counts_low_hr_time_in_zone_one(client, make_activity, db_session):
    from app.models import ActivityStream

    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    times = [i * 300 for i in range(6)]
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": [90.0] * 6, "distance": [None] * 6, "elevation": [], "pace": []},
        )
    )
    db_session.commit()

    body = client.get(f"/activities/{activity.id}").data.decode()

    assert "Heart rate zones" in body
    assert "100%" in body


def test_activity_detail_shows_hr_zones_for_non_run_with_hr(client, make_activity, db_session):
    from app.models import ActivityStream

    activity = make_activity(activity_type="TraditionalStrengthTraining", distance_meters=0.0)
    times = [i * 300 for i in range(6)]
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": [150.0] * 6, "distance": [None] * 6, "elevation": [], "pace": []},
        )
    )
    db_session.commit()

    body = client.get(f"/activities/{activity.id}").data.decode()

    assert "Heart rate zones" in body


def test_activity_detail_passes_zone_bands_to_charts_script(client, make_activity, db_session):
    from app.models import ActivityStream

    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    times = [i * 300 for i in range(6)]
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={
                "time": times,
                "hr": [150.0] * 6,
                "distance": [i * 1000.0 for i in range(6)],
                "lat": [47.6 + i * 0.001 for i in range(6)],
                "lon": [-122.3 + i * 0.001 for i in range(6)],
                "elevation": [],
                "pace": [],
            },
        )
    )
    db_session.commit()

    body = client.get(f"/activities/{activity.id}").data.decode()

    assert "min_bpm" in body


def test_activity_detail_omits_hr_zones_without_hr_data(client, make_activity, db_session):
    from app.models import ActivityStream

    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    times = [i * 300 for i in range(6)]
    distances = [i * 1000.0 for i in range(6)]
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": [None] * 6, "distance": distances, "elevation": [], "pace": []},
        )
    )
    db_session.commit()

    body = client.get(f"/activities/{activity.id}").data.decode()

    assert "Heart rate zones" not in body


def test_activity_stream_json_has_expected_keys(client, make_activity, db_session):
    from app.models import ActivityStream

    activity = make_activity()
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"hr": [140], "pace": [], "elevation": [], "distance": [0], "time": [0]},
        )
    )
    db_session.commit()

    response = client.get(f"/activities/{activity.id}/stream.json")

    assert response.status_code == 200
    data = response.get_json()
    assert set(data.keys()) == {"hr", "pace", "elevation", "distance", "time"}


def test_import_valid_zip_returns_200_and_summary(client, fixtures_dir):
    zip_bytes = (fixtures_dir / "sample_export.zip").read_bytes()

    response = client.post(
        "/import",
        data={"file": (io.BytesIO(zip_bytes), "sample_export.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["imported"] == 1
    assert data["skipped"] == 0
    assert data["filename"] == "sample_export.zip"
    assert data["size_bytes"] == len(zip_bytes)
    assert data["elapsed_seconds"] >= 0
    assert "date_range" in data


def test_import_invalid_file_type_returns_400(client):
    response = client.post(
        "/import",
        data={"file": (io.BytesIO(b"not a valid import"), "notes.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400


def test_import_oversized_returns_413(app):
    app.config["MAX_UPLOAD_BYTES"] = 10
    test_client = app.test_client()

    response = test_client.post(
        "/import",
        data={"file": (io.BytesIO(b"x" * 1000), "big.gpx")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 413


def test_import_page_returns_200(client):
    response = client.get("/import")
    assert response.status_code == 200


def test_settings_page_get_returns_200(client):
    response = client.get("/settings")
    assert response.status_code == 200


def test_settings_page_shows_weight_converted_to_pounds_when_imperial(client, db_session):
    from app.models import UserSettings

    db_session.add(UserSettings(weight_kg=72.0, units="imperial"))
    db_session.commit()

    response = client.get("/settings")

    assert "158.7" in response.data.decode()


def test_settings_page_has_explicit_save_button(client):
    body = client.get("/settings").data.decode()

    assert 'type="submit" form="settings-form"' in body
    assert ">Save<" in body


def test_settings_page_native_post_saves_resting_hr_and_redirects(client, db_session):
    from app.models import UserSettings

    response = client.post("/settings", data={"resting_hr": "52", "units": "metric"})

    assert response.status_code == 302
    assert db_session.query(UserSettings).one().resting_hr == 52


def test_settings_page_post_converts_submitted_pounds_back_to_kg(client, db_session):
    from app.models import UserSettings

    response = client.post(
        "/settings",
        data={"resting_hr": "55", "max_hr": "185", "birth_year": "1990", "weight_kg": "158.73", "units": "imperial"},
    )

    assert response.status_code == 302
    stored = db_session.query(UserSettings).one()
    assert stored.weight_kg == pytest.approx(72.0, abs=0.01)


def test_settings_page_post_creates_settings(client, db_session):
    from app.models import UserSettings

    response = client.post(
        "/settings", data={"resting_hr": "55", "max_hr": "185", "birth_year": "1990"}
    )

    assert response.status_code == 302
    stored = db_session.query(UserSettings).one()
    assert stored.resting_hr == 55
    assert stored.max_hr == 185
    assert stored.birth_year == 1990


def test_settings_page_post_updates_existing_row(client, db_session):
    from app.models import UserSettings

    client.post("/settings", data={"resting_hr": "55", "max_hr": "185", "birth_year": "1990"})
    client.post("/settings", data={"resting_hr": "60", "max_hr": "190", "birth_year": "1991"})

    assert db_session.query(UserSettings).count() == 1
    stored = db_session.query(UserSettings).one()
    assert stored.resting_hr == 60


def test_settings_page_post_persists_weight_and_units(client, db_session):
    from app.models import UserSettings

    response = client.post(
        "/settings",
        data={"resting_hr": "55", "max_hr": "185", "birth_year": "1990", "weight_kg": "72", "units": "metric"},
    )

    assert response.status_code == 302
    stored = db_session.query(UserSettings).one()
    assert stored.weight_kg == 72.0
    assert stored.units == "metric"


def test_settings_page_post_ajax_returns_204(client):
    response = client.post(
        "/settings",
        data={"resting_hr": "55", "max_hr": "185", "birth_year": "1990"},
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 204


def test_settings_wipe_deletes_all_activities(client, make_activity, db_session):
    from app.models import Activity

    make_activity()
    make_activity(dedup_key="second-key")

    response = client.post("/settings/wipe")

    assert response.status_code == 302
    assert db_session.query(Activity).count() == 0


def test_dashboard_returns_200(client, make_activity):
    make_activity()
    response = client.get("/dashboard")
    assert response.status_code == 200


def test_dashboard_returns_200_with_no_activities(client):
    response = client.get("/dashboard")
    assert response.status_code == 200


def test_dashboard_shows_empty_state_when_no_activities(client):
    response = client.get("/dashboard")
    assert "Nothing imported yet" in response.data.decode()


def test_dashboard_shows_populated_sections_when_activities_exist(client, make_activity):
    make_activity()

    body = client.get("/dashboard").data.decode()

    assert "Training calendar" in body
    assert "Weekly volume" in body
    assert "Recent activities" in body
    assert "Recent PRs" in body


def _add_best_effort(db_session, activity, label="5K", distance_meters=5000.0, duration_seconds=1500.0):
    from app.models import BestEffort

    db_session.add(
        BestEffort(
            distance_label=label,
            distance_meters=distance_meters,
            activity_id=activity.id,
            duration_seconds=duration_seconds,
            pace_per_km_seconds=duration_seconds / (distance_meters / 1000),
            achieved_at=activity.start_time,
        )
    )
    db_session.commit()


def test_dashboard_shows_race_predictions_from_best_effort(client, make_activity, db_session):
    from app import analytics

    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    _add_best_effort(db_session, activity)

    body = client.get("/dashboard").data.decode()

    expected_10k = analytics.format_duration(analytics.riegel_predict(1500.0, 5000.0, 10000.0))
    expected_marathon = analytics.format_duration(analytics.riegel_predict(1500.0, 5000.0, 42195.0))
    assert "Race predictions" in body
    assert "Marathon" in body
    assert expected_10k in body
    assert expected_marathon in body


def test_dashboard_predictions_use_longest_best_effort_as_basis(client, make_activity, db_session):
    activity = make_activity(duration_seconds=3200, distance_meters=10000.0)
    _add_best_effort(db_session, activity, label="1K", distance_meters=1000.0, duration_seconds=250.0)
    _add_best_effort(db_session, activity, label="10K", distance_meters=10000.0, duration_seconds=3200.0)

    body = client.get("/dashboard").data.decode()

    assert "fastest 10K" in body


def test_dashboard_shows_estimated_vo2max(client, make_activity, db_session):
    from app import analytics

    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    _add_best_effort(db_session, activity)

    body = client.get("/dashboard").data.decode()

    expected = analytics.estimate_vo2max(5000.0, 1500.0)
    assert "VO2max" in body
    assert f"{expected:.1f}" in body


def test_dashboard_omits_race_predictions_without_best_efforts(client, make_activity):
    make_activity()

    body = client.get("/dashboard").data.decode()

    assert "Race predictions" not in body
    assert "VO2max" not in body


def test_dashboard_shows_miles_unit_when_imperial(client, make_activity, db_session):
    from datetime import date, datetime, timedelta

    from app.models import UserSettings

    db_session.add(UserSettings(units="imperial"))
    db_session.commit()
    today = date.today()
    make_activity(
        distance_meters=5000.0,
        start_time=datetime.combine(today, datetime.min.time()),
        end_time=datetime.combine(today, datetime.min.time()) + timedelta(minutes=30),
    )

    body = client.get("/dashboard").data.decode()

    assert ">mi<" in body
