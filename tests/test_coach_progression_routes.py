import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.coach import routes as coach_routes
from app.models import CoachSession, CoachWeek

RESEARCH = (Path(__file__).resolve().parent.parent / "research" / "training-rules.md").read_text()


class FrozenWednesday(coach_routes.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


@pytest.fixture()
def run_on(make_activity):
    def _run_on(day, meters, activity_type="Run"):
        start = datetime(day.year, day.month, day.day, 7, 0)
        return make_activity(
            activity_type=activity_type,
            start_time=start,
            end_time=start + timedelta(minutes=40),
            duration_seconds=2400,
            distance_meters=meters,
            utc_offset_minutes=0,
            dedup_key=f"{activity_type}|{start.isoformat()}|{meters}",
        )

    return _run_on


def _add(client, db_session, template, day_index, effort=None):
    client.post("/coach/sessions", data={"template": template, "day_index": str(day_index), "week_start": "2026-10-19"})
    db_session.expire_all()
    session = db_session.query(CoachSession).order_by(CoachSession.id.desc()).first()
    if effort:
        client.post(f"/coach/sessions/{session.id}/planned-effort", data={"effort": effort})
    return session


def _panel(client):
    html = client.get("/coach/").get_data(as_text=True)
    return re.search(r'<div class="week-check-card">.*?</details>\s*</div>', html, re.S).group(0)


def _volumes(db_session):
    db_session.expire_all()
    return {
        (s.day_index, i.exercise.slug): (i.sets, i.distance_meters, i.duration_seconds)
        for s in db_session.query(CoachSession)
        for i in s.items
    }


# --- RULE-PROG-02 ---------------------------------------------------------------


def test_ac_rule_prog_02_a_big_distance_jump_is_noted_with_its_rule(client, db_session, run_on):
    run_on(datetime(2026, 10, 7), 10000.0)
    run_on(datetime(2026, 10, 14), 10000.0)
    run_on(datetime(2026, 10, 19), 8000.0)
    _add(client, db_session, "running_day", 4)  # planned 8 km Friday

    panel = _panel(client)

    # 16 km against a 10 km average: +60 %.
    assert "RULE-PROG-02" in panel
    assert "60%" in panel
    assert "16 km" in panel and "10 km" in panel


def test_ac_rule_prog_02_a_similar_week_has_no_note(client, db_session, run_on):
    run_on(datetime(2026, 10, 7), 10000.0)
    run_on(datetime(2026, 10, 14), 10000.0)
    run_on(datetime(2026, 10, 19), 10000.0)

    assert "RULE-PROG-02" not in _panel(client).split("<details")[0]


def test_rides_do_not_count_as_running_distance(client, db_session, run_on):
    run_on(datetime(2026, 10, 7), 10000.0)
    run_on(datetime(2026, 10, 14), 10000.0)
    run_on(datetime(2026, 10, 19), 40000.0, activity_type="Cycle")

    assert "RULE-PROG-02" not in _panel(client).split("<details")[0]


# --- RULE-PROG-04 + D7 ------------------------------------------------------------


def _week_after_a_break(client, db_session, run_on):
    run_on(datetime(2026, 10, 5), 10000.0)  # 16 days before today
    _add(client, db_session, "running_day", 0)  # Monday, already past
    _add(client, db_session, "running_day", 4)
    _add(client, db_session, "chest_triceps", 5)


def test_ac_d7_after_a_break_the_options_are_offered(client, db_session, run_on):
    _week_after_a_break(client, db_session, run_on)

    panel = _panel(client)

    assert "16 days" in panel
    form = re.search(r'action="/coach/weeks/2026-10-19/ease".*?</form>', panel, re.S).group(0)
    assert re.findall(r'name="factor" value="([0-9.]+)"', form) == ["0.6", "0.7", "0.8", "0.9"]


def test_ac_d7_no_options_without_a_break(client, db_session, run_on):
    run_on(datetime(2026, 10, 18), 10000.0)
    _add(client, db_session, "running_day", 4)

    assert "/ease" not in _panel(client)


def test_ac_d7_easing_scales_only_the_rest_of_the_week(client, db_session, run_on):
    _week_after_a_break(client, db_session, run_on)
    before = _volumes(db_session)

    response = client.post("/coach/weeks/2026-10-19/ease", data={"factor": "0.8"})

    assert response.status_code == 303
    after = _volumes(db_session)
    assert after[(0, "easy_run")] == before[(0, "easy_run")]
    assert after[(4, "easy_run")] == (None, 6400.0, None)
    assert after[(5, "bench_press")][0] == 3  # 4 sets × 0.8, rounded down
    assert "Eased to 80%" in _panel(client)


def test_ac_10_undo_restores_the_week_exactly(client, db_session, run_on):
    _week_after_a_break(client, db_session, run_on)
    before = _volumes(db_session)
    client.post("/coach/weeks/2026-10-19/ease", data={"factor": "0.6"})

    response = client.post("/coach/weeks/2026-10-19/ease/undo")

    assert response.status_code == 303
    assert _volumes(db_session) == before
    db_session.expire_all()
    week = db_session.query(CoachWeek).one()
    assert week.eased_factor is None and week.eased_snapshot is None


@pytest.mark.parametrize("factor", ["0.5", "1.0", "lots", ""])
def test_ac_d7_only_offered_factors_are_accepted(client, db_session, run_on, factor):
    _week_after_a_break(client, db_session, run_on)

    assert client.post("/coach/weeks/2026-10-19/ease", data={"factor": factor}).status_code == 400


def test_ac_d7_easing_twice_or_without_a_break_is_refused(client, db_session, run_on):
    _week_after_a_break(client, db_session, run_on)
    client.post("/coach/weeks/2026-10-19/ease", data={"factor": "0.8"})

    assert client.post("/coach/weeks/2026-10-19/ease", data={"factor": "0.8"}).status_code == 400

    client.post("/coach/weeks/2026-10-19/ease/undo")
    run_on(datetime(2026, 10, 20), 5000.0)
    assert client.post("/coach/weeks/2026-10-19/ease", data={"factor": "0.8"}).status_code == 400


def test_undo_without_easing_is_refused(client, db_session, run_on):
    _week_after_a_break(client, db_session, run_on)

    assert client.post("/coach/weeks/2026-10-19/ease/undo").status_code == 400


# --- RULE-WEEK-01 -----------------------------------------------------------------


def test_ac_rule_week_01_too_many_hard_runs_are_noted(client, db_session):
    for day, effort in [(3, "hard"), (5, "hard"), (4, "easy"), (6, "easy")]:
        _add(client, db_session, "running_day", day, effort=effort)

    panel = _panel(client)

    assert "RULE-WEEK-01" in panel
    assert "2 of 4 runs" in panel


def test_ac_rule_week_01_one_hard_run_in_three_has_no_note(client, db_session):
    for day, effort in [(3, "hard"), (5, "easy"), (6, "easy")]:
        _add(client, db_session, "running_day", day, effort=effort)

    assert "RULE-WEEK-01" not in _panel(client).split("<details")[0]


# --- explanation --------------------------------------------------------------------


def test_explanation_cites_the_new_rules_from_the_research_only(client, db_session):
    panel = _panel(client)

    source = re.search(r'class="explain-source">([^<]+)<', panel).group(1)
    for rule in ("RULE-PROG-02", "RULE-PROG-04", "RULE-WEEK-01"):
        assert rule in source
    for rule in re.findall(r"RULE-[A-Z]+-\d+", source):
        assert f"### {rule}:" in RESEARCH, rule
    for surname in re.findall(r"([A-Z][a-zé]+)(?=[ ,&]| \d{4})", source.split(" · ", 1)[1]):
        assert surname in RESEARCH, surname
