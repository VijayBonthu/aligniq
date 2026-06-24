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
    get_summary_report,
    update_analysis_link_with_full_report,
    list_rate_cards,
)

# Background regeneration tasks scheduled via asyncio.create_task are retained here
# so the event loop doesn't garbage-collect them mid-run.
_BG_REGEN_TASKS: set = set()


async def kickoff_regeneration(chat_history_id: str, user_id: str, db) -> dict:
    """SINGLE source of truth for regenerating a report from the pending-change queue.

    Builds the structured CRD + presales context, schedules run_full_pipeline_async
    (which branches on USE_CONTRACT_PIPELINE → the contract pipeline in prod), and
    clears the queue. Called by the REST /report/regenerate endpoint AND the chat /
    chat-with-doc-stream regenerate paths so they can NEVER diverge — the chat paths
    used to call legacy LLM section-regen and bypass the contract pipeline entirely.

    Returns the run dict (202-style). Raises HTTPException on validation failures.
    """
    import asyncio
    from fastapi import HTTPException
    from utils.chat_history import get_single_user_chat_history
    from utils.subscription import check_report_generation_limit, get_model_tier, consume_report_generation
    from database_scripts import (
        get_pending_changes, get_analysis_link, get_presales_by_id,
        create_or_reset_pipeline_run, get_pipeline_run_by_chat,
        clear_pending_changes, record_transaction, build_structured_crd,
    )

    check_report_generation_limit(user_id, db)
    model_tier = get_model_tier(user_id, db)

    chat = await get_single_user_chat_history(chat_history_id=chat_history_id, user_id=user_id, db=db)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat history not found")
    document_id = chat.get("document_id")
    if not document_id:
        raise HTTPException(status_code=400, detail="Chat is missing document_id")

    pending = await get_pending_changes(chat_history_id, db)
    if not pending:
        raise HTTPException(status_code=400, detail="No pending changes to apply. Queue a change first.")

    link = await get_analysis_link(document_id=document_id, user_id=user_id, db=db)
    if not link or not link.get("presales_id"):
        raise HTTPException(status_code=400, detail="No presales analysis linked to this chat.")
    presales_id = link["presales_id"]
    presales = await get_presales_by_id(presales_id=presales_id, user_id=user_id, db=db)
    if not presales:
        raise HTTPException(status_code=404, detail="Presales analysis not found")

    existing = await get_pipeline_run_by_chat(chat_history_id, db)
    if existing and existing["status"] in ("queued", "running"):
        return {
            "run_id": existing["run_id"], "chat_history_id": chat_history_id,
            "status": existing["status"], "current_stage": existing["current_stage"],
            "message": "Pipeline already in progress",
        }

    raw_messages = chat.get("message") or "[]"
    try:
        msgs = json.loads(raw_messages) if isinstance(raw_messages, str) else (raw_messages or [])
    except json.JSONDecodeError:
        msgs = []
    presales_brief_text = ""
    for m in reversed(msgs):
        if isinstance(m, dict) and m.get("type") == "presales_brief":
            presales_brief_text = m.get("content", "")
            break

    extracted = presales.get("extracted_requirements") or {}
    blind_spots = presales.get("blind_spots") or {}
    constraints_block = "## MANDATORY CHANGES TO APPLY (override prior analysis)\n" + "\n".join(
        f"- [{c.get('id', 'CHG')}] ({c.get('target_section', 'general')}/{c.get('change_type', 'modify')}) {c.get('user_request', '')}"
        for c in pending
    ) + "\n"
    enhanced_context = (
        constraints_block + "\n"
        "## Pre-Sales Analysis Context\n\n"
        f"### Project Summary\n{extracted.get('project_summary', 'N/A')}\n\n"
        f"### Technologies Identified\n{json.dumps(extracted.get('technologies_mentioned', []), indent=2)}\n\n"
        f"### Blind Spots & Risks Identified\n{json.dumps(blind_spots, indent=2)}\n\n"
        f"### Approved Presales Brief\n{presales_brief_text or '(brief not available — using extracted requirements only)'}\n"
    )
    title = (extracted.get("project_summary") or chat.get("title") or "Technical Analysis Report")[:100]
    crd_text = await build_structured_crd(presales_id, user_id, presales, presales_brief_text, db)

    run = await create_or_reset_pipeline_run(chat_history_id=chat_history_id, user_id=user_id, db=db)
    consume_report_generation(user_id, db, ref_id=run["run_id"])

    task = asyncio.create_task(run_full_pipeline_async(
        run_id=run["run_id"], chat_history_id=chat_history_id, user_id=user_id,
        document_id=document_id, presales_id=presales_id, document=[enhanced_context], title=title,
        applied_changes=pending, model_tier=model_tier, crd_text=crd_text,
    ))
    _BG_REGEN_TASKS.add(task)
    task.add_done_callback(_BG_REGEN_TASKS.discard)

    try:
        await record_transaction(
            chat_history_id=chat_history_id, action_type="regenerate",
            action_data={"applied_changes": pending},
            description=f"Regenerated applying {len(pending)} change(s)", db=db,
        )
        await clear_pending_changes(chat_history_id, db)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"kickoff_regeneration: failed to clear pending changes for {chat_history_id}: {e}")

    return {
        "run_id": run["run_id"], "chat_history_id": chat_history_id,
        "status": run["status"], "current_stage": run["current_stage"],
        "applied_changes": len(pending),
    }


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


