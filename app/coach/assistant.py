"""Connects the coach to the provider: the key, one recorded call per request.

Every call goes through run_task, so every call — successful or not — leaves a
row in coach_llm_calls with its tokens and estimated cost.
"""

from flask import current_app

from app.coach import keystore as keystores
from app.coach import llm_config
from app.coach.providers import AnthropicProvider, ProviderError
from app.coach.usage import call_cost, format_cost, summarize
from app.models import CoachLlmCall

_EMPTY_USAGE = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}


def keystore():
    return current_app.config.get("KEYSTORE") or keystores.default_keystore()


def api_key():
    try:
        return keystore().get()
    except keystores.KeystoreUnavailable:
        return None


def provider():
    key = api_key()
    if not key:
        return None
    factory = current_app.config.get("PROVIDER_FACTORY") or AnthropicProvider
    return factory(key)


def _record(db, task, provider_name, result=None, error=None):
    usage = result["usage"] if result else _EMPTY_USAGE
    model = result["model"] if result else None
    db.add(
        CoachLlmCall(
            task=task,
            provider=provider_name,
            requested_model=llm_config.TASKS[task]["model"],
            model=model,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
            # A failed request before any reply bills nothing.
            cost_usd=call_cost(model, usage) if result else 0.0,
            stop_reason=result["stop_reason"] if result else None,
            error_kind=error.kind if error else None,
            request_id=result["request_id"] if result else None,
        )
    )
    db.commit()


def run_task(db, chosen_provider, task, system, messages):
    try:
        result = chosen_provider.complete(task, system=system, messages=messages)
    except ProviderError as err:
        _record(db, task, chosen_provider.name, error=err)
        raise
    _record(db, task, chosen_provider.name, result=result)
    return result


def _usage_line(totals):
    calls = totals["calls"]
    return {
        "cost": format_cost(totals["cost_usd"]),
        "calls": f"{calls} call{'s' if calls != 1 else ''}",
        "tokens": f"{totals['input_tokens']:,} in · {totals['output_tokens']:,} out",
        "unpriced": totals["unpriced_calls"],
    }


def settings_view(db, today, status=None):
    store = keystore()
    try:
        key = store.get()
    except keystores.KeystoreUnavailable:
        key = None
    calls = [
        {
            "created_at": c.created_at,
            "input_tokens": c.input_tokens,
            "output_tokens": c.output_tokens,
            "cache_read_tokens": c.cache_read_tokens,
            "cache_write_tokens": c.cache_write_tokens,
            "cost_usd": c.cost_usd,
        }
        for c in db.query(CoachLlmCall)
    ]
    summary = summarize(calls, today)
    return {
        "available": store.available,
        "connected": bool(key),
        "masked": keystores.mask(key) if key else None,
        "message": STATUS_MESSAGES.get(status),
        "month": _usage_line(summary["month"]),
        "all": _usage_line(summary["all"]),
    }


STATUS_MESSAGES = {
    "saved": "Saved in the keychain.",
    "removed": "Key removed from the keychain.",
    "invalid": "Not saved: an API key is 20–300 characters, with no spaces, quotes or backslashes.",
    "unavailable": "Not saved: this computer has no keychain Distrava can use, and the key is never stored anywhere else.",
}
