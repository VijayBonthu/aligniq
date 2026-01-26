from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain.output_parsers import OutputFixingParser
from config import settings
from utils.prompts import Requirements_analyzer_prompt, Ambiguity_Resolver_Prompt, Validator_agent_prompt, midway_ba_report_prompt, Solution_Architect_Agent_Prompt, Critic_Agent_Prompt,Evidence_Gatherer_Agent_prompt, feasibility_estimator_prompt, Report_Generator_Prompt, SUMMARIZE_CHATCONVERSATION_PROMPT, SUMMARIAZE_MAIN_REPORT_PROMPT, SECTION_REGENERATION_PROMPT
from utils.logger import logger
import json
import asyncio
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from openai import RateLimitError, APITimeoutError, APIConnectionError
import logging


# LLM instances (stateless, safe to reuse)
llm = ChatOpenAI(api_key=settings.OPENAI_CHATGPT, model=settings.GENERATING_REPORT_MODEL, reasoning_effort="low")
llm_parser = ChatOpenAI(api_key=settings.OPENAI_CHATGPT, model=settings.SUMMARIZATION_MODEL, temperature=0)
fixed_parser = OutputFixingParser.from_llm(parser=JsonOutputParser(), llm=llm_parser)


# Custom exceptions for pipeline errors
class PipelineError(Exception):
    """Base exception for pipeline errors"""
    pass


class LLMTimeoutError(PipelineError):
    """Raised when LLM call times out"""
    pass


class LLMRetryExhaustedError(PipelineError):
    """Raised when all retry attempts are exhausted"""
    pass


class AgentOutputError(PipelineError):
    """Raised when agent output is invalid or missing"""
    pass


# Retry decorator for LLM calls - retries on rate limits, timeouts, and connection errors
def llm_retry():
    return retry(
        stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
        wait=wait_exponential(
            min=settings.LLM_RETRY_MIN_WAIT,
            max=settings.LLM_RETRY_MAX_WAIT
        ),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError, asyncio.TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )


