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
from agents.tools import validate_mermaid, validate_citations, format_prechecks_for_judge


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
_smart_json_parser = OutputFixingParser.from_llm(parser=JsonOutputParser(), llm=llm_parser)


_HASHES = {
    "contract_planner":      hash_prompt(PLANNER_PROMPT),
    "contract_decider":      hash_prompt(DECIDE_PROMPT),
    "contract_known_issues": hash_prompt(KNOWN_ISSUES_PROMPT),
    "contract_section_writer": hash_prompt(SECTION_WRITER_PROMPT),
    "contract_judge":        hash_prompt(JUDGE_PROMPT),
}


CONTRACT_STAGES_ORDER = ["plan", "decide", "write_sections", "judge_and_finalize"]


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


# ---------------------------------------------------------------------------
# Node 1 — planner
# ---------------------------------------------------------------------------
async def plan_node(
    *,
    crd: str,
    firm_context: str,
    document_chunks_block: str,
    evidence_index_block: str,
) -> ReportContract:
    """Smart model emits a ReportContract (structure only — decisions come later)."""
    logger.info("contract_pipeline: plan_node starting")

    chain = ChatPromptTemplate.from_template(PLANNER_PROMPT) | _smart_llm | _smart_json_parser
    response = await invoke_with_timeout(
        chain,
        {
            "firm_context": firm_context or "(none)",
            "crd": crd or "(no CRD provided)",
            "document_chunks": document_chunks_block,
            "evidence_index": evidence_index_block,
        },
        agent_name="contract_planner",
        model=settings.SMART_MODEL_NAME,
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
    "tech_decisions", "cost_lines", "cost_sensitivity",
    "contingency_pct", "timeline", "team", "feasibility",
    # Slice 2 — service_options ride inside tech_decisions (no separate key).
    "integration_points", "staffing_gaps",
)


