import hashlib
import json
from datetime import datetime

import pytest

from app import parser
from app.models import Activity, ActivityStream

EXPECTED_IMPORTS = {
    "sample_export.zip": dict(
        importer=parser.import_apple_health_zip,
        activity=dict(
            activity_type="Run",
            start_time=datetime(2026, 7, 1, 15, 0),
            end_time=datetime(2026, 7, 1, 15, 30),
            duration_seconds=1800,
            distance_meters=5000.0,
            avg_hr=148.5,
            max_hr=152.0,
            elevation_gain_meters=None,
            source="apple_health",
            source_device="Apple Watch",
            dedup_key="3523e91405e4eacd10f567101f31c40207dbb20663d2897d4689db7a235469f6",
        ),
        stream_sha256="60753ae4a26adbeedde0a40a87b21fb5c3cc50526c627dc6fe44e01bda953dc8",
    ),
    "sample.gpx": dict(
        importer=parser.import_gpx,
        activity=dict(
            activity_type="Run",
            start_time=datetime(2026, 7, 1, 8, 0),
            end_time=datetime(2026, 7, 1, 8, 10),
            duration_seconds=600,
            distance_meters=146.28076618833938,
            avg_hr=147.66666666666666,
            max_hr=155.0,
            elevation_gain_meters=5.0,
            source="gpx",
            source_device=None,
            dedup_key="51aed8c65ae8c4f5d9a44287d0e5cff7c2c4dd5cdee888376ec3f302b37e8ee2",
        ),
        stream_sha256="c5f4848de801ada044651f0099b77f61b44238cb6558778f4980badb45f8f2c9",
    ),
    "sample.csv": dict(
        importer=parser.import_csv,
        activity=dict(
            activity_type="Run",
            start_time=datetime(2026, 7, 1, 8, 0),
            end_time=datetime(2026, 7, 1, 8, 30),
            duration_seconds=1800,
            distance_meters=5000.0,
            avg_hr=148.0,
            max_hr=165.0,
            elevation_gain_meters=42.0,
            source="csv",
            source_device=None,
            dedup_key="98e6dfa767a30b7aab40f8fea99d6646a4d71d0c622c3af14336cf4c83e581a7",
        ),
        stream_sha256=None,
    ),
}


def _stream_digest(stream_data):
    return hashlib.sha256(json.dumps(stream_data, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("fixture_name", sorted(EXPECTED_IMPORTS))
def test_import_parses_identically(fixture_name, fixtures_dir, db_session):
    expected = EXPECTED_IMPORTS[fixture_name]

    summary = expected["importer"](fixtures_dir / fixture_name, db_session)

    assert summary == {"imported": 1, "skipped": 0}
    activity = db_session.query(Activity).one()
    actual = {field: getattr(activity, field) for field in expected["activity"]}
    assert actual == expected["activity"]
    streams = [_stream_digest(s.stream_data) for s in db_session.query(ActivityStream).all()]
    assert streams == ([expected["stream_sha256"]] if expected["stream_sha256"] else [])


@pytest.mark.parametrize("fixture_name", sorted(EXPECTED_IMPORTS))
def test_reimport_is_skipped(fixture_name, fixtures_dir, db_session):
    importer = EXPECTED_IMPORTS[fixture_name]["importer"]
    importer(fixtures_dir / fixture_name, db_session)

    summary = importer(fixtures_dir / fixture_name, db_session)

    assert summary == {"imported": 0, "skipped": 1}
    assert db_session.query(Activity).count() == 1
