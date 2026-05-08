"""
Per-call LLM telemetry recorder.

Used by every ChatOpenAI invocation in the agentic + presales pipelines and
the chat paths to capture tokens, cache-read subset, latency, and cost into
the llm_call_log table. Reads usage from langchain_core's AIMessage so it
works with both async and sync invocations.

The recorder writes synchronously: a single INSERT is microseconds against
multi-second LLM calls and gives us crash-durable telemetry. Failures here
are swallowed so a metrics outage never breaks a user-facing pipeline.
"""
from __future__ import annotations

import hashlib
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional, Iterator
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult

import models
from utils.llm_pricing import compute_cost
from utils.logger import logger


# Per-task identity for the in-flight LLM call. Set by the call-site wrapper
# so the LangChain callback (which only receives LLMResult, not the agent
# context) knows what agent/model/prompt to attribute the usage to.
_current_recorder: ContextVar[Optional["LLMCallRecorder"]] = ContextVar(
    "_current_recorder", default=None
)


def get_recorder() -> Optional["LLMCallRecorder"]:
    """Return the recorder bound for this async task, or None."""
    return _current_recorder.get()


@contextmanager
def use_recorder(recorder: Optional["LLMCallRecorder"]) -> Iterator[None]:
    """Bind a recorder for the duration of a block. Resets on exit."""
    token = _current_recorder.set(recorder)
    try:
        yield
    finally:
        _current_recorder.reset(token)


def hash_prompt(prefix: str) -> str:
    """sha256 hex of the prompt prefix (first 16 chars stored)."""
    return hashlib.sha256(prefix.encode("utf-8")).hexdigest()[:16]


def extract_usage(response: Any) -> tuple[int, int, int]:
    """
    Pull (input_tokens, cached_input_tokens, output_tokens) from a LangChain
    response. Handles AIMessage with usage_metadata (langchain-core ≥0.3)
    plus the legacy response_metadata.token_usage shape. Returns zeros if no
    usage info is present (e.g. parser-wrapped chains where the chain output
    is a dict, not an AIMessage).
    """
    msg = response
    # Some chains wrap AIMessage in a tuple/list or attach as `.message`.
    if hasattr(response, "message") and isinstance(response.message, AIMessage):
        msg = response.message

    if isinstance(msg, AIMessage):
        meta = getattr(msg, "usage_metadata", None) or {}
        if meta:
            input_tok = int(meta.get("input_tokens", 0) or 0)
            output_tok = int(meta.get("output_tokens", 0) or 0)
            details = meta.get("input_token_details") or {}
            cached = int(details.get("cache_read", 0) or 0)
            return input_tok, cached, output_tok

        rmeta = getattr(msg, "response_metadata", None) or {}
        usage = rmeta.get("token_usage") or rmeta.get("usage") or {}
        if usage:
            input_tok = int(usage.get("prompt_tokens", 0) or 0)
            output_tok = int(usage.get("completion_tokens", 0) or 0)
            details = usage.get("prompt_tokens_details") or {}
            cached = int(details.get("cached_tokens", 0) or 0)
            return input_tok, cached, output_tok

    return 0, 0, 0


@dataclass
class LLMCallRecorder:
    """
    Carries the identifiers needed to attribute LLM calls to a pipeline run
    or chat session. Threaded through agent state for pipeline calls; built
    inline for chat-path calls from the request session.
    """
    db: Any                                  # SQLAlchemy session
    pipeline_run_id: Optional[str] = None
    chat_history_id: Optional[str] = None
    presales_id: Optional[str] = None
    user_id: Optional[str] = None

    def record(
        self,
        *,
        agent_name: str,
        model: str,
        input_tokens: int,
        cached_input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        prompt_hash: Optional[str] = None,
    ) -> None:
        try:
            cost = compute_cost(model, input_tokens, cached_input_tokens, output_tokens)
            row = models.LLMCallLog(
                chat_history_id=self.chat_history_id,
                pipeline_run_id=self.pipeline_run_id,
                presales_id=self.presales_id,
                user_id=self.user_id,
                agent_name=agent_name,
                model=model,
                prompt_hash=prompt_hash,
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                cost_usd=cost,
            )
            self.db.add(row)
            self.db.commit()
        except Exception as e:
            # Telemetry must never break the request. Roll back and move on.
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"llm_metrics: failed to record call for {agent_name}: {e}")


