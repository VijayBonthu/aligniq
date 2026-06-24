"""Thin Tavily web-search client for the known-issues research step.

Tavily is reached over its REST API with the existing ``httpx`` dependency —
no new SDK. The single public coroutine ``tavily_search`` is intentionally
defensive: a missing key or any transport/HTTP error returns ``[]`` rather than
raising, because known-issues research is an *enrichment*. A report must still
render when Tavily is unconfigured or down.

Enable with ``ENABLE_KNOWN_ISSUES=true`` and ``TAVILY_API_KEY=...`` in the env.
"""

from __future__ import annotations

import httpx

from config import settings
from utils.logger import logger

_TAVILY_URL = "https://api.tavily.com/search"
_TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"


async def tavily_extract(url: str, *, timeout: int = 30) -> str:
    """Extract clean page content (markdown/text) for a single URL via Tavily.

    Returns '' (never raises) on missing key, blank url, non-200, or transport
    error — the pricing refresh treats an empty result as "fetch failed" and
    keeps the existing rates.
    """
    api_key = settings.TAVILY_API_KEY
    if not api_key or not (url and url.strip()):
        return ""
    payload = {"api_key": api_key, "urls": [url.strip()], "extract_depth": "advanced"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(_TAVILY_EXTRACT_URL, json=payload)
        if resp.status_code != 200:
            logger.warning(f"tavily_extract non-200 ({resp.status_code}) for {url}")
            return ""
        data = resp.json()
    except Exception as e:  # noqa: BLE001 — caller has a fallback
        logger.warning(f"tavily_extract failed for {url}: {e}")
        return ""
    results = data.get("results") or []
    if not results:
        return ""
    return results[0].get("raw_content") or ""


async def tavily_search(query: str, max_results: int = 3, *, timeout: int = 15) -> list[dict]:
    """Search the web via Tavily. Returns a list of {title, url, content} dicts.

    Returns an empty list (never raises) when:
      - no TAVILY_API_KEY is configured,
      - the query is blank,
      - Tavily returns a non-200, or
      - any transport error occurs.
    """
    api_key = settings.TAVILY_API_KEY
    if not api_key or not (query and query.strip()):
        return []

    payload = {
        "api_key": api_key,
        "query": query.strip(),
        "max_results": max_results,
        "search_depth": "advanced",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(_TAVILY_URL, json=payload)
        if resp.status_code != 200:
            logger.warning(f"tavily_search non-200 ({resp.status_code}) for query={query!r}")
            return []
        data = resp.json()
    except Exception as e:  # noqa: BLE001 — enrichment must never sink the run
        logger.warning(f"tavily_search failed for query={query!r}: {e}")
        return []

    results = []
    for r in data.get("results") or []:
        url = r.get("url")
        if not url:
            continue
        results.append({
            "title": r.get("title") or "",
            "url": url,
            "content": r.get("content") or "",
        })
    return results
