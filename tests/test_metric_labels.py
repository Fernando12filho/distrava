"""Estimates are labelled as estimates (RULE-METRIC-01, 04, 05)."""

from datetime import datetime

from app import routes, training_rules
from app.models import ActivityStream
from regression_fixtures import FrozenDate, captured_context, seed_best_effort_runs


def _dashboard(app, client, db_session, monkeypatch):
    monkeypatch.setattr(routes, "date", FrozenDate)
    seed_best_effort_runs(db_session)
    with captured_context(app) as contexts:
        html = client.get("/dashboard").get_data(as_text=True)
    return contexts[-1], html


def test_riegel_is_trusted_up_to_the_half_marathon():
    assert training_rules.RIEGEL_RELIABLE_UP_TO_METERS == 21097.0


def test_only_the_marathon_prediction_carries_a_caution(app, client, db_session, monkeypatch):
    context, _html = _dashboard(app, client, db_session, monkeypatch)

    cautions = {p["label"]: p["caution"] for p in context["race_predictions"]}
    assert cautions["5K"] is None and cautions["10K"] is None and cautions["Half Marathon"] is None
    assert "likely too fast" in cautions["Marathon"]


def test_dashboard_shows_the_marathon_caution(app, client, db_session, monkeypatch):
    _context, html = _dashboard(app, client, db_session, monkeypatch)

    assert "likely too fast" in html


def test_vdot_is_not_called_vo2max(app, client, db_session, monkeypatch):
    _context, html = _dashboard(app, client, db_session, monkeypatch)

    assert "VDOT" in html
    assert "race-equivalent score" in html
    assert "VO2max" not in html
    assert "ml/kg/min" not in html


def test_activity_zones_say_they_are_estimates(client, make_activity, db_session):
    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    times = list(range(0, 1501, 5))
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": [150.0] * len(times), "distance": [None] * len(times), "elevation": [], "pace": []},
        )
    )
    db_session.commit()

    html = client.get(f"/activities/{activity.id}").get_data(as_text=True)

    assert "estimated from max and resting HR" in html


def test_settings_zones_say_they_are_estimates(client):
    assert "Karvonen method · estimates" in client.get("/settings").get_data(as_text=True)
