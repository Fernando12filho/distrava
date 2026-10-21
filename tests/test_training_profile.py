import pytest

from app.coach.profile import FIELDS, parse_profile

FULL = {
    "runs_per_week": "4",
    "gym_days_per_week": "3",
    "split": "  Upper / lower  ",
    "goal": "Run a marathon, no hurry, and gain a little weight",
    "years_running": "6",
    "years_lifting": "0",
}


def test_parses_every_field():
    assert parse_profile(FULL) == {
        "runs_per_week": 4,
        "gym_days_per_week": 3,
        "split": "Upper / lower",
        "goal": "Run a marathon, no hurry, and gain a little weight",
        "years_running": 6,
        "years_lifting": 0,
    }


def test_empty_or_missing_fields_are_not_set():
    assert parse_profile({"split": "   ", "runs_per_week": ""}) == {name: None for name in FIELDS}


@pytest.mark.parametrize(
    "field, raw",
    [
        ("runs_per_week", "15"),
        ("runs_per_week", "-1"),
        ("gym_days_per_week", "8"),
        ("years_running", "81"),
        ("years_lifting", "2.5"),
        ("runs_per_week", "four"),
    ],
)
def test_out_of_range_or_non_whole_numbers_are_rejected(field, raw):
    with pytest.raises(ValueError, match=field.replace("_", " ")):
        parse_profile({field: raw})


def test_text_has_a_length_limit():
    with pytest.raises(ValueError, match="goal"):
        parse_profile({"goal": "x" * 301})


def test_there_is_no_default_split():
    # D3: the split is whatever you (or the coach, with your OK) say it is.
    assert parse_profile({})["split"] is None
