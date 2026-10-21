"""Session effort (sRPE, RULE-LOAD-01): one 0–10 rating per run or lift, and
load = rating × minutes. The rating is the user's; nothing estimates it."""

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import inspect

from app import analytics, create_app, parser
from app.coach import routes as coach_routes
from app.models import Activity, CoachSession
from app.training_rules import SRPE_ANCHORS, SRPE_EASY_MAX, SRPE_HARD_MIN
from test_app_schema import _old_schema_engine

RESEARCH = (Path(__file__).resolve().parent.parent / "research" / "training-rules.md").read_text()


# --- pure rules -------------------------------------------------------------


def test_rule_load_01_cut_offs_are_easy_up_to_2_and_hard_from_5():
    assert (SRPE_EASY_MAX, SRPE_HARD_MIN) == (2, 5)


def test_rule_load_01_scale_labels_are_the_anchors_the_research_lists():
    assert SRPE_ANCHORS == {2: "Easy", 3: "Moderate", 4: "Somewhat hard", 5: "Hard", 7: "Very hard"}


@pytest.mark.parametrize(
    "rating, label",
    [(0, "easy"), (2, "easy"), (3, "moderate"), (4, "moderate"), (5, "hard"), (10, "hard"), (None, None)],
)
def test_rule_load_01_effort_class_comes_only_from_the_rating(rating, label):
    assert analytics.effort_class(rating) == label


def test_rule_load_01_session_load_is_rating_times_minutes():
    assert analytics.session_load(6, 2400) == 240


def test_session_load_keeps_at_most_two_decimals():
    assert analytics.session_load(7, 2005) == 233.92


def test_no_rating_means_no_load():
    assert analytics.session_load(None, 2400) is None


# --- storing a rating -------------------------------------------------------


def _rate(client, activity_id, value, **extra):
    return client.post(f"/activities/{activity_id}/effort", data={"rpe": value, **extra})


def _stored(db_session, activity_id):
    db_session.expire_all()
    return db_session.get(Activity, activity_id).session_rpe


def test_rating_an_activity_stores_it_and_returns_to_the_activity(client, db_session, make_activity):
    run = make_activity()

    response = _rate(client, run.id, "6")

    assert response.status_code == 303
    assert response.headers["Location"].endswith(f"/activities/{run.id}")
    assert _stored(db_session, run.id) == 6


def test_a_blank_rating_clears_it(client, db_session, make_activity):
    run = make_activity()
    _rate(client, run.id, "6")

    _rate(client, run.id, "")

    assert _stored(db_session, run.id) is None


@pytest.mark.parametrize("value", ["11", "-1", "five", "5.5"])
def test_an_out_of_scale_rating_is_rejected(client, db_session, make_activity, value):
    run = make_activity()

    assert _rate(client, run.id, value).status_code == 400
    assert _stored(db_session, run.id) is None


def test_rating_an_unknown_activity_is_not_found(client):
    assert _rate(client, 999, "5").status_code == 404


def test_rating_can_return_to_the_coach_board(client, make_activity):
    run = make_activity()

    response = _rate(client, run.id, "4", next="/coach/?week=2026-10-19&session=3")

    assert response.headers["Location"].endswith("/coach/?week=2026-10-19&session=3")


@pytest.mark.parametrize("target", ["https://example.com/", "//example.com/x", "coach"])
def test_rating_never_redirects_off_the_app(client, make_activity, target):
    run = make_activity()

    response = _rate(client, run.id, "4", next=target)

    assert response.headers["Location"].endswith(f"/activities/{run.id}")


