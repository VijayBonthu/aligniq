"""
Async runner for the 9-agent full pipeline.

Wraps the compiled LangGraph from ``workflow_graph.py`` and uses
``agent.astream(stream_mode="updates")`` so each completed node updates the
``pipeline_runs`` row. The frontend polls
``GET /full-pipeline/status/{chat_history_id}`` to render per-stage progress.

Designed to run inside a FastAPI ``BackgroundTasks`` callback. The request
DB session is closed by the time we run, so this module opens its own
``sessionlocal()`` and tears it down per call.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Optional

from langchain_core.messages import AIMessage

import models
from utils.logger import logger
from config import settings
from vectordb import vector_db, chunking
from utils.chat_history import save_chat_history, save_report_version
from utils.llm_metrics import LLMCallRecorder, use_recorder
from agents.workflow_graph import agent  # compiled LangGraph
from agents.agentic_workflow import main_report_summary
from agents.firm_context import build_firm_context_block
from agents.contract_workflow import run_contract_pipeline, CONTRACT_STAGES_ORDER
from agents.tools import repair_mermaid_blocks
from database_scripts import (
    mark_stage_started,
    mark_stage_completed,
    increment_loop_count,
    complete_pipeline_run,
    fail_pipeline_run,
    persist_state_snapshot,
    get_resumable_run,
    update_analysis_link_with_full_report,
)


# Map LangGraph node names → user-facing stage names exposed to the UI.
# Keep in sync with PIPELINE_STAGES_ORDER in database_scripts.py and with
# the rows rendered by frontend_orange/src/components/pipeline/PipelineProgress.tsx.
NODE_TO_STAGE = {
    "req_analyse_node":             "requirements_analyzer",
    "amb_resolve_node":              "ambiguity_resolver",
    "validator_node":                "validator_agent",
    "solution_architectures_node":   "solution_architectures",
    "critic_node":                   "critic_agent",
    "evidence_gather_node":          "evidence_gather_agent",
    "feasibility_estimator_node":    "feasibility_estimator",
    "ba_final_report_node":          "ba_final_report_generation",
}

STAGE_ORDER = [
    "requirements_analyzer",
    "ambiguity_resolver",
    "validator_agent",
    "solution_architectures",
    "critic_agent",
    "evidence_gather_agent",
    "feasibility_estimator",
    "ba_final_report_generation",
]


def _next_stage_after(stage: str) -> Optional[str]:
    try:
        idx = STAGE_ORDER.index(stage)
        return STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else None
    except ValueError:
        return None


async def _persist_final_report(
    *,
    chat_history_id: str,
    user_id: str,
    document_id: str,
    presales_id: str,
    report_text: str,
    title: str,
    db,
    report_contract: Optional[dict] = None,
    applied_changes: Optional[list] = None,
) -> None:
    """Append the final report to chat_history, embed it, save report version,
    and mark the analysis_link as full_report_generated.

    `report_contract` is the structured ReportContract dump (contract pipeline);
    None for the legacy 8-agent path."""

    # Deterministically fix mermaid the writer left invalid (e.g. unquoted parens
    # in flowchart labels) BEFORE persisting — so the stored report, its
    # embeddings, and every client render share the same valid markdown. Covers
    # both the contract and legacy paths since this is their shared save point.
    report_text = repair_mermaid_blocks(report_text)

    # Append message to existing chat history.
    chat_record = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.chat_history_id == chat_history_id)
        .first()
    )
    existing = []
    if chat_record and chat_record.message:
        try:
            existing = json.loads(chat_record.message) if isinstance(chat_record.message, str) else (chat_record.message or [])
        except json.JSONDecodeError:
            existing = []

    updated_messages = list(existing) + [{
        "role":      "assistant",
        "content":   report_text,
        "timestamp": datetime.utcnow().isoformat(),
        "type":      "full_report",
        "selected":  True,
    }]

    await save_chat_history(
        chat={
            "chat_history_id": chat_history_id,
            "user_id":         user_id,
            "document_id":     document_id,
            "message":         updated_messages,
            "title":           title,
        },
        db=db,
    )

    # Vector embeddings for /chat-with-doc retrieval (fallback path — chat serves
    # sections/diagrams deterministically from report_content). Section-aware +
    # content_type metadata so even fuzzy search returns coherent sections.
    try:
        await vector_db.embed_report(
            markdown=report_text,
            model=settings.EMBEDDING_MODEL,
            chat_history_id=chat_history_id,
            document_id=document_id,
        )
    except Exception as e:
        # Non-fatal: chat still works without embeddings, just no fuzzy retrieval.
        logger.error(f"pipeline_runner: embedding failed for {chat_history_id}: {e}")

    # Build a human-readable changelog so each regenerated version is identifiable
    # in the Versions panel (deterministic — the changes the user actually queued).
    changes_applied = applied_changes or []
    changelog_summary = None
    if changes_applied:
        reqs = [c.get("user_request", "").strip() for c in changes_applied
                if isinstance(c, dict) and c.get("user_request")]
        reqs = [r for r in reqs if r]
        if reqs:
            head = "; ".join(reqs[:3])
            more = f" (+{len(reqs) - 3} more)" if len(reqs) > 3 else ""
            changelog_summary = f"Applied {len(reqs)} change(s): {head}{more}"
        else:
            changelog_summary = "Regenerated with changes"

    # Report version row (mirrors services.generate_full_report behavior).
    try:
        summary = await main_report_summary(main_report=report_text, version_number=1)
        await save_report_version(
            summary_report_details={
                "chat_history_id":    chat_history_id,
                "user_id":            user_id,
                "report_content":     report_text,
                "summary_report":     summary,
                "report_contract":    report_contract,
                "changes_applied":    changes_applied,
                "changelog_summary":  changelog_summary,
            },
            db=db,
        )
    except Exception as e:
        logger.error(f"pipeline_runner: save_report_version failed for {chat_history_id}: {e}")

    # Flip analysis_link to mark the project as full-report-ready.
    try:
        await update_analysis_link_with_full_report(
            presales_id=presales_id,
            chat_history_id=chat_history_id,
            db=db,
        )
    except Exception as e:
        logger.error(f"pipeline_runner: update_analysis_link failed for {chat_history_id}: {e}")


async def run_full_pipeline_async(
    *,
    run_id: str,
    chat_history_id: str,
    user_id: str,
    document_id: str,
    presales_id: str,
    document: list[str],
    title: str,
    resume_from_snapshot: Optional[dict] = None,
    applied_changes: Optional[list] = None,
) -> None:
    """
    Top-level entry scheduled via BackgroundTasks. Owns its own DB session.

    Streams per-node updates from the compiled LangGraph, persists progress to
    pipeline_runs, and on success persists the final report and marks the
    analysis link as full_report_generated.

    Bet 2.C — when `resume_from_snapshot` is provided (loaded from a previously
    failed run's `state_snapshot`), the runner hydrates the persisted state
    (req_analysis, loop_count, and the set of `completed_nodes`) into the
    initial state. The LangGraph re-walks from START, but each node wrapper
    checks `completed_nodes` and short-circuits if its own work is already done,
    so only the failing-and-after nodes actually call LLMs. This gives the
    user-visible behavior of "resume from last checkpoint" without requiring a
    LangGraph checkpointer.
    """
    db = models.sessionlocal()
    timeout = settings.PIPELINE_TIMEOUT

    # Bet 3 — look up the firm for this user and build the markdown context block
    # that every agent prompt consumes. Failure here is non-fatal: agents handle
    # an empty firm_context by falling back to generic best-practice output.
    firm_context_block = ""
    firm_id_for_run: Optional[str] = None
    if settings.ENABLE_FIRM_CONTEXT:
        try:
            firm_row = db.query(models.User).filter(models.User.user_id == user_id).first()
            firm_id_for_run = firm_row.firm_id if firm_row else None
            firm_context_block = await build_firm_context_block(firm_id_for_run, engagement_type=None, db=db)
            if firm_context_block:
                logger.info(f"pipeline_runner: firm_context loaded for run {run_id} (firm {firm_id_for_run}, {len(firm_context_block)} chars)")
        except Exception as e:
            logger.error(f"pipeline_runner: firm_context lookup failed for {user_id}: {e}")

    # Branch on USE_CONTRACT_PIPELINE before touching the legacy state shape.
    # Old path is untouched; new path uses the 4-stage plan/decide/write/judge runner.
    if settings.USE_CONTRACT_PIPELINE:
        await _run_contract_pipeline_path(
            run_id=run_id,
            chat_history_id=chat_history_id,
            user_id=user_id,
            document_id=document_id,
            presales_id=presales_id,
            document=document,
            title=title,
            firm_context=firm_context_block,
            firm_id=firm_id_for_run,
            db=db,
            applied_changes=applied_changes,
        )
        return

    initial_state: dict = {
        "document":        document,
        "req_analysis":    [],
        "loop_count":      0,
        "message":         [],
        "firm_context":    firm_context_block,
        "completed_nodes": [],
    }
    if settings.ENABLE_RESUMABLE_PIPELINE and resume_from_snapshot:
        initial_state["req_analysis"]    = list(resume_from_snapshot.get("req_analysis") or [])
        initial_state["loop_count"]      = int(resume_from_snapshot.get("loop_count") or 0)
        initial_state["completed_nodes"] = list(resume_from_snapshot.get("completed_nodes") or [])
        logger.info(
            f"pipeline_runner: resuming run {run_id} with "
            f"{len(initial_state['req_analysis'])} preserved agent outputs, "
            f"loop_count={initial_state['loop_count']}, "
            f"completed_nodes={initial_state['completed_nodes']}"
        )

    last_started_stage: Optional[str] = None
    stage_start_ts: float = 0.0
    final_state: Optional[dict] = None
    # Accumulated state for snapshotting. astream(updates) yields the node's
    # return value, which (since AgentState has no reducers) is the FULL state
    # for keys the node touched. We REPLACE rather than extend to avoid
    # duplicating req_analysis across nodes.
    snapshot_state: dict = {
        "req_analysis":    list(initial_state["req_analysis"]),
        "loop_count":      initial_state["loop_count"],
        "completed_nodes": list(initial_state["completed_nodes"]),
    }

    def _merge_into_snapshot(node_state: dict) -> None:
        if not isinstance(node_state, dict):
            return
        req = node_state.get("req_analysis")
        if isinstance(req, list):
            snapshot_state["req_analysis"] = list(req)
        lc = node_state.get("loop_count")
        if isinstance(lc, int):
            snapshot_state["loop_count"] = lc
        completed = node_state.get("completed_nodes")
        if isinstance(completed, list):
            snapshot_state["completed_nodes"] = list(completed)

    async def _stream() -> None:
        nonlocal last_started_stage, stage_start_ts, final_state

        # Mark first stage started so the UI shows "RUNNING" immediately.
        first_stage = STAGE_ORDER[0]
        await mark_stage_started(run_id, first_stage, db)
        last_started_stage = first_stage
        stage_start_ts = time.monotonic()

        async for chunk in agent.astream(initial_state, stream_mode="updates"):
            # `chunk` shape: {node_name: state_diff}
            if not isinstance(chunk, dict):
                continue
            for node_name, node_state in chunk.items():
                stage = NODE_TO_STAGE.get(node_name)
                if not stage:
                    continue

                # Mark previous stage complete (if any).
                if last_started_stage and last_started_stage == stage:
                    duration_ms = int((time.monotonic() - stage_start_ts) * 1000)
                    await mark_stage_completed(run_id, stage, duration_ms, db)
                elif last_started_stage:
                    # Out-of-order yield (rare); record completion of whatever started last.
                    duration_ms = int((time.monotonic() - stage_start_ts) * 1000)
                    await mark_stage_completed(run_id, last_started_stage, duration_ms, db)
                    await mark_stage_completed(run_id, stage, 0, db)

                # Bet 2.C — snapshot after each completed node so a failure
                # later doesn't lose the partial work. Skip the terminal node;
                # _persist_final_report owns persistence for that stage.
                if settings.ENABLE_RESUMABLE_PIPELINE and node_name != "ba_final_report_node":
                    _merge_into_snapshot(node_state)
                    try:
                        await persist_state_snapshot(
                            run_id=run_id,
                            state_subset=snapshot_state,
                            node_name=node_name,
                            db=db,
                        )
                    except Exception as e:
                        # Snapshotting is best-effort — never fail the pipeline on it.
                        logger.warning(f"pipeline_runner: persist_state_snapshot failed for {run_id}/{node_name}: {e}")

                # Bump loop counter when critic re-enters the architect.
                if stage == "critic_agent" and isinstance(node_state, dict):
                    if (node_state.get("loop_count") or 0) > 0:
                        # Loop count is also tracked in DB so the UI can show "loop 2/3".
                        # We use the model-side counter as source of truth.
                        await increment_loop_count(run_id, db)

                # Capture the final state when the terminal node completes.
                if stage == "ba_final_report_generation":
                    final_state = node_state
                    last_started_stage = None
                    continue

                # Start the next stage. For the critic→architect loop the next
                # stage is solution_architectures (loop continues), which is
                # correctly the next item in the static order only when
                # critic→evidence transition fires; for the loop case we still
                # set current_stage to solution_architectures which matches
                # what the graph is about to execute.
                next_stage = _next_stage_after(stage)
                if next_stage:
                    await mark_stage_started(run_id, next_stage, db)
                    last_started_stage = next_stage
                    stage_start_ts = time.monotonic()
                else:
                    last_started_stage = None

    recorder = LLMCallRecorder(
        db=db,
        pipeline_run_id=run_id,
        chat_history_id=chat_history_id,
        presales_id=presales_id,
        user_id=user_id,
    )

    # Bet 3 — bind firm_id into the contextvar that `firm_project_search` reads.
    # Tenant scope comes from the JWT-derived firm_row.firm_id, never from
    # LLM-supplied arguments. Reset after the run regardless of outcome.
    from utils.chat_tools import set_firm_id_context, _firm_id_ctx
    _firm_id_token = set_firm_id_context(firm_id_for_run)

    try:
        with use_recorder(recorder):
            await asyncio.wait_for(_stream(), timeout=timeout)

            if not final_state or not final_state.get("message"):
                raise RuntimeError("Pipeline finished but no final report was produced")

            last_message = final_state["message"][-1]
            report_text = last_message.content if hasattr(last_message, "content") else str(last_message)

            await _persist_final_report(
                chat_history_id=chat_history_id,
                user_id=user_id,
                document_id=document_id,
                presales_id=presales_id,
                report_text=report_text,
                title=title,
                db=db,
                applied_changes=applied_changes,
            )
        await complete_pipeline_run(run_id, db)
        logger.info(f"pipeline_runner: completed run {run_id} for chat {chat_history_id}")

    except asyncio.TimeoutError:
        logger.error(f"pipeline_runner: timeout after {timeout}s for run {run_id}")
        await fail_pipeline_run(run_id, f"Pipeline timed out after {timeout}s", db)
    except Exception as e:
        logger.error(f"pipeline_runner: run {run_id} failed: {e}", exc_info=True)
        await fail_pipeline_run(run_id, str(e), db)
    finally:
        try:
            _firm_id_ctx.reset(_firm_id_token)
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass


async def _run_contract_pipeline_path(
    *,
    run_id: str,
    chat_history_id: str,
    user_id: str,
    document_id: str,
    presales_id: str,
    document: list[str],
    title: str,
    firm_context: str,
    firm_id: Optional[str],
    db,
    applied_changes: Optional[list] = None,
) -> None:
    """Sibling of run_full_pipeline_async for USE_CONTRACT_PIPELINE=true.

    Same persistence contract (pipeline_runs rows, llm_call_log telemetry,
    final report + embeddings + analysis_link flip on success). Only the
    middle of the function differs: 4 stages instead of 8.
    """
    timeout = settings.PIPELINE_TIMEOUT
    stage_start_ts: dict[str, float] = {}

    async def _on_started(stage: str) -> None:
        stage_start_ts[stage] = time.monotonic()
        await mark_stage_started(run_id, stage, db)

    async def _on_completed(stage: str) -> None:
        started = stage_start_ts.get(stage, time.monotonic())
        duration_ms = int((time.monotonic() - started) * 1000)
        await mark_stage_completed(run_id, stage, duration_ms, db)

    # services.py merges the approved presales brief into the document blob.
    # The planner prompt treats the CRD and the raw chunks both as inputs;
    # passing the same blob to both is intentional for now — splitting CRD
    # from raw document chunks is a deferred refinement.
    document_blob = "\n\n".join(s for s in (document or []) if s) or "(empty document)"

    recorder = LLMCallRecorder(
        db=db,
        pipeline_run_id=run_id,
        chat_history_id=chat_history_id,
        presales_id=presales_id,
        user_id=user_id,
    )

    # Bind firm_id context the same way the legacy path does — the firm-project
    # tools the writers will eventually call (Step 3) read this contextvar.
    from utils.chat_tools import set_firm_id_context, _firm_id_ctx
    _firm_id_token = set_firm_id_context(firm_id)

    try:
        with use_recorder(recorder):
            result = await asyncio.wait_for(
                run_contract_pipeline(
                    document=[document_blob],
                    crd=document_blob,
                    firm_context=firm_context,
                    on_stage_started=_on_started,
                    on_stage_completed=_on_completed,
                ),
                timeout=timeout,
            )

            report_text = result["report_markdown"]
            if not report_text:
                raise RuntimeError("Contract pipeline finished but produced empty report")

            await _persist_final_report(
                chat_history_id=chat_history_id,
                user_id=user_id,
                document_id=document_id,
                presales_id=presales_id,
                report_text=report_text,
                title=title,
                db=db,
                report_contract=result.get("contract"),
                applied_changes=applied_changes,
            )

        await complete_pipeline_run(run_id, db)
        logger.info(f"pipeline_runner: contract path completed run {run_id} for chat {chat_history_id}")

    except asyncio.TimeoutError:
        logger.error(f"pipeline_runner: contract path timeout after {timeout}s for run {run_id}")
        await fail_pipeline_run(run_id, f"Pipeline timed out after {timeout}s", db)
    except Exception as e:
        logger.error(f"pipeline_runner: contract path run {run_id} failed: {e}", exc_info=True)
        await fail_pipeline_run(run_id, str(e), db)
    finally:
        try:
            _firm_id_ctx.reset(_firm_id_token)
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass
