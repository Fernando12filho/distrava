from datetime import datetime

import pytest

from app import parser
from app.models import BestEffort
from regression_fixtures import seed_best_effort_runs

# label -> (duration seconds, activity id, achieved at). Activity 3 is a ride
# and must never appear; no run reaches marathon distance.
EXPECTED_BEST_EFFORTS = {
    "400m": (110.0562, 1, datetime(2026, 7, 3, 7, 0)),
    "1/2 Mile": (221.5534, 1, datetime(2026, 7, 3, 7, 0)),
    "1K": (275.8699, 1, datetime(2026, 7, 3, 7, 0)),
    "1 Mile": (446.061, 1, datetime(2026, 7, 3, 7, 0)),
    "2 Miles": (911.9443, 1, datetime(2026, 7, 3, 7, 0)),
    "5K": (1463.4264, 1, datetime(2026, 7, 3, 7, 0)),
    "10K": (3017.707, 1, datetime(2026, 7, 3, 7, 0)),
    "15K": (4708.0055, 2, datetime(2026, 7, 12, 7, 0)),
    "10 Miles": (5063.1917, 2, datetime(2026, 7, 12, 7, 0)),
    "Half Marathon": (6653.0979, 2, datetime(2026, 7, 12, 7, 0)),
}


def _snapshot(db_session):
    return {
        be.distance_label: (be.duration_seconds, be.activity_id, be.achieved_at)
        for be in db_session.query(BestEffort).all()
    }


def _assert_matches_expected(actual):
    assert set(actual) == set(EXPECTED_BEST_EFFORTS)
    for label, (seconds, activity_id, achieved_at) in EXPECTED_BEST_EFFORTS.items():
        assert actual[label][0] == pytest.approx(seconds, abs=1e-4), label
        assert actual[label][1:] == (activity_id, achieved_at), label


def test_best_efforts_on_import_match_snapshot(db_session):
    seed_best_effort_runs(db_session)

    _assert_matches_expected(_snapshot(db_session))


def test_recompute_best_efforts_reproduces_snapshot(db_session):
    seed_best_effort_runs(db_session)

    parser.recompute_best_efforts(db_session)

    _assert_matches_expected(_snapshot(db_session))


def test_best_effort_pace_is_duration_over_distance(db_session):
    seed_best_effort_runs(db_session)

    for be in db_session.query(BestEffort).all():
        assert be.pace_per_km_seconds == pytest.approx(be.duration_seconds / (be.distance_meters / 1000.0))
