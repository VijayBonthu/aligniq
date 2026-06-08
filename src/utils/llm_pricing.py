"""
LLM pricing book and cost computation.

Rates are per 1M tokens, USD. The in-code SEED_PRICES is the bootstrap + the
last-resort fallback; the live book (`_PRICES`) is loaded from the `model_pricing`
DB table at startup (and after the daily LiteLLM-diff job) so rates can change
without a deploy. cost is computed deterministically from whatever book is loaded —
NEVER from a live web lookup, so every historical charge is reproducible.

Concrete model ids are usually dated snapshots (e.g. gpt-4o-2024-08-06). These are
normalized to their family key (gpt-4o) before lookup — without this, a snapshot
string misses the book and silently bills at gpt-4o-mini rates (10-40x too low).
"""
from __future__ import annotations

import re
from typing import Optional, TypedDict

from utils.logger import logger


class _Pricing(TypedDict):
    input: float
    cached_input: float
    output: float


# Bootstrap seed + fallback. Mirrored into the model_pricing table on first run.
SEED_PRICES: dict[str, _Pricing] = {
    # OpenAI — verified against the OpenAI pricing page. cached_input = prompt-cache read rate.
    "gpt-4o-mini":   {"input": 0.15,  "cached_input": 0.075, "output": 0.60},
    "gpt-4o":        {"input": 2.50,  "cached_input": 1.25,  "output": 10.00},
    "gpt-4.1-mini":  {"input": 0.40,  "cached_input": 0.10,  "output": 1.60},
    "gpt-4.1":       {"input": 2.00,  "cached_input": 0.50,  "output": 8.00},
    "gpt-4.1-nano":  {"input": 0.10,  "cached_input": 0.025, "output": 0.40},
    "gpt-5-mini":    {"input": 0.25,  "cached_input": 0.025, "output": 2.00},
    "gpt-5":         {"input": 1.25,  "cached_input": 0.125, "output": 10.00},
    # OpenAI embeddings — input-only (no output / no cache discount).
    "text-embedding-3-small": {"input": 0.02, "cached_input": 0.02, "output": 0.0},
    "text-embedding-3-large": {"input": 0.13, "cached_input": 0.13, "output": 0.0},
    "text-embedding-ada-002": {"input": 0.10, "cached_input": 0.10, "output": 0.0},
    # Anthropic — APPROXIMATE public list prices. ⚠️ VERIFY before invoicing.
    "claude-haiku-4-5":  {"input": 1.00,  "cached_input": 0.10, "output": 5.00},
    "claude-sonnet-4-6": {"input": 3.00,  "cached_input": 0.30, "output": 15.00},
    "claude-opus-4-8":   {"input": 15.00, "cached_input": 1.50, "output": 75.00},
}

# Back-compat alias (older imports referenced PRICES_PER_1M).
PRICES_PER_1M = SEED_PRICES

# Live book actually used by get_pricing — starts as the seed, replaced by
# load_pricing_from_db() at startup and after the daily refresh.
_PRICES: dict[str, _Pricing] = dict(SEED_PRICES)

_FALLBACK: _Pricing = SEED_PRICES["gpt-4o-mini"]

# Models already warned about, so the log isn't spammed once per call.
_warned_unknown: set[str] = set()

# Trailing dated-snapshot suffix: -YYYY-MM-DD  or  -YYYYMMDD.
_SNAPSHOT_RE = re.compile(r"-(?:\d{4}-\d{2}-\d{2}|\d{8})$")


def normalize_model(model: str) -> str:
    """Map a concrete model id to its price-book family key.

    Exact match wins; otherwise strip a trailing dated snapshot
    (gpt-4o-2024-08-06 -> gpt-4o). Returns the input unchanged if neither applies.
    """
    if not model:
        return model
    m = model.strip()
    if m in _PRICES:
        return m
    return _SNAPSHOT_RE.sub("", m)


