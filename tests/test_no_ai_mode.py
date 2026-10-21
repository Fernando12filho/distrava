"""AC-11: with no provider every non-coach feature works and no network call is made."""

import pytest

from app.coach import providers


@pytest.fixture()
def network_calls(monkeypatch):
    calls = []

    def record(*args, **kwargs):
        calls.append(args)
        raise AssertionError("network call attempted")

    monkeypatch.setattr(providers, "_urlopen", record)
    return calls


@pytest.mark.parametrize("path", ["/", "/dashboard", "/activities", "/records", "/settings", "/import", "/coach/"])
def test_ac_11_pages_work_without_a_key_and_touch_no_network(client, network_calls, path):
    response = client.get(path, follow_redirects=True)

    assert response.status_code == 200
    assert network_calls == []


def test_ac_11_the_coach_says_how_to_connect(client):
    html = client.get("/coach/").get_data(as_text=True)

    assert "NOT CONNECTED" in html
    assert "Coach not connected" in html


def test_tests_can_never_reach_the_real_keychain():
    # conftest swaps the default keystore for an in-memory one.
    from app.coach import keystore

    assert isinstance(keystore.default_keystore(), keystore.MemoryKeystore)


def test_tests_can_never_reach_the_network():
    with pytest.raises(AssertionError, match="network"):
        providers._urlopen(None, timeout=1)
