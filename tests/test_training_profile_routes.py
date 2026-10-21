from app.models import TrainingProfile, UserSettings

PROFILE_FORM = {
    "units": "metric",
    "runs_per_week": "4",
    "gym_days_per_week": "3",
    "split": "Upper / lower",
    "goal": "Marathon, no hurry",
    "years_running": "6",
    "years_lifting": "1",
}


def test_settings_page_has_a_training_profile_card(client):
    html = client.get("/settings").get_data(as_text=True)

    assert "Training profile" in html
    for name in ("runs_per_week", "gym_days_per_week", "split", "goal", "years_running", "years_lifting"):
        assert f'name="{name}"' in html


def test_saving_settings_stores_the_profile_in_one_row(client, db_session):
    client.post("/settings", data=PROFILE_FORM)
    client.post("/settings", data={**PROFILE_FORM, "runs_per_week": "5"})

    db_session.expire_all()
    profile = db_session.query(TrainingProfile).one()
    assert (profile.runs_per_week, profile.gym_days_per_week, profile.split) == (5, 3, "Upper / lower")
    assert (profile.goal, profile.years_running, profile.years_lifting) == ("Marathon, no hurry", 6, 1)


def test_saved_profile_is_shown_back(client):
    client.post("/settings", data=PROFILE_FORM)

    html = client.get("/settings").get_data(as_text=True)

    assert 'value="Upper / lower"' in html
    assert "Marathon, no hurry</textarea>" in html


def test_a_bad_value_saves_nothing_and_says_why(client, db_session):
    response = client.post("/settings", data={**PROFILE_FORM, "max_hr": "185", "gym_days_per_week": "9"})

    assert response.status_code == 400
    assert "gym days per week" in response.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.query(TrainingProfile).count() == 0
    assert db_session.query(UserSettings).count() == 0


def test_settings_without_profile_fields_create_no_profile(client, db_session):
    client.post("/settings", data={"units": "metric", "max_hr": "185"})

    assert db_session.query(TrainingProfile).count() == 0


def test_clearing_a_field_unsets_it(client, db_session):
    client.post("/settings", data=PROFILE_FORM)
    client.post("/settings", data={**PROFILE_FORM, "split": ""})

    db_session.expire_all()
    assert db_session.query(TrainingProfile).one().split is None