def _refund_failed_run(user_id: str, run_id: str, db) -> None:
    """Give back the report unit (credits or allowance) consumed at enqueue for a
    run that failed — so a user is never charged for a report they didn't get.
    Best-effort and idempotent; must never mask the original failure."""
    try:
        from utils.subscription import refund_report_generation
        refund_report_generation(user_id, run_id, db)
    except Exception:  # noqa: BLE001 — a refund hiccup must not break the failure path
        logger.warning(f"pipeline_runner: report refund failed for run {run_id}", exc_info=True)


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
    model_tier: str = "frontier",
    crd_text: Optional[str] = None,
) -> None:
    """
    Top-level entry scheduled via BackgroundTasks. Owns its own DB session.

    `crd_text` is the structured CRD block (confirmed Q&A + accepted assumptions
    + open questions as JSON, then the approved brief). Contract path only; when
    None the document blob doubles as the CRD (legacy behavior).

    `model_tier` ('lite' free/basic | 'frontier' plus/pro) gates the report's
    smart-model spend on the contract path — set by the caller from the user's
    effective subscription tier (utils.subscription.get_model_tier).

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
            model_tier=model_tier,
            crd_text=crd_text,
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
        _refund_failed_run(user_id, run_id, db)
    except Exception as e:
        logger.error(f"pipeline_runner: run {run_id} failed: {e}", exc_info=True)
        await fail_pipeline_run(run_id, str(e), db)
        _refund_failed_run(user_id, run_id, db)
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
    model_tier: str = "frontier",
    crd_text: Optional[str] = None,
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

    # The CRD (settled Q&A/assumptions, structured) and the document (raw
    # evidence chunks) are distinct planner inputs. crd_text is built by
    # services.py from the presales questions/assumptions; when absent (older
    # callers), the document blob doubles as the CRD — the pre-split behavior.
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

    # Firm rate card for deterministic cost grounding (resolve_rates inside the
    # pipeline). Empty list (no firm / no card) ⇒ the model's estimate stands.
    rate_cards: list = []
    if firm_id:
        try:
            rate_cards = list_rate_cards(firm_id, db, active_only=True)
        except Exception as e:  # noqa: BLE001 — missing rates just means no grounding
            logger.warning(f"pipeline_runner: rate-card lookup failed for firm {firm_id}: {e}")

    # On a regeneration, evolve the prior contract instead of redesigning from
    # scratch: load the active version's stored contract and pass it + the
    # requested changes to the planner/decider. applied_changes is the regen signal.
    prior_contract = None
    if applied_changes:
        try:
            prior = await get_summary_report(chat_history_id, db)
            prior_contract = getattr(prior, "report_contract", None) if prior else None
            if prior_contract:
                logger.info(f"pipeline_runner: contract regen for {chat_history_id} — evolving prior contract")
        except Exception as e:  # noqa: BLE001 — a missing prior contract just means a fresh run
            logger.warning(f"pipeline_runner: could not load prior contract for regen {chat_history_id}: {e}")

    try:
        with use_recorder(recorder):
            result = await asyncio.wait_for(
                run_contract_pipeline(
                    document=[document_blob],
                    crd=crd_text or document_blob,
                    firm_context=firm_context,
                    prior_contract=prior_contract,
                    applied_changes=applied_changes,
                    on_stage_started=_on_started,
                    on_stage_completed=_on_completed,
                    model_tier=model_tier,
                    rate_cards=rate_cards,
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
        _refund_failed_run(user_id, run_id, db)
    except Exception as e:
        logger.error(f"pipeline_runner: contract path run {run_id} failed: {e}", exc_info=True)
        await fail_pipeline_run(run_id, str(e), db)
        _refund_failed_run(user_id, run_id, db)
    finally:
        try:
            _firm_id_ctx.reset(_firm_id_token)
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass
