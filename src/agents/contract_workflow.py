"""Contract pipeline — plan -> decide -> parallel section writers -> judge -> stitch.

Replaces the 8-agent linear pipeline (see workflow_graph.py / agentic_workflow.py)
when settings.USE_CONTRACT_PIPELINE is true. Public entry point is
``run_contract_pipeline_async`` which pipeline_runner.py dispatches to.

Four stages in order:
  1. plan_node      — one smart-model call emits a ReportContract (structure).
  2. decide_node    — one smart-model call fills the typed decision artifacts
                      (tech stack, cost, timeline, team, feasibility verdict).
  3. write_sections — N cheap-model calls in parallel via asyncio.gather.
  4. judge_node     — one smart-model call scores sections; at most one
                      revision per section is sent back to the writer.

A LangGraph graph would be overkill here (no conditional edges, no loops);
plain sequential async with asyncio.gather inside stage 2 is the natural shape.
If a branch ever appears (e.g. skip-judge fast-path), this can be promoted to
LangGraph without changing the node functions' signatures.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain.output_parsers import OutputFixingParser

from config import settings
from utils.logger import logger
from utils.llm_metrics import hash_prompt
from utils.contract_prompts import (
    PLANNER_PROMPT,
    DECIDE_PROMPT,
    KNOWN_ISSUES_PROMPT,
    SECTION_WRITER_PROMPT,
    JUDGE_PROMPT,
)
from utils.web_research import tavily_search
from vectordb import chunking
from agents.agentic_workflow import invoke_with_timeout, llm_parser
from agents.contract import ReportContract
from agents.stitcher import render_report
from agents.tools import (
    validate_mermaid,
    validate_citations,
    validate_cost_bands,
    validate_verdict_discipline,
    research_gaps,
    reconcile_staffing_gaps,
    resolve_rates,
    sanitize_service_option_sources,
    format_prechecks_for_judge,
)


# ---------------------------------------------------------------------------
# LLM instances
# ---------------------------------------------------------------------------
# Smart model = planner + judge. Writer = cheap model. The smart model is
# behind a single config knob so flipping it to Sonnet 4.6 later is one env
# var change, not a code change.
_smart_llm = ChatOpenAI(
    api_key=settings.OPENAI_CHATGPT,
    model=settings.SMART_MODEL_NAME,
    temperature=0,
)
_writer_llm = ChatOpenAI(
    api_key=settings.OPENAI_CHATGPT,
    model=settings.GENERATING_REPORT_MODEL,
    reasoning_effort="low",
)
# Higher-effort writer for the substance-heavy sections (the recommended approach
# and the feasibility/cost narrative) — these carry the report's actual thinking,
# so they get more reasoning budget. Bulk sections stay on the cheap _writer_llm.
_writer_llm_high = ChatOpenAI(
    api_key=settings.OPENAI_CHATGPT,
    model=settings.GENERATING_REPORT_MODEL,
    reasoning_effort="high",
)
# Lite "smart" model — the cheap model standing in for the smart nodes on the
# free/basic tiers. The frontier SMART_MODEL is the single biggest per-report
# cost; gating it to plus/pro (model_tier='frontier') keeps free/basic reports
# margin-safe (COGS ~$0.65 vs ~$1.85). _resolve_smart() picks per run; the writers
# are always the cheap model regardless of tier.
_smart_llm_lite = ChatOpenAI(
    api_key=settings.OPENAI_CHATGPT,
    model=settings.GENERATING_REPORT_MODEL,
    temperature=0,
)


def _resolve_smart(model_tier: str) -> tuple[ChatOpenAI, str]:
    """Return (smart_llm, smart_model_name) for the plan/decide/known-issues/judge
    nodes. 'frontier' (plus/pro) → SMART_MODEL_NAME; anything else ('lite') → the
    cheap model. The model name is returned too so llm_call_log tags the real COGS."""
    if model_tier == "frontier":
        return _smart_llm, settings.SMART_MODEL_NAME
    return _smart_llm_lite, settings.GENERATING_REPORT_MODEL


_DEEP_REASONING_SECTIONS = {"recommended-approach", "feasibility-and-cost"}
_smart_json_parser = OutputFixingParser.from_llm(parser=JsonOutputParser(), llm=llm_parser)


_HASHES = {
    "contract_planner":      hash_prompt(PLANNER_PROMPT),
    "contract_decider":      hash_prompt(DECIDE_PROMPT),
    "contract_known_issues": hash_prompt(KNOWN_ISSUES_PROMPT),
    "contract_section_writer": hash_prompt(SECTION_WRITER_PROMPT),
    "contract_judge":        hash_prompt(JUDGE_PROMPT),
}


CONTRACT_STAGES_ORDER = ["plan", "research", "decide", "write_sections", "judge_and_finalize"]


# ---------------------------------------------------------------------------
# Evidence index — local, deterministic, no Chroma round-trip during planning.
# ---------------------------------------------------------------------------
# We chunk the document once at the top of the pipeline and assign ids
# (chunk_0, chunk_1, ...). The planner picks ids; writers look them up.
# This is the "tool, not stage" replacement for evidence_gather_agent —
# retrieval is a deterministic lookup, not an LLM reasoning step.


async def _build_evidence_index(document: list[str]) -> tuple[dict[str, str], str, str]:
    """Chunk the document and return (id->text, document_chunks_block, evidence_index_block).

    The latter two strings are pre-formatted for the planner prompt.
    """
    full_text = "\n\n".join(s for s in document if s)
    chunks = await chunking.chunk_text(text=full_text)

    by_id: dict[str, str] = {}
    chunk_lines: list[str] = []
    index_lines: list[str] = []
    for i, chunk in enumerate(chunks):
        cid = f"chunk_{i}"
        by_id[cid] = chunk
        label = chunk.strip().split("\n", 1)[0][:80] or "(no leading text)"
        chunk_lines.append(f"[{cid}] {chunk}")
        index_lines.append(f"- {cid}: {label}")

    return by_id, "\n\n".join(chunk_lines), "\n".join(index_lines)


def _evidence_block_for_section(
    evidence_pointers: list[str],
    evidence_by_id: dict[str, str],
) -> str:
    """Format the evidence chunks the writer is allowed to cite."""
    if not evidence_pointers:
        return "(no evidence chunks pinned for this section; rely on global assumptions)"
    lines: list[str] = []
    for cid in evidence_pointers:
        text = evidence_by_id.get(cid)
        if text is None:
            continue  # silently drop unknown ids — planner hallucination, writer can't cite it
        lines.append(f"--- {cid} ---\n{text}")
    return "\n\n".join(lines) if lines else "(planner pointed at chunks that do not exist)"


def _format_research_block(findings: list[dict]) -> str:
    """Format the research findings pool for the decider/writer prompts.

    Each finding is {query, url, title, snippet}. The url is the only thing the
    model may cite as a source — it is real (came from Tavily), so links are
    grounded, never invented.
    """
    if not findings:
        return "(no external research available — rely on the document + your expertise, and label expert claims as assumptions)"
    blocks: list[str] = []
    for f in findings:
        url = f.get("url", "")
        title = f.get("title", "")
        snippet = (f.get("content") or f.get("snippet") or "")[:500]
        blocks.append(f"[{title}]({url})\n{snippet}")
    return "\n\n".join(blocks)


def _format_prior_context(prior_contract: Optional[dict], applied_changes: Optional[list]) -> str:
    """Build the regeneration block: the prior contract + the requested changes.

    Present only on a regen. When absent, returns a first-run sentinel so the
    planner/decider prompts always have a concrete value to interpolate.
    """
    if not prior_contract and not applied_changes:
        return "(none — this is a first run; design from scratch)"
    parts: list[str] = []
    if applied_changes:
        parts.append("REQUESTED CHANGES (apply these; re-open only what they touch):")
        for c in applied_changes:
            if not isinstance(c, dict):
                continue
            cid = c.get("id", "CHG")
            target = c.get("target_section", "general")
            req = c.get("user_request", "")
            parts.append(f"- [{cid}] ({target}) {req}")
    if prior_contract:
        # The prior contract grounds "carry forward what the changes don't touch".
        parts.append("\nPRIOR CONTRACT (evolve this; do not restart):")
        parts.append(json.dumps(prior_contract, ensure_ascii=False)[:12000])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Node 1 — planner
# ---------------------------------------------------------------------------
async def plan_node(
    *,
    crd: str,
    firm_context: str,
    document_chunks_block: str,
    evidence_index_block: str,
    prior_context: str = "(none — this is a first run; design from scratch)",
    smart_llm: ChatOpenAI = _smart_llm,
    smart_model: str = settings.SMART_MODEL_NAME,
) -> ReportContract:
    """Smart model emits a ReportContract (structure only — decisions come later)."""
    logger.info("contract_pipeline: plan_node starting")

    chain = ChatPromptTemplate.from_template(PLANNER_PROMPT) | smart_llm | _smart_json_parser
    response = await invoke_with_timeout(
        chain,
        {
            "firm_context": firm_context or "(none)",
            "crd": crd or "(no CRD provided)",
            "document_chunks": document_chunks_block,
            "evidence_index": evidence_index_block,
            "prior_context": prior_context,
        },
        agent_name="contract_planner",
        model=smart_model,
        prompt_hash=_HASHES["contract_planner"],
    )

    if not isinstance(response, dict):
        raise ValueError(f"contract_planner: expected dict, got {type(response).__name__}")
    contract = ReportContract.model_validate(response)
    logger.info(f"contract_pipeline: plan_node produced contract with {len(contract.sections)} sections")
    return contract


# ---------------------------------------------------------------------------
# Node 1.5 — decider (solution & estimate)
# ---------------------------------------------------------------------------
# Smart model. Owns the consequential, interdependent decisions (tech stack,
# cost, timeline, team, feasibility verdict) as typed data. The arithmetic is
# the stitcher's job — this node only picks hours and rates.
_DECISION_FIELDS = (
    "approaches",
    "tech_decisions", "cost_lines", "cost_sensitivity",
    "contingency_pct", "timeline", "team", "feasibility",
    # Slice 2 — service_options ride inside tech_decisions (no separate key).
    "integration_points", "staffing_gaps",
    # Reality Gap — quote-anchored client-side understatements.
    "underplay_flags",
)


async def decide_node(
    *,
    contract: ReportContract,
    firm_context: str,
    document_chunks_block: str,
    research_block: str = "(no external research available)",
    prior_context: str = "(none — this is a first run; design from scratch)",
    smart_llm: ChatOpenAI = _smart_llm,
    smart_model: str = settings.SMART_MODEL_NAME,
) -> ReportContract:
    """Smart model fills the contract's decision artifacts. Returns the merged contract."""
    logger.info("contract_pipeline: decide_node starting")

    chain = ChatPromptTemplate.from_template(DECIDE_PROMPT) | smart_llm | _smart_json_parser
    response = await invoke_with_timeout(
        chain,
        {
            "firm_context": firm_context or "(none)",
            "contract_json": contract.model_dump_json(),
            "document_chunks": document_chunks_block,
            "research_block": research_block,
            "prior_context": prior_context,
        },
        agent_name="contract_decider",
        model=smart_model,
        prompt_hash=_HASHES["contract_decider"],
    )

    if not isinstance(response, dict):
        # Decisions are valuable but not fatal — render the report without them
        # rather than failing the whole run.
        logger.warning(
            f"contract_pipeline: decide_node returned non-dict ({type(response).__name__}); "
            "proceeding with no decision artifacts"
        )
        return contract

    merged = contract.model_dump()
    for key in _DECISION_FIELDS:
        if response.get(key) is not None:
            merged[key] = response[key]
    try:
        updated = ReportContract.model_validate(merged)
    except Exception as e:  # noqa: BLE001 — bad decision JSON should not sink the run
        logger.warning(f"contract_pipeline: decide_node output failed validation ({e}); proceeding without decisions")
        return contract

    logger.info(
        "contract_pipeline: decide_node produced "
        f"{len(updated.tech_decisions)} tech decisions, {len(updated.cost_lines)} cost lines, "
        f"{len(updated.timeline)} milestones, verdict="
        f"{updated.feasibility.verdict if updated.feasibility else 'none'}"
    )
    return updated


