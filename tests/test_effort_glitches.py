"""A best effort can't be built on a 'teleport': a gap of more than 15 s between
distance samples during which the distance implies more than twice the run's
typical speed. Old exports log distance in chunks like that (a 400 m in 18 s).
Pauses and GPS dropouts that catch up at normal pace stay valid — the real 10K
on 2026-09-27 has a 21 s pause."""

from datetime import datetime

import pytest

from app import analytics, parser, training_rules
from app.models import BestEffort

GAP = 15
RATIO = 2.0


def _dense_with_a_jump():
    """5 m/s for 600 s sampled every 5 s, then 500 m 'covered' in one 20 s jump."""
    times = list(range(0, 601, 5))
    distances = [t * 5.0 for t in times]
    times.append(620)
    distances.append(distances[-1] + 500.0)
    return times, distances


def _effort(times, distances, meters):
    return analytics.best_effort(times, distances, meters, max_sample_gap=GAP, max_gap_speed_ratio=RATIO)


def test_thresholds_are_configured():
    assert training_rules.EFFORT_MAX_SAMPLE_GAP_SECONDS == GAP
    assert training_rules.EFFORT_GAP_SPEED_RATIO == RATIO


def test_a_teleport_cannot_form_part_of_an_effort():
    times, distances = _dense_with_a_jump()

    assert _effort(times, distances, 400.0) == pytest.approx(80.0)


def test_without_the_check_the_teleport_wins():
    times, distances = _dense_with_a_jump()

    assert analytics.best_effort(times, distances, 400.0) < 80.0


def test_a_pause_inside_an_effort_is_fine():
    # 5 km at 5 m/s, a 21 s pause with no distance, then 5 km more.
    first = list(range(0, 1001, 5))
    times = first + [t + 1021 for t in first]
    distances = [t * 5.0 for t in first] + [5000.0 + t * 5.0 for t in first]

    assert _effort(times, distances, 10000.0) == pytest.approx(2021.0)


def test_sparse_samples_at_a_normal_pace_still_count():
    times = [0, 300, 600]
    distances = [0.0, 1000.0, 2000.0]

    assert _effort(times, distances, 400.0) == pytest.approx(120.0)


def test_dense_streams_are_unaffected():
    times = list(range(0, 601, 5))
    distances = [t * 5.0 for t in times]

    assert _effort(times, distances, 1000.0) == analytics.best_effort(times, distances, 1000.0)


def test_the_pr_table_ignores_glitched_stretches(db_session, make_activity):
    activity = make_activity(start_time=datetime(2021, 1, 6, 7), dedup_key="glitch")
    times, distances = _dense_with_a_jump()
    stream = {"time": times, "distance": distances, "hr": [None] * len(times), "elevation": [], "pace": []}

    parser.update_best_efforts(db_session, activity, stream)

    four_hundred = db_session.query(BestEffort).filter_by(distance_label="400m").one()
    assert four_hundred.duration_seconds == pytest.approx(80.0)
