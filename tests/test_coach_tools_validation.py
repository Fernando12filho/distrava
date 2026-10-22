"""Coach tools in pure code: every call is checked before it can become a preview.

The model only names a tool and its arguments; these functions decide whether
the change is allowed and what the week looks like after it.
"""

import pytest

from app.coach import tools
from app.coach.catalog import CATALOG

CAT = {e["slug"]: e for e in CATALOG}


def _item(item_id, slug, position=0, **volume):
    return {
        "id": item_id,
        "position": position,
        "exercise": slug,
        "sets": volume.get("sets"),
        "reps": volume.get("reps"),
        "duration_seconds": volume.get("duration_seconds"),
        "distance_meters": volume.get("distance_meters"),
    }


def _session(session_id, day, kind, focus, items, status="planned", position=0, effort=None, locked=False):
    return {
        "id": session_id,
        "day_index": day,
        "position": position,
        "kind": kind,
        "focus": focus,
        "status": status,
        "planned_effort": effort,
        "locked": locked,
        "items": items,
    }


def _week(today_index=2):
    return {
        "today_index": today_index,
        "sessions": [
            _session(1, 0, "run", "Running day", [_item(10, "easy_run", distance_meters=8000.0)], status="done"),
            _session(2, 3, "run", "Running day", [_item(20, "easy_run", distance_meters=8000.0)]),
            _session(
                3,
                4,
                "gym",
                "Chest & Triceps",
                [_item(30, "bench_press", sets=4, reps=6), _item(31, "dips", 1, sets=3, reps=8), _item(32, "plank", 2, sets=3, duration_seconds=45)],
            ),
            _session(4, 1, "gym", "Legs & Glutes", [_item(40, "back_squat", sets=4, reps=6)]),
            _session(5, 5, "gym", "Back & Biceps", [_item(50, "pull_up", sets=4, reps=5)], locked=True),
            _session(6, 6, "ride", "Easy ride", [_item(60, "easy_ride", duration_seconds=2700)]),
        ],
    }


def _call(name, **arguments):
    return {"name": name, "input": arguments}


def _by_id(week, session_id):
    return next(s for s in week["sessions"] if s["id"] == session_id)


# --- tool definitions -----------------------------------------------------------


def test_every_tool_is_strict_with_closed_required_arguments():
    names = {t["name"] for t in tools.TOOLS}
    assert names == {"move_session", "remove_session", "swap_exercise", "adjust_item", "set_planned_effort"}
    for tool in tools.TOOLS:
        schema = tool["input_schema"]
        assert tool["strict"] is True
        assert schema["additionalProperties"] is False
        assert sorted(schema["required"]) == sorted(schema["properties"])
        assert tool["description"]


# --- move_session ---------------------------------------------------------------


def test_move_puts_the_session_last_on_its_new_day():
    after = tools.apply(_week(), _call("move_session", session_id=2, day=4), CAT)

    moved = _by_id(after, 2)
    assert moved["day_index"] == 4
    assert moved["position"] == 1  # after Chest & Triceps


def test_apply_never_changes_the_week_it_was_given():
    week = _week()
    tools.apply(week, _call("move_session", session_id=2, day=4), CAT)
    assert week == _week()


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"session_id": 99, "day": 4}, "No session 99"),
        ({"session_id": 2, "day": 7}, "day must be 0–6"),
        ({"session_id": 2, "day": 1}, "already past"),
        ({"session_id": 2, "day": 3}, "already on"),
        ({"session_id": 1, "day": 4}, "only planned sessions"),
        ({"session_id": 4, "day": 5}, "already past"),
        ({"session_id": 5, "day": 6}, "logged work"),
    ],
)
def test_move_rejects_bad_ids_days_and_sessions_that_are_history(arguments, message):
    with pytest.raises(tools.ToolError, match=message):
        tools.apply(_week(), _call("move_session", **arguments), CAT)


def test_moving_to_today_is_allowed():
    after = tools.apply(_week(today_index=2), _call("move_session", session_id=2, day=2), CAT)
    assert _by_id(after, 2)["day_index"] == 2


def test_a_past_week_has_nothing_to_change():
    with pytest.raises(tools.ToolError, match="already past"):
        tools.apply(_week(today_index=7), _call("move_session", session_id=6, day=6), CAT)


# --- remove_session -------------------------------------------------------------


def test_remove_drops_a_planned_future_session():
    after = tools.apply(_week(), _call("remove_session", session_id=6), CAT)
    assert 6 not in {s["id"] for s in after["sessions"]}


def test_remove_rejects_done_sessions():
    with pytest.raises(tools.ToolError, match="only planned sessions"):
        tools.apply(_week(), _call("remove_session", session_id=1), CAT)


# --- swap_exercise --------------------------------------------------------------


