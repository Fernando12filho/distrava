import logging
import re

import pytest
from sqlalchemy import inspect, text

from app import create_app
from app.coach.keystore import MemoryKeystore, NoKeystore
from app.coach.providers import FakeProvider, ProviderError
from app.models import CoachLlmCall

KEY = "sk-ant-api03-Abc_def-123456789"


@pytest.fixture()
def keystore():
    return MemoryKeystore()


@pytest.fixture()
def fake():
    return FakeProvider([])


@pytest.fixture()
def ai_client(engine, keystore, fake):
    app = create_app({"TESTING": True, "ENGINE": engine, "KEYSTORE": keystore, "PROVIDER_FACTORY": lambda key: fake})
    return app.test_client()


def _settings(client):
    return client.get("/settings").get_data(as_text=True)


def test_settings_shows_the_ai_card_not_connected(ai_client):
    html = _settings(ai_client)

    assert "AI coach" in html
    assert "Not connected" in html
    assert 'action="/coach/settings/key"' in html


def test_the_key_form_is_outside_the_autosaving_settings_form(ai_client):
    html = _settings(ai_client)

    settings_form = re.search(r'<form id="settings-form".*?</form>', html, re.S).group(0)
    assert 'name="api_key"' not in settings_form


def test_ac_01_saving_a_key_stores_it_in_the_keychain_only(ai_client, keystore, engine, caplog):
    caplog.set_level(logging.DEBUG)

    response = ai_client.post("/coach/settings/key", data={"api_key": KEY})

    assert response.status_code == 303
    assert keystore.get() == KEY
    html = _settings(ai_client)
    assert "•••• 6789" in html
    assert KEY not in html
    assert KEY not in caplog.text
    with engine.connect() as conn:
        for table in inspect(engine).get_table_names():
            for row in conn.execute(text(f"SELECT * FROM {table}")):
                assert KEY not in " ".join(str(v) for v in row), table


def test_a_bad_key_is_refused_with_a_reason(ai_client, keystore):
    response = ai_client.post("/coach/settings/key", data={"api_key": "has space"}, follow_redirects=True)

    assert keystore.get() is None
    assert "Not saved" in response.get_data(as_text=True)


def test_without_a_keychain_the_key_is_not_saved_anywhere(engine, fake):
    client = create_app({"TESTING": True, "ENGINE": engine, "KEYSTORE": NoKeystore(), "PROVIDER_FACTORY": lambda key: fake}).test_client()

    html = client.post("/coach/settings/key", data={"api_key": KEY}, follow_redirects=True).get_data(as_text=True)

    assert "keychain" in html.lower()
    assert KEY not in html


def test_removing_the_key(ai_client, keystore):
    ai_client.post("/coach/settings/key", data={"api_key": KEY})

    ai_client.post("/coach/settings/key/delete")

    assert keystore.get() is None
    assert "Not connected" in _settings(ai_client)


def test_coach_page_shows_connected_once_a_key_is_saved(ai_client):
    assert "NOT CONNECTED" in ai_client.get("/coach/").get_data(as_text=True)

    ai_client.post("/coach/settings/key", data={"api_key": KEY})

    assert "YOUR API KEY" in ai_client.get("/coach/").get_data(as_text=True)


# --- connection test + spend tracking -------------------------------------------


def test_connection_test_calls_the_provider_and_records_the_call(ai_client, fake, db_session):
    ai_client.post("/coach/settings/key", data={"api_key": KEY})
    fake.replies.append(
        {"text": "OK", "model": "claude-haiku-5-5", "usage": {"input_tokens": 20, "output_tokens": 4, "cache_read_tokens": 0, "cache_write_tokens": 0}}
    )

    response = ai_client.post("/coach/settings/test")

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert fake.calls[0]["task"] == "connection_test"
    call = db_session.query(CoachLlmCall).one()
    assert (call.task, call.model, call.input_tokens, call.output_tokens) == ("connection_test", "claude-haiku-5-5", 20, 4)
    assert call.cost_usd == pytest.approx(20 * 0.10 / 1e6 + 4 * 0.50 / 1e6)
    assert call.error_kind is None


def test_a_failed_call_is_recorded_and_explained(ai_client, fake, db_session):
    ai_client.post("/coach/settings/key", data={"api_key": KEY})
    fake.replies.append(ProviderError("auth", "The API key was rejected."))

    response = ai_client.post("/coach/settings/test")

    body = response.get_json()
    assert body["ok"] is False
    assert "rejected" in body["message"]
    call = db_session.query(CoachLlmCall).one()
    assert (call.error_kind, call.input_tokens, call.cost_usd) == ("auth", 0, 0.0)


def test_connection_test_without_a_key_makes_no_call(ai_client, fake, db_session):
    response = ai_client.post("/coach/settings/test")

    assert response.get_json()["ok"] is False
    assert fake.calls == []
    assert db_session.query(CoachLlmCall).count() == 0


def test_settings_shows_spend_this_month_and_all_time(ai_client, fake):
    ai_client.post("/coach/settings/key", data={"api_key": KEY})
    fake.replies.append(
        {"text": "OK", "model": "claude-opus-5-5", "usage": {"input_tokens": 100_000, "output_tokens": 50_000, "cache_read_tokens": 0, "cache_write_tokens": 0}}
    )
    ai_client.post("/coach/settings/test")

    html = _settings(ai_client)

    # 0.1M × $4 + 0.05M × $20 = $1.40
    card = re.search(r'<section class="card" id="ai">.*?</section>', html, re.S).group(0)
    assert "$1.40" in card
    assert "1 call" in card
    assert "estimate" in card.lower()


def test_the_test_button_has_a_loading_state(ai_client):
    ai_client.post("/coach/settings/key", data={"api_key": KEY})

    html = _settings(ai_client)

    assert 'id="ai-test-btn"' in html
    assert "data-loading-label" in html
