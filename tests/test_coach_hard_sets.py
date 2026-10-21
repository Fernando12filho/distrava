from app.coach.hard_sets import weekly_hard_sets
from app.training_rules import SETS_PER_MUSCLE_IMPROVE_MIN, SETS_PER_MUSCLE_MAINTAIN_MIN


def _set(muscle_group, rir, session_id=1):
    return {"muscle_group": muscle_group, "rir": rir, "session_id": session_id}


def _group(result, name):
    return next(g for g in result["groups"] if g["muscle_group"] == name)


def test_ac_rule_load_03_only_sets_with_three_or_fewer_reps_in_reserve_count():
    result = weekly_hard_sets([_set("chest", 0), _set("chest", 3), _set("chest", 4), _set("chest", 8)])

    assert _group(result, "chest")["hard_sets"] == 2


def test_ac_rule_load_04_a_set_without_reps_in_reserve_is_unrated_not_hard():
    result = weekly_hard_sets([_set("legs", None), _set("legs", None), _set("legs", 2)])

    assert _group(result, "legs")["hard_sets"] == 1
    assert _group(result, "legs")["unrated"] == 2
    assert result["unrated"] == 2


def test_ac_rule_week_02_counts_are_per_muscle_group_in_catalog_order():
    result = weekly_hard_sets([_set("legs", 1), _set("chest", 1), _set("back", 1), _set("chest", 2)])

    assert [(g["muscle_group"], g["hard_sets"]) for g in result["groups"]] == [("chest", 2), ("back", 1), ("legs", 1)]


def test_a_group_with_only_easy_sets_still_shows_with_zero():
    result = weekly_hard_sets([_set("biceps", 6)])

    assert _group(result, "biceps")["hard_sets"] == 0


def test_sets_without_a_real_muscle_group_are_left_out():
    result = weekly_hard_sets([_set("none", 1), _set(None, 1)])

    assert result == {"groups": [], "unrated": 0}


def test_ac_rule_week_03_sessions_counts_each_session_with_a_hard_set_once():
    result = weekly_hard_sets([_set("legs", 1, 1), _set("legs", 1, 1), _set("legs", 2, 2), _set("legs", 7, 3)])

    assert _group(result, "legs")["sessions"] == 2


def test_ac_rule_week_02_range_names_the_research_bands():
    sets = (
        [_set("chest", 1)] * SETS_PER_MUSCLE_IMPROVE_MIN
        + [_set("back", 1)] * SETS_PER_MUSCLE_MAINTAIN_MIN
        + [_set("abs", 1)] * (SETS_PER_MUSCLE_MAINTAIN_MIN - 1)
    )

    result = weekly_hard_sets(sets)

    assert _group(result, "chest")["range"] == "growth"
    assert _group(result, "back")["range"] == "maintenance"
    assert _group(result, "abs")["range"] is None


def test_an_empty_week_has_no_groups():
    assert weekly_hard_sets([]) == {"groups": [], "unrated": 0}
