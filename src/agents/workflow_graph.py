from typing_extensions import TypedDict, List, Union, Optional
from typing import Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from .agentic_workflow import (
    requirements_analyzer,
    ambiguity_resolver,
    validator_agent,
    midway_report,
    solution_architect,
    critic_agent,
    evidence_gather_agent,
    feasibility_estimator,
    ba_final_report_generation,
    PipelineError,
    LLMTimeoutError,
    LLMRetryExhaustedError,
    AgentOutputError
)
from langchain_core.messages import AIMessage, HumanMessage
import asyncio
from utils.writing_to_file import write_to_file
from utils.logger import logger
from config import settings


# Re-export exceptions for use by services.py
__all__ = [
    'run_agent_pipeline',
    'AgentState',
    'PipelineError',
    'LLMTimeoutError',
    'LLMRetryExhaustedError',
    'AgentOutputError',
    'PipelineTimeoutError',
    'AgentNotFoundError'
]


class PipelineTimeoutError(PipelineError):
    """Raised when the entire pipeline times out"""
    pass


class AgentNotFoundError(PipelineError):
    """Raised when required agent output is not found in state"""
    pass


def get_agent_output(state: dict, agent_name: str, required: bool = True) -> Optional[dict]:
    """
    Safely retrieve agent output from state.

    Args:
        state: The AgentState dictionary
        agent_name: Name of the agent to retrieve output for
        required: If True, raises exception when not found

    Returns:
        The agent output dict, or None if not found and not required

    Raises:
        AgentNotFoundError: If required=True and agent not found
    """
    result = next(
        (item["output"] for item in state.get('req_analysis', []) if item.get('agent') == agent_name),
        None
    )

    if result is None and required:
        raise AgentNotFoundError(f"Required agent output '{agent_name}' not found in state")

    return result


def update_or_append(state: dict, agent_name: str, response: dict) -> None:
    """
    Update existing agent output or append new one to state.

    Args:
        state: The AgentState dictionary
        agent_name: Name of the agent
        response: The agent's response to store
    """
    for i, item in enumerate(state['req_analysis']):
        if item.get('agent') == agent_name:
            state['req_analysis'][i]['output'] = response
            logger.debug(f"Updated existing output for agent: {agent_name}")
            return
    # If agent not found, append it
    state['req_analysis'].append({"agent": agent_name, "output": response})
    logger.debug(f"Appended new output for agent: {agent_name}")

class AgentState(TypedDict):
    """
    State object passed through the LangGraph pipeline.

    Attributes:
        document: List of document strings to analyze
        req_analysis: List of agent outputs, each with 'agent' name and 'output' data
        loop_count: Counter for critic feedback loops
        message: List of AI/Human messages for conversation history
    """
    document: list[str]
    req_analysis: List[dict]
    loop_count: int
    message: List[Union[AIMessage, HumanMessage]]


async def req_analyse_node(state: AgentState) -> AgentState:
    """Requirements analysis node - first step in pipeline."""
    logger.info("Starting req_analyse_node")
    try:
        response = await requirements_analyzer(state['document'])
        update_or_append(state, "requirements_analyzer", response)
        logger.info("req_analyse_node completed successfully")
        return state
    except PipelineError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in req_analyse_node: {str(e)}")
        raise PipelineError(f"Requirements analysis failed: {str(e)}")


async def amb_resolve_node(state: AgentState) -> AgentState:
    """Ambiguity resolution node - identifies and resolves ambiguities."""
    logger.info("Starting amb_resolve_node")
    try:
        req_analyze_json = get_agent_output(state, "requirements_analyzer", required=True)
        raw_document = state["document"]
        process_flow = req_analyze_json.get("process_flow", "N/A") if isinstance(req_analyze_json, dict) else "N/A"
        org_policies = state.get("org_policies", "N/A")

        response = await ambiguity_resolver(
            req_analyzer_json=req_analyze_json,
            raw_document=raw_document,
            process_flow=process_flow,
            org_policies=org_policies
        )

        update_or_append(state, "ambiguity_resolver", response)
        logger.info("amb_resolve_node completed successfully")
        return state
    except PipelineError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in amb_resolve_node: {str(e)}")
        raise PipelineError(f"Ambiguity resolution failed: {str(e)}")


