#!/usr/bin/env python
"""Daily model-pricing review feed.

Diffs the `model_pricing` table against the LiteLLM community price dataset
(an authoritative, STRUCTURED source — not a web scrape). By design this is a
REVIEW gate, not an auto-updater: pricing is money, so a human confirms.

    python scripts/refresh_model_pricing.py            # report drift only (exit 1 if any)
    python scripts/refresh_model_pricing.py --apply    # write new rates into model_pricing
    python scripts/refresh_model_pricing.py --json      # machine-readable diff for alerting

Wire it to OS cron / the /schedule skill once a day. Default run never touches the
billing rates — it just tells you "OpenAI changed gpt-5" so you can apply deliberately.

Why not fetch rates live in the cost path? Determinism + auditability: every historical
charge must be reproducible, and an LLM/web-parsed number can silently mischarge.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

# Make `import models` / `utils.*` work when run from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
# How much relative change counts as drift (ignore float noise).
_EPS = 1e-9


def _per_1m(entry: dict, key: str) -> float | None:
    """LiteLLM stores USD-per-token; convert to per-1M. None if absent."""
    v = entry.get(key)
    return round(v * 1_000_000, 6) if isinstance(v, (int, float)) else None


def fetch_litellm() -> dict:
    req = urllib.request.Request(LITELLM_URL, headers={"User-Agent": "aligniq-pricing-feed"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh / diff the model_pricing table.")
    ap.add_argument("--source", choices=["litellm", "openai"], default="litellm",
                    help="litellm: diff vs the LiteLLM dataset. openai: Tavily-extract the official OpenAI page.")
    ap.add_argument("--apply", action="store_true", help="write new rates into model_pricing")
    ap.add_argument("--json", action="store_true", help="emit machine-readable diff")
    args = ap.parse_args()

    # OpenAI official page via Tavily (the primary production source).
    if args.source == "openai":
        import asyncio
        from utils.pricing_feed import refresh_openai_pricing
        report = asyncio.run(refresh_openai_pricing(apply=args.apply))
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1

    import models
    from utils.llm_pricing import SEED_PRICES, load_pricing_from_db

    try:
        data = fetch_litellm()
    except Exception as e:
        print(f"ERROR: could not fetch LiteLLM dataset: {e}", file=sys.stderr)
        return 2

    db = models.sessionlocal()
    try:
        try:
            rows = db.query(models.ModelPricing).all()
        except Exception:
            db.rollback()
            rows = []  # table not created yet — compare against the in-code seed
        if not rows:
            # Nothing seeded yet — compare against the in-code seed so the feed is
            # still useful before the app's first startup seeds the table.
            current = {m: dict(p) for m, p in SEED_PRICES.items()}
        else:
            current = {
                r.model: {"input": r.input_per_1m, "cached_input": r.cached_input_per_1m, "output": r.output_per_1m}
                for r in rows
            }

        drift, unmatched = [], []
        for model, cur in current.items():
            entry = data.get(model)
            if not entry:
                unmatched.append(model)
                continue
            new = {
                "input": _per_1m(entry, "input_cost_per_token"),
                "cached_input": _per_1m(entry, "cache_read_input_token_cost"),
                "output": _per_1m(entry, "output_cost_per_token"),
            }
            changed = {
                k: {"old": cur.get(k), "new": new[k]}
                for k in ("input", "cached_input", "output")
                if new[k] is not None and abs((new[k] or 0) - (cur.get(k) or 0)) > _EPS
            }
            if changed:
                drift.append({"model": model, "changes": changed})

        if args.json:
            print(json.dumps({"drift": drift, "unmatched": unmatched}, indent=2))
        else:
            if not drift:
                print(f"OK: {len(current)} models match LiteLLM. "
                      f"Unmatched (no LiteLLM entry): {unmatched or 'none'}")
            else:
                print(f"DRIFT in {len(drift)} model(s) vs LiteLLM:")
                for d in drift:
                    for k, ch in d["changes"].items():
                        print(f"  {d['model']:<28} {k:<13} {ch['old']} -> {ch['new']} (per 1M)")
                if unmatched:
                    print(f"Unmatched (no LiteLLM entry, left as-is): {unmatched}")

        if args.apply and drift:
            from datetime import datetime, timezone
            stamp = datetime.now(timezone.utc).date().isoformat()
            for d in drift:
                row = db.query(models.ModelPricing).filter(models.ModelPricing.model == d["model"]).first()
                if not row:
                    continue
                for k, ch in d["changes"].items():
                    col = {"input": "input_per_1m", "cached_input": "cached_input_per_1m", "output": "output_per_1m"}[k]
                    setattr(row, col, ch["new"])
                row.source = f"litellm:{stamp}"
            db.commit()
            print(f"APPLIED {len(drift)} update(s). Restart the app or call load_pricing_from_db() to load.")
            return 0

        # Non-zero on drift so a cron job surfaces it for review.
        return 1 if drift else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
