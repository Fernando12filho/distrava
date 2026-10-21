import re
from pathlib import Path

import pytest

from app.coach import routes as coach_routes
from app.models import CoachSession

RESEARCH = (Path(__file__).resolve().parent.parent / "research" / "training-rules.md").read_text()


class FrozenWednesday(coach_routes.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


def _logged_legs_day(client, db_session, week_start="2026-10-19", rirs=(1, 2, 5, None)):
    client.post("/coach/sessions", data={"template": "legs_glutes", "day_index": "1", "week_start": week_start})
    db_session.expire_all()
    session = db_session.query(CoachSession).filter_by(focus="Legs & Glutes").one()
    client.post(f"/coach/sessions/{session.id}/status", data={"status": "done"})
    db_session.expire_all()
    squat = next(i for i in session.items if i.exercise.slug == "back_squat")
    for logged, rir in zip(squat.logged_sets, rirs):
        client.post(f"/coach/sets/{logged.id}", data={"reps": "6", "rir": "" if rir is None else str(rir)})
    return session


def _panel(html):
    return re.search(r'<div class="hard-sets-card">.*?</details>\s*</div>', html, re.S).group(0)


def test_ac_rule_week_02_board_shows_this_weeks_hard_sets_per_muscle(client, db_session):
    _logged_legs_day(client, db_session)

    panel = _panel(client.get("/coach/").get_data(as_text=True))

    assert "Hard sets this week" in panel
    assert re.search(r'data-muscle="legs".*?<span class="hard-sets-count">2</span>', panel, re.S)
    # The squat's 4th set plus the untouched RDL, lunge and calf raise sets (3 each).
    assert "10 sets without reps in reserve" in panel


def test_another_weeks_sets_are_not_counted(client, db_session):
    _logged_legs_day(client, db_session, week_start="2026-10-12")

    panel = _panel(client.get("/coach/").get_data(as_text=True))

    assert 'data-muscle="legs"' not in panel
    assert "No sets logged this week" in panel


def test_the_panel_follows_the_week_being_viewed(client, db_session):
    _logged_legs_day(client, db_session, week_start="2026-10-12")

    panel = _panel(client.get("/coach/?week=2026-10-12").get_data(as_text=True))

    assert 'data-muscle="legs"' in panel


def test_ac_rule_week_02_explanation_cites_only_the_research(client, db_session):
    _logged_legs_day(client, db_session)

    panel = _panel(client.get("/coach/").get_data(as_text=True))

    source = re.search(r'class="explain-source">([^<]+)<', panel).group(1)
    for rule in re.findall(r"RULE-[A-Z]+-\d+", source):
        assert f"### {rule}:" in RESEARCH, rule
    for surname in re.findall(r"([A-Z][a-zé]+)(?=[ ,&]| \d{4})", source.split(" · ", 1)[1]):
        assert surname in RESEARCH, surname
    assert "RULE-WEEK-02" in source


def test_no_pressure_copy_in_the_panel(client, db_session):
    _logged_legs_day(client, db_session, rirs=(6, 6, 6, 6))

    panel = _panel(client.get("/coach/").get_data(as_text=True)).lower()

    for word in ("missed", "behind", "streak", "only "):
        assert word not in panel