async def validator_node(state: AgentState) -> AgentState:
    """Validator node - validates requirements for consistency."""
    logger.info("Starting validator_node")
    try:
        requirements = get_agent_output(state, "requirements_analyzer", required=True)
        assumptions = get_agent_output(state, "ambiguity_resolver", required=True)

        response = await validator_agent(req_analyzer_json=requirements, amb_resolver_json=assumptions)

        update_or_append(state, "validator_agent", response)
        logger.info("validator_node completed successfully")
        return state
    except PipelineError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in validator_node: {str(e)}")
        raise PipelineError(f"Validation failed: {str(e)}")


async def midway_report_node(state: AgentState) -> AgentState:
    """Midway report node - generates intermediate progress report."""
    logger.info("Starting midway_report_node")
    try:
        requirements = get_agent_output(state, "requirements_analyzer", required=True)
        assumptions = get_agent_output(state, "ambiguity_resolver", required=True)
        validators = get_agent_output(state, "validator_agent", required=True)

        response = await midway_report(
            req_analyzer_json=requirements,
            amb_resolver_json=assumptions,
            validator_json=validators
        )

        state['message'].append(AIMessage(content=response))
        logger.info("midway_report_node completed successfully")
        return state
    except PipelineError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in midway_report_node: {str(e)}")
        raise PipelineError(f"Midway report generation failed: {str(e)}")


async def solution_architectures_node(state: AgentState) -> AgentState:
    """Solution architecture node - designs technical solution."""
    logger.info("Starting solution_architectures_node")
    try:
        requirements = get_agent_output(state, "requirements_analyzer", required=True)
        amb_resolver_json = get_agent_output(state, "ambiguity_resolver", required=True)
        validators = get_agent_output(state, "validator_agent", required=True)
        # Critic feedback is optional on first pass
        critic_feedback = get_agent_output(state, "critic_agent", required=False) or "N/A"

        response = await solution_architect(
            req_analyzer_json=requirements,
            amb_resolver_json=amb_resolver_json,
            validator_json=validators,
            critic_feedback=critic_feedback
        )

        update_or_append(state, "solution_architectures", response)
        logger.info("solution_architectures_node completed successfully")
        return state
    except PipelineError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in solution_architectures_node: {str(e)}")
        raise PipelineError(f"Solution architecture design failed: {str(e)}")


async def evidence_gather_node(state: AgentState) -> AgentState:
    """Evidence gathering node - collects supporting evidence and best practices."""
    logger.info("Starting evidence_gather_node")
    try:
        requirements = get_agent_output(state, "requirements_analyzer", required=True)
        validators = get_agent_output(state, "validator_agent", required=True)
        sol_architecture = get_agent_output(state, "solution_architectures", required=True)

        response = await evidence_gather_agent(
            recommendations_json=requirements,
            validated_requirements_json=validators,
            solution_architectures=sol_architecture
        )

        update_or_append(state, "evidence_gather_agent", response)
        logger.info("evidence_gather_node completed successfully")
        return state
    except PipelineError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in evidence_gather_node: {str(e)}")
        raise PipelineError(f"Evidence gathering failed: {str(e)}")


async def critic_node(state: AgentState) -> AgentState:
    """Critic node - critiques solution and identifies issues."""
    logger.info("Starting critic_node")
    try:
        requirements = get_agent_output(state, "requirements_analyzer", required=True)
        validators = get_agent_output(state, "validator_agent", required=True)
        solution_architectures = get_agent_output(state, "solution_architectures", required=True)
        # Previous feedback is optional
        previous_critic_feedback = get_agent_output(state, "critic_agent", required=False) or "N/A"

        response = await critic_agent(
            req_analyzer_json=requirements,
            validator_json=validators,
            solution_architectures_json=solution_architectures,
            previous_critic_feedback=previous_critic_feedback
        )

        update_or_append(state, "critic_agent", response)

        state["loop_count"] = state.get("loop_count", 0) + 1
        logger.info(f"critic_node completed successfully, loop_count={state['loop_count']}")
        return state
    except PipelineError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in critic_node: {str(e)}")
        raise PipelineError(f"Critic analysis failed: {str(e)}")