def get_pricing(model: str) -> _Pricing:
    """Per-1M pricing for `model`. Falls back to gpt-4o-mini LOUDLY (warn once) so
    an unpriced/frontier model can't be silently billed 10-40x too low."""
    p = _PRICES.get(model)
    if p is not None:
        return p
    base = normalize_model(model)
    if base != model:
        p = _PRICES.get(base)
        if p is not None:
            return p
    if model not in _warned_unknown:
        _warned_unknown.add(model)
        logger.warning(
            "llm_pricing: no price entry for model %r (normalized %r) — falling back "
            "to gpt-4o-mini rates. COST IS UNDERSTATED. Add it to model_pricing / SEED_PRICES.",
            model, base,
        )
    return _FALLBACK


def compute_cost(
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> float:
    """USD cost for a single LLM call.

    `input_tokens` is the TOTAL prompt tokens (cached + uncached); `cached_input_tokens`
    is the cache-read subset, billed at the discounted rate; the remainder at full rate.
    """
    p = get_pricing(model)
    uncached = max(input_tokens - cached_input_tokens, 0)
    return (
        uncached * p["input"]
        + cached_input_tokens * p["cached_input"]
        + output_tokens * p["output"]
    ) / 1_000_000


def set_price_book(prices: dict[str, _Pricing]) -> None:
    """Replace the in-memory book (used by load_pricing_from_db / the daily refresh)."""
    global _PRICES
    if prices:
        _PRICES = dict(prices)
        _warned_unknown.clear()


def seed_pricing(db) -> int:
    """Insert any SEED_PRICES rows missing from model_pricing. Returns rows added."""
    import models

    added = 0
    for name, p in SEED_PRICES.items():
        exists = db.query(models.ModelPricing).filter(models.ModelPricing.model == name).first()
        if not exists:
            db.add(models.ModelPricing(
                model=name,
                input_per_1m=p["input"],
                cached_input_per_1m=p["cached_input"],
                output_per_1m=p["output"],
                source="seed",
            ))
            added += 1
    if added:
        db.commit()
    return added


def load_pricing_from_db(db=None) -> int:
    """Load model_pricing into the in-memory book (seeding from SEED_PRICES if empty).

    Robust: on any error keeps the current (seed) book and logs. Returns model count.
    """
    import models

    close = False
    try:
        if db is None:
            db = models.sessionlocal()
            close = True
        rows = db.query(models.ModelPricing).all()
        if not rows:
            seed_pricing(db)
            rows = db.query(models.ModelPricing).all()
        book = {
            r.model: {
                "input": float(r.input_per_1m or 0.0),
                "cached_input": float(r.cached_input_per_1m or 0.0),
                "output": float(r.output_per_1m or 0.0),
            }
            for r in rows
        }
        set_price_book(book)
        logger.info("llm_pricing: loaded %d model prices from DB", len(book))
        return len(book)
    except Exception as e:
        logger.warning("llm_pricing: load_pricing_from_db failed, using seed prices: %s", e)
        return 0
    finally:
        if close and db is not None:
            db.close()


def assert_pricing_coverage() -> list[str]:
    """Warn about any configured model name not resolvable in the current book.

    Uses normalization, so a dated snapshot of a priced family counts as covered.
    Call at startup so a mis-set model surfaces immediately instead of as silently
    understated cost weeks later. Returns the missing names (empty == covered).
    """
    from config import settings

    configured = {
        getattr(settings, name, None)
        for name in (
            "GENERATING_REPORT_MODEL",
            "SUMMARIZATION_MODEL",
            "SMART_MODEL_NAME",
            "FALL_BACK_MODEL",
            "EMBEDDING_MODEL",
        )
    }
    missing = sorted(
        m for m in configured
        if m and m not in _PRICES and normalize_model(m) not in _PRICES
    )
    if missing:
        logger.warning(
            "llm_pricing: configured model(s) not in the price book — will bill at "
            "gpt-4o-mini rates: %s", ", ".join(missing),
        )
    return missing
