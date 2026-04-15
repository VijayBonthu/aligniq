from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain.output_parsers import OutputFixingParser
from config import settings
from utils.prompts import Requirements_analyzer_prompt, Ambiguity_Resolver_Prompt, Validator_agent_prompt, midway_ba_report_prompt, Solution_Architect_Agent_Prompt, Critic_Agent_Prompt,Evidence_Gatherer_Agent_prompt, feasibility_estimator_prompt, Report_Generator_Prompt, SUMMARIZE_CHATCONVERSATION_PROMPT, SUMMARIAZE_MAIN_REPORT_PROMPT, SECTION_REGENERATION_PROMPT, CHANGELOG_SUMMARY_PROMPT
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


async def main_report_summary(main_report: str, version_number: int = 1) -> dict:
    """
    Generate a structured summary of the main report.

    Args:
        main_report: Full report markdown content
        version_number: The version number of this report (default: 1)

    Returns:
        dict: Structured report summary
    """
    logger.info(f"Starting main_report_summary for version {version_number}")
    main_summary = ChatPromptTemplate.from_template(SUMMARIAZE_MAIN_REPORT_PROMPT)
    parser = JsonOutputParser()
    chain = main_summary | llm_parser | parser
    input_dict = {
        "full_report_markdown": main_report,
        "version_number": f"v{version_number}"
    }

    response = await invoke_with_timeout(chain, input_dict, agent_name="main_report_summary")
    logger.info(f"Completed main_report_summary for version {version_number}")
    return validate_response(response, "main_report_summary")


async def generate_changelog_summary(
    previous_summary: str,
    new_summary: str,
    changes_applied: list,
    previous_version: int,
    new_version: int
) -> str:
    """
    Generate a human-readable summary of what changed between report versions.

    This function takes the old and new summaries along with the changes that
    were applied and produces a concise explanation of what changed and why.

    Args:
        previous_summary: Executive summary from the previous report version
        new_summary: Executive summary from the new report version
        changes_applied: List of pending change objects that were applied
        previous_version: Version number of the previous report
        new_version: Version number of the new report

    Returns:
        str: Human-readable changelog summary (2-4 sentences)
    """
    logger.info(f"Starting generate_changelog_summary for v{previous_version} -> v{new_version}")

    # Format changes_applied for the prompt
    if changes_applied:
        changes_text = "\n".join([
            f"- {change.get('user_request', 'Unknown change')} (Type: {change.get('type', 'unknown')})"
            for change in changes_applied
        ])
    else:
        changes_text = "No specific changes recorded"

    changelog_prompt = ChatPromptTemplate.from_template(CHANGELOG_SUMMARY_PROMPT)
    str_parser = StrOutputParser()
    chain = changelog_prompt | llm_parser | str_parser

    input_dict = {
        "previous_summary": previous_summary,
        "new_summary": new_summary,
        "changes_applied": changes_text,
        "previous_version": previous_version,
        "new_version": new_version
    }

    try:
        response = await invoke_with_timeout(chain, input_dict, agent_name="generate_changelog_summary")
        logger.info(f"Completed generate_changelog_summary for v{previous_version} -> v{new_version}")
        return response.strip() if response else "Changes applied to generate this version."
    except Exception as e:
        logger.warning(f"Failed to generate changelog summary: {e}")
        # Return a fallback summary if generation fails
        return f"Version {new_version} created from version {previous_version} with {len(changes_applied)} change(s) applied."


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