def critic_to_alternative_loop(state: AgentState) -> str:
    """
    Conditional edge function - decides whether to loop back for improvements.

    Returns:
        "continue_loop" if major blockers exist and under loop limit
        "end_loop" otherwise
    """
    try:
        critic_feedback = get_agent_output(state, "critic_agent", required=True)
        loop_back_required = critic_feedback.get("major_blockers", False) if isinstance(critic_feedback, dict) else False

        current_loop = state.get("loop_count", 0)

        if loop_back_required and current_loop < 3:
            logger.info(f"Critic found major blockers, looping back (loop {current_loop}/3)")
            return "continue_loop"
        else:
            if current_loop >= 3:
                logger.info(f"Max loop count reached ({current_loop}), proceeding to evidence gathering")
            else:
                logger.info("No major blockers found, proceeding to evidence gathering")
            state["loop_count"] = 0
            return "end_loop"
    except Exception as e:
        logger.warning(f"Error in critic_to_alternative_loop: {str(e)}, defaulting to end_loop")
        return "end_loop"


async def feasibility_estimator_node(state: AgentState) -> AgentState:
    """Feasibility estimator node - estimates timeline and resources."""
    logger.info("Starting feasibility_estimator_node")
    try:
        requirements = get_agent_output(state, "requirements_analyzer", required=True)
        validators = get_agent_output(state, "validator_agent", required=True)
        solution_architectures = get_agent_output(state, "solution_architectures", required=True)
        evidence_gathered = get_agent_output(state, "evidence_gather_agent", required=True)

        response = await feasibility_estimator(
            req_analyzer_json=requirements,
            validator_json=validators,
            solution_architectures_json=solution_architectures,
            evidence_gather_json=evidence_gathered
        )

        update_or_append(state, "feasibility_estimator", response)
        logger.info("feasibility_estimator_node completed successfully")

        # Debug output - only in debug mode
        if settings.DEBUG_MODE:
            try:
                await write_to_file("output/state_data.json", str(state))
                logger.debug("Debug: Wrote state data to output/state_data.json")
            except Exception as e:
                logger.warning(f"Debug file write failed (non-critical): {str(e)}")

        return state
    except PipelineError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in feasibility_estimator_node: {str(e)}")
        raise PipelineError(f"Feasibility estimation failed: {str(e)}")


async def ba_final_report_node(state: AgentState) -> AgentState:
    """Final report node - generates comprehensive BA report."""
    logger.info("Starting ba_final_report_node")
    try:
        requirements = get_agent_output(state, "requirements_analyzer", required=True)
        validators = get_agent_output(state, "validator_agent", required=True)
        ambiguity_resolver_json = get_agent_output(state, "ambiguity_resolver", required=True)
        solution_architectures = get_agent_output(state, "solution_architectures", required=True)
        critic_feedback_json = get_agent_output(state, "critic_agent", required=True)
        evidence_gathered = get_agent_output(state, "evidence_gather_agent", required=True)
        feasibility_json = get_agent_output(state, "feasibility_estimator", required=True)

        response = await ba_final_report_generation(
            requirements_json=requirements,
            validated_requirements=validators,
            ambiguity_resolutions=ambiguity_resolver_json,
            solution_architectures=solution_architectures,
            critic_feedback=critic_feedback_json,
            evidence=evidence_gathered,
            feasibility=feasibility_json
        )

        state['message'].append(AIMessage(content=response))
        logger.info("ba_final_report_node completed successfully")

        # Debug output - only in debug mode
        if settings.DEBUG_MODE:
            try:
                await write_to_file("output/final_report.md", str(state["message"][-1].content))
                logger.debug("Debug: Wrote final report to output/final_report.md")
            except Exception as e:
                logger.warning(f"Debug file write failed (non-critical): {str(e)}")

        return state
    except PipelineError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in ba_final_report_node: {str(e)}")
        raise PipelineError(f"Final report generation failed: {str(e)}")
    

