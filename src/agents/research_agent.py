"""Iterative deep-research agent — the Depth Cut's engine.

Replaces the single-shot research pass for frontier tiers: instead of one
fan-out of snippet-truncated results, this runs the proven deep-research loop —
fan-out → reflect (pick pages to READ IN FULL + follow-up queries) → extract +
follow-up searches → synthesize — and emits a typed ResearchDossier whose every
entry cites a URL the search actually returned (entries citing anything else
are dropped mechanically, same guard as known_issues_node).

Budget knobs (config.py): RESEARCH_MAX_ROUNDS, RESEARCH_MAX_EXTRACTS,
RESEARCH_EXTRACT_CHARS, RESEARCH_MAX_FOLLOWUP_QUERIES — plus the existing
RESEARCH_MAX_QUERIES / RESEARCH_RESULTS_PER_QUERY for the round-1 fan-out.

Never raises: any failure degrades to whatever was gathered so far (worst case
an empty dossier, which callers treat as "no research" — the pre-Depth-Cut
behavior). Reused by both the pipeline research stage and the chat
`deep_research` tool.
"""

from __future__ import annotations

import asyncio
import json

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from config import settings
from utils.logger import logger
from utils.llm_metrics import hash_prompt
from utils.web_research import tavily_search, tavily_extract
from utils.contract_prompts import RESEARCH_REFLECT_PROMPT, RESEARCH_SYNTHESIS_PROMPT
from agents.contract import ReportContract, ResearchDossier

_HASHES = {
    "research_reflect":   hash_prompt(RESEARCH_REFLECT_PROMPT),
    "research_synthesis": hash_prompt(RESEARCH_SYNTHESIS_PROMPT),
}


def _mandate_queries(contract: ReportContract) -> list[str]:
    """Queries derived from the standing research mandates, beyond the planner's
    crux-targeted ones: prior art, library landscape, per-tech limits, benchmarks."""
    queries: list[str] = []
    crux_topic = (contract.core_challenge or contract.problem_statement or contract.report_title or "").strip()
    # Keep the topic phrase short enough to search well.
    topic = " ".join(crux_topic.split()[:14])
    if topic:
        queries.append(f"case study postmortem {topic}")
        queries.append(f"open source libraries tools for {topic}")
        queries.append(f"{topic} cost effort real-world")
    profile = contract.problem_profile
    if profile and profile.delivery_mode:
        queries.append(f"{profile.delivery_mode} project lessons learned {topic}"[:200])
    return queries


def _engagement_brief(contract: ReportContract) -> str:
    parts = [f"Title: {contract.report_title}"]
    if contract.problem_statement:
        parts.append(f"Problem: {contract.problem_statement}")
    if contract.problem_profile:
        p = contract.problem_profile
        parts.append(f"Problem shape: {p.delivery_mode}; dominant axes: {', '.join(p.dominant_axes) or '—'}")
    if contract.validated_requirements:
        constraints = contract.validated_requirements.get("constraints")
        if isinstance(constraints, list) and constraints:
            parts.append("Constraints: " + "; ".join(str(c) for c in constraints[:6]))
    return "\n".join(parts)


def _snippets_block(snippets: dict[str, dict]) -> str:
    if not snippets:
        return "(no results yet)"
    blocks = []
    for url, s in snippets.items():
        blocks.append(f"url: {url}\ntitle: {s.get('title', '')}\n{(s.get('content') or '')[:600]}")
    return "\n\n".join(blocks)


def _extracts_block(extracts: dict[str, str]) -> str:
    if not extracts:
        return "(no full-page extracts)"
    return "\n\n".join(f"=== {url} ===\n{text}" for url, text in extracts.items())