def _decision_context_for_section(contract: ReportContract, section_id: str) -> str:
    """Compact JSON of the decisions relevant to a section, for the writer's narrative.

    Keyed to the same anchor slugs the stitcher uses. Returns "(none)" for
    sections that don't carry decisions so the writer prompt stays clean.
    """
    if section_id == "proposed-architecture" and contract.tech_decisions:
        return "Tech stack decisions:\n" + json.dumps(
            [d.model_dump() for d in contract.tech_decisions], indent=2
        )
    if section_id == "feasibility-and-cost":
        payload: dict = {}
        if contract.cost_lines:
            payload["cost_lines"] = [c.model_dump() for c in contract.cost_lines]
        if contract.cost_sensitivity:
            payload["cost_sensitivity"] = [s.model_dump() for s in contract.cost_sensitivity]
        if contract.timeline:
            payload["timeline"] = [m.model_dump() for m in contract.timeline]
        if contract.team:
            payload["team"] = [t.model_dump() for t in contract.team]
        if contract.feasibility:
            payload["feasibility"] = contract.feasibility.model_dump()
        if payload:
            return json.dumps(payload, indent=2)
    return "(none)"


# ---------------------------------------------------------------------------
# Node 1.4 — research (Tavily-backed; flag-gated; runs after plan, before decide)
# ---------------------------------------------------------------------------
# Generalizes the known_issues retrieval from a post-decide appendix into a spine
# that grounds the WHOLE report: the planner emits research_queries aimed at the
# core_challenge, this runs them, and the findings feed the decider (approaches +
# feasibility) and the section writers. This is what lets the report speak to the
# current real world instead of only the client's document.
async def research_node(*, contract: ReportContract) -> list[dict]:
    """Run the planner's research_queries through Tavily; return a findings pool.

    Each finding is {query, url, title, content}. Inert (returns []) unless
    ENABLE_RESEARCH and a Tavily key are set. Never raises — enrichment only.
    """
    if not (settings.ENABLE_RESEARCH and settings.TAVILY_API_KEY):
        return []
    queries = [q.strip() for q in (contract.research_queries or []) if q and q.strip()]
    if not queries:
        return []
    queries = queries[: settings.RESEARCH_MAX_QUERIES]

    try:
        logger.info(f"contract_pipeline: research_node running {len(queries)} Tavily queries")
        result_lists = await asyncio.gather(*[
            tavily_search(q, max_results=settings.RESEARCH_RESULTS_PER_QUERY) for q in queries
        ])
        findings: list[dict] = []
        seen_urls: set[str] = set()
        for q, results in zip(queries, result_lists):
            for r in results:
                url = r.get("url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                findings.append({
                    "query": q,
                    "url": url,
                    "title": r.get("title", ""),
                    "content": (r.get("content") or "")[:600],
                })
        logger.info(f"contract_pipeline: research_node gathered {len(findings)} unique findings")
        return findings
    except Exception as e:  # noqa: BLE001 — research must never sink the run
        logger.warning(f"contract_pipeline: research_node error (skipping): {e}")
        return []


