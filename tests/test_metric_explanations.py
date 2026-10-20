"""Every research-backed number explains itself, citing its rule id and only
sources that appear in research/training-rules.md."""

import re
from pathlib import Path

from app import routes
from app.models import ActivityStream, UserSettings
from regression_fixtures import FrozenDate, seed_best_effort_runs, seed_load_schedule

RESEARCH = (Path(__file__).resolve().parent.parent / "research" / "training-rules.md").read_text()


def _dashboard(client, db_session, monkeypatch):
    monkeypatch.setattr(routes, "date", FrozenDate)
    db_session.add(UserSettings(resting_hr=55, max_hr=188))
    db_session.commit()
    seed_load_schedule(db_session)
    seed_best_effort_runs(db_session)
    return client.get("/dashboard").get_data(as_text=True)


def _activity_page(client, make_activity, db_session):
    activity = make_activity(duration_seconds=1500, distance_meters=5000.0)
    times = list(range(0, 1501, 5))
    db_session.add(
        ActivityStream(
            activity_id=activity.id,
            stream_data={"time": times, "hr": [150.0] * len(times), "distance": [None] * len(times), "elevation": [], "pace": []},
        )
    )
    db_session.commit()
    return client.get(f"/activities/{activity.id}").get_data(as_text=True)


def _sources(html):
    return re.findall(r'class="explain-source">([^<]+)<', html)


def test_dashboard_explains_training_load_predictions_and_vdot(client, db_session, monkeypatch):
    html = _dashboard(client, db_session, monkeypatch)

    assert html.count("What is this?") == 3
    for rule in ("RULE-METRIC-03", "RULE-METRIC-04", "RULE-METRIC-05"):
        assert rule in html


def test_training_load_is_explained_as_a_personal_trend(client, db_session, monkeypatch):
    html = _dashboard(client, db_session, monkeypatch)

    assert "personal trend" in html
    assert "not with other people" in html


def test_activity_zones_explain_where_max_and_resting_come_from(client, make_activity, db_session):
    html = _activity_page(client, make_activity, db_session)

    assert "RULE-METRIC-01" in html and "RULE-METRIC-02" in html
    assert "208 − 0.7 × age" in html
    assert "Apple Health" in html


def test_every_rule_id_cited_exists_in_the_research(client, db_session, monkeypatch, make_activity):
    html = _dashboard(client, db_session, monkeypatch) + _activity_page(client, make_activity, db_session)

    for rule in set(re.findall(r"RULE-[A-Z]+-\d+", html)):
        assert f"### {rule}:" in RESEARCH, rule


def test_every_cited_author_appears_in_the_research(client, db_session, monkeypatch, make_activity):
    html = _dashboard(client, db_session, monkeypatch) + _activity_page(client, make_activity, db_session)
    sources = _sources(html)

    assert sources, "no explain-source lines rendered"
    for line in sources:
        citations = line.split(" · ", 1)[1]
        for surname in re.findall(r"([A-Z][a-zé]+)(?=[ ,&]| \d{4})", citations):
            assert surname in RESEARCH, f"{surname!r} cited but not in research/training-rules.md"
