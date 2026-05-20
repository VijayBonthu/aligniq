"""
Tavily-backed web search tool used by the evidence-gathering agent.

The tool is exposed via the LangChain @tool decorator so it can be bound to a
ChatOpenAI instance (`llm.bind_tools([web_search])`) and invoked through the
standard tool-call loop. Outputs are JSON strings — one row per result with the
fields the evidence agent needs to render basis tags:

    {
        "status": "success" | "skipped" | "error",
        "query": "...",
        "results": [
            {"title": "...", "url": "https://...",
             "snippet": "...", "published_date": "...|null",
             "score": 0.83}
        ],
        "retrieved_at": "2026-05-14T08:30:00Z",
    }

Bookkeeping:
- A module-level call counter (`get_call_count`) lets the caller enforce the
  per-run budget defined by `settings.EVIDENCE_SEARCH_MAX_CALLS`. Call
  `reset_call_count()` once per pipeline run.
- A module-level `get_retrieved_urls()` returns the full list of URLs the tool
  actually returned during the run — used by the post-validation step to
  detect hallucinated `retrieved_url` citations.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

from config import settings
from utils.logger import logger


_call_count: int = 0
_retrieved_urls: set[str] = set()


def reset_call_count() -> None:
    """Call once at the start of a pipeline run."""
    global _call_count
    _call_count = 0
    _retrieved_urls.clear()


def get_call_count() -> int:
    return _call_count


def get_retrieved_urls() -> set[str]:
    """URLs the tool actually returned during this run (for post-validation)."""
    return set(_retrieved_urls)


def _tavily_client() -> Any | None:
    if not settings.TAVILY_API_KEY:
        return None
    try:
        from tavily import TavilyClient
    except ImportError:
        logger.warning("tavily-python is not installed; web_search disabled")
        return None
    return TavilyClient(api_key=settings.TAVILY_API_KEY)


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the public web for current, currency-sensitive facts.

    Use this tool ONLY when the answer depends on something that changes over
    time and is NOT in the customer document:
    - Current vendor pricing, tiers, or limits
    - Whether a service is deprecated or end-of-life
    - Recent CVEs, security advisories, breaking changes
    - Version compatibility between libraries
    - Regulatory or compliance updates (e.g., GDPR, HIPAA, DORA)

    Do NOT use this for general architecture knowledge — the model already
    knows that. Do NOT use it to look up the customer's own requirements —
    those come from the document.

    Args:
        query: Concrete search query. Include vendor/product name and the year
            if relevance is time-sensitive (e.g., "AWS Aurora Serverless v2
            pricing 2026", "Kafka 3.x to 4.x migration breaking changes").
        max_results: Number of results to return (1-5). Default 3.

    Returns:
        JSON string with status, query, retrieved_at, and a list of results.
        Each result has title, url, snippet, published_date, score.
    """
    global _call_count

    retrieved_at = datetime.now(timezone.utc).isoformat()

    if _call_count >= settings.EVIDENCE_SEARCH_MAX_CALLS:
        return json.dumps({
            "status": "skipped",
            "reason": "search_budget_exhausted",
            "query": query,
            "budget": settings.EVIDENCE_SEARCH_MAX_CALLS,
            "retrieved_at": retrieved_at,
            "results": [],
        })

    client = _tavily_client()
    if client is None:
        return json.dumps({
            "status": "skipped",
            "reason": "tavily_unavailable",
            "query": query,
            "retrieved_at": retrieved_at,
            "results": [],
        })

    _call_count += 1
    capped = max(1, min(int(max_results or 3), 5))

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.search,
                query=query,
                max_results=capped,
                search_depth="basic",
                include_answer=False,
            ),
            timeout=settings.EVIDENCE_SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(f"web_search timed out: query={query!r}")
        return json.dumps({
            "status": "error",
            "reason": "timeout",
            "query": query,
            "retrieved_at": retrieved_at,
            "results": [],
        })
    except Exception as e:
        logger.error(f"web_search failed: {e}")
        return json.dumps({
            "status": "error",
            "reason": str(e),
            "query": query,
            "retrieved_at": retrieved_at,
            "results": [],
        })

    raw_results = response.get("results", []) if isinstance(response, dict) else []
    formatted = []
    for r in raw_results[:capped]:
        url = r.get("url") or ""
        if url:
            _retrieved_urls.add(url)
        formatted.append({
            "title": r.get("title") or "",
            "url": url,
            "snippet": (r.get("content") or "")[:600],
            "published_date": r.get("published_date"),
            "score": r.get("score"),
        })

    return json.dumps({
        "status": "success",
        "query": query,
        "retrieved_at": retrieved_at,
        "results": formatted,
        "calls_used": _call_count,
        "budget": settings.EVIDENCE_SEARCH_MAX_CALLS,
    })