# ---------------------------------------------------------------------------
# Node 1.6 — known issues (Tavily-backed; flag-gated; runs inside decide stage)
# ---------------------------------------------------------------------------
def _dossier_covers(contract: ReportContract, subject: str) -> bool:
    """True when the research dossier already carries a gotcha/limit finding
    about `subject` — the known-issues pass skips it to avoid paying for the
    same research twice. Token-overlap match (a 'Power BI iframe -> Azure
    Function' seam is never a literal substring of a short claim): covered when
    ≥half of the subject's salient tokens appear in a gotcha/limit finding."""
    dossier = contract.research_dossier
    if not dossier or not subject:
        return False
    import re as _re
    tokens = [t for t in _re.findall(r"[a-z0-9]+", subject.lower()) if len(t) >= 3]
    if not tokens:
        return False
    for f in dossier.findings:
        if f.kind not in ("gotcha", "limit"):
            continue
        haystack = f"{f.claim} {f.relevance_note}".lower()
        hits = sum(1 for t in tokens if t in haystack)
        if hits and hits * 2 >= len(tokens):
            return True
    return False


def _build_known_issue_queries(contract: ReportContract, limit: int) -> list[str]:
    """Targeted queries from integration points (highest signal) then tech picks.
    Skips subjects the research dossier already covers with gotcha/limit findings."""
    queries: list[str] = []
    for ip in contract.integration_points:
        if ip and ip.strip() and not _dossier_covers(contract, ip):
            queries.append(f"known issues integrating {ip.strip()}")
    for td in contract.tech_decisions:
        if td.choice and td.choice.strip() and not _dossier_covers(contract, td.choice):
            queries.append(f"{td.choice.strip()} production gotchas known issues")
    # De-dupe preserving order, then cap.
    seen: set[str] = set()
    deduped = [q for q in queries if not (q in seen or seen.add(q))]
    return deduped[:limit]


