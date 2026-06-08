"""Daily model-pricing refresh from the official OpenAI pricing page.

Flow (runs in a daily background job — NEVER the cost hot path):
  Tavily-extract the page -> LLM parses the STANDARD-tier per-1M rates to strict
  JSON -> every number is bounds-validated -> the model_pricing table is updated
  -> the in-memory price book reloads. compute_cost always reads the table.

This is the one fragile spot (parsing a page for money), so it is heavily guarded:
  - fetch/parse failure or implausibly few models  -> change NOTHING, alert, keep current rates
  - a KNOWN model swinging > PRICING_CHANGE_FLAG_PCT -> NOT auto-applied, flagged + alerted
  - every applied row is stamped source='openai:<date>' for audit
The in-code SEED_PRICES + the existing table remain the fallback at all times.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from config import settings
from utils.logger import logger

_PARSE_INSTRUCTION = (
    "You are extracting OpenAI API token pricing from the page content below.\n"
    "Rules:\n"
    "1. Use ONLY the STANDARD processing tier. IGNORE the Batch, Flex, and Priority tables.\n"
    "2. If a model shows 'Short context' and 'Long context' columns, use the SHORT context\n"
    "   (the base) prices.\n"
    "3. Report prices PER 1 MILLION TOKENS in USD as plain numbers (no $ or commas).\n"
    "4. Include every text/chat model and every embedding model you find.\n"
    "5. Use the EXACT model id string shown (e.g. 'gpt-5.4-mini', 'text-embedding-3-small').\n"
    "6. If a price is absent ('-' or blank, e.g. embeddings have no output/cached), use null.\n"
    "Return ONLY a JSON array, no prose, each element exactly:\n"
    '{"model": "<id>", "input_per_1m": <num|null>, "cached_input_per_1m": <num|null>, "output_per_1m": <num|null>}'
)

# The OpenAI docs page is ~50k chars with the price tables buried past a ~43k-char
# nav/TOC. Slice from the first real pricing cue so the tables are actually inside
# the window we hand the LLM (the old flat text[:24000] truncation cut them off).
_PRICING_ANCHORS = ("Prices per 1M", "| Model | Input", "## Flagship")


def _focus_pricing_text(text: str, max_chars: int = 80000) -> str:
    starts = [i for i in (text.find(a) for a in _PRICING_ANCHORS) if i != -1]
    start = min(starts) if starts else 0
    # Back up a little so the section heading/context isn't clipped.
    start = max(0, start - 200)
    return text[start:start + max_chars]

# Plausible per-1M bounds — anything outside is a parse error, not a real price.
_MIN_RATE = 0.0001
_MAX_RATE = 1000.0


def _valid_rate(x) -> bool:
    return isinstance(x, (int, float)) and _MIN_RATE <= float(x) <= _MAX_RATE


def _coerce(item: dict) -> dict | None:
    """Validate one parsed model row -> {model, input, cached_input, output} or None."""
    model = (item.get("model") or "").strip()
    inp = item.get("input_per_1m")
    # Real model ids are a single token — reject parser artifacts where a table note
    # got glued on (e.g. "o4-mini-2025-04-16 with data sharing").
    if not model or " " in model or len(model) < 2 or not _valid_rate(inp):
        return None
    inp = float(inp)
    out = item.get("output_per_1m")
    out = float(out) if _valid_rate(out) else 0.0
    cac = item.get("cached_input_per_1m")
    if _valid_rate(cac):
        cac = float(cac)
    else:
        # No cached rate parsed: text models discount ~0.5x input; embeddings (no
        # output) have no cache discount, so mirror input.
        cac = round(inp * 0.5, 6) if out > 0 else inp
    return {"model": model, "input": inp, "cached_input": cac, "output": out}


async def _parse_with_llm(text: str) -> list[dict]:
    """LLM-extract validated pricing rows from page text. Raises on hard failure."""
    from langchain_openai import ChatOpenAI

    model_name = settings.SUMMARIZATION_MODEL or "gpt-4o-mini"
    llm = ChatOpenAI(api_key=settings.OPENAI_CHATGPT, model=model_name, temperature=0)
    focused = _focus_pricing_text(text)
    resp = await llm.ainvoke(_PARSE_INSTRUCTION + "\n\nPAGE CONTENT:\n" + focused)
    content = getattr(resp, "content", None) or str(resp)
    m = re.search(r"\[.*\]", content, re.S)
    raw = json.loads(m.group(0) if m else content)
    rows = [c for c in (_coerce(i) for i in raw if isinstance(i, dict)) if c]
    return rows


async def _notify(subject: str, body: str) -> None:
    """Loud log + best-effort email (if PRICING_ALERT_EMAIL set)."""
    logger.error("[PRICING ALERT] %s: %s", subject, body)
    email = getattr(settings, "PRICING_ALERT_EMAIL", "") or ""
    if email:
        try:
            from utils.email import send_email
            await send_email(email, f"[AlignIQ] {subject}", f"<pre>{body}</pre>")
        except Exception as e:  # noqa: BLE001
            logger.warning("pricing alert email failed: %s", e)


async def refresh_openai_pricing(*, apply: bool = True, db=None) -> dict:
    """Fetch + parse + guarded-update model_pricing from the OpenAI page.

    Returns a report dict; on any failure changes nothing and returns ok=False.
    """
    import models
    from utils.web_research import tavily_extract
    from utils.llm_pricing import load_pricing_from_db

    url = settings.PRICING_PAGE_URL
    text = await tavily_extract(url)
    if not text or len(text) < 200:
        await _notify("pricing refresh: fetch failed",
                      f"Tavily extract returned no usable content for {url}. Existing rates kept.")
        return {"ok": False, "reason": "fetch_failed"}

    try:
        parsed = await _parse_with_llm(text)
    except Exception as e:  # noqa: BLE001
        await _notify("pricing refresh: parse failed",
                      f"Could not parse pricing page {url}: {e}. Existing rates kept.")
        return {"ok": False, "reason": "parse_failed", "error": str(e)}

    if len(parsed) < 3:
        await _notify("pricing refresh: implausibly few models",
                      f"Parsed only {len(parsed)} models from {url}; treating as a bad parse. Existing rates kept.")
        return {"ok": False, "reason": "too_few", "parsed": len(parsed)}

    close = False
    if db is None:
        db = models.sessionlocal()
        close = True
    try:
        existing = {r.model: r for r in db.query(models.ModelPricing).all()}
        stamp = datetime.now(timezone.utc).date().isoformat()
        applied, added, flagged = [], [], []

        for p in parsed:
            cur = existing.get(p["model"])
            if cur is None:
                added.append(p["model"])
                if apply:
                    db.add(models.ModelPricing(
                        model=p["model"], provider="openai",
                        input_per_1m=p["input"], cached_input_per_1m=p["cached_input"],
                        output_per_1m=p["output"], source=f"openai:{stamp}",
                    ))
                continue
            old = float(cur.input_per_1m or 0.0)
            if old > 0 and abs(p["input"] - old) / old > settings.PRICING_CHANGE_FLAG_PCT:
                # Big swing on a known model — likely a parse error. Hold for review.
                flagged.append({"model": p["model"], "old_input": old, "new_input": p["input"]})
                continue
            applied.append(p["model"])
            if apply:
                cur.input_per_1m = p["input"]
                cur.cached_input_per_1m = p["cached_input"]
                cur.output_per_1m = p["output"]
                cur.source = f"openai:{stamp}"

        if apply:
            db.commit()
            load_pricing_from_db(db)  # refresh the in-memory book the cost path reads

        if flagged:
            await _notify("pricing refresh: large changes held for review",
                          json.dumps(flagged, indent=2))
        logger.info("pricing refresh from OpenAI page: applied=%d added=%d flagged=%d (parsed=%d)",
                    len(applied), len(added), len(flagged), len(parsed))
        return {"ok": True, "applied": applied, "added": added, "flagged": flagged, "parsed": len(parsed)}
    finally:
        if close and db is not None:
            db.close()


def pricing_is_stale(hours: int) -> bool:
    """True if no OpenAI-sourced price row was updated within `hours` (so a refresh
    is due). True on any error / empty table so the first run always proceeds."""
    import models
    from sqlalchemy import func
    from datetime import timedelta

    db = models.sessionlocal()
    try:
        latest = (
            db.query(func.max(models.ModelPricing.updated_at))
            .filter(models.ModelPricing.source.like("openai:%"))
            .scalar()
        )
        if latest is None:
            return True
        return latest < datetime.now(timezone.utc) - timedelta(hours=hours)
    except Exception:
        return True
    finally:
        db.close()
