import pytest

from app.coach import set_log
from app.training_rules import HARD_SET_MAX_RIR


def _item(sets=None, reps=None, duration=None, distance=None):
    return {"sets": sets, "reps": reps, "duration_seconds": duration, "distance_meters": distance}


def test_planned_sets_give_one_row_per_set_with_the_planned_reps():
    assert set_log.planned_sets(_item(sets=3, reps=10)) == [
        {"set_number": 1, "reps": 10, "duration_seconds": None},
        {"set_number": 2, "reps": 10, "duration_seconds": None},
        {"set_number": 3, "reps": 10, "duration_seconds": None},
    ]


def test_timed_sets_carry_their_planned_seconds():
    assert set_log.planned_sets(_item(sets=2, duration=45)) == [
        {"set_number": 1, "reps": None, "duration_seconds": 45},
        {"set_number": 2, "reps": None, "duration_seconds": 45},
    ]


@pytest.mark.parametrize("item", [_item(distance=8000.0), _item(duration=600), _item()])
def test_exercises_without_sets_get_no_rows(item):
    assert set_log.planned_sets(item) == []


def test_blank_fields_parse_to_none():
    assert set_log.parse_set("reps", {"reps": "", "weight": " ", "rir": ""}, "metric") == {
        "reps": None,
        "weight_kg": None,
        "rir": None,
    }


def test_a_full_set_parses_reps_weight_and_rir():
    assert set_log.parse_set("reps", {"reps": "8", "weight": "62,5", "rir": "2"}, "metric") == {
        "reps": 8,
        "weight_kg": 62.5,
        "rir": 2,
    }


def test_imperial_weight_is_stored_in_kg_rounded_to_two_decimals():
    assert set_log.parse_set("reps", {"weight": "135"}, "imperial")["weight_kg"] == 61.23


def test_timed_sets_parse_seconds_instead_of_reps():
    assert set_log.parse_set("seconds", {"seconds": "50", "rir": ""}, "metric") == {
        "duration_seconds": 50,
        "weight_kg": None,
        "rir": None,
    }


@pytest.mark.parametrize(
    "form",
    [
        {"reps": "-1"},
        {"reps": "101"},
        {"reps": "eight"},
        {"weight": "0"},
        {"weight": "-5"},
        {"weight": "1001"},
        {"weight": "nan"},
        {"rir": "11"},
        {"rir": "-1"},
        {"rir": "1.5"},
    ],
)
def test_out_of_range_values_are_rejected(form):
    with pytest.raises(ValueError):
        set_log.parse_set("reps", form, "metric")


def test_zero_reps_is_allowed_for_a_set_that_did_not_go():
    assert set_log.parse_set("reps", {"reps": "0"}, "metric")["reps"] == 0


def test_rule_load_03_hard_set_threshold_is_three_reps_in_reserve():
    assert HARD_SET_MAX_RIR == 3


@pytest.mark.parametrize("rir, hard", [(0, True), (3, True), (4, False), (10, False)])
def test_rule_load_03_a_set_is_hard_only_at_or_below_the_threshold(rir, hard):
    assert set_log.is_hard(rir) is hard


def test_rule_load_04_without_reps_in_reserve_hardness_is_unknown_not_guessed():
    assert set_log.is_hard(None) is None


def test_weight_shows_at_most_two_decimals_in_the_users_units():
    assert set_log.weight_value(61.23, "metric") == "61.23"
    assert set_log.weight_value(60.0, "metric") == "60"
    assert set_log.weight_value(61.23, "imperial") == "134.99"
    assert set_log.weight_value(None, "metric") == ""