async def known_issues_node(
    *,
    contract: ReportContract,
    smart_llm: ChatOpenAI = _smart_llm,
    smart_model: str = settings.SMART_MODEL_NAME,
) -> ReportContract:
    """Enrich the contract with web-sourced known issues. Inert unless
    ENABLE_KNOWN_ISSUES and a Tavily key are set. Never raises — enrichment only.

    Source URLs are constrained deterministically to the URLs Tavily actually
    returned; any LLM-emitted entry citing some other URL is dropped.
    """
    if not (settings.ENABLE_KNOWN_ISSUES and settings.TAVILY_API_KEY):
        return contract
    if not contract.tech_decisions and not contract.integration_points:
        return contract

    try:
        queries = _build_known_issue_queries(contract, settings.KNOWN_ISSUES_MAX_QUERIES)
        if not queries:
            return contract

        logger.info(f"contract_pipeline: known_issues_node running {len(queries)} Tavily queries")
        result_lists = await asyncio.gather(*[
            tavily_search(q, max_results=settings.KNOWN_ISSUES_RESULTS_PER_QUERY) for q in queries
        ])

        allowed_urls: set[str] = set()
        result_blocks: list[str] = []
        for q, results in zip(queries, result_lists):
            for r in results:
                allowed_urls.add(r["url"])
                snippet = (r.get("content") or "")[:600]
                result_blocks.append(f"[query: {q}]\nurl: {r['url']}\ntitle: {r.get('title','')}\n{snippet}")

        if not allowed_urls:
            logger.info("contract_pipeline: known_issues_node found no search results; skipping")
            return contract

        technologies = "\n".join(
            f"- {td.layer}: {td.choice}" for td in contract.tech_decisions
        ) or "(none)"
        integration_points = "\n".join(f"- {ip}" for ip in contract.integration_points) or "(none)"

        chain = ChatPromptTemplate.from_template(KNOWN_ISSUES_PROMPT) | smart_llm | _smart_json_parser
        response = await invoke_with_timeout(
            chain,
            {
                "technologies": technologies,
                "integration_points": integration_points,
                "search_results": "\n\n".join(result_blocks),
            },
            agent_name="contract_known_issues",
            model=smart_model,
            prompt_hash=_HASHES["contract_known_issues"],
        )

        raw_issues = response.get("known_issues") if isinstance(response, dict) else None
        if not isinstance(raw_issues, list):
            return contract

        # Deterministic guard: keep only entries citing a URL Tavily actually returned.
        kept = [
            it for it in raw_issues
            if isinstance(it, dict) and it.get("source_url") in allowed_urls
        ]
        dropped = len(raw_issues) - len(kept)
        if dropped:
            logger.warning(f"contract_pipeline: known_issues_node dropped {dropped} issue(s) with non-sourced URLs")
        if not kept:
            return contract

        merged = contract.model_dump()
        merged["known_issues"] = kept
        try:
            updated = ReportContract.model_validate(merged)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"contract_pipeline: known_issues_node merge failed validation ({e}); skipping")
            return contract

        logger.info(f"contract_pipeline: known_issues_node added {len(updated.known_issues)} sourced issue(s)")
        return updated

    except Exception as e:  # noqa: BLE001 — enrichment must never sink the run
        logger.warning(f"contract_pipeline: known_issues_node error (skipping): {e}")
        return contract


