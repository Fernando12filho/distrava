import pytest

from app import analytics, routes
from regression_fixtures import FrozenDate, captured_context, seed_best_effort_runs


@pytest.mark.parametrize(
    "known_seconds, known_meters, target_meters, expected",
    [
        (1500.0, 5000.0, 10000.0, 3127.397283),
        (1500.0, 5000.0, 21097.0, 6900.125654),
        (1500.0, 5000.0, 42195.0, 14386.650894),
        (3000.0, 10000.0, 42195.0, 13800.598),
    ],
)
def test_riegel_matches_snapshot(known_seconds, known_meters, target_meters, expected):
    assert analytics.riegel_predict(known_seconds, known_meters, target_meters) == pytest.approx(expected, abs=1e-6)


def test_vdot_without_hr_matches_snapshot():
    assert analytics.estimate_vo2max(5000.0, 1500.0) == pytest.approx(38.309363, abs=1e-6)


def test_vdot_with_hr_matches_snapshot():
    assert analytics.estimate_vo2max(10000.0, 3000.0, 150.0, 185.0) == pytest.approx(49.348196, abs=1e-6)


def test_dashboard_predictions_match_snapshot(app, client, db_session, monkeypatch):
    monkeypatch.setattr(routes, "date", FrozenDate)
    seed_best_effort_runs(db_session)

    with captured_context(app) as contexts:
        response = client.get("/dashboard")

    assert response.status_code == 200
    context = contexts[-1]
    assert context["prediction_basis_label"] == "Half Marathon"
    assert context["race_predictions"] == [
        {"label": "5K", "value": "24:06"},
        {"label": "10K", "value": "50:15"},
        {"label": "Half Marathon", "value": "1:50:53"},
        {"label": "Marathon", "value": "3:51:12"},
    ]
    assert context["vo2max"] == pytest.approx(40.0045, abs=1e-4)
