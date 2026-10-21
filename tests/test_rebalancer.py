from app.coach.rebalancer import check_week, effort, move_options

_ids = iter(range(1, 10_000))


def _session(day, kind="run", status="planned", planned=None, **actual):
    session = {
        "id": next(_ids),
        "day_index": day,
        "position": actual.pop("position", 0),
        "kind": kind,
        "status": status,
        "focus": kind,
        "planned_effort": planned,
        "srpe": None,
        "z3_minutes": None,
        "muscle_groups": set(),
        "hard_set_groups": set(),
        "rated_set_groups": set(),
    }
    session.update(actual)
    return session


def _gym(day, groups, **kw):
    return _session(day, "gym", muscle_groups=set(groups), **kw)


def _rules(conflicts):
    return sorted(c["rule"] for c in conflicts)


# --- effort: what makes a session hard ---------------------------------------


def test_ac_rule_load_02_d1_a_run_is_hard_on_either_signal():
    assert effort(_session(0, status="done", srpe=5))["hard"] is True
    assert effort(_session(0, status="done", srpe=3, z3_minutes=12))["hard"] is True
    assert effort(_session(0, status="done", srpe=3, z3_minutes=4))["hard"] is False


def test_ac_rule_load_04_what_was_done_beats_the_plan():
    done = effort(_session(0, status="done", planned="hard", srpe=2))

    assert done == {"hard": False, "groups": set(), "source": "done"}


def test_ac_rule_load_04_the_plan_counts_only_without_actual_data():
    assert effort(_session(0, status="done", planned="hard"))["source"] == "plan"
    assert effort(_session(0, planned="hard"))["hard"] is True
    assert effort(_session(0, planned="easy"))["hard"] is False


def test_an_untagged_unrated_session_is_unknown():
    assert effort(_session(0)) == {"hard": None, "groups": set(), "source": None}


def test_ac_rule_load_03_a_gym_session_is_hard_for_the_groups_with_hard_sets():
    session = _gym(0, ["chest", "triceps"], status="done", hard_set_groups={"chest"}, rated_set_groups={"chest", "triceps"})

    assert effort(session) == {"hard": True, "groups": {"chest"}, "source": "done"}


def test_a_gym_session_rated_hard_without_set_detail_is_hard_for_all_its_groups():
    session = _gym(0, ["legs", "glutes"], status="done", srpe=7)

    assert effort(session)["groups"] == {"legs", "glutes"}


def test_a_planned_hard_gym_session_is_hard_for_all_its_groups():
    assert effort(_gym(0, ["back"], planned="hard"))["groups"] == {"back"}


def test_skipped_rest_and_mobility_sessions_are_never_hard():
    for session in (_session(0, status="skipped", planned="hard"), _session(0, "rest"), _session(0, "mobility", srpe=8)):
        assert effort(session)["hard"] is not True


# --- check_week: spacing rules -------------------------------------------------


def test_ac_05_rule_rec_02_two_hard_runs_on_consecutive_days_clash():
    week = [_session(1, planned="hard"), _session(2, planned="hard")]

    assert _rules(check_week(week)) == ["RULE-REC-02"]


def test_ac_05_rule_rec_02_hard_runs_two_days_apart_are_fine():
    assert check_week([_session(1, planned="hard"), _session(3, planned="hard")]) == []


def test_ac_05_rule_rec_02_a_third_hard_run_goes_over_the_weekly_cap():
    week = [_session(0, planned="hard"), _session(2, planned="hard"), _session(4, planned="hard")]

    conflicts = check_week(week)

    assert _rules(conflicts) == ["RULE-REC-02"]
    assert len(conflicts[0]["session_ids"]) == 3


def test_ac_05_rule_rec_01_same_muscle_hard_two_days_running_clashes():
    week = [_gym(1, ["chest"], planned="hard"), _gym(2, ["chest", "triceps"], planned="hard")]

    assert _rules(check_week(week)) == ["RULE-REC-01"]


def test_ac_05_rule_rec_01_different_muscles_on_consecutive_days_are_fine():
    assert check_week([_gym(1, ["chest"], planned="hard"), _gym(2, ["back"], planned="hard")]) == []


