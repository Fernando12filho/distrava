from datetime import date, datetime

import pytest

from app.coach.matcher import TOLERANCE, match_sessions

SAT = date(2026, 10, 24)
SUN = date(2026, 10, 25)


def _session(id=1, day=SAT, kind="run", status="planned", distance=8000.0, duration=None, matched=None):
    return {
        "id": id,
        "date": day,
        "kind": kind,
        "status": status,
        "distance_meters": distance,
        "duration_seconds": duration,
        "matched_activity_id": matched,
    }


def _activity(id=10, day=SAT, hour=7, activity_type="Run", distance=8000.0, duration=2700):
    return {
        "id": id,
        "activity_type": activity_type,
        "start_time": datetime(day.year, day.month, day.day, hour, 0),
        "distance_meters": distance,
        "duration_seconds": duration,
    }


def test_ac06_same_day_same_type_within_tolerance_is_a_match():
    result = match_sessions([_session()], [_activity(distance=8300.0)])

    assert result == {1: {"kind": "match", "activity_ids": [10]}}


def test_tolerance_is_twenty_five_percent():
    assert TOLERANCE == 0.25


@pytest.mark.parametrize("distance", [6000.0, 10000.0])
def test_exactly_at_the_tolerance_edge_still_matches(distance):
    assert match_sessions([_session()], [_activity(distance=distance)])[1]["kind"] == "match"


@pytest.mark.parametrize("distance", [5900.0, 10100.0])
def test_outside_the_tolerance_is_no_suggestion(distance):
    assert match_sessions([_session()], [_activity(distance=distance)]) == {}


def test_wrong_activity_type_is_no_suggestion():
    assert match_sessions([_session()], [_activity(activity_type="Cycle")]) == {}


def test_ride_session_matches_a_cycle_by_duration():
    session = _session(kind="ride", distance=None, duration=2700)

    result = match_sessions([session], [_activity(activity_type="Cycle", distance=21000.0, duration=3000)])

    assert result == {1: {"kind": "match", "activity_ids": [10]}}


def test_session_without_a_planned_volume_matches_on_type_and_date():
    result = match_sessions([_session(distance=None)], [_activity(distance=3000.0)])

    assert result[1]["kind"] == "match"


def test_ac06_a_run_one_day_late_asks_instead_of_matching():
    result = match_sessions([_session(day=SAT)], [_activity(day=SUN)])

    assert result == {1: {"kind": "ask", "activity_ids": [10]}}


def test_two_days_late_is_no_suggestion():
    assert match_sessions([_session(day=SAT)], [_activity(day=date(2026, 10, 26))]) == {}


def test_ac06_two_fitting_activities_on_the_day_ask_in_start_order():
    activities = [_activity(id=11, hour=18), _activity(id=10, hour=7)]

    result = match_sessions([_session()], activities)

    assert result == {1: {"kind": "ask", "activity_ids": [10, 11]}}


def test_ac06_one_activity_fitting_two_sessions_asks_on_both():
    sessions = [_session(id=1), _session(id=2, distance=7000.0)]

    result = match_sessions(sessions, [_activity(distance=7500.0)])

    assert result == {
        1: {"kind": "ask", "activity_ids": [10]},
        2: {"kind": "ask", "activity_ids": [10]},
    }


def test_an_activity_that_matches_its_own_day_is_not_offered_to_a_neighbour():
    sessions = [_session(id=1, day=SAT), _session(id=2, day=SUN)]

    result = match_sessions(sessions, [_activity(day=SAT)])

    assert result == {1: {"kind": "match", "activity_ids": [10]}}


@pytest.mark.parametrize("status", ["done", "partial", "skipped", "moved"])
def test_only_planned_sessions_get_suggestions(status):
    assert match_sessions([_session(status=status)], [_activity()]) == {}


@pytest.mark.parametrize("kind", ["gym", "mobility", "rest"])
def test_non_cardio_sessions_are_never_matched(kind):
    assert match_sessions([_session(kind=kind, distance=None)], [_activity()]) == {}


def test_an_activity_already_confirmed_elsewhere_is_not_offered_again():
    sessions = [_session(id=1, status="done", matched=10), _session(id=2)]

    assert match_sessions(sessions, [_activity()]) == {}


def test_no_activities_means_no_suggestions():
    assert match_sessions([_session()], []) == {}