def record_from_response(
    recorder: Optional[LLMCallRecorder],
    *,
    agent_name: str,
    model: str,
    response: Any,
    latency_ms: int,
    prompt_hash: Optional[str] = None,
) -> None:
    """Convenience: extract usage and write one row. No-op when recorder is None."""
    if recorder is None:
        return
    input_tok, cached, output_tok = extract_usage(response)
    if input_tok == 0 and output_tok == 0:
        # Chain returned a parsed dict/string, not an AIMessage. Skip silently.
        return
    recorder.record(
        agent_name=agent_name,
        model=model,
        input_tokens=input_tok,
        cached_input_tokens=cached,
        output_tokens=output_tok,
        latency_ms=latency_ms,
        prompt_hash=prompt_hash,
    )


class UsageCaptureHandler(BaseCallbackHandler):
    """
    LangChain callback that captures token usage for every LLM call inside a
    chain. Required because chains piped through parsers (JsonOutputParser,
    StrOutputParser, OutputFixingParser) discard the AIMessage before we see
    the chain output, so we can't read usage_metadata from the chain return
    value alone.

    Each `on_llm_end` records one row against the contextvar-bound recorder
    using the agent_name + model + prompt_hash this handler was constructed
    with. Multiple calls inside one chain (e.g. OutputFixingParser retries)
    each get their own row, which is what we want for cost accounting.
    """

    def __init__(self, *, agent_name: str, model: str, prompt_hash: Optional[str] = None):
        self.agent_name = agent_name
        self.model = model
        self.prompt_hash = prompt_hash
        self._starts: dict[UUID, float] = {}

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):  # type: ignore[override]
        self._starts[run_id] = time.monotonic()

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):  # type: ignore[override]
        self._starts[run_id] = time.monotonic()

    def on_llm_end(self, response: LLMResult, *, run_id, **kwargs) -> None:  # type: ignore[override]
        recorder = get_recorder()
        if recorder is None:
            self._starts.pop(run_id, None)
            return

        started = self._starts.pop(run_id, None)
        latency_ms = int((time.monotonic() - started) * 1000) if started else 0

        # langchain-openai populates llm_output["token_usage"] and the per-
        # generation .message.usage_metadata. Prefer usage_metadata since it
        # has the cache_read breakdown.
        input_tok = cached = output_tok = 0
        try:
            gens = response.generations[0] if response.generations else []
            first = gens[0] if gens else None
            msg = getattr(first, "message", None)
            if isinstance(msg, AIMessage):
                input_tok, cached, output_tok = extract_usage(msg)
        except Exception:
            pass

        if input_tok == 0 and output_tok == 0:
            usage = (response.llm_output or {}).get("token_usage") or {}
            input_tok = int(usage.get("prompt_tokens", 0) or 0)
            output_tok = int(usage.get("completion_tokens", 0) or 0)
            details = usage.get("prompt_tokens_details") or {}
            cached = int(details.get("cached_tokens", 0) or 0)

        if input_tok == 0 and output_tok == 0:
            return

        recorder.record(
            agent_name=self.agent_name,
            model=self.model,
            input_tokens=input_tok,
            cached_input_tokens=cached,
            output_tokens=output_tok,
            latency_ms=latency_ms,
            prompt_hash=self.prompt_hash,
        )


def callback_for(
    *, agent_name: str, model: str, prompt_hash: Optional[str] = None
) -> dict[str, Any]:
    """
    Build a LangChain config dict containing the usage callback. Use as:

        await chain.ainvoke(input_dict, config=callback_for(agent_name="x", model=m))

    Returns an empty config when no recorder is bound, so it's safe to pass
    unconditionally on cold paths.
    """
    if get_recorder() is None:
        return {}
    return {"callbacks": [UsageCaptureHandler(
        agent_name=agent_name, model=model, prompt_hash=prompt_hash
    )]}