# ---------------------------------------------------------------------------
# Node 2 — parallel section writers
# ---------------------------------------------------------------------------

# Typed research routing: which dossier finding kinds each standard section
# consumes. Sections not listed (and any dossier-less run) get the full block.
_SECTION_RESEARCH_KINDS = {
    "recommended-approach":  ["capability", "prior_art", "library", "benchmark"],
    "proposed-architecture": ["capability", "limit", "library"],
    "risks-and-mitigations": ["gotcha", "limit"],
    "feasibility-and-cost":  ["benchmark", "limit"],
}


async def _write_one_section(
    *,
    contract: ReportContract,
    section_id: str,
    evidence_by_id: dict[str, str],
    firm_context: str,
    research_block: str = "(no external research available)",
    judge_note: str = "",
    previous_draft: str = "",
) -> tuple[str, str]:
    """Write or revise one section. Returns (section_id, markdown_body)."""
    section = contract.get_section(section_id)
    if section is None:
        raise KeyError(f"contract_pipeline: section_id '{section_id}' not in contract")

    # Depth Cut: when a typed dossier exists, route each section the finding
    # kinds it actually consumes (verbatim quotes + real links) instead of one
    # undifferentiated block for everyone.
    if contract.research_dossier:
        from agents.research_agent import dossier_research_block
        research_block = dossier_research_block(
            contract.research_dossier, _SECTION_RESEARCH_KINDS.get(section_id)
        )

    # Substance-heavy sections get the higher-reasoning writer; bulk sections stay cheap.
    llm = _writer_llm_high if section_id in _DEEP_REASONING_SECTIONS else _writer_llm
    chain = ChatPromptTemplate.from_template(SECTION_WRITER_PROMPT) | llm | StrOutputParser()
    body = await invoke_with_timeout(
        chain,
        {
            "section_id":          section.id,
            "section_title":       section.title,
            "writer_brief":        section.writer_brief,
            "claims_to_make":      json.dumps(section.claims_to_make),
            "rubric_focus":        json.dumps(section.rubric_focus),
            "diagrams_required":   json.dumps(section.diagrams_required),
            "rate_card_required":  str(section.rate_card_required),
            "evidence_block":      _evidence_block_for_section(section.evidence_pointers, evidence_by_id),
            "research_block":      research_block,
            "global_assumptions":  "\n".join(f"- {a}" for a in contract.global_assumptions) or "(none)",
            "firm_context":        firm_context or "(none)",
            "decision_context":    _decision_context_for_section(contract, section.id),
            "judge_note":          judge_note or "(first pass)",
            "previous_draft":      previous_draft or "(first pass)",
        },
        agent_name="contract_section_writer",
        model=settings.GENERATING_REPORT_MODEL,
        prompt_hash=_HASHES["contract_section_writer"],
    )
    return section.id, body


