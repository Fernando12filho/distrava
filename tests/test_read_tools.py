"""Step 8a: read tools answer from what the app knows and never write (AC-15).
search_exercises: catalog entries that fit the equipment on hand, a muscle group
or category, or stand in for another exercise ("legs, dumbbells only").
get_history: what was actually done in a range, week by week, from existing code.
"""

import copy
import json
import re
from datetime import date, datetime

import pytest

from app.coach import agent, history, read_tools
from app.coach.catalog import CATALOG
from app.coach.providers import FakeProvider
from app.coach.tools import ToolError
from app.models import CoachExercise, CoachSession, CoachSessionItem, CoachSetLog, CoachWeek

from tests.test_agent_loop import CAT, _run, _tool_results
from tests.test_preview_undo import WEEK, client, fake, frozen_today, keystore  # noqa: F401


def _call(muscle_groups=(), equipment=(), category=None, like=None):
    return {
        "name": "search_exercises",
        "input": {"muscle_groups": list(muscle_groups), "equipment": list(equipment), "category": category, "like": like},
    }


def _search(**arguments):
    return json.loads(read_tools.run(_call(**arguments), {"catalog": CAT}))


def _slugs(result):
    return [e["slug"] for e in result["exercises"]]


def test_legs_with_dumbbells_only_includes_bodyweight_but_no_barbell():
    found = _search(muscle_groups=["legs"], equipment=["dumbbell"], category="strength")

    assert set(_slugs(found)) == {"walking_lunge", "calf_raise"}


def test_bodyweight_always_fits_even_with_no_equipment_named():
    found = _search(muscle_groups=["chest"], equipment=["none"])

    assert _slugs(found) == ["push_up"]


def test_no_equipment_filter_means_any_equipment():
    found = _search(muscle_groups=["back"])

    assert set(_slugs(found)) == {"pull_up", "barbell_row", "dumbbell_row"}


def test_like_finds_stand_ins_for_the_same_muscle_group():
    found = _search(equipment=["dumbbell"], like="bench_press")

    assert set(_slugs(found)) == {"dumbbell_bench_press", "incline_dumbbell_press", "push_up"}


def test_an_entry_carries_what_the_coach_needs_to_use_it():
    entry = _search(muscle_groups=["back"], equipment=["pullup_bar"])["exercises"][0]

    assert entry == {"slug": "pull_up", "name": "Pull-up", "category": "strength", "muscle_group": "back", "equipment": "pullup_bar"}


def test_nothing_fitting_says_so():
    found = _search(muscle_groups=["biceps"], equipment=["band"])

    assert found["exercises"] == []
    assert "No catalog exercise fits" in found["note"]


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"like": "moon_jump"}, "moon_jump"),
        ({"equipment": ["rowing_machine"]}, "rowing_machine"),
        ({"muscle_groups": ["calves"]}, "calves"),
        ({"category": "yoga"}, "yoga"),
    ],
)
def test_unknown_values_are_refused_by_name(arguments, message):
    with pytest.raises(ToolError, match=message):
        _search(**arguments)


def test_ac_15_searching_leaves_the_catalog_as_it_was():
    before = copy.deepcopy(CAT)

    _search(muscle_groups=["legs"], equipment=["dumbbell"])

    assert CAT == before


def test_the_tool_is_strict_and_lists_the_catalogs_values():
    tool = next(t for t in read_tools.READ_TOOLS if t["name"] == "search_exercises")

    assert tool["strict"] is True
    assert set(tool["input_schema"]["required"]) == {"muscle_groups", "equipment", "category", "like"}
    equipment = tool["input_schema"]["properties"]["equipment"]["items"]["enum"]
    assert set(equipment) == {e["equipment"] for e in CATALOG}


# --- In the agent loop ---


