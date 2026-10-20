"""Records page: for each distance, the current best and every time it was beaten."""

import re
from datetime import date, datetime

import pytest

from app import analytics
from app.models import BestEffort
from regression_fixtures import seed_best_effort_runs, synthetic_run_stream

D1, D2, D3, D4 = date(2024, 3, 2), date(2025, 1, 5), date(2026, 6, 10), date(2026, 10, 17)


# ---------------------------------------------------------------- pure helper


def test_progression_lists_each_improvement_newest_first():
    efforts = [(D1, 1600.0, 1), (D2, 1650.0, 2), (D3, 1550.0, 3), (D4, 1500.0, 4)]

    assert analytics.pr_progression(efforts) == [
        {"date": D4, "seconds": 1500.0, "activity_id": 4, "improvement": 50.0},
        {"date": D3, "seconds": 1550.0, "activity_id": 3, "improvement": 50.0},
        {"date": D1, "seconds": 1600.0, "activity_id": 1, "improvement": None},
    ]


def test_a_tie_is_not_a_new_record():
    efforts = [(D1, 1600.0, 1), (D2, 1600.0, 2)]

    assert [p["activity_id"] for p in analytics.pr_progression(efforts)] == [1]


def test_order_of_input_does_not_matter():
    efforts = [(D4, 1500.0, 4), (D1, 1600.0, 1)]

    assert [p["activity_id"] for p in analytics.pr_progression(efforts)] == [4, 1]


def test_no_efforts_no_progression():
    assert analytics.pr_progression([]) == []


def test_fast_best_effort_matches_a_brute_force_search():
    stream = synthetic_run_stream(10600.0, 300.0, phase=0.7)
    times, distances = stream["time"], stream["distance"]

    for target in (400.0, 1000.0, 5000.0, 10000.0):
        brute = min(
            analytics._interpolate(times[i:], distances[i:], distances[i] + target) - times[i]
            for i in range(len(distances))
            if analytics._interpolate(times[i:], distances[i:], distances[i] + target) is not None
        )
        assert analytics.best_effort(times, distances, target) == pytest.approx(brute)


# ---------------------------------------------------------------- page


def _seed_with_an_improvement(db_session):
    """The shared fixture's faster run comes first; add a later, faster one."""
    from datetime import timedelta

    from app import parser

    seed_best_effort_runs(db_session)
    stream = synthetic_run_stream(10600.0, 285.0, phase=0.2)
    start = datetime(2026, 7, 20, 7, 0)
    parser._persist_activity(
        db_session,
        activity_type="Run",
        start_time=start,
        end_time=start + timedelta(seconds=stream["time"][-1]),
        duration_seconds=stream["time"][-1],
        distance_meters=stream["distance"][-1],
        avg_hr=None,
        max_hr=None,
        elevation_gain_meters=None,
        source="gpx",
        source_id=None,
        stream_data=stream,
    )


def test_records_page_shows_current_bests_matching_the_pr_table(client, db_session):
    _seed_with_an_improvement(db_session)

    html = client.get("/records").get_data(as_text=True)

    for be in db_session.query(BestEffort).all():
        assert be.distance_label in html
        assert analytics.format_duration(be.duration_seconds) in html


def test_records_page_shows_progression_with_improvements(client, db_session):
    _seed_with_an_improvement(db_session)

    html = client.get("/records").get_data(as_text=True)

    assert "first" in html
    assert re.search(r"−\d+:\d\d", html)


def test_records_page_links_each_record_to_its_run_and_never_to_a_ride(client, db_session):
    seed_best_effort_runs(db_session)

    html = client.get("/records").get_data(as_text=True)

    assert 'href="/activities/1"' in html
    assert 'href="/activities/2"' in html
    assert 'href="/activities/3"' not in html


def test_records_page_with_no_runs_says_so(client):
    html = client.get("/records").get_data(as_text=True)

    assert "No records yet" in html


def test_chart_data_carries_whole_seconds_only(client, db_session):
    _seed_with_an_improvement(db_session)

    html = client.get("/records").get_data(as_text=True)

    assert not re.search(r"\d+\.\d{3,}", html)
    assert "data-chart=" in html


def test_dashboard_links_to_the_records_page(client, make_activity):
    make_activity()

    assert 'href="/records"' in client.get("/dashboard").get_data(as_text=True)
