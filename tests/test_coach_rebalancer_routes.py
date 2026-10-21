import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.coach import routes as coach_routes
from app.models import ActivityStream, CoachSession, UserSettings

RESEARCH = (Path(__file__).resolve().parent.parent / "research" / "training-rules.md").read_text()


class FrozenWednesday(coach_routes.date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)


def _add(client, db_session, template, day_index, effort=None):
    client.post("/coach/sessions", data={"template": template, "day_index": str(day_index), "week_start": "2026-10-19"})
    db_session.expire_all()
    session = db_session.query(CoachSession).order_by(CoachSession.id.desc()).first()
    if effort:
        client.post(f"/coach/sessions/{session.id}/planned-effort", data={"effort": effort})
    return session


def _panel(html):
    return re.search(r'<div class="week-check-card">.*?</details>\s*</div>', html, re.S).group(0)


def _board(client):
    return client.get("/coach/").get_data(as_text=True)


# --- planned effort -------------------------------------------------------------


def test_planned_effort_is_saved_cleared_and_validated(client, db_session):
    session = _add(client, db_session, "running_day", 4)

    client.post(f"/coach/sessions/{session.id}/planned-effort", data={"effort": "hard"})
    db_session.expire_all()
    assert db_session.get(CoachSession, session.id).planned_effort == "hard"

    client.post(f"/coach/sessions/{session.id}/planned-effort", data={"effort": ""})
    db_session.expire_all()
    assert db_session.get(CoachSession, session.id).planned_effort is None

    assert client.post(f"/coach/sessions/{session.id}/planned-effort", data={"effort": "brutal"}).status_code == 400


def test_session_detail_offers_planned_effort(client, db_session):
    session = _add(client, db_session, "running_day", 4)

    html = client.get(f"/coach/?session={session.id}").get_data(as_text=True)

    assert f'action="/coach/sessions/{session.id}/planned-effort"' in html
    for value in ('value=""', 'value="easy"', 'value="hard"'):
        assert value in html


def test_rest_days_have_no_planned_effort(client, db_session):
    session = _add(client, db_session, "rest", 4)

    html = client.get(f"/coach/?session={session.id}").get_data(as_text=True)

    assert "planned-effort" not in html


# --- week check -----------------------------------------------------------------


def test_ac_05_week_check_names_a_clash_and_its_rule(client, db_session):
    _add(client, db_session, "running_day", 3, effort="hard")
    _add(client, db_session, "running_day", 4, effort="hard")

    panel = _panel(_board(client))

    assert "RULE-REC-02" in panel
    assert "Thu" in panel and "Fri" in panel


def test_ac_05_rule_rec_04_hard_legs_before_a_hard_run_is_named(client, db_session):
    _add(client, db_session, "legs_glutes", 3, effort="hard")
    _add(client, db_session, "running_day", 4, effort="hard")

    assert "RULE-REC-04" in _panel(_board(client))


def test_a_week_without_clashes_says_so(client, db_session):
    _add(client, db_session, "running_day", 3, effort="hard")
    _add(client, db_session, "running_day", 5, effort="hard")

    assert "No spacing clashes" in _panel(_board(client))


def test_ac_05_a_done_run_rated_hard_counts_even_if_planned_easy(client, db_session, make_activity):
    _add(client, db_session, "running_day", 0, effort="easy")
    _add(client, db_session, "running_day", 1, effort="hard")
    monday = db_session.query(CoachSession).filter_by(day_index=0).one()
    start = datetime(2026, 10, 19, 7, 0)
    run = make_activity(start_time=start, end_time=start + timedelta(minutes=45), duration_seconds=2700, distance_meters=8000.0)
    run.session_rpe = 6
    monday.matched_activity_id = run.id
    monday.status = "done"
    db_session.commit()

    assert "RULE-REC-02" in _panel(_board(client))