async def _run_searches(queries: list[str], snippets: dict[str, dict], queries_run: list[str]) -> None:
    """Run queries in parallel; merge unique-by-url results into `snippets`."""
    queries = [q.strip() for q in queries if q and q.strip() and q.strip() not in queries_run]
    if not queries:
        return
    result_lists = await asyncio.gather(*[
        tavily_search(q, max_results=settings.RESEARCH_RESULTS_PER_QUERY) for q in queries
    ])
    queries_run.extend(queries)
    for results in result_lists:
        for r in results:
            url = r.get("url")
            if url and url not in snippets:
                snippets[url] = {"title": r.get("title", ""), "content": r.get("content", "")}


def _filter_to_sources(dossier_raw: dict, allowed_urls: set[str]) -> dict:
    """Drop every entry citing a URL the search never returned. The mechanical
    guard that makes dossier citations trustworthy."""
    def _keep(items, url_key):
        kept, dropped = [], 0
        for it in items or []:
            if isinstance(it, dict) and it.get(url_key) in allowed_urls:
                kept.append(it)
            else:
                dropped += 1
        return kept, dropped

    findings, d1 = _keep(dossier_raw.get("findings"), "source_url")
    prior_art, d2 = _keep(dossier_raw.get("prior_art"), "url")
    libraries, d3 = _keep(dossier_raw.get("libraries"), "url")
    total_dropped = d1 + d2 + d3
    if total_dropped:
        logger.warning(f"research_agent: dropped {total_dropped} dossier entr(ies) citing non-consulted URLs")
    return {
        "findings": findings,
        "prior_art": prior_art,
        "libraries": libraries,
        "unanswered": [u for u in (dossier_raw.get("unanswered") or []) if isinstance(u, str)],
    }


async def run_deep_research(
    *,
    contract: ReportContract,
    smart_llm: ChatOpenAI,
    smart_model: str,
    extra_queries: list[str] | None = None,
) -> ResearchDossier:
    """Run the iterative research loop and return a typed dossier.

    `extra_queries` lets the chat `deep_research` tool aim the same agent at a
    user-named topic on top of the engagement brief.
    """
    from agents.agentic_workflow import invoke_with_timeout
    from agents.contract_workflow import _smart_json_parser  # shared OutputFixing parser

    empty = ResearchDossier()
    if not (settings.ENABLE_RESEARCH and settings.TAVILY_API_KEY):
        return empty

    snippets: dict[str, dict] = {}
    extracts: dict[str, str] = {}
    queries_run: list[str] = []
    rounds_done = 0
    brief = _engagement_brief(contract)

    try:
        # Round 1 — fan out: planner's crux queries + standing-mandate queries (+ caller's topic).
        round1 = list(contract.research_queries or [])[: settings.RESEARCH_MAX_QUERIES]
        round1 += _mandate_queries(contract)
        round1 += list(extra_queries or [])
        await _run_searches(round1, snippets, queries_run)
        rounds_done = 1
        if not snippets:
            logger.info("research_agent: round 1 returned nothing; emitting empty dossier")
            return empty

        # Rounds 2..R — reflect, extract the load-bearing pages in full, follow up.
        extract_budget = settings.RESEARCH_MAX_EXTRACTS
        while rounds_done < settings.RESEARCH_MAX_ROUNDS:
            chain = ChatPromptTemplate.from_template(RESEARCH_REFLECT_PROMPT) | smart_llm | _smart_json_parser
            reflection = await invoke_with_timeout(
                chain,
                {
                    "core_challenge": contract.core_challenge or "(not stated)",
                    "engagement_brief": brief,
                    "snippets_block": _snippets_block(snippets),
                    "queries_run": "\n".join(f"- {q}" for q in queries_run),
                    "max_extracts": extract_budget,
                    "max_followups": settings.RESEARCH_MAX_FOLLOWUP_QUERIES,
                },
                agent_name="research_reflect",
                model=smart_model,
                prompt_hash=_HASHES["research_reflect"],
            )
            if not isinstance(reflection, dict):
                break

            # Full-page extracts — only URLs we actually have snippets for.
            wanted = [u for u in (reflection.get("extract_urls") or []) if u in snippets and u not in extracts]
            wanted = wanted[:extract_budget]
            if wanted:
                texts = await asyncio.gather(*[tavily_extract(u) for u in wanted])
                for u, t in zip(wanted, texts):
                    if t:
                        extracts[u] = t[: settings.RESEARCH_EXTRACT_CHARS]
                extract_budget -= len(wanted)

            followups = [q for q in (reflection.get("followup_queries") or []) if isinstance(q, str)]
            followups = followups[: settings.RESEARCH_MAX_FOLLOWUP_QUERIES]
            if followups:
                await _run_searches(followups, snippets, queries_run)
            rounds_done += 1

            if reflection.get("done") or (not followups and (extract_budget <= 0 or not wanted)):
                break

        # Synthesize the typed dossier.
        chain = ChatPromptTemplate.from_template(RESEARCH_SYNTHESIS_PROMPT) | smart_llm | _smart_json_parser
        raw = await invoke_with_timeout(
            chain,
            {
                "core_challenge": contract.core_challenge or "(not stated)",
                "engagement_brief": brief,
                "snippets_block": _snippets_block(snippets),
                "extracts_block": _extracts_block(extracts),
            },
            agent_name="research_synthesis",
            model=smart_model,
            prompt_hash=_HASHES["research_synthesis"],
        )
        if not isinstance(raw, dict):
            logger.warning("research_agent: synthesis returned non-dict; emitting empty dossier")
            return ResearchDossier(rounds=rounds_done, queries_run=len(queries_run), sources_consulted=len(snippets))

        filtered = _filter_to_sources(raw, set(snippets.keys()))
        dossier = ResearchDossier.model_validate({
            **filtered,
            "rounds": rounds_done,
            "queries_run": len(queries_run),
            "sources_consulted": len(snippets),
        })
        logger.info(
            f"research_agent: dossier built — {len(dossier.findings)} findings, "
            f"{len(dossier.prior_art)} prior-art, {len(dossier.libraries)} libraries, "
            f"{len(dossier.unanswered)} unanswered ({rounds_done} rounds, "
            f"{len(queries_run)} queries, {len(extracts)} extracts, {len(snippets)} sources)"
        )
        return dossier

    except Exception as e:  # noqa: BLE001 — research must never sink the run
        logger.warning(f"research_agent: failed ({e}); degrading to empty dossier")
        return ResearchDossier(rounds=rounds_done, queries_run=len(queries_run), sources_consulted=len(snippets))


