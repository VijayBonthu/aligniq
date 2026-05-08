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
from database_scripts import (
    mark_stage_started,
    mark_stage_completed,
    increment_loop_count,
    complete_pipeline_run,
    fail_pipeline_run,
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
) -> None:
    """Append the final report to chat_history, embed it, save report version,
    and mark the analysis_link as full_report_generated."""

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

    # Vector embeddings for /chat-with-doc retrieval.
    try:
        chunks = await chunking.chunk_text(text=report_text)
        await vector_db.create_embeddings(
            texts=chunks,
            model=settings.EMBEDDING_MODEL,
            chat_history_id=chat_history_id,
        )
    except Exception as e:
        # Non-fatal: chat still works without embeddings, just no retrieval.
        logger.error(f"pipeline_runner: embedding failed for {chat_history_id}: {e}")

    # Report version row (mirrors services.generate_full_report behavior).
    try:
        summary = await main_report_summary(main_report=report_text, version_number=1)
        await save_report_version(
            summary_report_details={
                "chat_history_id": chat_history_id,
                "user_id":         user_id,
                "report_content":  report_text,
                "summary_report":  summary,
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
) -> None:
    """
    Top-level entry scheduled via BackgroundTasks. Owns its own DB session.

    Streams per-node updates from the compiled LangGraph, persists progress to
    pipeline_runs, and on success persists the final report and marks the
    analysis link as full_report_generated.
    """
    db = models.sessionlocal()
    timeout = settings.PIPELINE_TIMEOUT
    initial_state = {
        "document":     document,
        "req_analysis": [],
        "loop_count":   0,
        "message":      [],
    }

    last_started_stage: Optional[str] = None
    stage_start_ts: float = 0.0
    final_state: Optional[dict] = None

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
            db.close()
        except Exception:
            pass
