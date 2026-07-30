import pytest

from app import analytics


def _constant_pace_stream(total_km, seconds_per_km=300):
    times = [i * seconds_per_km for i in range(total_km + 1)]
    distances = [i * 1000.0 for i in range(total_km + 1)]
    return times, distances


# --- best_effort ---------------------------------------------------------

def test_best_effort_correct_5k_from_known_stream():
    times, distances = _constant_pace_stream(total_km=10, seconds_per_km=300)

    duration = analytics.best_effort(times, distances, target_distance_meters=5000)

    assert duration == pytest.approx(1500.0, abs=0.01)


def test_best_effort_activity_shorter_than_target_returns_none():
    times, distances = _constant_pace_stream(total_km=3, seconds_per_km=300)

    duration = analytics.best_effort(times, distances, target_distance_meters=5000)

    assert duration is None


def test_new_best_effort_replaces_old():
    assert analytics.is_new_best_effort(existing_seconds=1600, candidate_seconds=1500) is True


def test_non_pr_does_not_overwrite():
    assert analytics.is_new_best_effort(existing_seconds=1500, candidate_seconds=1600) is False
    assert analytics.is_new_best_effort(existing_seconds=None, candidate_seconds=1600) is True


# --- HR zones --------------------------------------------------------------

ZONES = [
    {"zone_number": 1, "min_bpm": 100, "max_bpm": 129},
    {"zone_number": 2, "min_bpm": 130, "max_bpm": 159},
    {"zone_number": 3, "min_bpm": 160, "max_bpm": 200},
]


def test_hr_zones_time_in_zone_sums_to_total_duration():
    times = [0, 60, 120, 180]
    hr_values = [110, 145, 170, 110]

    zone_seconds = analytics.time_in_zone(times, hr_values, ZONES)

    assert sum(zone_seconds.values()) == pytest.approx(180.0)


def test_hr_zones_sample_on_boundary_correct_zone():
    times = [0, 60, 120, 180]
    hr_values = [110, 130, 170, 110]

    zone_seconds = analytics.time_in_zone(times, hr_values, ZONES)

    assert zone_seconds[1] == pytest.approx(60.0)
    assert zone_seconds[2] == pytest.approx(60.0)
    assert zone_seconds[3] == pytest.approx(60.0)


# --- splits ------------------------------------------------------------

def test_splits_1km_correct_from_known_distance_stream():
    times, distances = _constant_pace_stream(total_km=10, seconds_per_km=300)

    splits = analytics.km_splits(times, distances, split_meters=1000)

    assert len(splits) == 10
    for split in splits:
        assert split["distance_meters"] == pytest.approx(1000.0)
        assert split["duration_seconds"] == pytest.approx(300.0)
        assert split["pace_per_km_seconds"] == pytest.approx(300.0)


def test_splits_partial_final_split_included():
    times = [0, 300, 600, 900, 1200, 1500, 1650]
    distances = [0, 1000, 2000, 3000, 4000, 5000, 5500]

    splits = analytics.km_splits(times, distances, split_meters=1000)

    assert len(splits) == 6
    for split in splits[:5]:
        assert split["distance_meters"] == pytest.approx(1000.0)
        assert split["duration_seconds"] == pytest.approx(300.0)
    last = splits[-1]
    assert last["distance_meters"] == pytest.approx(500.0)
    assert last["duration_seconds"] == pytest.approx(150.0)


def test_km_splits_pace_normalized_to_split_unit_not_hardcoded_km():
    times, distances = _constant_pace_stream(total_km=2, seconds_per_km=300)

    splits = analytics.km_splits(times, distances, split_meters=1609.344)

    assert splits[0]["duration_seconds"] == pytest.approx(482.8032, abs=0.01)
    assert splits[0]["pace_per_km_seconds"] == pytest.approx(splits[0]["duration_seconds"], abs=0.001)


# --- grade-adjusted pace -------------------------------------------------

