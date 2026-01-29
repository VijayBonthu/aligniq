"""
Pre-Sales Workflow Pipeline

A fast 3-agent LangGraph workflow for pre-sales analysis (target: 60-120 seconds).

Agents:
1. Scanner - Extract requirements, technologies, integrations (15-20 sec)
2. Blind Spot Detector - Identify risks, unknowns, red flags (30-40 sec)
3. Brief Generator - Create actionable markdown brief (15-20 sec)

Usage:
    result = await run_presales_pipeline(document="Your document text here")
    brief = result["presales_brief"]
"""

from typing_extensions import TypedDict, Optional, List
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain.output_parsers import OutputFixingParser
from config import settings
from utils.presales_prompts import (
    PRESALES_SCANNER_PROMPT,
    BLINDSPOT_DETECTOR_PROMPT,
    PRESALES_BRIEF_PROMPT
)
from utils.logger import logger
import json
import asyncio
import time
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from openai import RateLimitError, APITimeoutError, APIConnectionError
import logging


# =============================================================================
# EXCEPTIONS
# =============================================================================

class PresalesPipelineError(Exception):
    """Base exception for pre-sales pipeline errors"""
    pass


class PresalesTimeoutError(PresalesPipelineError):
    """Raised when pre-sales pipeline times out"""
    pass


class PresalesAgentError(PresalesPipelineError):
    """Raised when a pre-sales agent fails"""
    pass


# =============================================================================
# LLM CONFIGURATION
# =============================================================================

# Fast model for scanner and brief generation
llm_fast = ChatOpenAI(
    api_key=settings.OPENAI_CHATGPT,
    model=settings.GENERATING_REPORT_MODEL,  # gpt-4o-mini
    temperature=0.1,
    request_timeout=60  # 60 second timeout for fast agents
)

# Stronger model for blind spot detection (needs better reasoning)
llm_reasoning = ChatOpenAI(
    api_key=settings.OPENAI_CHATGPT,
    model=settings.GENERATING_REPORT_MODEL,  # Can be upgraded to gpt-4o if needed
    temperature=0.2,
    request_timeout=90  # 90 second timeout for reasoning agent
)

# Parser for JSON responses
llm_parser = ChatOpenAI(
    api_key=settings.OPENAI_CHATGPT,
    model=settings.SUMMARIZATION_MODEL,
    temperature=0
)
json_parser = JsonOutputParser()
fixed_parser = OutputFixingParser.from_llm(parser=json_parser, llm=llm_parser)


# =============================================================================
# STATE DEFINITION
# =============================================================================

class PresalesState(TypedDict):
    """
    State object passed through the pre-sales LangGraph pipeline.

    Attributes:
        document: Raw document text to analyze
        scanned_requirements: Output from scanner agent (JSON)
        blind_spots: Output from blind spot detector (JSON)
        p1_blockers: Extracted P1 blockers with questions
        critical_unknowns: Kickstart questions (critical unknowns)
        technology_risks: Extracted tech risks for passive capture
        red_flags: Warning signs from analysis
        presales_brief: Final markdown brief
        error: Error message if pipeline fails
        processing_times: Dict tracking time for each agent
    """
    document: str
    scanned_requirements: Optional[dict]
    blind_spots: Optional[dict]
    p1_blockers: Optional[List[dict]]
    critical_unknowns: Optional[List[dict]]
    technology_risks: Optional[List[dict]]
    red_flags: Optional[List[dict]]
    presales_brief: Optional[str]
    error: Optional[str]
    processing_times: dict


# =============================================================================
# RETRY DECORATOR
# =============================================================================

def presales_retry():
    """Retry decorator for pre-sales LLM calls - fewer retries for speed"""
    return retry(
        stop=stop_after_attempt(2),  # Only 2 retries for speed
        wait=wait_exponential(min=1, max=5),  # Shorter waits
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError, asyncio.TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )


async def invoke_presales_agent(chain, input_dict: dict, timeout: int, agent_name: str):
    """
    Invoke a pre-sales agent with timeout and retry.

    Args:
        chain: The LangChain chain to invoke
        input_dict: Input parameters
        timeout: Timeout in seconds
        agent_name: Name for logging

    Returns:
        The chain response

    Raises:
        PresalesAgentError: If agent fails after retries
    """
    @presales_retry()
    async def _invoke():
        try:
            return await asyncio.wait_for(
                chain.ainvoke(input_dict),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Pre-sales agent '{agent_name}' timed out after {timeout}s")
            raise

    try:
        return await _invoke()
    except Exception as e:
        logger.error(f"Pre-sales agent '{agent_name}' failed: {str(e)}")
        raise PresalesAgentError(f"Agent '{agent_name}' failed: {str(e)}")


def parse_json_response(content: str, agent_name: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code blocks.

    Args:
        content: Raw LLM response
        agent_name: Name for error logging

    Returns:
        Parsed JSON dict

    Raises:
        PresalesAgentError: If JSON parsing fails
    """
    try:
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return json.loads(content.strip())
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in {agent_name}: {str(e)}")
        logger.debug(f"Raw content: {content[:500]}...")
        raise PresalesAgentError(f"Failed to parse {agent_name} response as JSON: {str(e)}")


# =============================================================================
# AGENT NODES
# =============================================================================

async def scanner_node(state: PresalesState) -> PresalesState:
    """
    Requirements Scanner Node - Extract essentials quickly.

    Target time: 15-20 seconds

    Extracts:
    - Project summary
    - Technologies mentioned
    - Integrations required
    - Scope indicators
    - Obvious gaps
    """
    logger.info("Starting presales scanner_node")
    start_time = time.time()

    try:
        prompt = ChatPromptTemplate.from_template(PRESALES_SCANNER_PROMPT)
        chain = prompt | llm_fast | fixed_parser

        response = await invoke_presales_agent(
            chain=chain,
            input_dict={"document": state["document"]},
            timeout=60,
            agent_name="scanner"
        )

        # Response should already be parsed by fixed_parser
        if isinstance(response, str):
            response = parse_json_response(response, "scanner")

        state["scanned_requirements"] = response
        state["processing_times"]["scanner"] = round(time.time() - start_time, 2)

        logger.info(f"scanner_node completed in {state['processing_times']['scanner']}s")
        return state

    except Exception as e:
        logger.error(f"scanner_node error: {str(e)}")
        state["error"] = f"Scanner failed: {str(e)}"
        state["processing_times"]["scanner"] = round(time.time() - start_time, 2)
        return state


async def blindspot_node(state: PresalesState) -> PresalesState:
    """
    Blind Spot Detector Node - Identify what will bite the team.

    Target time: 30-40 seconds

    Identifies:
    - Client underestimations
    - Critical unknowns (kickstart questions)
    - Technology risks (from LLM knowledge)
    - Red flags
    """
    logger.info("Starting presales blindspot_node")
    start_time = time.time()

    # Skip if previous node failed
    if state.get("error"):
        logger.warning("Skipping blindspot_node due to previous error")
        return state

    try:
        # Extract technologies for focused risk analysis
        technologies = []
        if state.get("scanned_requirements"):
            technologies = state["scanned_requirements"].get("technologies_mentioned", [])

        prompt = ChatPromptTemplate.from_template(BLINDSPOT_DETECTOR_PROMPT)
        chain = prompt | llm_reasoning | fixed_parser

        response = await invoke_presales_agent(
            chain=chain,
            input_dict={
                "document": state["document"],
                "scanned_requirements": json.dumps(state["scanned_requirements"], indent=2),
                "technologies": ", ".join(technologies) if technologies else "None specified"
            },
            timeout=90,
            agent_name="blindspot"
        )

        # Response should already be parsed by fixed_parser
        if isinstance(response, str):
            response = parse_json_response(response, "blindspot")

        state["blind_spots"] = response
        state["p1_blockers"] = response.get("p1_blockers", [])
        state["critical_unknowns"] = response.get("critical_unknowns", [])
        state["technology_risks"] = response.get("technology_risks", [])
        state["red_flags"] = response.get("red_flags", [])
        state["processing_times"]["blindspot"] = round(time.time() - start_time, 2)

        logger.info(f"blindspot_node completed in {state['processing_times']['blindspot']}s")
        logger.info(f"Identified {len(state['p1_blockers'])} P1 blockers, {len(state['critical_unknowns'])} kickstart questions, {len(state['technology_risks'])} technology risks")
        return state

    except Exception as e:
        logger.error(f"blindspot_node error: {str(e)}")
        state["error"] = f"Blind spot detection failed: {str(e)}"
        state["processing_times"]["blindspot"] = round(time.time() - start_time, 2)
        return state


async def brief_generator_node(state: PresalesState) -> PresalesState:
    """
    Pre-Sales Brief Generator Node - Create actionable markdown brief.

    Target time: 15-20 seconds

    Generates:
    - Quick assessment (complexity, biggest unknown, next step)
    - P1 blockers
    - Kickstart questions by category
    - Technology risks table
    - Red flags
    - Notes for SA and PM
    """
    logger.info("Starting presales brief_generator_node")
    start_time = time.time()

    # Skip if previous node failed
    if state.get("error"):
        logger.warning("Skipping brief_generator_node due to previous error")
        return state

    try:
        # Extract project summary for the brief
        project_summary = ""
        if state.get("scanned_requirements"):
            project_summary = state["scanned_requirements"].get("project_summary", "")

        prompt = ChatPromptTemplate.from_template(PRESALES_BRIEF_PROMPT)
        chain = prompt | llm_fast | StrOutputParser()

        response = await invoke_presales_agent(
            chain=chain,
            input_dict={
                "project_summary": project_summary,
                "scanned_requirements": json.dumps(state["scanned_requirements"], indent=2),
                "p1_blockers": json.dumps(state.get("p1_blockers", []), indent=2),
                "critical_unknowns": json.dumps(state.get("critical_unknowns", []), indent=2),
                "technology_risks": json.dumps(state.get("technology_risks", []), indent=2),
                "red_flags": json.dumps(state.get("red_flags", []), indent=2)
            },
            timeout=60,
            agent_name="brief_generator"
        )

        state["presales_brief"] = response
        state["processing_times"]["brief_generator"] = round(time.time() - start_time, 2)

        logger.info(f"brief_generator_node completed in {state['processing_times']['brief_generator']}s")
        return state

    except Exception as e:
        logger.error(f"brief_generator_node error: {str(e)}")
        state["error"] = f"Brief generation failed: {str(e)}"
        state["processing_times"]["brief_generator"] = round(time.time() - start_time, 2)
        return state


# =============================================================================
# GRAPH DEFINITION
# =============================================================================

def _build_presales_graph() -> StateGraph:
    """
    Build and return the pre-sales LangGraph pipeline.

    Flow: scanner -> blindspot -> brief_generator

    This is a simple linear flow with no loops (speed is priority).

    Returns:
        Compiled StateGraph ready for execution
    """
    graph = StateGraph(PresalesState)

    # Add nodes
    graph.add_node("scanner", scanner_node)
    graph.add_node("blindspot", blindspot_node)
    graph.add_node("brief_generator", brief_generator_node)

    # Linear flow - simple and fast
    graph.add_edge(START, "scanner")
    graph.add_edge("scanner", "blindspot")
    graph.add_edge("blindspot", "brief_generator")
    graph.add_edge("brief_generator", END)

    return graph.compile()


# Compile the graph once at module load
presales_agent = _build_presales_graph()


# =============================================================================
# PUBLIC API
# =============================================================================

async def run_presales_pipeline(
    document: str,
    timeout: int = 180  # 3 minute default timeout for entire pipeline
) -> dict:
    """
    Run the pre-sales analysis pipeline.

    This is the main entry point for quick pre-sales document analysis.
    Target completion time: 60-120 seconds.

    Args:
        document: Raw document text to analyze
        timeout: Maximum time for entire pipeline (default 180 seconds)

    Returns:
        dict containing:
            - presales_brief: Markdown brief for pre-sales (str)
            - scanned_requirements: Extracted requirements (dict)
            - blind_spots: Full blind spots analysis (dict)
            - p1_blockers: List of P1 blockers with questions (list)
            - critical_unknowns: Kickstart questions (list)
            - technology_risks: List of tech risks for capture (list)
            - red_flags: Warning signs from analysis (list)
            - processing_times: Time taken by each agent (dict)
            - error: Error message if failed (str or None)

    Raises:
        PresalesTimeoutError: If pipeline exceeds timeout
        PresalesPipelineError: If pipeline fails

    Example:
        result = await run_presales_pipeline(document="Build a Netflix-like app...")
        if result.get("error"):
            print(f"Failed: {result['error']}")
        else:
            print(result["presales_brief"])
    """
    logger.info(f"Starting pre-sales pipeline with timeout={timeout}s")
    logger.info(f"Document length: {len(document)} characters")
    total_start = time.time()

    initial_state: PresalesState = {
        "document": document,
        "scanned_requirements": None,
        "blind_spots": None,
        "p1_blockers": None,
        "critical_unknowns": None,
        "technology_risks": None,
        "red_flags": None,
        "presales_brief": None,
        "error": None,
        "processing_times": {}
    }

    try:
        result = await asyncio.wait_for(
            presales_agent.ainvoke(initial_state),
            timeout=timeout
        )

        result["processing_times"]["total"] = round(time.time() - total_start, 2)

        if result.get("error"):
            logger.error(f"Pre-sales pipeline completed with error: {result['error']}")
        else:
            logger.info(f"Pre-sales pipeline completed successfully in {result['processing_times']['total']}s")

        return result

    except asyncio.TimeoutError:
        logger.error(f"Pre-sales pipeline timed out after {timeout}s")
        return {
            **initial_state,
            "error": f"Pre-sales analysis timed out after {timeout} seconds",
            "processing_times": {"total": round(time.time() - total_start, 2)}
        }

    except Exception as e:
        logger.error(f"Pre-sales pipeline error: {str(e)}")
        return {
            **initial_state,
            "error": str(e),
            "processing_times": {"total": round(time.time() - total_start, 2)}
        }


# =============================================================================
# FULL REPORT WITH ASSUMPTIONS GENERATOR
# =============================================================================

async def generate_report_with_assumptions(
    document: str,
    scanned_requirements: dict,
    confirmed_answers: list,
    assumptions_list: list,
    timeout: int = 180
) -> dict:
    """
    Generate a comprehensive technical report that clearly distinguishes
    between confirmed information (from answers) and assumptions made.

    Args:
        document: Original document text
        scanned_requirements: Extracted requirements from scanner
        confirmed_answers: List of questions with their answers
        assumptions_list: List of assumptions to be made for unanswered questions
        timeout: Timeout in seconds

    Returns:
        dict containing:
            - report: Generated markdown report
            - processing_time: Time taken in seconds
            - error: Error message if failed (None if successful)
    """
    from utils.presales_prompts import FULL_REPORT_WITH_ASSUMPTIONS_PROMPT

    logger.info("Starting report generation with assumptions")
    logger.info(f"Confirmed answers: {len(confirmed_answers)}, Assumptions: {len(assumptions_list)}")
    start_time = time.time()

    try:
        # Format confirmed answers for the prompt
        confirmed_formatted = []
        for answer in confirmed_answers:
            q_type = answer.get("question_type", "unknown")
            q_num = answer.get("question_number", "?")
            q_text = answer.get("question_text", "")
            ans = answer.get("answer", "")

            if ans:  # Only include answered questions
                confirmed_formatted.append(f"""
**{q_num}** ({q_type})
- Question: {q_text}
- Answer: {ans}
""")

        # Format assumptions for the prompt
        assumptions_formatted = []
        for assumption in assumptions_list:
            risk_level = assumption.get("risk_level", "medium")
            risk_emoji = "🔴" if risk_level == "high" else "🟡" if risk_level == "medium" else "🟢"
            assumptions_formatted.append(f"""
**For {assumption.get('for_question_id', 'Unknown')}** {risk_emoji} ({risk_level} risk)
- Assumption: {assumption.get('assumption', 'N/A')}
- Basis: {assumption.get('basis', 'Industry standard practice')}
- Impact if wrong: {assumption.get('impact_if_wrong', 'May require rework')}
""")

        prompt = ChatPromptTemplate.from_template(FULL_REPORT_WITH_ASSUMPTIONS_PROMPT)
        chain = prompt | llm_reasoning | StrOutputParser()

        response = await asyncio.wait_for(
            chain.ainvoke({
                "document": document[:15000],  # Limit document size
                "confirmed_answers": "\n".join(confirmed_formatted) if confirmed_formatted else "No confirmed answers provided.",
                "assumptions_list": "\n".join(assumptions_formatted) if assumptions_formatted else "No assumptions needed - all information confirmed."
            }),
            timeout=timeout
        )

        processing_time = round(time.time() - start_time, 2)
        logger.info(f"Report with assumptions generated in {processing_time}s")

        return {
            "report": response,
            "processing_time": processing_time,
            "error": None,
            "confirmed_count": len([a for a in confirmed_answers if a.get("answer")]),
            "assumptions_count": len(assumptions_list)
        }

    except asyncio.TimeoutError:
        logger.error(f"Report generation timed out after {timeout}s")
        return {
            "report": None,
            "processing_time": round(time.time() - start_time, 2),
            "error": f"Report generation timed out after {timeout} seconds"
        }
    except Exception as e:
        logger.error(f"Report generation failed: {str(e)}")
        return {
            "report": None,
            "processing_time": round(time.time() - start_time, 2),
            "error": str(e)
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'run_presales_pipeline',
    'generate_report_with_assumptions',
    'PresalesState',
    'PresalesPipelineError',
    'PresalesTimeoutError',
    'PresalesAgentError'
]