# =============================================================================
# GRAPH DEFINITION
# =============================================================================

def _build_graph() -> StateGraph:
    """
    Build and return the LangGraph pipeline.

    Returns:
        Compiled StateGraph ready for execution
    """
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("req_analyse_node", req_analyse_node)
    graph.add_node("amb_resolve_node", amb_resolve_node)
    graph.add_node("validator_node", validator_node)
    graph.add_node("midway_report_node", midway_report_node)
    graph.add_node("solution_architectures_node", solution_architectures_node)
    graph.add_node("critic_node", critic_node)
    graph.add_node("evidence_gather_node", evidence_gather_node)
    graph.add_node("feasibility_estimator_node", feasibility_estimator_node)
    graph.add_node("ba_final_report_node", ba_final_report_node)

    # Define edges (flow)
    graph.add_edge(START, "req_analyse_node")
    graph.add_edge("req_analyse_node", "amb_resolve_node")
    graph.add_edge("amb_resolve_node", "validator_node")
    graph.add_edge("validator_node", "solution_architectures_node")
    graph.add_edge("solution_architectures_node", "critic_node")

    # Conditional loop for critic feedback
    graph.add_conditional_edges(
        "critic_node",
        critic_to_alternative_loop,
        {
            "continue_loop": "solution_architectures_node",
            "end_loop": "evidence_gather_node"
        }
    )

    graph.add_edge("evidence_gather_node", "feasibility_estimator_node")
    graph.add_edge("feasibility_estimator_node", "ba_final_report_node")
    graph.add_edge("ba_final_report_node", END)

    return graph.compile()


# Compile the graph once at module load (safe for multi-user)
agent = _build_graph()


# =============================================================================
# PUBLIC API
# =============================================================================

async def run_agent_pipeline(
    document: list[str],
    timeout: int = None
) -> AgentState:
    """
    Run the full agent pipeline to analyze a document and generate a report.

    This is the main entry point for document analysis. It runs through all
    agent nodes sequentially, with the critic potentially looping back to
    improve the solution architecture.

    Args:
        document: List of document strings to analyze
        timeout: Optional timeout in seconds (defaults to settings.PIPELINE_TIMEOUT)

    Returns:
        AgentState: Final state containing:
            - document: Original document
            - req_analysis: List of all agent outputs
            - loop_count: Final loop count (should be 0)
            - message: List containing midway report and final report

    Raises:
        PipelineTimeoutError: If pipeline exceeds timeout
        PipelineError: If any agent fails
        LLMTimeoutError: If an individual LLM call times out
        LLMRetryExhaustedError: If retries are exhausted
        AgentNotFoundError: If required agent output is missing

    Example:
        result = await run_agent_pipeline(document=["Your requirements text here"])
        final_report = result["message"][-1].content
    """
    timeout = timeout or settings.PIPELINE_TIMEOUT

    initial_state: AgentState = {
        "document": document,
        "req_analysis": [],
        "loop_count": 0,
        "message": []
    }

    logger.info(f"Starting agent pipeline with timeout={timeout}s")
    logger.info(f"Document length: {sum(len(d) for d in document)} characters")

    try:
        result = await asyncio.wait_for(
            agent.ainvoke(initial_state),
            timeout=timeout
        )

        # Validate result
        if not result.get("message"):
            raise PipelineError("Pipeline completed but no report was generated")

        logger.info(f"Pipeline completed successfully. Generated {len(result['message'])} message(s)")
        return result

    except asyncio.TimeoutError:
        logger.error(f"Pipeline timed out after {timeout} seconds")
        raise PipelineTimeoutError(f"Report generation timed out after {timeout} seconds. Please try with a shorter document or contact support.")

    except PipelineError:
        # Re-raise pipeline errors as-is
        raise

    except Exception as e:
        logger.error(f"Unexpected error in pipeline: {str(e)}")
        raise PipelineError(f"Report generation failed: {str(e)}")