def test_ac_15_the_coach_searches_without_writing():
    fake = FakeProvider([{"tool_calls": [_call(muscle_groups=["legs"], equipment=["dumbbell"], category="strength")]}, {"text": "Lunges work."}])

    result, _ = _run(fake, request="Legs with dumbbells only?")

    found = json.loads(_tool_results(fake.calls[1])[0]["content"])
    assert "walking_lunge" in _slugs(found)
    assert result["status"] == "answer" and result["calls"] == []


def test_the_step_names_what_was_found():
    found = {"exercises": [{"name": "Walking lunge"}, {"name": "Calf raise"}]}

    assert agent.step_label(_call(), [], found) == "Looked up exercises: Walking lunge, Calf raise"
    assert agent.step_label(_call(), [], {"exercises": [], "note": "…"}) == "Looked up exercises: none fit"


# --- get_history ---

OCT_05 = date(2026, 10, 5)
ACTIVITIES = [
    {"date": date(2026, 10, 6), "type": "Run", "distance_meters": 6123.456, "duration_seconds": 2100, "session_rpe": 3},
    {"date": date(2026, 10, 8), "type": "Run", "distance_meters": 8000.0, "duration_seconds": 2950, "session_rpe": None},
    {"date": date(2026, 10, 9), "type": "Traditional Strength Training", "distance_meters": 0.0, "duration_seconds": 3600, "session_rpe": 6},
]
SESSIONS = [
    {"date": date(2026, 10, 7), "kind": "gym", "focus": "Legs & Glutes", "status": "done"},
    {"date": date(2026, 10, 9), "kind": "gym", "focus": "Chest & Triceps", "status": "skipped"},
]
SETS = [
    {"date": date(2026, 10, 7), "muscle_group": "legs", "rir": 2, "session_id": 1},
    {"date": date(2026, 10, 7), "muscle_group": "legs", "rir": 2, "session_id": 1},
    {"date": date(2026, 10, 7), "muscle_group": "glutes", "rir": None, "session_id": 1},
]


def _summary(start=OCT_05, end=date(2026, 10, 18), units="metric"):
    return history.summary(ACTIVITIES, SESSIONS, SETS, start, end, units)


def test_every_week_in_the_range_is_listed_even_an_empty_one():
    weeks = _summary()["weeks"]

    assert [w["week_start"] for w in weeks] == ["2026-10-05", "2026-10-12"]
    assert weeks[1]["runs"] == 0 and weeks[1]["run_distance_meters"] == 0


def test_a_week_sums_runs_distance_and_time():
    week = _summary()["weeks"][0]

    assert week["runs"] == 2
    assert week["run_distance_meters"] == 14123.46
    assert week["run_distance"] == "14.12 km"
    assert week["run_minutes"] == 84.17


def test_load_counts_only_rated_workouts_and_says_how_many_are_unrated():
    week = _summary()["weeks"][0]

    # RULE-LOAD-01: 3 × 35 min + 6 × 60 min; the unrated run adds nothing.
    assert week["load"] == 465
    assert week["unrated_workouts"] == 1
    assert week["other_workouts"] == 1


def test_hard_sets_per_muscle_come_from_the_logged_sets():
    groups = _summary()["weeks"][0]["hard_sets"]

    assert groups == [{"muscle_group": "legs", "hard_sets": 2, "unrated": 0}, {"muscle_group": "glutes", "hard_sets": 0, "unrated": 1}]


def test_coach_sessions_are_counted_by_status():
    assert _summary()["weeks"][0]["coach_sessions"] == {"done": 1, "skipped": 1}


def test_each_workout_is_listed_with_its_effort():
    workouts = _summary()["workouts"]

    assert workouts[0] == {
        "date": "2026-10-06", "type": "Run", "distance": "6.12 km", "distance_meters": 6123.46,
        "minutes": 35, "effort": 3, "load": 105,
    }
    assert workouts[2]["distance"] is None and workouts[2]["type"] == "Traditional Strength Training"