def test_swap_keeps_the_volume_and_changes_the_exercise():
    after = tools.apply(_week(), _call("swap_exercise", item_id=30, exercise="dumbbell_bench_press"), CAT)
    item = _by_id(after, 3)["items"][0]
    assert item["exercise"] == "dumbbell_bench_press"
    assert (item["sets"], item["reps"]) == (4, 6)


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"item_id": 999, "exercise": "push_up"}, "No exercise 999"),
        ({"item_id": 30, "exercise": "made_up_press"}, "not in the catalog"),
        ({"item_id": 30, "exercise": "easy_run"}, "strength exercise"),
        ({"item_id": 20, "exercise": "easy_ride"}, "Run"),
        ({"item_id": 30, "exercise": "bench_press"}, "already"),
        ({"item_id": 10, "exercise": "tempo_run"}, "only planned sessions"),
    ],
)
def test_swap_rejects_unknown_or_mismatched_exercises(arguments, message):
    with pytest.raises(tools.ToolError, match=message):
        tools.apply(_week(), _call("swap_exercise", **arguments), CAT)


def test_a_run_can_swap_to_another_kind_of_run():
    after = tools.apply(_week(), _call("swap_exercise", item_id=20, exercise="tempo_run"), CAT)
    assert _by_id(after, 2)["items"][0]["exercise"] == "tempo_run"


# --- adjust_item ----------------------------------------------------------------

_NO_VOLUME = {"sets": None, "reps": None, "duration_seconds": None, "distance_meters": None}


def test_adjust_changes_volume_within_the_items_shape():
    after = tools.apply(_week(), _call("adjust_item", item_id=30, **{**_NO_VOLUME, "sets": 3, "reps": 8}), CAT)
    item = _by_id(after, 3)["items"][0]
    assert (item["sets"], item["reps"]) == (3, 8)

    after = tools.apply(_week(), _call("adjust_item", item_id=20, **{**_NO_VOLUME, "distance_meters": 6000.0}), CAT)
    assert _by_id(after, 2)["items"][0]["distance_meters"] == 6000.0


@pytest.mark.parametrize(
    "item_id, volume, message",
    [
        (30, {"sets": 0, "reps": 8}, "sets must be 1–20"),
        (30, {"sets": 3, "reps": 101}, "reps must be 1–100"),
        (30, {"sets": 3, "reps": None}, "needs sets and reps"),
        (30, {"sets": 3, "reps": 8, "distance_meters": 5000.0}, "only takes sets and reps"),
        (32, {"sets": 3, "duration_seconds": 4000}, "seconds must be 1–3600"),
        (20, {"distance_meters": 0.0}, "distance must be"),
        (20, {"distance_meters": 250000.0}, "distance must be"),
        (60, {"duration_seconds": 36001}, "duration must be"),
        (20, {"distance_meters": 8000.0}, "already"),
    ],
)
def test_adjust_rejects_impossible_volumes(item_id, volume, message):
    with pytest.raises(tools.ToolError, match=message):
        tools.apply(_week(), _call("adjust_item", item_id=item_id, **{**_NO_VOLUME, **volume}), CAT)


# --- set_planned_effort ---------------------------------------------------------


def test_planned_effort_can_be_set_and_cleared():
    after = tools.apply(_week(), _call("set_planned_effort", session_id=2, effort="hard"), CAT)
    assert _by_id(after, 2)["planned_effort"] == "hard"
    after = tools.apply(after, _call("set_planned_effort", session_id=2, effort=None), CAT)
    assert _by_id(after, 2)["planned_effort"] is None


def test_planned_effort_rejects_unknown_values():
    with pytest.raises(tools.ToolError, match="easy, hard or null"):
        tools.apply(_week(), _call("set_planned_effort", session_id=2, effort="brutal"), CAT)


def test_unknown_tool_is_rejected():
    with pytest.raises(tools.ToolError, match="Unknown tool"):
        tools.apply(_week(), _call("rewrite_week"), CAT)


# --- several calls --------------------------------------------------------------


def test_apply_all_keeps_valid_calls_and_reports_each_bad_one():
    calls = [
        _call("move_session", session_id=2, day=5),
        _call("remove_session", session_id=1),
        _call("set_planned_effort", session_id=2, effort="easy"),
    ]
    after, errors = tools.apply_all(_week(), calls, CAT)

    assert errors[0] is None and errors[2] is None
    assert "only planned sessions" in errors[1]
    assert _by_id(after, 2)["day_index"] == 5
    assert _by_id(after, 2)["planned_effort"] == "easy"


# --- what changed ---------------------------------------------------------------


def test_touched_lists_only_sessions_that_differ():
    after = tools.apply(_week(), _call("move_session", session_id=2, day=5), CAT)
    after = tools.apply(after, _call("remove_session", session_id=6), CAT)

    before, changed = tools.touched(_week(), after)

    assert set(before) == {2, 6}
    assert changed[2]["day_index"] == 5
    assert changed[6] is None