def format_full_context_for_pipeline(
    pending_changes: list,
    presales_context: dict = None
) -> str:
    """
    Format ALL context (constraints + presales data) as a document section.

    This function creates a comprehensive markdown section that will be prepended
    to the document for the full 9-agent pipeline. All agents will see this context
    as part of the source document.

    Creates sections for:
    1. MANDATORY ARCHITECTURAL CONSTRAINTS (pending changes)
    2. CLIENT CLARIFICATIONS (Q&A from presales questions)
    3. ASSUMPTIONS (from presales analysis)
    4. ADDITIONAL CLIENT CONTEXT (user comments)

    Args:
        pending_changes: List of pending change objects with:
            - id: Change ID (e.g., "CHG-001")
            - type: Change type (e.g., "modify_architecture")
            - user_request: The user's original request
            - affected_sections: List of affected section names
        presales_context: Dict containing:
            - scanned_requirements: dict
            - blind_spots: dict
            - assumptions_list: list of assumption objects
            - questions_and_answers: list of {question_text, answer, answer_quality}
            - additional_context: str (user comments)
            - user_answers: dict

    Returns:
        str: Formatted markdown context section to prepend to document
    """
    context_parts = []

    # Section 1: MANDATORY CONSTRAINTS (Pending Changes)
    if pending_changes:
        constraints_section = """
## MANDATORY ARCHITECTURAL CONSTRAINTS

The following changes have been requested by the client and MUST be incorporated
into all analysis and recommendations. These override any conflicting decisions
from the original analysis.

"""
        for change in pending_changes:
            change_id = change.get('id', 'CHG-XXX')
            change_type = change.get('type', 'modification')
            user_request = change.get('user_request', '')
            affected = change.get('affected_sections', [])

            constraints_section += f"""
### Constraint {change_id}
- **Type**: {change_type}
- **Requirement**: {user_request}
- **Affected Areas**: {', '.join(affected) if affected else 'General'}
"""
        context_parts.append(constraints_section)

    if presales_context:
        # Section 2: CLIENT Q&A CLARIFICATIONS (Answered Questions)
        qa_list = presales_context.get("questions_and_answers", [])
        if qa_list:
            qa_section = """
## CLIENT CLARIFICATIONS (Questions & Answers)

The following questions were asked and answered during the pre-sales phase.
These answers represent confirmed client requirements and should be treated
as authoritative input for the analysis.

"""
            for qa in qa_list:
                if qa.get("answer"):  # Only include answered questions
                    q_num = qa.get('question_number', 'Q')
                    q_text = qa.get('question_text', '')
                    answer = qa.get('answer', '')
                    quality = qa.get('answer_quality', 'unknown')
                    area = qa.get('area_or_category', '')

                    qa_section += f"""
### {q_num} ({area})
- **Question**: {q_text}
- **Answer**: {answer}
- **Answer Quality**: {quality}
"""
            context_parts.append(qa_section)

        # Section 3: ASSUMPTIONS
        assumptions = presales_context.get("assumptions_list", [])
        if assumptions:
            assumptions_section = """
## ASSUMPTIONS

The following assumptions were made during the pre-sales analysis phase.
Treat these as working assumptions unless contradicted by the mandatory
constraints above or by explicit client clarifications.

"""
            for assumption in assumptions:
                if isinstance(assumption, dict):
                    assumption_text = assumption.get('assumption', str(assumption))
                    basis = assumption.get('basis', '')
                    impact = assumption.get('impact_if_wrong', '')

                    assumptions_section += f"""
- **Assumption**: {assumption_text}
"""
                    if basis:
                        assumptions_section += f"  - **Basis**: {basis}\n"
                    if impact:
                        assumptions_section += f"  - **Risk if wrong**: {impact}\n"
                else:
                    assumptions_section += f"- {assumption}\n"

            context_parts.append(assumptions_section)

        # Section 4: ADDITIONAL CLIENT CONTEXT
        additional = presales_context.get("additional_context", "")
        if additional and additional.strip():
            additional_section = f"""
## ADDITIONAL CLIENT CONTEXT

The client provided the following additional information/comments that should
be considered in the analysis:

{additional}
"""
            context_parts.append(additional_section)

        # Section 5: BLIND SPOTS (from presales analysis)
        blind_spots = presales_context.get("blind_spots", {})
        if blind_spots:
            blind_spots_section = """
## IDENTIFIED BLIND SPOTS

The following blind spots were identified during pre-sales analysis.
These areas require special attention in the full analysis:

"""
            if isinstance(blind_spots, dict):
                for category, items in blind_spots.items():
                    if items:
                        blind_spots_section += f"\n### {category}\n"
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    blind_spots_section += f"- {item.get('description', str(item))}\n"
                                else:
                                    blind_spots_section += f"- {item}\n"
                        else:
                            blind_spots_section += f"- {items}\n"
            context_parts.append(blind_spots_section)

    # Combine all sections
    if context_parts:
        full_context = """
# REGENERATION CONTEXT - READ CAREFULLY

This report is being regenerated with the following context and constraints.
All agents MUST consider this information when producing their analysis.

---
""" + "\n---\n".join(context_parts) + """

---
## END OF REGENERATION CONTEXT
---

"""
        return full_context

    return ""


