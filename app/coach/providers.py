"""AI providers behind one small interface: complete(task, system, messages, tools).

The only network traffic the app makes is AnthropicProvider's HTTPS call to the
provider you chose. Plain urllib, so no SDK dependency. Tests use FakeProvider
and a conftest guard that makes `_urlopen` refuse.
"""

import json
import time
import urllib.error
import urllib.request

from app.coach import llm_config

_RETRYABLE = {429: "rate_limit", 500: "server", 502: "server", 503: "server", 504: "server", 529: "overloaded"}
_FINAL = {400: "bad_request", 401: "auth", 402: "billing", 403: "permission", 404: "not_found", 413: "too_large"}
_MESSAGES = {
    "auth": "The API key was rejected. Check it in the Anthropic console.",
    "billing": "The Anthropic account needs billing set up or more credit.",
    "permission": "This API key isn't allowed to use that model.",
    "rate_limit": "Too many requests right now. Try again in a minute.",
    "overloaded": "Anthropic is busy right now. Try again shortly.",
    "server": "Anthropic had a problem answering. Try again shortly.",
    "network": "Couldn't reach Anthropic. Check the internet connection.",
    "bad_request": "The request was not accepted.",
    "not_found": "The model or endpoint was not found.",
    "too_large": "The request was too large.",
}


class ProviderError(Exception):
    def __init__(self, kind, message=None):
        self.kind = kind
        super().__init__(message or _MESSAGES.get(kind, "The AI provider returned an error."))


def _urlopen(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout)


def _send(url, headers, body, timeout):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), err.read()
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise ConnectionError(str(err)) from None


def _usage(raw):
    return {
        "input_tokens": raw.get("input_tokens") or 0,
        "output_tokens": raw.get("output_tokens") or 0,
        "cache_read_tokens": raw.get("cache_read_input_tokens") or 0,
        "cache_write_tokens": raw.get("cache_creation_input_tokens") or 0,
    }


def _retry_wait(headers, attempt):
    lowered = {k.lower(): v for k, v in headers.items()}
    try:
        wait = float(lowered["retry-after"])
    except (KeyError, ValueError):
        wait = 2.0**attempt
    return min(wait, llm_config.MAX_RETRY_WAIT_SECONDS)


def _tool_calls(content):
    return [{"id": b["id"], "name": b["name"], "input": b.get("input") or {}} for b in content if b.get("type") == "tool_use"]


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key, send=_send, sleep=time.sleep):
        self._api_key = api_key
        self._send = send
        self._sleep = sleep

    def __repr__(self):
        # Never the key, even in a traceback.
        return "AnthropicProvider()"

    def _request(self, task, system, messages, tools):
        config = llm_config.TASKS[task]
        body = {
            "model": config["model"],
            "max_tokens": config["max_tokens"],
            "messages": messages,
            "output_config": {"effort": config["effort"]},
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools
        headers = {
            "content-type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": llm_config.API_VERSION,
        }
        if config["model"] in llm_config.FALLBACK_MODELS:
            body["fallbacks"] = "default"
            headers["anthropic-beta"] = llm_config.FALLBACK_BETA
        return config["model"], headers, json.dumps(body).encode()

    def complete(self, task, system, messages, tools=None):
        requested_model, headers, body = self._request(task, system, messages, tools)
        for attempt in range(llm_config.MAX_RETRIES + 1):
            last = attempt == llm_config.MAX_RETRIES
            try:
                status, response_headers, raw = self._send(llm_config.API_URL, headers, body, llm_config.TIMEOUT_SECONDS)
            except ConnectionError:
                if last:
                    raise ProviderError("network") from None
                self._sleep(_retry_wait({}, attempt))
                continue
            if status == 200:
                return self._parse(requested_model, response_headers, raw)
            if status in _RETRYABLE and not last:
                self._sleep(_retry_wait(response_headers, attempt))
                continue
            raise ProviderError(_RETRYABLE.get(status) or _FINAL.get(status, "server"))
        raise ProviderError("server")  # unreachable: the last attempt returns or raises

    @staticmethod
    def _parse(requested_model, headers, raw):
        data = json.loads(raw)
        lowered = {k.lower(): v for k, v in headers.items()}
        content = data.get("content", [])
        return {
            "text": "".join(block.get("text", "") for block in content if block.get("type") == "text"),
            "tool_calls": _tool_calls(content),
            # Whole, thinking blocks included: a follow-up turn must send them back unchanged.
            "content": content,
            "model": data.get("model", requested_model),
            "requested_model": requested_model,
            # "refusal" is returned, not raised: the call still cost tokens.
            "stop_reason": data.get("stop_reason"),
            "request_id": lowered.get("request-id"),
            "usage": _usage(data.get("usage") or {}),
        }


class FakeProvider:
    """Replays canned replies (dicts, or ProviderErrors to raise) for tests."""

    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self._next_id = 0

    def complete(self, task, system, messages, tools=None):
        self.calls.append({"task": task, "system": system, "messages": messages, "tools": tools})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        model = reply.get("model", llm_config.TASKS[task]["model"])
        content = [{"type": "text", "text": reply["text"]}] if reply.get("text") else []
        for call in reply.get("tool_calls", []):
            self._next_id += 1
            content.append({"type": "tool_use", "id": f"toolu_fake_{self._next_id}", "name": call["name"], "input": call["input"]})
        calls = _tool_calls(content)
        return {
            "text": reply.get("text", ""),
            "tool_calls": calls,
            "content": content,
            "model": model,
            "requested_model": llm_config.TASKS[task]["model"],
            "stop_reason": reply.get("stop_reason", "tool_use" if calls else "end_turn"),
            "request_id": reply.get("request_id"),
            "usage": {**_usage({}), **reply.get("usage", {})},
        }
