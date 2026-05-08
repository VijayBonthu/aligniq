"""
LLM pricing table and cost computation.

Per 1M tokens, USD. Update when OpenAI pricing changes. cached_input is the
discounted rate OpenAI applies to tokens served from the prompt cache.
"""
from __future__ import annotations

from typing import TypedDict


class _Pricing(TypedDict):
    input: float
    cached_input: float
    output: float


PRICES_PER_1M: dict[str, _Pricing] = {
    # Verified against OpenAI pricing page; cached_input = 0.5 * input on
    # 4o-mini. Keep keys in sync with settings.GENERATING_REPORT_MODEL /
    # SUMMARIZATION_MODEL.
    "gpt-4o-mini":      {"input": 0.15,  "cached_input": 0.075, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {"input": 0.15,  "cached_input": 0.075, "output": 0.60},
    "gpt-4o":           {"input": 2.50,  "cached_input": 1.25,  "output": 10.00},
    "gpt-4.1-mini":     {"input": 0.40,  "cached_input": 0.10,  "output": 1.60},
    "gpt-4.1":          {"input": 2.00,  "cached_input": 0.50,  "output": 8.00},
    "gpt-5-mini":       {"input": 0.25,  "cached_input": 0.025, "output": 2.00},
    "gpt-5":            {"input": 1.25,  "cached_input": 0.125, "output": 10.00},
}

_FALLBACK = PRICES_PER_1M["gpt-4o-mini"]


def get_pricing(model: str) -> _Pricing:
    """Return per-1M pricing for `model`, falling back to gpt-4o-mini if unknown."""
    return PRICES_PER_1M.get(model, _FALLBACK)


def compute_cost(
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> float:
    """USD cost for a single LLM call.

    `input_tokens` is the TOTAL prompt tokens reported by the provider (cached
    + uncached). `cached_input_tokens` is the cache-read subset. We bill the
    cached subset at the discounted rate and the remainder at the full rate.
    """
    p = get_pricing(model)
    uncached = max(input_tokens - cached_input_tokens, 0)
    return (
        uncached * p["input"]
        + cached_input_tokens * p["cached_input"]
        + output_tokens * p["output"]
    ) / 1_000_000