async def run_pipeline_with_constraints(
    document: list[str],
    pending_changes: list,
    presales_context: dict = None,
    timeout: int = None
) -> dict:
    """
    Run the full 9-agent pipeline with pending changes as mandatory constraints
    AND full presales context (questions, answers, assumptions, additional context).

    This function wraps the existing run_agent_pipeline() but prepends
    all context information to the document so all agents consider them.

    Args:
        document: Original document text as list of chunks
        pending_changes: List of pending change objects as constraints
        presales_context: Dict containing:
            - scanned_requirements: dict
            - blind_spots: dict
            - assumptions_list: list
            - questions_and_answers: list of {question, answer, quality}
            - additional_context: str (user comments)
            - user_answers: dict
        timeout: Pipeline timeout in seconds (defaults to settings.PIPELINE_TIMEOUT)

    Returns:
        {
            "report": str,              # Generated markdown report from final agent
            "processing_time": float,   # Time taken in seconds
            "constraints_applied": int, # Number of constraints applied
            "context_included": dict,   # What context was included
            "error": str or None        # Error message if failed
        }

    Raises:
        PipelineError: If the pipeline fails catastrophically
    """
    import time
    from agents.workflow_graph import run_agent_pipeline

    start_time = time.time()
    timeout = timeout or settings.PIPELINE_TIMEOUT

    # Track what context we're including
    context_included = {
        "constraints": len(pending_changes),
        "questions_answered": len(presales_context.get("questions_and_answers", [])) if presales_context else 0,
        "assumptions": len(presales_context.get("assumptions_list", [])) if presales_context else 0,
        "has_additional_context": bool(presales_context and presales_context.get("additional_context")),
        "has_blind_spots": bool(presales_context and presales_context.get("blind_spots"))
    }

    logger.info(
        f"Starting pipeline with constraints: {context_included['constraints']} constraints, "
        f"{context_included['questions_answered']} Q&A pairs, "
        f"{context_included['assumptions']} assumptions"
    )

    try:
        # Format all context as document section
        context_section = format_full_context_for_pipeline(
            pending_changes=pending_changes,
            presales_context=presales_context
        )

        # Prepend context to document
        if context_section:
            enhanced_document = [context_section] + document
            logger.info(f"Enhanced document with {len(context_section)} chars of context")
        else:
            enhanced_document = document
            logger.info("No context to prepend, using original document")

        # Run full 9-agent pipeline
        result = await run_agent_pipeline(
            document=enhanced_document,
            timeout=timeout
        )

        # Extract final report from result
        if not result.get("message") or len(result["message"]) == 0:
            raise AgentOutputError("Pipeline completed but no report was generated")

        final_message = result["message"][-1]
        final_report = final_message.content if hasattr(final_message, 'content') else str(final_message)

        processing_time = time.time() - start_time
        logger.info(f"Pipeline with constraints completed in {processing_time:.2f}s")

        return {
            "report": final_report,
            "processing_time": processing_time,
            "constraints_applied": len(pending_changes),
            "context_included": context_included,
            "error": None
        }

    except (LLMTimeoutError, LLMRetryExhaustedError) as e:
        processing_time = time.time() - start_time
        logger.error(f"Pipeline failed due to LLM error: {str(e)}")
        return {
            "report": None,
            "processing_time": processing_time,
            "constraints_applied": len(pending_changes),
            "context_included": context_included,
            "error": f"LLM error: {str(e)}"
        }
    except AgentOutputError as e:
        processing_time = time.time() - start_time
        logger.error(f"Pipeline failed due to agent output error: {str(e)}")
        return {
            "report": None,
            "processing_time": processing_time,
            "constraints_applied": len(pending_changes),
            "context_included": context_included,
            "error": f"Agent error: {str(e)}"
        }
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Pipeline failed unexpectedly: {str(e)}")
        return {
            "report": None,
            "processing_time": processing_time,
            "constraints_applied": len(pending_changes),
            "context_included": context_included,
            "error": f"Unexpected error: {str(e)}"
        }