def test_grade_adjusted_pace_flat_same_as_raw():
    adjusted = analytics.grade_adjusted_pace(raw_pace_sec_per_km=300, grade_percent=0)

    assert adjusted == pytest.approx(300.0)


def test_grade_adjusted_pace_uphill_slower():
    adjusted = analytics.grade_adjusted_pace(raw_pace_sec_per_km=300, grade_percent=5)

    assert adjusted > 300.0
    assert adjusted == pytest.approx(349.5, abs=0.01)


# --- TRIMP -----------------------------------------------------------------

def test_trimp_known_hr_and_duration_expected_value():
    trimp = analytics.trimp(duration_minutes=30, avg_hr=150, hr_rest=60, hr_max=190)

    assert trimp == pytest.approx(50.22, abs=0.01)


# --- CTL / ATL ---------------------------------------------------------

def test_ctl_atl_day1_value_equals_that_days_load():
    result = analytics.ctl_atl([100])

    assert result[0]["ctl"] == pytest.approx(100.0)
    assert result[0]["atl"] == pytest.approx(100.0)
    assert result[0]["form"] == pytest.approx(0.0)


def test_ctl_atl_decays_correctly_with_zero_activity_days():
    result = analytics.ctl_atl([100, 0, 50])

    assert result[1]["ctl"] == pytest.approx(97.647, abs=0.01)
    assert result[1]["atl"] == pytest.approx(86.688, abs=0.01)
    assert result[2]["ctl"] == pytest.approx(96.526, abs=0.01)
    assert result[2]["atl"] == pytest.approx(81.804, abs=0.01)
    assert result[2]["form"] == pytest.approx(result[2]["ctl"] - result[2]["atl"], abs=0.001)


# --- Riegel predictions ------------------------------------------------

def test_riegel_known_5k_time_predicts_10k_within_tolerance():
    predicted = analytics.riegel_predict(
        known_time_seconds=1500, known_distance_meters=5000, target_distance_meters=10000
    )

    assert predicted == pytest.approx(3127.4, abs=0.5)


# --- VO2max ------------------------------------------------------------

def test_vo2max_known_pace_and_hr_expected_value_within_tolerance():
    vdot = analytics.estimate_vo2max(
        distance_meters=5000, duration_seconds=1500, avg_hr=170, max_hr=190
    )

    assert vdot == pytest.approx(42.82, abs=0.01)


def test_vo2max_without_hr_returns_unadjusted_vdot():
    vdot = analytics.estimate_vo2max(distance_meters=5000, duration_seconds=1500)

    assert vdot == pytest.approx(38.31, abs=0.01)


# --- stream coalescing ---------------------------------------------------

def test_coalesce_stream_metric_drops_none_values():
    times = [0, 100, 200, 300]
    values = [None, 5.0, None, 15.0]

    ts, vs = analytics.coalesce_stream_metric(times, values)

    assert ts == [100, 300]
    assert vs == [5.0, 15.0]


# --- daily TRIMP loads / default max HR -----------------------------------

def test_build_daily_trimp_loads_fills_gaps_with_zero():
    from datetime import date

    daily_totals = {date(2026, 1, 1): 50.0, date(2026, 1, 3): 30.0}

    loads = analytics.build_daily_trimp_loads(daily_totals, date(2026, 1, 1), date(2026, 1, 3))

    assert loads == [50.0, 0.0, 30.0]


def test_default_max_hr_uses_220_minus_age_formula():
    assert analytics.default_max_hr(birth_year=1990, reference_year=2026) == 184


def test_value_at_time_returns_nearest_sample():
    times = [0, 100, 200]
    values = [10.0, 20.0, 30.0]

    assert analytics.value_at_time(times, values, 90) == 20.0
    assert analytics.value_at_time(times, values, 40) == 10.0


# --- activity type categorization ------------------------------------------

def test_categorize_activity_type_run():
    result = analytics.categorize_activity_type("Run")
    assert result == {"category": "Run", "label": "Run", "dot": "#7FB2E8"}