async def invoke_with_timeout(chain, input_dict: dict, timeout: int = None, agent_name: str = "unknown"):
    """
    Invoke a LangChain chain with timeout and proper error handling.

    Args:
        chain: The LangChain chain to invoke
        input_dict: Input parameters for the chain
        timeout: Timeout in seconds (defaults to settings.LLM_CALL_TIMEOUT)
        agent_name: Name of the agent for logging

    Returns:
        The chain response

    Raises:
        LLMTimeoutError: If the call times out
        LLMRetryExhaustedError: If all retries are exhausted
    """
    timeout = timeout or settings.LLM_CALL_TIMEOUT

    @llm_retry()
    async def _invoke():
        try:
            return await asyncio.wait_for(
                chain.ainvoke(input_dict),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Agent '{agent_name}' timed out after {timeout}s")
            raise LLMTimeoutError(f"Agent '{agent_name}' timed out after {timeout} seconds")

    try:
        return await _invoke()
    except (RateLimitError, APITimeoutError, APIConnectionError) as e:
        logger.error(f"Agent '{agent_name}' failed after {settings.LLM_MAX_RETRIES} retries: {str(e)}")
        raise LLMRetryExhaustedError(f"Agent '{agent_name}' failed after {settings.LLM_MAX_RETRIES} retries: {str(e)}")


def validate_response(response, agent_name: str, required_fields: list = None):
    """
    Validate agent response has expected structure.

    Args:
        response: The response to validate
        agent_name: Name of the agent for error messages
        required_fields: Optional list of required fields for dict responses

    Returns:
        The validated response

    Raises:
        AgentOutputError: If response is invalid
    """
    if response is None:
        raise AgentOutputError(f"Agent '{agent_name}' returned None")

    if required_fields and isinstance(response, dict):
        missing = [f for f in required_fields if f not in response]
        if missing:
            logger.warning(f"Agent '{agent_name}' missing fields: {missing}")
            # Don't raise, just log - fields might be optional

    return response

async def requirements_analyzer(docs: list) -> dict:
    """
    Analyze raw requirements document and extract structured information.

    Args:
        docs: List of document strings to analyze

    Returns:
        dict: Structured requirements analysis
    """
    logger.info("Starting requirements_analyzer")
    req_analyzer_prompt = ChatPromptTemplate.from_template(Requirements_analyzer_prompt)
    chain = req_analyzer_prompt | llm | fixed_parser
    input_dict = {"requirements_text": docs}

    response = await invoke_with_timeout(chain, input_dict, agent_name="requirements_analyzer")
    logger.info("Completed requirements_analyzer")
    return validate_response(response, "requirements_analyzer")


async def ambiguity_resolver(req_analyzer_json, raw_document, process_flow, org_policies) -> dict:
    """
    Identify and resolve ambiguities in requirements.

    Args:
        req_analyzer_json: Output from requirements analyzer
        raw_document: Original document text
        process_flow: Process flow information
        org_policies: Organization policies

    Returns:
        dict: Ambiguity analysis and resolutions
    """
    logger.info("Starting ambiguity_resolver")
    amb_resolver_prompt = ChatPromptTemplate.from_template(Ambiguity_Resolver_Prompt)
    parser = JsonOutputParser()
    chain = amb_resolver_prompt | llm | parser
    input_dict = {
        "requirements_json": json.dumps(req_analyzer_json),
        "raw_document": json.dumps(raw_document),
        "process_flow": json.dumps(process_flow),
        "org_policies": json.dumps(org_policies)
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="ambiguity_resolver")
    logger.info("Completed ambiguity_resolver")
    return validate_response(response, "ambiguity_resolver")


async def validator_agent(req_analyzer_json: dict, amb_resolver_json: dict) -> dict:
    """
    Validate requirements for consistency and completeness.

    Args:
        req_analyzer_json: Output from requirements analyzer
        amb_resolver_json: Output from ambiguity resolver

    Returns:
        dict: Validation results
    """
    logger.info("Starting validator_agent")
    valid_agent_prompt = ChatPromptTemplate.from_template(Validator_agent_prompt)
    chain = valid_agent_prompt | llm | fixed_parser
    input_dict = {
        "requirements_json": json.dumps(req_analyzer_json),
        "clarified_assumptions": json.dumps(amb_resolver_json)
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="validator_agent")
    logger.info("Completed validator_agent")
    return validate_response(response, "validator_agent")


async def midway_report(req_analyzer_json: dict, amb_resolver_json: dict, validator_json: dict) -> str:
    """
    Generate intermediate progress report.

    Args:
        req_analyzer_json: Output from requirements analyzer
        amb_resolver_json: Output from ambiguity resolver
        validator_json: Output from validator agent

    Returns:
        str: Midway report content
    """
    logger.info("Starting midway_report generation")
    mid_way_report_prompt = ChatPromptTemplate.from_template(midway_ba_report_prompt)
    parser = StrOutputParser()
    chain = mid_way_report_prompt | llm | parser
    input_dict = {
        "requirements_analyzer": json.dumps(req_analyzer_json),
        "ambiguity_resolver": json.dumps(amb_resolver_json),
        "validator": json.dumps(validator_json)
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="midway_report")
    logger.info("Completed midway_report generation")
    return validate_response(response, "midway_report")


async def solution_architect(req_analyzer_json: dict, amb_resolver_json: dict, validator_json: dict, critic_feedback: dict) -> dict:
    """
    Design solution architecture based on validated requirements.

    Args:
        req_analyzer_json: Output from requirements analyzer
        amb_resolver_json: Output from ambiguity resolver
        validator_json: Output from validator agent
        critic_feedback: Feedback from critic agent (if any)

    Returns:
        dict: Solution architecture design
    """
    logger.info("Starting solution_architect")
    sol_architecture_prompt = ChatPromptTemplate.from_template(Solution_Architect_Agent_Prompt)
    chain = sol_architecture_prompt | llm | fixed_parser
    input_dict = {
        "requirements_json": json.dumps(req_analyzer_json),
        "clarified_assumptions": json.dumps(amb_resolver_json),
        "validated_requirements": json.dumps(validator_json),
        "critic_feedback": json.dumps(critic_feedback)
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="solution_architect")
    logger.info("Completed solution_architect")
    return validate_response(response, "solution_architect")


async def evidence_gather_agent(recommendations_json: dict, validated_requirements_json: dict, solution_architectures: dict) -> dict:
    """
    Gather evidence and best practices for proposed solution.

    Args:
        recommendations_json: Requirements recommendations
        validated_requirements_json: Validated requirements
        solution_architectures: Proposed solution architecture

    Returns:
        dict: Evidence and best practices
    """
    logger.info("Starting evidence_gather_agent")
    evi_gather_prompt = ChatPromptTemplate.from_template(Evidence_Gatherer_Agent_prompt)
    chain = evi_gather_prompt | llm | fixed_parser
    input_dict = {
        "requirements_json": json.dumps(recommendations_json),
        "validated_requirements": json.dumps(validated_requirements_json),
        "solution_architectures": json.dumps(solution_architectures)
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="evidence_gather_agent")
    logger.info("Completed evidence_gather_agent")
    return validate_response(response, "evidence_gather_agent")


async def critic_agent(req_analyzer_json: dict, validator_json: dict, solution_architectures_json: dict, previous_critic_feedback: dict) -> dict:
    """
    Critique the solution architecture and identify issues.

    Args:
        req_analyzer_json: Output from requirements analyzer
        validator_json: Output from validator agent
        solution_architectures_json: Proposed solution architecture
        previous_critic_feedback: Previous feedback (for iterations)

    Returns:
        dict: Critique and recommendations
    """
    logger.info("Starting critic_agent")
    cric_agent_prompt = ChatPromptTemplate.from_template(Critic_Agent_Prompt)
    chain = cric_agent_prompt | llm | fixed_parser
    input_dict = {
        "requirements_json": json.dumps(req_analyzer_json),
        "validated_requirements": json.dumps(validator_json),
        "solution_architectures": json.dumps(solution_architectures_json),
        "previous_critic_feedback": json.dumps(previous_critic_feedback)
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="critic_agent")
    logger.info("Completed critic_agent")
    return validate_response(response, "critic_agent")


async def feasibility_estimator(req_analyzer_json: dict, validator_json: dict, solution_architectures_json: dict, evidence_gather_json: dict) -> dict:
    """
    Estimate feasibility, timeline, and resource requirements.

    Args:
        req_analyzer_json: Output from requirements analyzer
        validator_json: Output from validator agent
        solution_architectures_json: Proposed solution architecture
        evidence_gather_json: Evidence and best practices

    Returns:
        dict: Feasibility analysis and estimates
    """
    logger.info("Starting feasibility_estimator")
    feas_estimator_prompt = ChatPromptTemplate.from_template(feasibility_estimator_prompt)
    chain = feas_estimator_prompt | llm | fixed_parser
    input_dict = {
        "requirements_json": json.dumps(req_analyzer_json),
        "validated_requirements": json.dumps(validator_json),
        "solution_architectures": json.dumps(solution_architectures_json),
        "evidence_json": json.dumps(evidence_gather_json)
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="feasibility_estimator")
    logger.info("Completed feasibility_estimator")
    return validate_response(response, "feasibility_estimator")


async def ba_final_report_generation(
    requirements_json: dict,
    validated_requirements: dict,
    ambiguity_resolutions: dict,
    solution_architectures: dict,
    critic_feedback: dict,
    evidence: dict,
    feasibility: dict
) -> str:
    """
    Generate the final comprehensive BA report.

    Args:
        requirements_json: Analyzed requirements
        validated_requirements: Validated requirements
        ambiguity_resolutions: Resolved ambiguities
        solution_architectures: Solution architecture
        critic_feedback: Final critic feedback
        evidence: Supporting evidence
        feasibility: Feasibility analysis

    Returns:
        str: Final report in markdown format
    """
    logger.info("Starting ba_final_report_generation")
    final_report_prompt = ChatPromptTemplate.from_template(Report_Generator_Prompt)
    parser = StrOutputParser()
    chain = final_report_prompt | llm | parser
    input_dict = {
        "requirements_analysis_json": json.dumps(requirements_json),
        "validated_requirements": json.dumps(validated_requirements),
        "ambiguity_resolver_json": json.dumps(ambiguity_resolutions),
        "solution_architect_json": json.dumps(solution_architectures),
        "critic_feedback_json": json.dumps(critic_feedback),
        "evidence_gathering_json": json.dumps(evidence),
        "feasibility_estimator_json": json.dumps(feasibility)
    }

    # Final report generation might take longer, use extended timeout
    response = await invoke_with_timeout(
        chain,
        input_dict,
        timeout=settings.LLM_CALL_TIMEOUT * 2,  # Double timeout for final report
        agent_name="ba_final_report_generation"
    )
    logger.info("Completed ba_final_report_generation")
    return validate_response(response, "ba_final_report_generation")


async def conversational_summary(chat_history: list, main_report_summary: str) -> str:
    """
    Generate a summary of the conversation history.

    Args:
        chat_history: List of chat messages
        main_report_summary: Summary of the main report

    Returns:
        str: Conversation summary
    """
    logger.info("Starting conversational_summary")
    convo_summary = ChatPromptTemplate.from_template(SUMMARIZE_CHATCONVERSATION_PROMPT)
    parser = StrOutputParser()
    chain = convo_summary | llm_parser | parser
    input_dict = {
        "chat_history": json.dumps(chat_history),
        "main report_summary": main_report_summary
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="conversational_summary")
    logger.info("Completed conversational_summary")
    return validate_response(response, "conversational_summary")


async def main_report_summary(main_report: str) -> dict:
    """
    Generate a structured summary of the main report.

    Args:
        main_report: Full report markdown content

    Returns:
        dict: Structured report summary
    """
    logger.info("Starting main_report_summary")
    main_summary = ChatPromptTemplate.from_template(SUMMARIAZE_MAIN_REPORT_PROMPT)
    parser = JsonOutputParser()
    chain = main_summary | llm_parser | parser
    input_dict = {
        "full_report_markdown": main_report
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="main_report_summary")
    logger.info("Completed main_report_summary")
    return validate_response(response, "main_report_summary")


async def regenerate_report_sections(
    original_report: str,
    regeneration_plan: dict,
    pending_changes: list
) -> str:
    """
    Regenerate specific sections of a report based on pending changes.

    This function takes the original report and applies the pending changes
    to only the affected sections, preserving unchanged sections exactly.

    Args:
        original_report: The full original report in markdown format
        regeneration_plan: Dict containing:
            - sections_to_regenerate: List of section names to update
            - change_instructions: List of change objects with details
            - sections_to_keep: List of sections that should remain unchanged
            - estimated_impact: "low", "medium", or "high"
        pending_changes: List of pending change objects with:
            - type: Change type (modify_requirements, modify_architecture, etc.)
            - user_request: The user's original request
            - affected_sections: List of affected section names

    Returns:
        str: The regenerated report in markdown format

    Raises:
        LLMTimeoutError: If the regeneration times out
        LLMRetryExhaustedError: If retries are exhausted
        AgentOutputError: If the response is invalid

    Example:
        updated_report = await regenerate_report_sections(
            original_report=current_report,
            regeneration_plan={"sections_to_regenerate": ["architecture"]},
            pending_changes=[{"type": "modify_architecture", "user_request": "Use AWS instead of Azure"}]
        )
    """
    logger.info(f"Starting section regeneration for {len(regeneration_plan.get('sections_to_regenerate', []))} sections")
    logger.info(f"Applying {len(pending_changes)} pending changes")

    regen_prompt = ChatPromptTemplate.from_template(SECTION_REGENERATION_PROMPT)
    parser = StrOutputParser()
    chain = regen_prompt | llm | parser

    input_dict = {
        "original_report": original_report,
        "regeneration_plan": json.dumps(regeneration_plan, indent=2),
        "pending_changes": json.dumps(pending_changes, indent=2)
    }

    # Section regeneration might take longer due to long context, use extended timeout
    response = await invoke_with_timeout(
        chain,
        input_dict,
        timeout=settings.LLM_CALL_TIMEOUT * 2,  # Double timeout for regeneration
        agent_name="section_regeneration"
    )

    logger.info("Section regeneration completed")

    # Validate the response is not empty
    validated_response = validate_response(response, "section_regeneration")

    # Basic validation - check it looks like a markdown report
    if not validated_response or len(validated_response) < 500:
        logger.warning(f"Regenerated report seems too short ({len(validated_response) if validated_response else 0} chars)")
        raise AgentOutputError("Regenerated report is too short - regeneration may have failed")

    return validated_response