def test_a_re_import_keeps_the_rating(db_session, make_activity):
    start = datetime(2026, 7, 1, 8, 0, 0)
    run = make_activity(dedup_key=parser._make_dedup_key("Run", start, 1800))
    run.session_rpe = 7
    db_session.commit()

    parser._persist_activity(
        db_session,
        activity_type=run.activity_type,
        start_time=run.start_time,
        end_time=run.end_time,
        duration_seconds=run.duration_seconds,
        distance_meters=run.distance_meters,
        avg_hr=150.0,
        max_hr=170.0,
        elevation_gain_meters=None,
        source="apple_health",
        source_id="again",
        refresh_existing={"avg_hr": 150.0, "max_hr": 170.0},
    )

    assert _stored(db_session, run.id) == 7


def test_an_existing_database_gets_the_rating_column_without_losing_rows():
    app = create_app({"TESTING": True, "ENGINE": _old_schema_engine()})

    columns = {c["name"] for c in inspect(app.engine).get_columns("activities")}
    assert "session_rpe" in columns


# --- showing it -------------------------------------------------------------


def _page(client, activity_id):
    return client.get(f"/activities/{activity_id}").get_data(as_text=True)


def test_an_unrated_activity_offers_the_0_to_10_scale_with_its_anchors(client, make_activity):
    run = make_activity()

    html = _page(client, run.id)

    assert "How hard was the whole session?" in html
    for value in range(0, 11):
        assert f'name="rpe" value="{value}"' in html
    for label in SRPE_ANCHORS.values():
        assert label in html
    assert "about 30 minutes after" in html


def test_a_rated_activity_shows_its_rating_class_and_load(client, make_activity):
    run = make_activity(duration_seconds=2400)
    client.post(f"/activities/{run.id}/effort", data={"rpe": "6"})

    html = _page(client, run.id)

    assert re.search(r'name="rpe" value="6"[^>]*aria-pressed="true"', html)
    assert "Hard" in html
    assert "240" in html
    assert "6 × 40 min" in html


def test_the_effort_explanation_cites_rule_load_01_and_only_researched_sources(client, make_activity):
    run = make_activity()

    html = _page(client, run.id)

    assert "RULE-LOAD-01" in html
    source = re.search(r'class="explain-source">(RULE-LOAD-01[^<]+)<', html).group(1)
    for surname in re.findall(r"([A-Z][a-zé]+)(?=[ ,&]| \d{4})", source.split(" · ", 1)[1]):
        assert surname in RESEARCH


def test_effort_copy_has_no_pressure_words(client, make_activity):
    html = _page(client, make_activity().id).lower()

    for word in ("missed", "streak", "you forgot", "failed"):
        assert word not in html


# --- on the coach board -----------------------------------------------------


class FrozenWednesday(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 21)


def test_a_matched_board_session_rates_the_same_activity(client, db_session, make_activity, monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)
    start = datetime(2026, 10, 21, 18, 0)
    workout = make_activity(
        activity_type="TraditionalStrengthTraining",
        start_time=start,
        end_time=start + timedelta(minutes=50),
        duration_seconds=3000,
        distance_meters=0.0,
        dedup_key="gym-wed",
    )
    client.post("/coach/sessions", data={"template": "legs_glutes", "day_index": "2", "week_start": "2026-10-19"})
    session = db_session.query(CoachSession).one()
    client.post(f"/coach/sessions/{session.id}/confirm", data={"activity_id": str(workout.id)})

    html = client.get(f"/coach/?week=2026-10-19&session={session.id}").get_data(as_text=True)

    assert f'action="/activities/{workout.id}/effort"' in html
    assert f'name="next" value="/coach/?week=2026-10-19&amp;session={session.id}"' in html
    assert "How hard was the whole session?" in html


def test_an_unmatched_board_session_has_no_effort_scale(client, monkeypatch):
    monkeypatch.setattr(coach_routes, "date", FrozenWednesday)
    client.post("/coach/sessions", data={"template": "legs_glutes", "day_index": "2", "week_start": "2026-10-19"})

    html = client.get("/coach/?week=2026-10-19&session=1").get_data(as_text=True)

    assert "How hard was the whole session?" not in html
