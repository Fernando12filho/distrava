"""AI providers behind one small interface: complete(task, system, messages, tools).

The only network traffic the app makes is AnthropicProvider's HTTPS call to the
provider you chose. Plain urllib, so no SDK dependency. Tests use FakeProvider
and a conftest guard that makes `_urlopen` refuse.
"""

import json
import re
import time
import urllib.error
import urllib.request

from app.coach import llm_config

_RETRYABLE = {429: "rate_limit", 500: "server", 502: "server", 503: "server", 504: "server", 529: "overloaded"}
_FINAL = {400: "bad_request", 401: "auth", 402: "billing", 403: "permission", 404: "not_found", 413: "too_large"}
# An "error" event inside a stream that already started (no HTTP status by then).
_STREAM_ERRORS = {"overloaded_error": "overloaded", "rate_limit_error": "rate_limit", "api_error": "server"}
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


def _open_stream(url, headers, body, timeout):
    """(status, headers, lines) for a streamed reply; on an HTTP error the third item is the error body."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        response = _urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), err.read()
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise ConnectionError(str(err)) from None

    def lines():
        with response:
            for raw in response:
                yield raw.decode("utf-8").rstrip("\r\n")

    return response.status, dict(response.headers), lines()


def _read_stream(lines, on_text):
    """Rebuilds the whole reply from server-sent events, passing each piece of text
    on as it arrives. Blocks come back whole (thinking signatures included), since a
    follow-up turn must send them back unchanged."""
    message, blocks, partial_json, usage, stop_reason = {}, {}, {}, {}, None
    try:
        for line in lines:
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:].strip())
            kind, index = event["type"], event.get("index")
            if kind == "message_start":
                message = event["message"]
                usage.update(message.get("usage") or {})
            elif kind == "content_block_start":
                blocks[index] = dict(event["content_block"])
            elif kind == "content_block_delta":
                block, delta = blocks[index], event["delta"]
                if delta["type"] == "text_delta":
                    block["text"] = block.get("text", "") + delta["text"]
                    on_text(delta["text"])
                elif delta["type"] == "input_json_delta":
                    partial_json[index] = partial_json.get(index, "") + delta["partial_json"]
                elif delta["type"] == "thinking_delta":
                    block["thinking"] = block.get("thinking", "") + delta["thinking"]
                elif delta["type"] == "signature_delta":
                    block["signature"] = block.get("signature", "") + delta["signature"]
            elif kind == "content_block_stop" and index in partial_json:
                blocks[index]["input"] = json.loads(partial_json.pop(index) or "{}")
            elif kind == "message_delta":
                stop_reason = event["delta"].get("stop_reason")
                usage.update(event.get("usage") or {})
            elif kind == "error":
                raise ProviderError(_STREAM_ERRORS.get(event["error"].get("type"), "server"))
    except OSError:
        raise ProviderError("network") from None
    return {"content": [blocks[i] for i in sorted(blocks)], "model": message.get("model"), "stop_reason": stop_reason, "usage": usage}


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


def _rejection(raw):
    try:
        reason = json.loads(raw)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return None
    return f"{_MESSAGES['bad_request'].rstrip('.')}: {reason}"


def _tool_calls(content):
    return [{"id": b["id"], "name": b["name"], "input": b.get("input") or {}} for b in content if b.get("type") == "tool_use"]


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key, send=_send, sleep=time.sleep, stream=_open_stream):
        self._api_key = api_key
        self._send = send
        self._sleep = sleep
        self._stream = stream

    def __repr__(self):
        # Never the key, even in a traceback.
        return "AnthropicProvider()"

    def _request(self, task, system, messages, tools, stream=False):
        config = llm_config.TASKS[task]
        body = {
            "model": config["model"],
            "max_tokens": config["max_tokens"],
            "messages": messages,
            "output_config": {"effort": config["effort"]},
        }
        if stream:
            body["stream"] = True
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

    def complete(self, task, system, messages, tools=None, on_text=None):
        """on_text, when given, streams the reply (#43): it gets each piece of text as
        it arrives. Only errors before the stream starts are retried — after that,
        text may already be on screen."""
        requested_model, headers, body = self._request(task, system, messages, tools, stream=on_text is not None)
        send = self._stream if on_text is not None else self._send
        for attempt in range(llm_config.MAX_RETRIES + 1):
            last = attempt == llm_config.MAX_RETRIES
            try:
                status, response_headers, raw = send(llm_config.API_URL, headers, body, llm_config.TIMEOUT_SECONDS)
            except ConnectionError:
                if last:
                    raise ProviderError("network") from None
                self._sleep(_retry_wait({}, attempt))
                continue
            if status == 200:
                if on_text is not None:
                    return self._result(requested_model, response_headers, _read_stream(raw, on_text))
                return self._parse(requested_model, response_headers, raw)
            if status in _RETRYABLE and not last:
                self._sleep(_retry_wait(response_headers, attempt))
                continue
            kind = _RETRYABLE.get(status) or _FINAL.get(status, "server")
            # A 400 is our own request's fault, so the API's reason is the only
            # way to fix it; it never echoes the key header.
            raise ProviderError(kind, _rejection(raw) if kind == "bad_request" else None)
        raise ProviderError("server")  # unreachable: the last attempt returns or raises

    @classmethod
    def _parse(cls, requested_model, headers, raw):
        return cls._result(requested_model, headers, json.loads(raw))

    @staticmethod
    def _result(requested_model, headers, data):
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

    def complete(self, task, system, messages, tools=None, on_text=None):
        self.calls.append({"task": task, "system": system, "messages": messages, "tools": tools})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if on_text is not None:
            # Word by word, so streaming code is exercised with more than one piece.
            for piece in re.findall(r"\S+\s*", reply.get("text", "")):
                on_text(piece)
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