def test_ac_05_rule_rec_04_d4_hard_legs_the_day_before_a_hard_run_clashes():
    week = [_gym(1, ["legs"], planned="hard"), _session(2, planned="hard")]

    assert _rules(check_week(week)) == ["RULE-REC-04"]


def test_ac_05_rule_rec_04_a_hard_run_before_leg_day_is_fine():
    assert check_week([_session(1, planned="hard"), _gym(2, ["legs"], planned="hard")]) == []


def test_ac_05_rule_rec_04_same_day_legs_first_clashes_run_first_does_not():
    legs_first = [_gym(2, ["legs"], planned="hard", position=0), _session(2, planned="hard", position=1)]
    run_first = [_session(2, planned="hard", position=0), _gym(2, ["legs"], planned="hard", position=1)]

    assert _rules(check_week(legs_first)) == ["RULE-REC-04"]
    assert check_week(run_first) == []


def test_easy_runs_after_leg_day_are_fine():
    assert check_week([_gym(1, ["legs"], planned="hard"), _session(2, planned="easy")]) == []


def test_unknown_sessions_never_clash():
    assert check_week([_session(1), _session(2), _gym(1, ["legs"]), _gym(2, ["legs"])]) == []


def test_skipped_sessions_never_clash():
    assert check_week([_session(1, planned="hard", status="skipped"), _session(2, planned="hard")]) == []


def test_the_end_of_last_week_counts_for_spacing():
    # Day -1 is last Sunday; it spaces against Monday but not the weekly cap.
    week = [_session(-1, planned="hard"), _session(0, planned="hard")]

    assert _rules(check_week(week)) == ["RULE-REC-02"]
    assert check_week([_session(-1, planned="hard"), _session(1, planned="hard"), _session(3, planned="hard")]) == []


# --- move_options: a skipped session is dropped, or moved only where it fits ---


def test_ac_05_rule_prog_01_a_skipped_session_can_move_only_to_a_free_later_day_that_fits():
    skipped = _session(1, planned="hard", status="skipped")
    week = [skipped, _session(3, planned="hard"), _gym(5, ["chest"], planned="hard")]

    # Today is Tuesday (1): Thu and Sat are taken; Wed and Fri sit next to
    # Thu's hard run. Only Sunday fits.
    assert move_options(week, skipped["id"], today_index=1) == [6]


def test_ac_05_rule_prog_01_never_stacks_onto_a_day_with_a_session():
    skipped = _session(0, status="skipped")
    week = [skipped] + [_session(day, planned="easy") for day in range(1, 7)]

    assert move_options(week, skipped["id"], today_index=0) == []


def test_ac_05_rule_prog_01_a_rest_day_does_not_block_a_move():
    skipped = _session(0, planned="easy", status="skipped")
    week = [skipped, _session(6, "rest")]

    assert move_options(week, skipped["id"], today_index=5) == [6]


def test_ac_05_no_move_options_on_the_last_day():
    skipped = _session(5, status="skipped")

    assert move_options([skipped], skipped["id"], today_index=6) == []


def test_ac_05_all_days_skipped_has_no_clashes_and_nowhere_to_go():
    week = [_session(day, planned="hard", status="skipped") for day in range(7)]

    assert check_week(week) == []
    assert move_options(week, week[0]["id"], today_index=6) == []


def test_full_body_overlaps_whatever_the_other_session_trained():
    week = [_gym(1, ["full_body"], planned="hard"), _gym(2, ["chest"], planned="hard")]

    assert check_week(week)[0]["groups"] == ["chest"]


def test_full_body_counts_as_legs_before_a_hard_run():
    assert _rules(check_week([_gym(1, ["full_body"], planned="hard"), _session(2, planned="hard")])) == ["RULE-REC-04"]


def test_full_body_overlap_names_only_the_groups_both_sessions_trained():
    week = [_gym(1, ["full_body", "legs"], planned="hard"), _gym(2, ["chest"], planned="hard")]

    assert check_week(week)[0]["groups"] == ["chest"]


def test_ac_05_rule_prog_01_a_move_never_offers_the_sessions_own_day():
    skipped = _session(3, planned="easy", status="skipped")

    assert move_options([skipped], skipped["id"], today_index=2) == [4, 5, 6]
