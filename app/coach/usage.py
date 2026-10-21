"""What the coach's calls cost — pure arithmetic over recorded usage.

An estimate from the price table; Anthropic's console has the real bill.
"""

from app.coach.llm_config import PRICES_PER_MTOK

_FIELDS = (("input_tokens", "input"), ("output_tokens", "output"), ("cache_read_tokens", "cache_read"), ("cache_write_tokens", "cache_write"))


def call_cost(model, usage):
    prices = PRICES_PER_MTOK.get(model)
    if prices is None:
        return None
    prompt = usage["input_tokens"] + usage["cache_read_tokens"] + usage["cache_write_tokens"]
    if "long_prompt_over" in prices and prompt > prices["long_prompt_over"]:
        prices = prices["long"]
    return sum(usage[field] * prices[price] for field, price in _FIELDS) / 1_000_000


def format_cost(dollars):
    if dollars is None:
        return "unknown"
    if 0 < dollars < 0.01:
        return "< $0.01"
    return f"${dollars:.2f}"


def _totals(calls):
    return {
        "calls": len(calls),
        "input_tokens": sum(c["input_tokens"] + c["cache_read_tokens"] + c["cache_write_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "cost_usd": sum(c["cost_usd"] or 0.0 for c in calls),
        "unpriced_calls": sum(1 for c in calls if c["cost_usd"] is None),
    }


def summarize(calls, today):
    this_month = [c for c in calls if (c["created_at"].year, c["created_at"].month) == (today.year, today.month)]
    return {"month": _totals(this_month), "all": _totals(calls)}
