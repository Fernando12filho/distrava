"""RULE-METRIC-01: resting heart rate comes from Apple Health's daily
RestingHeartRate, as the median of the last 7 days, unless typed in Settings."""

import zipfile
from datetime import date

import pytest

from app import analytics, parser
from app.models import UserSettings
from app.routes import _resolve_hr_profile


def _resting_record(day, bpm):
    return (
        f'<Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="Watch" unit="count/min" '
        f'startDate="{day} 00:10:00 -0400" endDate="{day} 23:50:00 -0400" value="{bpm}"/>'
    )


def _export(tmp_path, days, name="export.zip"):
    records = "\n".join(_resting_record(day, bpm) for day, bpm in days)
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<HealthData>\n{records}\n</HealthData>'
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("apple_health_export/export.xml", xml)
    return path


TEN_DAYS = [(f"2026-10-{d:02d}", bpm) for d, bpm in zip(range(10, 20), [70, 70, 70, 52, 50, 54, 51, 55, 49, 53])]


# ---------------------------------------------------------------- pure helper


def test_recent_median_uses_the_last_seven_days():
    readings = [(date.fromisoformat(d), bpm) for d, bpm in TEN_DAYS]

    assert analytics.recent_resting_hr(readings, days=7) == (52.0, date(2026, 10, 19))


def test_recent_median_skips_days_without_a_reading():
    readings = [(date(2026, 10, 1), 60.0), (date(2026, 10, 18), 50.0), (date(2026, 10, 19), 54.0)]

    assert analytics.recent_resting_hr(readings, days=7) == (52.0, date(2026, 10, 19))


def test_no_readings_give_nothing():
    assert analytics.recent_resting_hr([], days=7) is None


# ---------------------------------------------------------------- import


def test_import_records_the_resting_hr(tmp_path, db_session):
    parser.import_apple_health_zip(_export(tmp_path, TEN_DAYS), db_session)

    settings = db_session.query(UserSettings).one()
    assert settings.observed_resting_hr == 52
    assert settings.observed_resting_hr_on == date(2026, 10, 19)


def test_a_newer_export_updates_it(tmp_path, db_session):
    parser.import_apple_health_zip(_export(tmp_path, TEN_DAYS, "old.zip"), db_session)
    newer = TEN_DAYS + [(f"2026-10-{d}", 47) for d in range(20, 27)]

    parser.import_apple_health_zip(_export(tmp_path, newer, "new.zip"), db_session)

    settings = db_session.query(UserSettings).one()
    assert (settings.observed_resting_hr, settings.observed_resting_hr_on) == (47, date(2026, 10, 26))


def test_an_older_export_never_replaces_a_newer_reading(tmp_path, db_session):
    newer = TEN_DAYS + [(f"2026-10-{d}", 47) for d in range(20, 27)]
    parser.import_apple_health_zip(_export(tmp_path, newer, "new.zip"), db_session)

    parser.import_apple_health_zip(_export(tmp_path, TEN_DAYS, "old.zip"), db_session)

    assert db_session.query(UserSettings).one().observed_resting_hr == 47


def test_an_export_without_resting_hr_leaves_it_alone(tmp_path, db_session, fixtures_dir):
    parser.import_apple_health_zip(_export(tmp_path, TEN_DAYS), db_session)

    parser.import_apple_health_zip(fixtures_dir / "sample_export.zip", db_session)

    assert db_session.query(UserSettings).one().observed_resting_hr == 52


# ---------------------------------------------------------------- which resting HR is used


@pytest.mark.parametrize(
    "settings, expected_resting",
    [
        (None, 60),
        (UserSettings(observed_resting_hr=52), 52),
        (UserSettings(observed_resting_hr=52, resting_hr=58), 58),
    ],
)
def test_resting_hr_resolution(settings, expected_resting):
    assert _resolve_hr_profile(settings, date(2026, 10, 20))[0] == expected_resting


def test_settings_page_shows_where_resting_hr_comes_from(client, db_session):
    db_session.add(UserSettings(observed_resting_hr=52, observed_resting_hr_on=date(2026, 10, 19)))
    db_session.commit()

    html = client.get("/settings").get_data(as_text=True)

    assert 'placeholder="52"' in html
    assert "Apple Health, 7 days to Oct 19" in html
