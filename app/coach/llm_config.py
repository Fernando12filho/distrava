"""Which model each coach task uses, how far it may go, and what tokens cost.

Spec "Token budget" §4: a small model for quick checks and extraction, the
larger one for planning and explanations — set per task here, not in code.
"""

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

TASKS = {
    # Settings → "Test connection": the cheapest call that proves the key works.
    "connection_test": {"model": "claude-haiku-5-5", "max_tokens": 256, "effort": "low"},
    "default": {"model": "claude-opus-5-5", "max_tokens": 16000, "effort": "medium"},
    # Steps 7-8a: reading a request, working the week in steps, proposing a draft.
    # The caps bound one request (AC-14); a step is one round trip to the model.
    "coach": {"model": "claude-opus-5-5", "max_tokens": 16000, "effort": "medium", "max_steps": 8, "max_cost_usd": 0.25},
}

# A declined request is re-run on another model inside the same call, chosen
# by the API from the refusal category. Not available on Haiku.
FALLBACK_MODELS = {"claude-opus-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

MAX_RETRIES = 2  # for 429, 5xx/529 and network errors
MAX_RETRY_WAIT_SECONDS = 10
TIMEOUT_SECONDS = 120

# US dollars per million tokens, from Anthropic's published prices
# (2026-10). Cache writes are the 5-minute TTL (1.25 × input); cache reads are
# the listed price, or 0.1 × input where only the multiplier is published.
PRICES_PER_MTOK = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
    "claude-haiku-5-5": {
        "input": 0.10,
        "output": 0.50,
        "cache_read": 0.01,
        "cache_write": 0.125,
        # Prompts above this many tokens are billed at the long-prompt rates.
        "long_prompt_over": 100_000,
        "long": {"input": 0.50, "output": 2.50, "cache_read": 0.05, "cache_write": 0.625},
    },
}
