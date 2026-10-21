from datetime import date

import pytest

from app.coach.progression import break_days, distance_change, return_options, run_balance, scale_item
from app.training_rules import (
    DISTANCE_INCREASE_BIG_PCT,
    DISTANCE_INCREASE_NOTE_PCT,
    RETURN_BREAK_MIN_DAYS,
    RETURN_WEEK_FACTORS,
)

# --- RULE-PROG-02: weekly distance against the recent baseline ------------------


def test_ac_rule_prog_02_baseline_is_the_mean_of_the_previous_weeks():
    change = distance_change(24000.0, [20000.0, 20000.0])

    assert change["baseline_meters"] == 20000.0
    assert change["pct"] == 20.0
    assert change["level"] is None


def test_ac_rule_prog_02_over_the_first_line_is_noted():
    assert distance_change(20000.0 * (1 + (DISTANCE_INCREASE_NOTE_PCT + 1) / 100), [20000.0, 20000.0])["level"] == "jump"


def test_ac_rule_prog_02_over_the_second_line_is_a_big_jump():
    assert distance_change(20000.0 * (1 + (DISTANCE_INCREASE_BIG_PCT + 1) / 100), [20000.0, 20000.0])["level"] == "big"


def test_less_running_than_usual_is_never_flagged():
    assert distance_change(5000.0, [20000.0, 20000.0])["level"] is None


def test_no_baseline_means_no_comparison():
    assert distance_change(10000.0, [0.0, 0.0]) is None
    assert distance_change(10000.0, []) is None


def test_percent_has_at_most_two_decimals():
    assert distance_change(10001.0, [3000.0, 3000.0])["pct"] == 233.37


# --- RULE-PROG-04 + D7: a break, and the options offered ------------------------


def test_break_days_counts_whole_days_since_the_last_workout():
    assert break_days(date(2026, 10, 1), date(2026, 10, 21)) == 20
    assert break_days(None, date(2026, 10, 21)) is None


def test_d7_options_are_offered_only_after_a_long_enough_break():
    assert return_options(RETURN_BREAK_MIN_DAYS - 1) == []
    assert return_options(None) == []
    options = return_options(RETURN_BREAK_MIN_DAYS)
    assert [o["factor"] for o in options] == list(RETURN_WEEK_FACTORS)
    assert [o["percent"] for o in options] == [round(f * 100) for f in RETURN_WEEK_FACTORS]


def test_d7_every_offered_factor_is_inside_the_research_range():
    assert all(0.6 <= f <= 0.9 for f in RETURN_WEEK_FACTORS)


@pytest.mark.parametrize(
    "item, factor, expected",
    [
        ({"sets": 4, "reps": 6, "duration_seconds": None, "distance_meters": None}, 0.8, {"sets": 3}),
        ({"sets": 1, "reps": 10, "duration_seconds": None, "distance_meters": None}, 0.6, {"sets": 1}),
        ({"sets": 3, "reps": None, "duration_seconds": 45, "distance_meters": None}, 0.7, {"sets": 2}),
        ({"sets": None, "reps": None, "duration_seconds": None, "distance_meters": 8000.0}, 0.8, {"distance_meters": 6400.0}),
        ({"sets": None, "reps": None, "duration_seconds": 2700, "distance_meters": None}, 0.9, {"duration_seconds": 2430}),
        ({"sets": None, "reps": None, "duration_seconds": None, "distance_meters": None}, 0.8, {}),
    ],
)
def test_d7_scaling_cuts_volume_never_reps_or_below_one_set(item, factor, expected):
    assert scale_item(item, factor) == expected


# --- RULE-WEEK-01: easy/hard balance of the week's runs, by count ---------------


def test_ac_rule_week_01_mostly_easy_runs_need_no_note():
    assert run_balance([True, False, False, False, False]) == {"runs": 5, "hard": 1, "suggested_hard": 1, "note": False}


def test_ac_rule_week_01_one_hard_run_in_three_is_what_the_rule_suggests():
    # 80/20 can't be expressed by count at 3 runs; the rule says 1 hard run.
    assert run_balance([True, False, False])["note"] is False


def test_ac_rule_week_01_more_hard_runs_than_suggested_get_a_note():
    assert run_balance([True, True, False, False])["note"] is True


def test_ac_rule_week_01_ten_runs_allow_two_hard():
    assert run_balance([True, True] + [False] * 8)["suggested_hard"] == 2


def test_unknown_runs_are_left_out():
    assert run_balance([True, None, None, False]) == {"runs": 2, "hard": 1, "suggested_hard": 1, "note": False}


def test_no_known_runs_means_no_balance():
    assert run_balance([None, None]) is None
    assert run_balance([]) is None
