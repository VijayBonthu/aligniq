"""
Agents module for AlignIQ document analysis pipeline.

This module provides the LangGraph-based multi-agent pipeline for analyzing
requirements documents and generating comprehensive technical reports.

Main exports:
    - run_agent_pipeline: Main entry point for full document analysis
    - run_presales_pipeline: Fast pre-sales analysis (60-120 seconds)
    - AgentState: TypedDict for pipeline state
    - Exception classes for error handling
"""

from .workflow_graph import (
    run_agent_pipeline,
    AgentState,
    PipelineError,
    PipelineTimeoutError,
    LLMTimeoutError,
    LLMRetryExhaustedError,
    AgentOutputError,
    AgentNotFoundError
)

from .agentic_workflow import (
    main_report_summary,
    conversational_summary
)

from .presales_workflow import (
    run_presales_pipeline,
    PresalesState,
    PresalesPipelineError,
    PresalesTimeoutError,
    PresalesAgentError
)

__all__ = [
    # Main API - Full Analysis
    'run_agent_pipeline',
    'AgentState',

    # Pre-Sales API - Fast Analysis
    'run_presales_pipeline',
    'PresalesState',

    # Full Analysis Exceptions
    'PipelineError',
    'PipelineTimeoutError',
    'LLMTimeoutError',
    'LLMRetryExhaustedError',
    'AgentOutputError',
    'AgentNotFoundError',

    # Pre-Sales Exceptions
    'PresalesPipelineError',
    'PresalesTimeoutError',
    'PresalesAgentError',

    # Utilities
    'main_report_summary',
    'conversational_summary'
]
