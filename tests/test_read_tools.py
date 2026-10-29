"""Step 8a: read tools answer from what the app knows and never write (AC-15).
search_exercises: catalog entries that fit the equipment on hand, a muscle group
or category, or stand in for another exercise ("legs, dumbbells only").
"""

import copy
import json

import pytest

from app.coach import agent, read_tools
from app.coach.catalog import CATALOG
from app.coach.providers import FakeProvider
from app.coach.tools import ToolError

from tests.test_agent_loop import CAT, _run, _tool_results


def _call(muscle_groups=(), equipment=(), category=None, like=None):
    return {
        "name": "search_exercises",
        "input": {"muscle_groups": list(muscle_groups), "equipment": list(equipment), "category": category, "like": like},
    }


def _search(**arguments):
    return json.loads(read_tools.run(_call(**arguments), None, None, catalog=CAT))


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
