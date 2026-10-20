"""RULE-METRIC-07 + decision D10: when a workout has no second-by-second heart
rate (Apple's export omits it for some), time-in-zones, the HR chart and
per-split HR are hidden instead of being computed from a few samples."""

import pytest

from app import analytics, training_rules
from app.models import ActivityStream


# ---------------------------------------------------------------- pure helpers


def test_coverage_of_dense_samples_is_complete():
    times = list(range(0, 601, 5))

    assert analytics.hr_coverage(times, [150.0] * len(times), 600, 30) == pytest.approx(1.0)


def test_coverage_of_samples_minutes_apart_is_zero():
    times = list(range(0, 1801, 300))

    assert analytics.hr_coverage(times, [150.0] * len(times), 1800, 30) == 0.0


def test_coverage_counts_a_missing_second_half():
    times = list(range(0, 901, 5))

    assert analytics.hr_coverage(times, [150.0] * len(times), 1800, 30) == pytest.approx(0.5)


def test_coverage_counts_a_late_start_and_early_end():
    times = list(range(300, 1501, 5))

    assert analytics.hr_coverage(times, [150.0] * len(times), 1800, 30) == pytest.approx(1200 / 1800)


def test_coverage_ignores_missing_readings():
    times = list(range(0, 601, 5))
    hr = [150.0 if t < 300 else None for t in times]

    assert analytics.hr_coverage(times, hr, 600, 30) == pytest.approx(295 / 600)


@pytest.mark.parametrize("times, hr", [([], []), ([0], [150.0]), ([0, 5], [None, None])])
def test_coverage_without_two_readings_is_zero(times, hr):
    assert analytics.hr_coverage(times, hr, 600, 30) == 0.0


def test_jump_count_flags_implausible_changes():
    times = [0, 5, 6, 7]
    hr = [130.0, 131.0, 200.0, 135.0]

    assert analytics.hr_jump_count(times, hr, 15) == 2


def test_normal_heart_rate_changes_are_not_jumps():
    times = list(range(0, 61, 5))
    hr = [120.0 + t for t in times]

    assert analytics.hr_jump_count(times, hr, 15) == 0


def test_thresholds_sit_inside_the_researched_ranges():
    assert 15 <= training_rules.HR_GAP_FLAG_SECONDS <= 60
    assert 10 <= training_rules.HR_JUMP_FLAG_BPM_PER_S <= 20


# ---------------------------------------------------------------- activity page


def _activity_with_hr(make_activity, db_session, times, hr, duration=1800):
    activity = make_activity(duration_seconds=duration, distance_meters=5000.0, dedup_key=f"hr-{len(times)}-{duration}")
    distance = [t * 5000.0 / duration for t in times]
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": hr, "distance": distance, "elevation": [], "pace": []},
        )
    )
    db_session.commit()
    return activity


def test_sparse_heart_rate_hides_zones_chart_and_split_hr(client, make_activity, db_session):
    times = list(range(0, 1801, 5))
    hr = [150.0 if t in (5, 600, 1200) else None for t in times]
    activity = _activity_with_hr(make_activity, db_session, times, hr)

    html = client.get(f"/activities/{activity.id}").get_data(as_text=True)

    assert "no second-by-second heart rate" in html
    assert "Heart rate zones" not in html
    assert 'id="hrChart"' not in html
    assert "initActivityCharts(" in html and ", false);" in html
    assert ">150<" not in html


def test_dense_heart_rate_shows_everything_without_a_note(client, make_activity, db_session):
    times = list(range(0, 1801, 5))
    activity = _activity_with_hr(make_activity, db_session, times, [150.0] * len(times))

    html = client.get(f"/activities/{activity.id}").get_data(as_text=True)

    assert "Heart rate zones" in html
    assert 'id="hrChart"' in html
    assert "no second-by-second heart rate" not in html
    assert "Heart rate has gaps" not in html


def test_patchy_heart_rate_shows_everything_with_a_gaps_note(client, make_activity, db_session):
    times = list(range(0, 1801, 5))
    hr = [150.0 if t < 1260 else None for t in times]
    activity = _activity_with_hr(make_activity, db_session, times, hr)

    html = client.get(f"/activities/{activity.id}").get_data(as_text=True)

    assert "Heart rate zones" in html
    assert "Heart rate has gaps" in html
    assert "70% of the workout covered" in html


def test_implausible_jumps_are_mentioned(client, make_activity, db_session):
    times = list(range(0, 1801, 5))
    hr = [150.0] * len(times)
    hr[100] = 230.0
    activity = _activity_with_hr(make_activity, db_session, times, hr)

    html = client.get(f"/activities/{activity.id}").get_data(as_text=True)

    assert "Heart rate has gaps" not in html
    assert "2 implausible jumps" in html


def test_average_and_max_hr_still_show_when_detail_is_hidden(client, make_activity, db_session):
    times = list(range(0, 1801, 5))
    hr = [150.0 if t in (5, 600) else None for t in times]
    activity = _activity_with_hr(make_activity, db_session, times, hr)

    html = client.get(f"/activities/{activity.id}").get_data(as_text=True)

    assert "Avg HR" in html
    assert f">{round(activity.avg_hr)}<" in html