def test_d1_a_done_run_with_10_minutes_above_threshold_counts_as_hard(client, db_session, make_activity):
    db_session.add(UserSettings(resting_hr=50, max_hr=190))
    _add(client, db_session, "running_day", 0)
    _add(client, db_session, "running_day", 1, effort="hard")
    monday = db_session.query(CoachSession).filter_by(day_index=0).one()
    start = datetime(2026, 10, 19, 7, 0)
    run = make_activity(start_time=start, end_time=start + timedelta(minutes=20), duration_seconds=1200, distance_meters=4000.0)
    times = list(range(0, 1201, 5))
    # 85 % of reserve = 50 + 0.85 × 140 = 169 bpm; 11 minutes at 175.
    hr = [175.0 if t < 660 else 140.0 for t in times]
    db_session.add(ActivityStream(activity_id=run.id, stream_data={"time": times, "hr": hr, "distance": [], "elevation": [], "pace": []}))
    monday.matched_activity_id = run.id
    monday.status = "done"
    db_session.commit()

    assert "RULE-REC-02" in _panel(_board(client))


def test_week_check_explanation_cites_only_the_research_and_says_skips_are_a_design_choice(client, db_session):
    panel = _panel(_board(client))

    source = re.search(r'class="explain-source">([^<]+)<', panel).group(1)
    for rule in re.findall(r"RULE-[A-Z]+-\d+", source):
        assert f"### {rule}:" in RESEARCH, rule
    for surname in re.findall(r"([A-Z][a-zé]+)(?=[ ,&]| \d{4})", source.split(" · ", 1)[1]):
        assert surname in RESEARCH, surname
    assert "design choice" in panel


def test_no_pressure_copy_in_the_week_check(client, db_session):
    skipped = _add(client, db_session, "running_day", 1, effort="hard")
    client.post(f"/coach/sessions/{skipped.id}/status", data={"status": "skipped"})
    _add(client, db_session, "running_day", 3, effort="hard")
    _add(client, db_session, "running_day", 4, effort="hard")

    panel = _panel(_board(client)).lower()

    for word in ("missed", "behind", "streak", "failed", "warning"):
        assert word not in panel


# --- skipped sessions: drop, or move where it fits --------------------------------


def _skip(client, db_session, day_index, effort="hard"):
    session = _add(client, db_session, "running_day", day_index, effort=effort)
    client.post(f"/coach/sessions/{session.id}/status", data={"status": "skipped"})
    return session


def test_ac_05_rule_prog_01_a_skipped_session_offers_only_days_that_fit(client, db_session):
    skipped = _skip(client, db_session, 1)
    _add(client, db_session, "running_day", 4, effort="hard")

    panel = _panel(_board(client))

    # Today is Wednesday: Thu and Sat sit next to Fri's hard run and Fri is
    # taken, so Sunday is the only fit.
    form = re.search(rf'action="/coach/sessions/{skipped.id}/reschedule".*?</form>', panel, re.S).group(0)
    assert re.findall(r'name="day_index" value="(\d)"', form) == ["6"]
    assert "Dropped" in panel


def test_rescheduling_moves_the_session_and_plans_it_again(client, db_session):
    skipped = _skip(client, db_session, 1)

    response = client.post(f"/coach/sessions/{skipped.id}/reschedule", data={"day_index": "6"})

    assert response.status_code == 303
    db_session.expire_all()
    moved = db_session.get(CoachSession, skipped.id)
    assert (moved.day_index, moved.status) == (6, "planned")


def test_ac_05_rescheduling_to_a_day_that_breaks_a_rule_is_refused(client, db_session):
    skipped = _skip(client, db_session, 1)
    _add(client, db_session, "running_day", 4, effort="hard")

    response = client.post(f"/coach/sessions/{skipped.id}/reschedule", data={"day_index": "5"})

    assert response.status_code == 400
    db_session.expire_all()
    assert db_session.get(CoachSession, skipped.id).day_index == 1


def test_only_skipped_sessions_can_be_rescheduled(client, db_session):
    session = _add(client, db_session, "running_day", 1, effort="hard")

    assert client.post(f"/coach/sessions/{session.id}/reschedule", data={"day_index": "6"}).status_code == 400