def test_categorize_activity_type_cycle_maps_to_ride():
    result = analytics.categorize_activity_type("Cycle")
    assert result == {"category": "Ride", "label": "Ride", "dot": "#8FD1B0"}


def test_categorize_activity_type_strength_cluster_maps_to_gym():
    for raw in ["TraditionalStrengthTraining", "FunctionalStrengthTraining", "CoreTraining",
                "HighIntensityIntervalTraining", "JumpRope"]:
        result = analytics.categorize_activity_type(raw)
        assert result["category"] == "Gym"
        assert result["dot"] == "#C9A46B"


def test_categorize_activity_type_unmapped_falls_back_to_neutral_dot():
    result = analytics.categorize_activity_type("Volleyball")
    assert result == {"category": "Other", "label": "Volleyball", "dot": "#9C9CA6"}


# --- formatting --------------------------------------------------------

def test_format_duration_under_an_hour_is_minutes_seconds():
    assert analytics.format_duration(341) == "5:41"


def test_format_duration_over_an_hour_is_hours_minutes_seconds():
    assert analytics.format_duration(3661) == "1:01:01"


def test_format_pace_formats_minutes_seconds():
    assert analytics.format_pace(274) == "4:34"


def test_format_pace_none_input_returns_none():
    assert analytics.format_pace(None) is None


# --- HR zone bands -------------------------------------------------------

def test_hr_zone_bands_computes_five_zones_from_heart_rate_reserve():
    zones = analytics.hr_zone_bands(200, 60)

    assert len(zones) == 5
    assert zones[0]["name"] == "Zone 1 — Recovery"
    assert zones[0]["pct_range"] == "50–60%"
    assert zones[0]["bpm_range"] == "< 144 bpm"
    assert zones[0]["color"] == "#38BDF8"
    assert zones[1]["bpm_range"] == "144–158 bpm"
    assert zones[4]["name"] == "Zone 5 — VO2 max"
    assert zones[4]["bpm_range"] == "186–200 bpm"
    assert zones[4]["color"] == "#E11D48"


def test_hr_zone_colors_are_five_distinct_hues():
    zones = analytics.hr_zone_bands(200, 60)

    assert len({z["color"] for z in zones}) == 5


def test_hr_zone_bands_feed_time_in_zone_directly():
    zones = analytics.hr_zone_bands(200, 60)

    seconds = analytics.time_in_zone([0, 60, 120], [150.0, 190.0, 190.0], zones)

    assert seconds[2] == pytest.approx(60.0)
    assert seconds[5] == pytest.approx(60.0)


def test_hr_zone_bands_zone_one_is_open_ended_below():
    zones = analytics.hr_zone_bands(200, 60)

    seconds = analytics.time_in_zone([0, 60, 120], [80.0, 100.0, 100.0], zones)

    assert seconds[1] == pytest.approx(120.0)
    assert sum(seconds.values()) == pytest.approx(120.0)


# --- training calendar ---------------------------------------------------

def test_calendar_levels_buckets_loads_into_terciles():
    from datetime import date

    daily_loads = {
        date(2026, 1, 1): 0.0,
        date(2026, 1, 2): 10.0,
        date(2026, 1, 3): 20.0,
        date(2026, 1, 4): 30.0,
    }

    levels = analytics.calendar_levels(daily_loads, date(2026, 1, 1), date(2026, 1, 4))

    assert [d["level"] for d in levels] == [0, 1, 2, 3]


def test_calendar_levels_fills_missing_days_as_rest():
    from datetime import date

    levels = analytics.calendar_levels({date(2026, 1, 2): 10.0}, date(2026, 1, 1), date(2026, 1, 3))

    assert [d["level"] for d in levels] == [0, 3, 0]


def test_current_streak_counts_trailing_trained_days():
    levels = [{"level": lvl} for lvl in [3, 0, 2, 1]]
    assert analytics.current_streak(levels) == 2


def test_current_streak_zero_when_most_recent_day_is_rest():
    levels = [{"level": lvl} for lvl in [3, 2, 0]]
    assert analytics.current_streak(levels) == 0


