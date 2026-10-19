import pytest

from app.coach.volume import form_values, item_shape, parse_volume


@pytest.mark.parametrize(
    "item, shape",
    [
        ({"sets": 4, "reps": 6}, "sets_reps"),
        ({"sets": 3, "duration_seconds": 45}, "sets_seconds"),
        ({"distance_meters": 8000.0}, "distance"),
        ({"duration_seconds": 600}, "duration"),
        ({}, "none"),
    ],
)
def test_item_shape(item, shape):
    assert item_shape(item) == shape


def test_sets_and_reps():
    assert parse_volume("sets_reps", {"sets": "5", "reps": "5"}, "metric") == {"sets": 5, "reps": 5}


def test_sets_and_seconds():
    assert parse_volume("sets_seconds", {"sets": "3", "seconds": "60"}, "metric") == {"sets": 3, "duration_seconds": 60}


def test_distance_in_kilometres():
    assert parse_volume("distance", {"distance": "5"}, "metric") == {"distance_meters": 5000.0}


def test_distance_in_miles_is_stored_in_metres():
    assert parse_volume("distance", {"distance": "3.1"}, "imperial") == {"distance_meters": 4988.97}


def test_distance_accepts_a_decimal_comma():
    assert parse_volume("distance", {"distance": "5,5"}, "metric") == {"distance_meters": 5500.0}


@pytest.mark.parametrize("minutes, seconds", [("45", 2700), ("7.5", 450), ("90", 5400)])
def test_duration_in_minutes(minutes, seconds):
    assert parse_volume("duration", {"minutes": minutes}, "metric") == {"duration_seconds": seconds}


@pytest.mark.parametrize(
    "shape, form",
    [
        ("sets_reps", {"sets": "0", "reps": "8"}),
        ("sets_reps", {"sets": "4", "reps": "-1"}),
        ("sets_reps", {"sets": "21", "reps": "8"}),
        ("sets_reps", {"sets": "4", "reps": "101"}),
        ("sets_reps", {"sets": "4.5", "reps": "8"}),
        ("sets_reps", {"sets": "four", "reps": "8"}),
        ("sets_reps", {"sets": "4"}),
        ("sets_seconds", {"sets": "3", "seconds": "3601"}),
        ("distance", {"distance": "0"}),
        ("distance", {"distance": "101"}),
        ("distance", {"distance": "far"}),
        ("distance", {"distance": "nan"}),
        ("duration", {"minutes": "0"}),
        ("duration", {"minutes": "601"}),
        ("duration", {"minutes": ""}),
        ("none", {"sets": "3"}),
    ],
)
def test_rejects_impossible_volumes(shape, form):
    with pytest.raises(ValueError):
        parse_volume(shape, form, "metric")


def test_fields_for_another_shape_are_ignored():
    updates = parse_volume("sets_reps", {"sets": "4", "reps": "8", "distance": "10"}, "metric")

    assert updates == {"sets": 4, "reps": 8}


@pytest.mark.parametrize(
    "item, units, expected",
    [
        ({"sets": 4, "reps": 6}, "metric", {"sets": "4", "reps": "6"}),
        ({"sets": 3, "duration_seconds": 45}, "metric", {"sets": "3", "seconds": "45"}),
        ({"distance_meters": 8000.0}, "metric", {"distance": "8.0"}),
        ({"distance_meters": 8046.72}, "imperial", {"distance": "5.0"}),
        ({"duration_seconds": 2700}, "metric", {"minutes": "45"}),
        ({"duration_seconds": 450}, "metric", {"minutes": "7.5"}),
    ],
)
def test_form_values_prefill_in_the_users_units(item, units, expected):
    assert form_values(item, units) == expected