def dossier_research_block(dossier: ResearchDossier, kinds: list[str] | None = None) -> str:
    """Format dossier findings as the research block decide/writers consume.

    `kinds` filters findings for per-section routing (None = all). Prior art and
    libraries ride along when relevant kinds are included (or unfiltered)."""
    if not dossier or not (dossier.findings or dossier.prior_art or dossier.libraries):
        return "(no external research available — rely on the document + your expertise, and label expert claims as assumptions)"

    want = set(kinds) if kinds else None
    blocks: list[str] = []
    for f in dossier.findings:
        if want and f.kind not in want:
            continue
        quote = f' — "{f.quote}"' if f.quote else ""
        blocks.append(f"[{f.kind}] {f.claim}{quote}\nsource: [{f.source_title or f.source_url}]({f.source_url})")
    if want is None or "prior_art" in want:
        for p in dossier.prior_art:
            blocks.append(
                f"[prior_art] {p.name}: {p.what_they_did} → {p.outcome or 'outcome unstated'} "
                f"({p.applicability})\nsource: [{p.name}]({p.url})"
            )
    if want is None or "library" in want:
        for lib in dossier.libraries:
            blocks.append(f"[library] {lib.name}: {lib.purpose} {('— ' + lib.maturity_note) if lib.maturity_note else ''}\nsource: [{lib.name}]({lib.url})")
    if not blocks:
        return "(no research findings matched this section — rely on the document + your expertise, and label expert claims as assumptions)"
    return "\n\n".join(blocks)
