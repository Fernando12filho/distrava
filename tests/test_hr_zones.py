from datetime import date

import pytest

from app import analytics
from app.models import UserSettings
from app.routes import _resolve_hr_profile, _time_in_zones_display
from regression_fixtures import HR_MAX, HR_REST, synthetic_run_stream

# zone -> (min_bpm, bpm_range, pct_range) for resting 55 / max 188
EXPECTED_BANDS = {
    1: (0, "< 135 bpm", "50–60%"),
    2: (135, "135–148 bpm", "60–70%"),
    3: (148, "148–161 bpm", "70–80%"),
    4: (161, "161–175 bpm", "80–90%"),
    5: (175, "175–188 bpm", "90–100%"),
}

EXPECTED_ZONE_COLORS = ["#38BDF8", "#4ADE80", "#FDE047", "#F97316", "#E11D48"]


def test_zone_boundaries_match_snapshot():
    bands = analytics.hr_zone_bands(HR_MAX, HR_REST)

    actual = {b["zone_number"]: (b["min_bpm"], b["bpm_range"], b["pct_range"]) for b in bands}
    assert actual == EXPECTED_BANDS


def test_zone_colors_are_five_distinct_hues():
    bands = analytics.hr_zone_bands(HR_MAX, HR_REST)

    assert [b["color"] for b in bands] == EXPECTED_ZONE_COLORS


def test_time_in_zone_matches_snapshot():
    stream = synthetic_run_stream(10600.0, 300.0)
    times, hr = analytics.coalesce_stream_metric(stream["time"], stream["hr"])

    seconds = analytics.time_in_zone(times, hr, analytics.hr_zone_bands(HR_MAX, HR_REST))

    assert seconds == pytest.approx({1: 10.0, 2: 1100.0, 3: 1110.0, 4: 860.0, 5: 130.0})


def test_time_in_zones_display_matches_snapshot():
    stream = synthetic_run_stream(10600.0, 300.0)

    rows = _time_in_zones_display(stream, HR_MAX, HR_REST)

    assert [(r["zone_number"], r["time"], r["pct"]) for r in rows] == [
        (1, "0:10", 0.31),
        (2, "18:20", 34.27),
        (3, "18:30", 34.58),
        (4, "14:20", 26.79),
        (5, "2:10", 4.05),
    ]


@pytest.mark.parametrize(
    "settings, expected",
    [
        (None, (60, 190)),
        (UserSettings(resting_hr=52), (52, 190)),
        # Was 184 (220 - age); changed on purpose to Tanaka per RULE-METRIC-02.
        (UserSettings(birth_year=1990), (60, 183)),
        (UserSettings(resting_hr=50, max_hr=181, birth_year=1990), (50, 181)),
    ],
)
def test_hr_profile_resolution_matches_snapshot(settings, expected):
    assert _resolve_hr_profile(settings, date(2026, 7, 28)) == expected