async def write_sections_node(
    *,
    contract: ReportContract,
    evidence_by_id: dict[str, str],
    firm_context: str,
    research_block: str = "(no external research available)",
) -> dict[str, str]:
    """Run one writer per section in parallel. Returns {section_id: markdown}."""
    logger.info(f"contract_pipeline: write_sections_node fanning out {len(contract.sections)} writers")
    results = await asyncio.gather(*[
        _write_one_section(
            contract=contract,
            section_id=section.id,
            evidence_by_id=evidence_by_id,
            firm_context=firm_context,
            research_block=research_block,
        )
        for section in contract.sections
    ])
    sections_md = dict(results)
    logger.info("contract_pipeline: write_sections_node complete")
    return sections_md


# ---------------------------------------------------------------------------
# Node 3 — judge + targeted revisions
# ---------------------------------------------------------------------------
async def judge_node(
    *,
    contract: ReportContract,
    sections_md: dict[str, str],
    evidence_by_id: dict[str, str],
    firm_context: str,
    prechecks_context: str = "",
    research_block: str = "(no external research available)",
    smart_llm: ChatOpenAI = _smart_llm,
    smart_model: str = settings.SMART_MODEL_NAME,
) -> tuple[dict[str, str], dict[str, str], dict]:
    """Smart-model judge scores sections; revise flagged ones once.

    Returns (final_sections_md, judge_notes_by_section, raw_judge_response).
    """
    logger.info("contract_pipeline: judge_node starting")

    sections_block = "\n\n".join(
        f"=== {sid} ===\n{body}" for sid, body in sections_md.items()
    )

    chain = ChatPromptTemplate.from_template(JUDGE_PROMPT) | smart_llm | _smart_json_parser
    judge_response = await invoke_with_timeout(
        chain,
        {
            "max_revisions_per_section": settings.CONTRACT_JUDGE_MAX_REVISIONS_PER_SECTION,
            "contract_json":             contract.model_dump_json(),
            "sections_block":            sections_block,
            "deterministic_prechecks":   prechecks_context or "(none — all deterministic checks passed)",
        },
        agent_name="contract_judge",
        model=smart_model,
        prompt_hash=_HASHES["contract_judge"],
    )

    if not isinstance(judge_response, dict):
        logger.warning(f"contract_pipeline: judge returned non-dict ({type(judge_response).__name__}); skipping revisions")
        return sections_md, {}, {}

    section_scores = judge_response.get("section_scores") or []
    to_revise: list[tuple[str, str]] = []
    judge_notes: dict[str, str] = {}
    for entry in section_scores:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("section_id")
        if not sid or sid not in sections_md:
            continue
        if entry.get("revise") and entry.get("revision_note"):
            to_revise.append((sid, entry["revision_note"]))
        # Keep the score-line in judge_notes so the stitcher's HTML comment is
        # informative even when no revision happened — useful for debugging.
        if entry.get("issues"):
            judge_notes[sid] = "; ".join(entry["issues"][:3])

    if not to_revise:
        logger.info("contract_pipeline: judge_node passed all sections; no revisions")
        return sections_md, judge_notes, judge_response

    logger.info(f"contract_pipeline: judge_node revising {len(to_revise)} sections in parallel")
    revised = await asyncio.gather(*[
        _write_one_section(
            contract=contract,
            section_id=sid,
            evidence_by_id=evidence_by_id,
            firm_context=firm_context,
            research_block=research_block,
            judge_note=note,
            previous_draft=sections_md[sid],
        )
        for sid, note in to_revise
    ])
    final_sections_md = dict(sections_md)
    for sid, new_body in revised:
        final_sections_md[sid] = new_body
        judge_notes[sid] = f"revised: {judge_notes.get(sid, '')}".rstrip(": ")

    return final_sections_md, judge_notes, judge_response


