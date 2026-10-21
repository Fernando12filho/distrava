"""What each call cost, worked out in code from the price table (an estimate)."""

from datetime import datetime

import pytest

from app.coach import llm_config
from app.coach.usage import call_cost, format_cost, summarize


def _usage(inp=0, out=0, read=0, write=0):
    return {"input_tokens": inp, "output_tokens": out, "cache_read_tokens": read, "cache_write_tokens": write}


def test_opus_cost_uses_the_per_million_prices():
    # 1M in at $4 + 1M out at $20.
    assert call_cost("claude-opus-5-5", _usage(1_000_000, 1_000_000)) == 24.0


def test_cache_reads_and_writes_have_their_own_prices():
    prices = llm_config.PRICES_PER_MTOK["claude-opus-5-5"]

    assert call_cost("claude-opus-5-5", _usage(read=1_000_000)) == prices["cache_read"]
    assert call_cost("claude-opus-5-5", _usage(write=1_000_000)) == prices["cache_write"]


def test_haiku_switches_to_long_prompt_prices_above_100k_prompt_tokens():
    short = call_cost("claude-haiku-5-5", _usage(100_000, 1_000_000))
    long = call_cost("claude-haiku-5-5", _usage(100_001, 1_000_000))

    assert short == pytest.approx(0.01 + 0.50)
    assert long == pytest.approx(100_001 * 0.50 / 1e6 + 2.50)


def test_an_unknown_model_has_no_cost_rather_than_a_guess():
    assert call_cost("some-new-model", _usage(10, 10)) is None


def test_costs_show_at_most_two_decimals():
    assert format_cost(1.23456) == "$1.23"
    assert format_cost(0.004) == "< $0.01"
    assert format_cost(0.0) == "$0.00"
    assert format_cost(None) == "unknown"


def test_summary_splits_this_month_from_all_time():
    calls = [
        {"created_at": datetime(2026, 9, 30, 23, 0), "input_tokens": 100, "output_tokens": 10, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 1.0},
        {"created_at": datetime(2026, 10, 1, 8, 0), "input_tokens": 50, "output_tokens": 5, "cache_read_tokens": 20, "cache_write_tokens": 0, "cost_usd": 0.5},
        {"created_at": datetime(2026, 10, 20, 8, 0), "input_tokens": 50, "output_tokens": 5, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": None},
    ]

    summary = summarize(calls, today=datetime(2026, 10, 21).date())

    assert summary["month"] == {"calls": 2, "input_tokens": 120, "output_tokens": 10, "cost_usd": 0.5, "unpriced_calls": 1}
    assert summary["all"] == {"calls": 3, "input_tokens": 220, "output_tokens": 20, "cost_usd": 1.5, "unpriced_calls": 1}


def test_empty_history_is_all_zero():
    empty = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "unpriced_calls": 0}

    assert summarize([], today=datetime(2026, 10, 21).date()) == {"month": empty, "all": empty}