# --- split display annotation --------------------------------------------

def test_annotate_splits_marks_fastest_and_scales_bar():
    splits = [
        {"pace_per_km_seconds": 300},
        {"pace_per_km_seconds": 250},
        {"pace_per_km_seconds": 350},
    ]

    annotated = analytics.annotate_splits_for_display(splits)

    assert annotated[1]["is_fastest"] is True
    assert annotated[0]["is_fastest"] is False
    assert annotated[1]["bar_pct"] == pytest.approx(100.0)
    assert annotated[2]["bar_pct"] == pytest.approx(30.0)
    assert annotated[0]["bar_pct"] == pytest.approx(65.0)


def test_annotate_splits_handles_empty_list():
    assert analytics.annotate_splits_for_display([]) == []


def test_annotate_splits_handles_uniform_pace_without_division_by_zero():
    splits = [{"pace_per_km_seconds": 300}, {"pace_per_km_seconds": 300}]

    annotated = analytics.annotate_splits_for_display(splits)

    assert all(s["bar_pct"] == pytest.approx(100.0) for s in annotated)
    assert all(s["is_fastest"] for s in annotated)


# --- elevation gain from stream -------------------------------------------

def test_elevation_gain_from_stream_sums_positive_deltas_only():
    times = [0, 10, 20, 30]
    elevations = [100.0, 105.0, 102.0, 108.0]

    gain = analytics.elevation_gain_from_stream(times, elevations)

    assert gain == pytest.approx(11.0)


def test_elevation_gain_from_stream_ignores_none_values():
    times = [0, 10, 20, 30]
    elevations = [100.0, None, 90.0, 95.0]

    gain = analytics.elevation_gain_from_stream(times, elevations)

    assert gain == pytest.approx(5.0)


def test_elevation_gain_from_stream_empty_returns_zero():
    assert analytics.elevation_gain_from_stream([], []) == 0.0


# --- unit conversion -------------------------------------------------------

def test_convert_distance_metric_is_kilometers():
    value, label = analytics.convert_distance(5000.0, "metric")
    assert value == pytest.approx(5.0)
    assert label == "km"


def test_convert_distance_imperial_is_miles():
    value, label = analytics.convert_distance(1609.344, "imperial")
    assert value == pytest.approx(1.0)
    assert label == "mi"


def test_convert_pace_metric_passes_through():
    value, label = analytics.convert_pace(300.0, "metric")
    assert value == pytest.approx(300.0)
    assert label == "km"


def test_convert_pace_imperial_scales_to_per_mile():
    value, label = analytics.convert_pace(300.0, "imperial")
    assert value == pytest.approx(482.803, abs=0.01)
    assert label == "mi"


def test_convert_elevation_metric_is_meters():
    value, label = analytics.convert_elevation(100.0, "metric")
    assert value == pytest.approx(100.0)
    assert label == "m"


def test_convert_elevation_imperial_is_feet():
    value, label = analytics.convert_elevation(100.0, "imperial")
    assert value == pytest.approx(328.084, abs=0.01)
    assert label == "ft"


def test_convert_weight_metric_is_kilograms():
    value, label = analytics.convert_weight(72.0, "metric")
    assert value == pytest.approx(72.0)
    assert label == "kg"


def test_convert_weight_imperial_is_pounds():
    value, label = analytics.convert_weight(72.0, "imperial")
    assert value == pytest.approx(158.73, abs=0.01)
    assert label == "lb"


def test_split_distance_meters_metric_is_one_kilometer():
    assert analytics.split_distance_meters("metric") == pytest.approx(1000.0)


def test_split_distance_meters_imperial_is_one_mile():
    assert analytics.split_distance_meters("imperial") == pytest.approx(1609.344)


def test_weight_to_kg_metric_passes_through():
    assert analytics.weight_to_kg(72.0, "metric") == pytest.approx(72.0)


def test_weight_to_kg_imperial_converts_pounds_back():
    assert analytics.weight_to_kg(158.73, "imperial") == pytest.approx(72.0, abs=0.01)
