from datetime import date

import pytest

from app.coach.board import build_week_view, item_volume, parse_week_param, session_summary

MONDAY = date(2026, 10, 19)
WEDNESDAY = date(2026, 10, 21)


@pytest.mark.parametrize(
    "item, units, expected",
    [
        ({"sets": 4, "reps": 6}, "metric", "4 × 6"),
        ({"sets": 3, "duration_seconds": 45}, "metric", "3 × 45 s"),
        ({"duration_seconds": 600}, "metric", "10:00"),
        ({"distance_meters": 8000.0}, "metric", "8.0 km"),
        ({"distance_meters": 8000.0}, "imperial", "5.0 mi"),
        ({}, "metric", "—"),
    ],
)
def test_item_volume(item, units, expected):
    assert item_volume(item, units) == expected


def test_rest_session_has_no_summary():
    assert session_summary("rest", [], "metric") == ""


def test_run_summary_is_total_distance():
    items = [{"distance_meters": 1500.0}, {"distance_meters": 3000.0}, {"distance_meters": 1500.0}]

    assert session_summary("run", items, "metric") == "6.0 km"


def test_ride_summary_falls_back_to_total_time():
    assert session_summary("ride", [{"duration_seconds": 2700}], "metric") == "45:00"


@pytest.mark.parametrize("count, expected", [(1, "1 exercise"), (4, "4 exercises")])
def test_gym_summary_counts_exercises(count, expected):
    assert session_summary("gym", [{"sets": 3, "reps": 10}] * count, "metric") == expected


def test_mobility_summary_is_total_time():
    items = [{"duration_seconds": 600}, {"duration_seconds": 600}]

    assert session_summary("mobility", items, "metric") == "20:00"


def test_summary_never_shows_more_than_two_decimals():
    summary = session_summary("run", [{"distance_meters": 1234.5678}], "imperial")

    assert summary == "0.8 mi"


def test_week_view_has_seven_days_monday_to_sunday():
    days = build_week_view(MONDAY, WEDNESDAY, [])

    assert [d["dow"] for d in days] == ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    assert [d["num"] for d in days] == [19, 20, 21, 22, 23, 24, 25]


def test_week_view_marks_today_and_past_days():
    days = build_week_view(MONDAY, WEDNESDAY, [])

    assert [d["is_today"] for d in days] == [False, False, True, False, False, False, False]
    assert [d["is_past"] for d in days] == [True, True, False, False, False, False, False]


def test_week_view_for_another_week_has_no_today():
    days = build_week_view(date(2026, 10, 26), WEDNESDAY, [])

    assert not any(d["is_today"] for d in days)
    assert not any(d["is_past"] for d in days)


def test_week_view_groups_sessions_by_day_in_position_order():
    sessions = [
        {"id": 1, "day_index": 2, "position": 1},
        {"id": 2, "day_index": 0, "position": 0},
        {"id": 3, "day_index": 2, "position": 0},
    ]

    days = build_week_view(MONDAY, WEDNESDAY, sessions)

    assert [s["id"] for s in days[0]["sessions"]] == [2]
    assert [s["id"] for s in days[2]["sessions"]] == [3, 1]
    assert days[1]["sessions"] == []


def test_parse_week_param_defaults_to_the_current_week():
    assert parse_week_param(None, WEDNESDAY) == MONDAY


def test_parse_week_param_snaps_any_day_to_its_monday():
    assert parse_week_param("2026-10-24", WEDNESDAY) == MONDAY


@pytest.mark.parametrize("raw", ["", "next week", "2026-13-01"])
def test_parse_week_param_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_week_param(raw, WEDNESDAY)
