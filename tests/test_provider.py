"""The Anthropic provider over plain HTTPS: request shape, parsing, retries, errors.

Every test uses an injected transport — nothing here reaches the network.
"""

import json

import pytest

from app.coach import llm_config
from app.coach.providers import AnthropicProvider, FakeProvider, ProviderError

KEY = "sk-ant-api03-Abc_def-123456789"


def _ok(text="OK", model="claude-haiku-5-5", **usage):
    body = {
        "id": "msg_1",
        "type": "message",
        "model": model,
        "stop_reason": "end_turn",
        "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}],
        "usage": {"input_tokens": 12, "output_tokens": 3, **usage},
    }
    return 200, {"request-id": "req_123"}, json.dumps(body).encode()


def _error(status, kind, headers=None):
    return status, headers or {}, json.dumps({"type": "error", "error": {"type": kind, "message": "nope"}}).encode()


class Transport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, url, headers, body, timeout):
        self.requests.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _provider(*replies):
    transport = Transport(*replies)
    return AnthropicProvider(KEY, send=transport, sleep=lambda _s: None), transport


def test_request_has_the_documented_endpoint_headers_and_task_model():
    provider, transport = _provider(_ok())

    provider.complete("connection_test", system="Be brief.", messages=[{"role": "user", "content": "Hi"}])

    request = transport.requests[0]
    task = llm_config.TASKS["connection_test"]
    assert request["url"] == "https://api.anthropic.com/v1/messages"
    assert request["headers"]["x-api-key"] == KEY
    assert request["headers"]["anthropic-version"] == "2023-06-01"
    assert request["headers"]["content-type"] == "application/json"
    assert request["body"]["model"] == task["model"]
    assert request["body"]["max_tokens"] == task["max_tokens"]
    assert request["body"]["output_config"] == {"effort": task["effort"]}
    assert request["body"]["system"] == "Be brief."


def test_opus_requests_opt_into_the_server_side_refusal_fallback():
    provider, transport = _provider(_ok(model="claude-opus-5-5"))

    provider.complete("default", system=None, messages=[{"role": "user", "content": "Hi"}])

    request = transport.requests[0]
    assert request["body"]["model"] == "claude-opus-5-5"
    assert request["body"]["fallbacks"] == "default"
    assert request["headers"]["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert "system" not in request["body"]


def test_haiku_requests_send_no_fallback():
    provider, transport = _provider(_ok())

    provider.complete("connection_test", system=None, messages=[{"role": "user", "content": "Hi"}])

    assert "fallbacks" not in transport.requests[0]["body"]
    assert "anthropic-beta" not in transport.requests[0]["headers"]


def test_response_is_reduced_to_text_model_stop_reason_and_usage():
    provider, _ = _provider(_ok(text="Hello", cache_read_input_tokens=7, cache_creation_input_tokens=5))

    result = provider.complete("connection_test", system=None, messages=[{"role": "user", "content": "Hi"}])

    assert result == {
        "text": "Hello",
        "model": "claude-haiku-5-5",
        "requested_model": llm_config.TASKS["connection_test"]["model"],
        "stop_reason": "end_turn",
        "request_id": "req_123",
        "usage": {"input_tokens": 12, "output_tokens": 3, "cache_read_tokens": 7, "cache_write_tokens": 5},
    }


@pytest.mark.parametrize("status, kind", [(429, "rate_limit_error"), (529, "overloaded_error"), (500, "api_error")])
def test_retryable_errors_are_retried_then_succeed(status, kind):
    provider, transport = _provider(_error(status, kind), _ok())

    assert provider.complete("connection_test", system=None, messages=[{"role": "user", "content": "Hi"}])["text"] == "OK"
    assert len(transport.requests) == 2


def test_network_errors_are_retried():
    provider, transport = _provider(ConnectionError("offline"), _ok())

    provider.complete("connection_test", system=None, messages=[{"role": "user", "content": "Hi"}])

    assert len(transport.requests) == 2


def test_retries_stop_after_the_configured_count():
    replies = [_error(529, "overloaded_error")] * (llm_config.MAX_RETRIES + 1)
    provider, transport = _provider(*replies)

    with pytest.raises(ProviderError) as err:
        provider.complete("connection_test", system=None, messages=[{"role": "user", "content": "Hi"}])

    assert err.value.kind == "overloaded"
    assert len(transport.requests) == llm_config.MAX_RETRIES + 1


def test_retry_after_is_honoured_but_capped():
    waits = []
    transport = Transport(_error(429, "rate_limit_error", {"retry-after": "999"}), _ok())
    provider = AnthropicProvider(KEY, send=transport, sleep=waits.append)

    provider.complete("connection_test", system=None, messages=[{"role": "user", "content": "Hi"}])

    assert waits == [llm_config.MAX_RETRY_WAIT_SECONDS]


@pytest.mark.parametrize(
    "status, kind, expected",
    [(401, "authentication_error", "auth"), (403, "permission_error", "permission"), (402, "billing_error", "billing"), (400, "invalid_request_error", "bad_request")],
)
def test_client_errors_are_not_retried_and_are_named(status, kind, expected):
    provider, transport = _provider(_error(status, kind))

    with pytest.raises(ProviderError) as err:
        provider.complete("connection_test", system=None, messages=[{"role": "user", "content": "Hi"}])

    assert err.value.kind == expected
    assert len(transport.requests) == 1


def test_ac_01_errors_never_carry_the_key():
    provider, _ = _provider(_error(401, "authentication_error"))

    with pytest.raises(ProviderError) as err:
        provider.complete("connection_test", system=None, messages=[{"role": "user", "content": "Hi"}])

    assert KEY not in str(err.value)
    assert KEY not in repr(err.value)


def test_a_refusal_comes_back_as_a_result_with_its_stop_reason():
    status, headers, body = _ok(text="")
    data = json.loads(body)
    data["stop_reason"] = "refusal"
    provider, _ = _provider((status, headers, json.dumps(data).encode()))

    result = provider.complete("connection_test", system=None, messages=[{"role": "user", "content": "Hi"}])

    assert result["stop_reason"] == "refusal"
    assert result["usage"]["input_tokens"] == 12


def test_unknown_task_is_a_programming_error():
    provider, _ = _provider(_ok())

    with pytest.raises(KeyError):
        provider.complete("nonsense", system=None, messages=[])


def test_fake_provider_replays_and_records():
    fake = FakeProvider([{"text": "one"}, {"text": "two"}])

    first = fake.complete("default", system="s", messages=[{"role": "user", "content": "a"}])
    second = fake.complete("default", system="s", messages=[{"role": "user", "content": "b"}])

    assert (first["text"], second["text"]) == ("one", "two")
    assert first["usage"] == {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}
    assert [c["messages"][0]["content"] for c in fake.calls] == ["a", "b"]


def test_fake_provider_can_raise():
    fake = FakeProvider([ProviderError("auth", "The API key was rejected.")])

    with pytest.raises(ProviderError):
        fake.complete("default", system=None, messages=[])