def test_change_lines_are_written_by_code_in_plain_words():
    week = _week()
    after, _ = tools.apply_all(
        week,
        [
            _call("move_session", session_id=2, day=5),
            _call("adjust_item", item_id=20, **{**_NO_VOLUME, "distance_meters": 6000.0}),
            _call("swap_exercise", item_id=30, exercise="dumbbell_bench_press"),
            _call("remove_session", session_id=6),
            _call("set_planned_effort", session_id=3, effort="hard"),
        ],
        CAT,
    )

    lines = tools.change_lines(week, after, CAT, "metric")

    assert lines == [
        "Running day: Thu → Sat",
        "Running day · Easy run: 8.0 km → 6.0 km",
        "Chest & Triceps · Bench press → Dumbbell bench press",
        "Chest & Triceps: planned hard",
        "Easy ride on Sun: removed",
    ]


# --- spacing rules after the change (AC-05) -------------------------------------


def _rb(session_id, day, kind, groups=(), effort=None, status="planned", position=0):
    return {
        "id": session_id,
        "day_index": day,
        "position": position,
        "kind": kind,
        "status": status,
        "focus": "",
        "planned_effort": effort,
        "srpe": None,
        "z3_minutes": None,
        "muscle_groups": set(groups),
        "hard_set_groups": set(),
        "rated_set_groups": set(),
    }


def test_a_change_that_adds_a_spacing_clash_is_reported():
    week = _week(today_index=0)
    week["sessions"][1]["planned_effort"] = "hard"  # Thu run
    week["sessions"][3]["planned_effort"] = "hard"  # Tue legs
    rb = [_rb(2, 3, "run", effort="hard"), _rb(4, 1, "gym", {"legs"}, effort="hard"), _rb(3, 4, "gym", {"chest", "triceps"})]
    # Legs moved onto Wednesday, the day before the hard run: RULE-REC-04.
    after = tools.apply(week, _call("move_session", session_id=4, day=2), CAT)

    clashes = tools.new_conflicts(rb, after, CAT)

    assert [c["rule"] for c in clashes] == ["RULE-REC-04"]


def test_clashes_that_were_already_there_are_not_blamed_on_the_change():
    rb = [_rb(2, 3, "run", effort="hard"), _rb(4, 2, "gym", {"legs"}, effort="hard")]
    week = _week(today_index=0)
    week["sessions"][1]["planned_effort"] = "hard"
    week["sessions"][3].update(day_index=2, planned_effort="hard")
    assert tools.new_conflicts(rb, week, CAT) == []  # the clash exists either way
    after = tools.apply(week, _call("set_planned_effort", session_id=3, effort="easy"), CAT)

    assert tools.new_conflicts(rb, after, CAT) == []


def test_a_swap_changes_the_muscle_groups_the_rules_see():
    # Back on Sat after legs on Fri is fine; swapping the row for a deadlift
    # makes it a second hard legs day in a row.
    rb = [_rb(3, 4, "gym", {"legs"}, effort="hard"), _rb(7, 5, "gym", {"back"}, effort="hard")]
    week = {
        "today_index": 0,
        "sessions": [
            _session(3, 4, "gym", "Legs", [_item(30, "back_squat", sets=4, reps=6)], effort="hard"),
            _session(7, 5, "gym", "Back", [_item(70, "barbell_row", sets=4, reps=8)], effort="hard"),
        ],
    }
    after = tools.apply(week, _call("swap_exercise", item_id=70, exercise="deadlift"), CAT)

    assert [c["rule"] for c in tools.new_conflicts(rb, after, CAT)] == ["RULE-REC-01"]


def test_a_removed_session_leaves_the_rules():
    rb = [_rb(2, 3, "run", effort="hard"), _rb(6, 4, "run", effort="hard")]
    week = _week()
    after = tools.apply(week, _call("remove_session", session_id=6), CAT)
    assert tools.new_conflicts(rb, after, CAT) == []


# --- the model's words never carry a number it wasn't given ---------------------


def test_stray_numbers_finds_numbers_not_in_what_the_model_was_given():
    allowed = '{"distance_meters": 8000.0, "date": "2026-10-23"} Running day · Easy run: 8.0 km → 6.0 km'

    assert tools.stray_numbers("Cut Thursday from 8 km to 6 km on the 23rd.", allowed) == []
    assert tools.stray_numbers("That's 25% less, about 3.7 miles.", allowed) == ["25", "3.7"]
    assert tools.stray_numbers("6.00 km is fine", allowed) == []


def test_planned_efforts_match_the_model():
    from app.models import PLANNED_EFFORTS

    assert tools.PLANNED_EFFORTS == PLANNED_EFFORTS