async def decide_node(
    *,
    contract: ReportContract,
    firm_context: str,
    document_chunks_block: str,
) -> ReportContract:
    """Smart model fills the contract's decision artifacts. Returns the merged contract."""
    logger.info("contract_pipeline: decide_node starting")

    chain = ChatPromptTemplate.from_template(DECIDE_PROMPT) | _smart_llm | _smart_json_parser
    response = await invoke_with_timeout(
        chain,
        {
            "firm_context": firm_context or "(none)",
            "contract_json": contract.model_dump_json(),
            "document_chunks": document_chunks_block,
        },
        agent_name="contract_decider",
        model=settings.SMART_MODEL_NAME,
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
# Node 1.6 — known issues (Tavily-backed; flag-gated; runs inside decide stage)
# ---------------------------------------------------------------------------
def _build_known_issue_queries(contract: ReportContract, limit: int) -> list[str]:
    """Targeted queries from integration points (highest signal) then tech picks."""
    queries: list[str] = []
    for ip in contract.integration_points:
        if ip and ip.strip():
            queries.append(f"known issues integrating {ip.strip()}")
    for td in contract.tech_decisions:
        if td.choice and td.choice.strip():
            queries.append(f"{td.choice.strip()} production gotchas known issues")
    # De-dupe preserving order, then cap.
    seen: set[str] = set()
    deduped = [q for q in queries if not (q in seen or seen.add(q))]
    return deduped[:limit]


async def known_issues_node(*, contract: ReportContract) -> ReportContract:
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

        chain = ChatPromptTemplate.from_template(KNOWN_ISSUES_PROMPT) | _smart_llm | _smart_json_parser
        response = await invoke_with_timeout(
            chain,
            {
                "technologies": technologies,
                "integration_points": integration_points,
                "search_results": "\n\n".join(result_blocks),
            },
            agent_name="contract_known_issues",
            model=settings.SMART_MODEL_NAME,
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
async def _write_one_section(
    *,
    contract: ReportContract,
    section_id: str,
    evidence_by_id: dict[str, str],
    firm_context: str,
    judge_note: str = "",
    previous_draft: str = "",
) -> tuple[str, str]:
    """Write or revise one section. Returns (section_id, markdown_body)."""
    section = contract.get_section(section_id)
    if section is None:
        raise KeyError(f"contract_pipeline: section_id '{section_id}' not in contract")

    chain = ChatPromptTemplate.from_template(SECTION_WRITER_PROMPT) | _writer_llm | StrOutputParser()
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
) -> dict[str, str]:
    """Run one writer per section in parallel. Returns {section_id: markdown}."""
    logger.info(f"contract_pipeline: write_sections_node fanning out {len(contract.sections)} writers")
    results = await asyncio.gather(*[
        _write_one_section(
            contract=contract,
            section_id=section.id,
            evidence_by_id=evidence_by_id,
            firm_context=firm_context,
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
) -> tuple[dict[str, str], dict[str, str], dict]:
    """Smart-model judge scores sections; revise flagged ones once.

    Returns (final_sections_md, judge_notes_by_section, raw_judge_response).
    """
    logger.info("contract_pipeline: judge_node starting")

    sections_block = "\n\n".join(
        f"=== {sid} ===\n{body}" for sid, body in sections_md.items()
    )

    chain = ChatPromptTemplate.from_template(JUDGE_PROMPT) | _smart_llm | _smart_json_parser
    judge_response = await invoke_with_timeout(
        chain,
        {
            "max_revisions_per_section": settings.CONTRACT_JUDGE_MAX_REVISIONS_PER_SECTION,
            "contract_json":             contract.model_dump_json(),
            "sections_block":            sections_block,
            "deterministic_prechecks":   prechecks_context or "(none — all deterministic checks passed)",
        },
        agent_name="contract_judge",
        model=settings.SMART_MODEL_NAME,
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
    on_stage_started: Optional[callable] = None,
    on_stage_completed: Optional[callable] = None,
) -> dict:
    """Run all three stages and stitch the final report.

    Stage callbacks are how pipeline_runner.py records progress to pipeline_runs.
    They are optional so this function is independently testable.

    Returns:
        {
          "report_markdown": str,
          "contract": dict (ReportContract.model_dump()),
          "judge_response": dict,
        }
    """
    # Evidence index is built once and shared by the planner, the decider, and
    # the per-section writers (deterministic lookup, no Chroma round-trip).
    evidence_by_id, document_chunks_block, evidence_index_block = await _build_evidence_index(document)

    # Stage 1 — plan (structure)
    if on_stage_started:
        await on_stage_started("plan")
    contract = await plan_node(
        crd=crd,
        firm_context=firm_context,
        document_chunks_block=document_chunks_block,
        evidence_index_block=evidence_index_block,
    )
    if on_stage_completed:
        await on_stage_completed("plan")

    # Stage 2 — decide (tech stack, cost, timeline, team, feasibility verdict).
    # The Tavily known-issues research is a sub-step of this stage: it depends on
    # the decider's tech_decisions + integration_points and is inert when the
    # ENABLE_KNOWN_ISSUES flag / key are absent, so it adds no UI stage.
    if on_stage_started:
        await on_stage_started("decide")
    contract = await decide_node(
        contract=contract,
        firm_context=firm_context,
        document_chunks_block=document_chunks_block,
    )
    contract = await known_issues_node(contract=contract)
    if on_stage_completed:
        await on_stage_completed("decide")

    # Stage 3 — write sections
    if on_stage_started:
        await on_stage_started("write_sections")
    sections_md = await write_sections_node(
        contract=contract,
        evidence_by_id=evidence_by_id,
        firm_context=firm_context,
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
    prechecks_context = format_prechecks_for_judge(mermaid_issues, citation_issues)
    if mermaid_issues or citation_issues:
        logger.info(
            f"contract_pipeline: prechecks flagged {len(mermaid_issues)} mermaid + "
            f"{len(citation_issues)} citation issue(s)"
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
    )
    report_markdown = render_report(contract, final_sections_md, judge_notes=judge_notes)
    if on_stage_completed:
        await on_stage_completed("judge_and_finalize")

    return {
        "report_markdown": report_markdown,
        "contract":        contract.model_dump(),
        "judge_response":  judge_response,
    }
