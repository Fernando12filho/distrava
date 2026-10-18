import pytest

from app import analytics, routes
from app.models import UserSettings
from regression_fixtures import (
    HR_MAX,
    HR_REST,
    LOAD_START,
    TODAY,
    FrozenDate,
    captured_context,
    load_schedule_rows,
    seed_load_schedule,
)

EXPECTED_DAILY_TRIMP = {
    "2026-07-01": 51.404054,
    "2026-07-02": 28.10464,
    "2026-07-03": 75.736102,
    "2026-07-05": 73.304514,
    "2026-07-06": 95.274874,
    "2026-07-08": 60.324003,
    "2026-07-10": 103.653891,
    "2026-07-12": 125.306252,
    "2026-07-15": 83.364884,
    "2026-07-17": 101.347764,
    "2026-07-19": 101.917737,
    "2026-07-20": 154.776533,
    "2026-07-23": 59.577185,
    "2026-07-24": 30.893204,
    "2026-07-26": 101.586414,
    "2026-07-27": 195.468498,
}

EXPECTED_SERIES = {
    0: {"ctl": 51.404054, "atl": 51.404054, "form": 0.0},
    6: {"ctl": 50.601583, "atl": 47.667635, "form": 2.933948},
    13: {"ctl": 49.092088, "atl": 41.271601, "form": 7.820488},
    20: {"ctl": 51.266192, "atl": 55.568482, "form": -4.30229},
    27: {"ctl": 52.070998, "atl": 59.367227, "form": -7.296229},
}


def _daily_trimp():
    daily = {}
    for row in load_schedule_rows():
        if row["avg_hr"] is None:
            continue
        day = row["start_time"].date()
        load = analytics.trimp(row["duration_seconds"] / 60, row["avg_hr"], HR_REST, HR_MAX)
        daily[day] = daily.get(day, 0.0) + load
    return daily


def test_daily_trimp_matches_snapshot():
    daily = {day.isoformat(): load for day, load in _daily_trimp().items()}

    assert daily == pytest.approx(EXPECTED_DAILY_TRIMP, abs=1e-6)


def test_ctl_atl_tsb_series_matches_snapshot():
    loads = analytics.build_daily_trimp_loads(_daily_trimp(), LOAD_START, TODAY)
    series = analytics.ctl_atl(loads)

    assert len(series) == 28
    for index, expected in EXPECTED_SERIES.items():
        assert series[index] == pytest.approx(expected, abs=1e-6)


def test_dashboard_training_load_matches_snapshot(app, client, db_session, monkeypatch):
    monkeypatch.setattr(routes, "date", FrozenDate)
    db_session.add(UserSettings(resting_hr=HR_REST, max_hr=HR_MAX))
    db_session.commit()
    seed_load_schedule(db_session)

    with captured_context(app) as contexts:
        response = client.get("/dashboard")

    assert response.status_code == 200
    context = contexts[-1]
    assert context["training_load"] == pytest.approx(59.367227, abs=1e-6)
    assert context["training_load_delta"] == pytest.approx(6.836151, abs=1e-6)