# ---------------------------------------------------------------------------
# Top-level runner — what pipeline_runner.py dispatches to
# ---------------------------------------------------------------------------
async def run_contract_pipeline(
    *,
    document: list[str],
    crd: str,
    firm_context: str,
    prior_contract: Optional[dict] = None,
    applied_changes: Optional[list] = None,
    on_stage_started: Optional[callable] = None,
    on_stage_completed: Optional[callable] = None,
    model_tier: str = "frontier",
    rate_cards: Optional[list[dict]] = None,
) -> dict:
    """Run all stages and stitch the final report.

    Stage callbacks are how pipeline_runner.py records progress to pipeline_runs.
    They are optional so this function is independently testable.

    `prior_contract` + `applied_changes` are present only on a regeneration: the
    planner/decider evolve the prior contract by applying the requested changes
    instead of redesigning from scratch (the "feed new answers → converge" loop).

    `model_tier` gates the plan/decide/known-issues/judge model: 'frontier'
    (plus/pro) uses SMART_MODEL_NAME; 'lite' (free/basic) uses the cheap model so
    those tiers stay margin-safe. Writers are the cheap model in either case.

    Returns:
        {
          "report_markdown": str,
          "contract": dict (ReportContract.model_dump()),
          "judge_response": dict,
        }
    """
    smart_llm, smart_model = _resolve_smart(model_tier)

    # Evidence index is built once and shared by the planner, the decider, and
    # the per-section writers (deterministic lookup, no Chroma round-trip).
    evidence_by_id, document_chunks_block, evidence_index_block = await _build_evidence_index(document)
    prior_context = _format_prior_context(prior_contract, applied_changes)

    # Stage 1 — plan (structure + the core challenge + research queries)
    if on_stage_started:
        await on_stage_started("plan")
    contract = await plan_node(
        crd=crd,
        firm_context=firm_context,
        document_chunks_block=document_chunks_block,
        evidence_index_block=evidence_index_block,
        prior_context=prior_context,
        smart_llm=smart_llm,
        smart_model=smart_model,
    )
    if on_stage_completed:
        await on_stage_completed("plan")

    # Stage 2 — research (its own visible stage). Frontier tiers run the
    # iterative deep-research agent (fan-out → reflect → full-page extracts →
    # follow-ups → typed ResearchDossier); lite tiers keep the original
    # single-pass fan-out so free/basic COGS is unchanged. Inert without
    # ENABLE_RESEARCH + a Tavily key — the report renders normally either way.
    if on_stage_started:
        await on_stage_started("research")
    dossier = None
    if model_tier == "frontier":
        from agents.research_agent import run_deep_research, dossier_research_block
        dossier = await run_deep_research(
            contract=contract, smart_llm=smart_llm, smart_model=smart_model,
        )
        if dossier and (dossier.findings or dossier.prior_art or dossier.libraries):
            contract.research_dossier = dossier
            research_block = dossier_research_block(dossier)
            # Honest gaps: mandates research could not settle become Confidence Notes.
            contract.confidence_notes.extend(
                f"Research could not settle: {u}" for u in dossier.unanswered
            )
        else:
            dossier = None  # empty dossier → fall through to the single-pass path

    if dossier is None:
        research_findings = await research_node(contract=contract)
        research_block = _format_research_block(research_findings)

        # Research-gap detection (deterministic): queries that came back with too
        # little evidence mean the related claims are NOT grounded. Tell the decider
        # now (so it lowers confidence instead of asserting), and stamp the gaps
        # into the report's Confidence Notes.
        gap_queries = research_gaps(contract.research_queries, research_findings)
        if gap_queries:
            gap_block = "\n\nRESEARCH GAPS — these queries returned little or no usable evidence; treat any related claim as an Assumption and lower its confidence:\n" + "\n".join(f"- {q}" for q in gap_queries)
            research_block = research_block + gap_block
            contract.confidence_notes.extend(
                f"External research found little or no evidence for: “{q}” — related claims rest on expert judgment, not sources."
                for q in gap_queries
            )
            logger.info(f"contract_pipeline: {len(gap_queries)} research quer(ies) returned insufficient evidence")
    if on_stage_completed:
        await on_stage_completed("research")

    # Stage 3 — decide (+ the post-decide known-issues pass; both fold into one UI stage).
    if on_stage_started:
        await on_stage_started("decide")
    contract = await decide_node(
        contract=contract,
        firm_context=firm_context,
        document_chunks_block=document_chunks_block,
        research_block=research_block,
        prior_context=prior_context,
        smart_llm=smart_llm,
        smart_model=smart_model,
    )
    contract = await known_issues_node(contract=contract, smart_llm=smart_llm, smart_model=smart_model)

    # Deterministic decider-level enforcement — the decide prompt states these
    # rules, but only a validator makes them real:
    #  - every team role marked off-roster gets a staffing_gaps entry (firm-fit),
    #  - estimate bands above the discipline ratio and hedge-verdicts are flagged
    #    as contract issues → judge context + Confidence Notes (a writer cannot
    #    prose-fix a 3x band, so these never trigger writer revisions).
    gaps_added = reconcile_staffing_gaps(contract)
    if gaps_added:
        logger.info(f"contract_pipeline: reconcile_staffing_gaps appended {gaps_added} missing gap entr(ies)")
    # Firm rate-card grounding (deterministic): overwrite the model's per-role
    # rate with the firm's own rate card and stamp the rate_card_ref, BEFORE the
    # writers run so any prose that references the cost lines sees the real
    # numbers. Roles the card doesn't cover keep their estimate + a Confidence
    # Note. No-op when the firm has no rate card loaded.
    rate_notes = resolve_rates(contract.cost_lines, rate_cards or [])
    if rate_notes:
        contract.confidence_notes.extend(rate_notes)
        logger.info(f"contract_pipeline: {len(rate_notes)} cost role(s) not on the firm rate card — market estimate kept")
    blanked = sanitize_service_option_sources(contract)
    if blanked:
        logger.info(f"contract_pipeline: blanked {blanked} service-option source_url(s) not in the dossier")
    contract_issues = validate_cost_bands(contract.cost_lines) + validate_verdict_discipline(contract.feasibility)
    if contract_issues:
        contract.confidence_notes.extend(ci.message[0].upper() + ci.message[1:] + "." for ci in contract_issues)
        logger.info(f"contract_pipeline: validators flagged {len(contract_issues)} contract-level issue(s)")

    if on_stage_completed:
        await on_stage_completed("decide")

    # Stage 3 — write sections (writers may cite the research findings as real links)
    if on_stage_started:
        await on_stage_started("write_sections")
    sections_md = await write_sections_node(
        contract=contract,
        evidence_by_id=evidence_by_id,
        firm_context=firm_context,
        research_block=research_block,
    )
    if on_stage_completed:
        await on_stage_completed("write_sections")

    # Deterministic prechecks — run between writing and judging so the judge sees
    # broken diagrams and uncited numbers as pre-failed rubric items instead of
    # re-deriving the same conclusions via LLM reasoning.
    mermaid_issues = []
    citation_issues = []
    for section in contract.sections:
        body = sections_md.get(section.id, "")
        if section.diagrams_required:
            mermaid_issues.extend(validate_mermaid(section.id, body))
        citation_issues.extend(validate_citations(section.id, body))
    prechecks_context = format_prechecks_for_judge(mermaid_issues, citation_issues, contract_issues)
    if mermaid_issues or citation_issues or contract_issues:
        logger.info(
            f"contract_pipeline: prechecks flagged {len(mermaid_issues)} mermaid + "
            f"{len(citation_issues)} citation + {len(contract_issues)} contract issue(s)"
        )

    # Stage 4 — judge + targeted revisions
    if on_stage_started:
        await on_stage_started("judge_and_finalize")
    final_sections_md, judge_notes, judge_response = await judge_node(
        contract=contract,
        sections_md=sections_md,
        evidence_by_id=evidence_by_id,
        firm_context=firm_context,
        prechecks_context=prechecks_context,
        research_block=research_block,
        smart_llm=smart_llm,
        smart_model=smart_model,
    )
    # Harvest decider-level defects the judge found (issues prefixed "DECIDER:")
    # into Confidence Notes — these are contract problems prose cannot fix, so
    # they surface honestly instead of being papered over by a writer revision.
    if isinstance(judge_response, dict):
        for entry in judge_response.get("section_scores") or []:
            if not isinstance(entry, dict):
                continue
            for issue in entry.get("issues") or []:
                if isinstance(issue, str) and issue.strip().upper().startswith("DECIDER:"):
                    note = issue.strip()[len("DECIDER:"):].strip()
                    if note and note not in contract.confidence_notes:
                        contract.confidence_notes.append(note)

    # Judge notes are a debugging aid, not client content. Only embed them (as
    # HTML comments) when DEBUG_MODE is on; otherwise they would leak into the
    # client-facing PDF. The PDF generator also strips HTML comments as a backstop.
    report_markdown = render_report(
        contract,
        final_sections_md,
        judge_notes=judge_notes if settings.DEBUG_MODE else None,
    )
    if on_stage_completed:
        await on_stage_completed("judge_and_finalize")

    return {
        "report_markdown": report_markdown,
        "contract":        contract.model_dump(),
        "judge_response":  judge_response,
    }
