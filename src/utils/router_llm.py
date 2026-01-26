from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from config import settings
from utils.prompts import (
    ROUTER_LLM_PROMPT,
    SUMMARIZE_CHATCONVERSATION_PROMPT,
    ACTION_RESPONSE_PROMPT,
    CHANGE_ACKNOWLEDGMENT_PROMPT,
    CONFLICT_RESOLUTION_PROMPT,
    REGENERATE_WITH_CHANGES_PROMPT
)
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
import tiktoken
from utils.logger import logger

llm_router = ChatOpenAI(api_key=settings.OPENAI_CHATGPT, model=settings.SUMMARIZATION_MODEL, temperature=0)
llm_response = ChatOpenAI(api_key=settings.OPENAI_CHATGPT, model=settings.SUMMARIZATION_MODEL, temperature=0.3)

# Actions that should track changes instead of regenerating
CHANGE_TRACKING_ACTIONS = ["modify_requirements", "modify_architecture", "correct_assumptions"]
async def router_query_llm(user_message:str, conversation_summary:dict, report_summary:dict) -> str:
    router_prompt = ChatPromptTemplate.from_template(ROUTER_LLM_PROMPT)
    parser = JsonOutputParser()
    chain = router_prompt | llm_router | parser
    input_dict = {"report_summary": report_summary,
                  "conversation_summary": conversation_summary,
                  "user_message": user_message
                  }
    response = await chain.ainvoke(input_dict)
    return response

async def conversation_summary_llm(conversation:list[dict]) -> str:
    summary_prompt = ChatPromptTemplate.from_template(SUMMARIZE_CHATCONVERSATION_PROMPT)
    parser = JsonOutputParser()
    chain = summary_prompt | llm_router | parser
    input_dict = {"conversation": conversation}
    response = await chain.ainvoke(input_dict)
    return response

async def count_token(data:list[dict]) -> int:
    encoding = tiktoken.encoding_for_model(settings.SUMMARIZATION_MODEL)
    total_tokens = 0
    for message in data:
        total_tokens += len(encoding.encode(message["role"]))
        total_tokens += len(encoding.encode(message["content"]))
    return total_tokens


async def generate_action_response(
    report_summary: dict,
    conversation_context: any,  # Can be list[dict] or summarized dict
    user_message: str,
    action: str,
    action_reason: str,
    retrieved_context: str = "N/A"
) -> str:
    """
    Generate a response based on the router's classified action.

    Args:
        report_summary: The compressed report summary from DB
        conversation_context: Either full messages or summarized conversation
        user_message: The user's latest message
        action: The classified action from router LLM
        action_reason: Why the router chose this action
        retrieved_context: Content retrieved from vector DB (if applicable)

    Returns:
        str: The generated response text
    """
    try:
        response_prompt = ChatPromptTemplate.from_template(ACTION_RESPONSE_PROMPT)
        parser = StrOutputParser()
        chain = response_prompt | llm_response | parser

        input_dict = {
            "report_summary": report_summary,
            "conversation_context": conversation_context,
            "user_message": user_message,
            "action": action,
            "action_reason": action_reason,
            "retrieved_context": retrieved_context
        }

        response = await chain.ainvoke(input_dict)
        logger.info(f"Generated response for action: {action}")
        return response
    except Exception as e:
        logger.error(f"Error generating action response: {str(e)}")
        raise


def is_change_tracking_action(action: str) -> bool:
    """Check if the action should track changes instead of regenerating."""
    return action in CHANGE_TRACKING_ACTIONS


async def generate_change_acknowledgment(
    change_type: str,
    user_request: str,
    affected_sections: list,
    existing_pending_changes: list,
    change_id: str
) -> str:
    """
    Generate a response acknowledging a tracked change.

    Args:
        change_type: Type of change (modify_requirements, modify_architecture, etc.)
        user_request: The user's original request
        affected_sections: List of sections that will be affected
        existing_pending_changes: List of already pending changes
        change_id: The ID assigned to this change

    Returns:
        str: Acknowledgment response text
    """
    try:
        ack_prompt = ChatPromptTemplate.from_template(CHANGE_ACKNOWLEDGMENT_PROMPT)
        parser = StrOutputParser()
        chain = ack_prompt | llm_response | parser

        input_dict = {
            "change_type": change_type,
            "user_request": user_request,
            "affected_sections": affected_sections,
            "existing_pending_changes": existing_pending_changes,
            "change_id": change_id
        }

        response = await chain.ainvoke(input_dict)
        logger.info(f"Generated change acknowledgment for {change_id}")
        return response
    except Exception as e:
        logger.error(f"Error generating change acknowledgment: {str(e)}")
        raise


async def generate_conflict_resolution(
    conflicts: list,
    all_pending_changes: list
) -> str:
    """
    Generate a response asking user to resolve conflicts.

    Args:
        conflicts: List of detected conflicts
        all_pending_changes: All pending changes for context

    Returns:
        str: Conflict resolution prompt text
    """
    try:
        conflict_prompt = ChatPromptTemplate.from_template(CONFLICT_RESOLUTION_PROMPT)
        parser = StrOutputParser()
        chain = conflict_prompt | llm_response | parser

        input_dict = {
            "conflicts": conflicts,
            "all_pending_changes": all_pending_changes
        }

        response = await chain.ainvoke(input_dict)
        logger.info(f"Generated conflict resolution prompt for {len(conflicts)} conflicts")
        return response
    except Exception as e:
        logger.error(f"Error generating conflict resolution: {str(e)}")
        raise


async def generate_regeneration_plan(
    original_report_summary: dict,
    pending_changes: list,
    conversation_context: any
) -> dict:
    """
    Generate a plan for how to regenerate the report with pending changes.

    Args:
        original_report_summary: The current report summary
        pending_changes: List of changes to apply
        conversation_context: Conversation context for additional info

    Returns:
        dict: Regeneration plan with sections to update and instructions
    """
    try:
        regen_prompt = ChatPromptTemplate.from_template(REGENERATE_WITH_CHANGES_PROMPT)
        parser = JsonOutputParser()
        chain = regen_prompt | llm_router | parser

        input_dict = {
            "original_report_summary": original_report_summary,
            "pending_changes": pending_changes,
            "conversation_context": conversation_context
        }

        response = await chain.ainvoke(input_dict)
        logger.info(f"Generated regeneration plan for {len(pending_changes)} changes")
        return response
    except Exception as e:
        logger.error(f"Error generating regeneration plan: {str(e)}")
        raise