def test_distances_follow_the_users_units():
    assert _summary(units="imperial")["weeks"][0]["run_distance"] == "8.78 mi"


def test_only_the_range_is_counted():
    week = _summary(start=date(2026, 10, 7), end=date(2026, 10, 7))["weeks"][0]

    assert week["runs"] == 0 and week["coach_sessions"] == {"done": 1}


def test_history_numbers_have_at_most_2_decimals():
    text = json.dumps(_summary())

    assert re.findall(r"\d+\.\d{3,}", text) == []


def _history_call(start, end):
    return {"name": "get_history", "input": {"from_date": start, "to_date": end}}


def _sources(asked):
    def load_history(start, end):
        asked.append((start, end))
        return {"activities": ACTIVITIES, "sessions": SESSIONS, "logged_sets": SETS}

    return {"history": load_history, "today": date(2026, 10, 20), "units": "metric"}


def test_get_history_reads_the_asked_range():
    asked = []

    found = json.loads(read_tools.run(_history_call("2026-10-05", "2026-10-18"), _sources(asked)))

    assert asked == [(OCT_05, date(2026, 10, 18))]
    assert found["weeks"][0]["runs"] == 2


@pytest.mark.parametrize(
    "start, end, message",
    [
        ("2026-10-18", "2026-10-05", "before"),
        ("2026-10-05", "2026-10-21", "today"),
        ("2026-06-01", "2026-10-18", "12 weeks"),
        ("last week", "2026-10-18", "YYYY-MM-DD"),
    ],
)
def test_get_history_refuses_a_bad_range(start, end, message):
    with pytest.raises(ToolError, match=message):
        read_tools.run(_history_call(start, end), _sources([]))


def test_ac_15_the_coach_reads_history_without_writing():
    fake = FakeProvider([{"tool_calls": [_history_call("2026-10-05", "2026-10-11")]}, {"text": "You ran 2 times."}])

    def load_week(_week_start):
        raise AssertionError("not read here")

    result, _ = _run(fake, request="How did that week go?", readers={"load_week": load_week, "history": _sources([])["history"]})

    found = json.loads(_tool_results(fake.calls[1])[0]["content"])
    assert found["weeks"][0]["run_distance"] == "14.12 km"
    assert result["status"] == "answer" and result["calls"] == []


def test_the_coach_page_reads_history_from_the_database(client, db_session, fake, frozen_today, make_activity):
    make_activity(
        start_time=datetime(2026, 10, 13, 7), end_time=datetime(2026, 10, 13, 7, 40), duration_seconds=2400,
        distance_meters=6000.0, session_rpe=4, dedup_key="Run|2026-10-13",
    )
    last_week = CoachWeek(week_start=date(2026, 10, 12))
    session = CoachSession(week=last_week, day_index=2, kind="gym", focus="Legs & Glutes", status="done")
    squat = db_session.query(CoachExercise).filter_by(slug="back_squat").one()
    item = CoachSessionItem(session=session, exercise=squat, sets=3, reps=8)
    item.logged_sets = [CoachSetLog(set_number=n, reps=8, rir=2) for n in (1, 2)]
    db_session.add(last_week)
    db_session.commit()
    fake.replies.extend([{"tool_calls": [_history_call("2026-10-12", "2026-10-18")]}, {"text": "One run."}])

    client.post(f"/coach/weeks/{WEEK}/ask", data={"message": "How did last week go?"})

    week = json.loads(_tool_results(fake.calls[1])[0]["content"])["weeks"][0]
    assert week["runs"] == 1 and week["run_distance"] == "6 km" and week["load"] == 160
    assert week["hard_sets"] == [{"muscle_group": "legs", "hard_sets": 2, "unrated": 0}]
    assert week["coach_sessions"] == {"done": 1}


def test_the_history_step_names_the_range():
    assert agent.step_label(_history_call("2026-10-05", "2026-10-18"), []) == "Read your history, Oct 05 – Oct 18"
