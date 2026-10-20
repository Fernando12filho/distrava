"""RULE-METRIC-03: TRIMP's weighting constants are sex-specific. Sex is set by
the user in Settings; while it isn't set, the male constants keep the numbers
exactly where they were."""

import pytest

from app import analytics, routes, training_rules
from app.models import UserSettings
from regression_fixtures import HR_MAX, HR_REST, FrozenDate, captured_context, seed_load_schedule


def test_constants_match_the_research_file():
    assert training_rules.TRIMP_WEIGHTING == {"male": (0.64, 1.92), "female": (0.86, 1.67)}


def test_female_and_male_trimp_differ():
    male = analytics.trimp(45, 150, 55, 188, gender="male")
    female = analytics.trimp(45, 150, 55, 188, gender="female")

    assert female != pytest.approx(male)


def test_an_unknown_sex_is_an_error_not_a_silent_default():
    with pytest.raises(KeyError):
        analytics.trimp(45, 150, 55, 188, gender="other")


# ---------------------------------------------------------------- settings


def test_settings_page_offers_sex(client):
    html = client.get("/settings").get_data(as_text=True)

    assert 'name="sex"' in html
    for label in ("Not set", "Male", "Female"):
        assert f">{label}<" in html


@pytest.mark.parametrize("posted, stored", [("female", "female"), ("male", "male"), ("", None), ("robot", None)])
def test_settings_saves_sex(client, db_session, posted, stored):
    client.post("/settings", data={"sex": posted}, headers={"X-Requested-With": "fetch"})

    db_session.expire_all()
    assert db_session.query(UserSettings).one().sex == stored


def test_settings_page_keeps_the_chosen_sex_selected(client, db_session):
    db_session.add(UserSettings(sex="female"))
    db_session.commit()

    html = client.get("/settings").get_data(as_text=True)

    assert '<option value="female" selected>' in html


# ---------------------------------------------------------------- training load


def _dashboard_load(app, client, db_session, monkeypatch, sex):
    monkeypatch.setattr(routes, "date", FrozenDate)
    db_session.add(UserSettings(resting_hr=HR_REST, max_hr=HR_MAX, sex=sex))
    db_session.commit()
    seed_load_schedule(db_session)
    with captured_context(app) as contexts:
        client.get("/dashboard")
    return contexts[-1]["training_load"]


def test_unset_sex_keeps_the_pinned_training_load(app, client, db_session, monkeypatch):
    assert _dashboard_load(app, client, db_session, monkeypatch, None) == pytest.approx(59.367227, abs=1e-6)


def test_female_training_load_uses_the_female_constants(app, client, db_session, monkeypatch):
    female = _dashboard_load(app, client, db_session, monkeypatch, "female")

    assert female != pytest.approx(59.367227, abs=1e-3)
    assert female > 0
