from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from config import settings
from utils.prompts import (
    ROUTER_LLM_PROMPT,
    SUMMARIZE_CHATCONVERSATION_PROMPT,
    ACTION_RESPONSE_PROMPT,
    CHANGE_ACKNOWLEDGMENT_PROMPT,
    CONFLICT_RESOLUTION_PROMPT,
    REGENERATE_WITH_CHANGES_PROMPT,
    HYBRID_INTENT_CLASSIFIER_PROMPT,
    HYBRID_RESPONSE_PROMPT,
    MULTI_INTENT_CLASSIFIER_PROMPT,
    SEMANTIC_INTENT_CLASSIFIER_PROMPT,
    ARCHITECTURE_DEFENSE_PROMPT
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


# ============================================================
# MULTI-PART REQUEST DETECTION & CLARIFICATION
# ============================================================

import re

# Multi-part indicators
MULTI_PART_INDICATORS = [
    " and ", " also ", " plus ", " as well as ",
    " additionally ", " furthermore ", " then "
]

# Change keywords for classifying parts
CHANGE_KEYWORDS = {
    "modify_architecture": ["use", "switch", "replace", "change to", "migrate", "instead of"],
    "modify_requirements": ["add", "remove", "include", "exclude", "need", "want", "require"],
    "correct_assumptions": ["actually", "not", "incorrect", "wrong", "should be", "is not"],
}


def detect_multi_part_request(user_message: str) -> dict:
    """
    Detect if message contains multiple distinct requests.

    Args:
        user_message: The user's message

    Returns:
        {
            "is_multi_part": bool,
            "parts": [
                {"text": "use PostgreSQL", "likely_action": "modify_architecture"},
                {"text": "add real-time messaging", "likely_action": "modify_requirements"}
            ]
        }
    """
    # Check for multi-part indicators
    has_indicator = any(ind in user_message.lower() for ind in MULTI_PART_INDICATORS)

    if not has_indicator:
        return {"is_multi_part": False, "parts": []}

    # Split on common conjunctions
    segments = re.split(r'\s+and\s+|\s*,\s+|\s+also\s+|\s+plus\s+', user_message, flags=re.IGNORECASE)

    parts = []
    for segment in segments:
        segment = segment.strip()
        if len(segment) < 5:  # Too short to be meaningful
            continue

        # Determine likely action
        likely_action = "general_discussion"
        segment_lower = segment.lower()

        for action, keywords in CHANGE_KEYWORDS.items():
            if any(kw in segment_lower for kw in keywords):
                likely_action = action
                break

        # Only include parts that are likely change requests
        if likely_action != "general_discussion":
            parts.append({
                "text": segment,
                "likely_action": likely_action
            })

    # Only consider it multi-part if we found at least 2 change requests
    return {
        "is_multi_part": len(parts) > 1,
        "parts": parts
    }


def needs_clarification(user_message: str) -> bool:
    """
    Check if message is too vague to process and needs clarification.

    Args:
        user_message: The user's message

    Returns:
        bool: True if clarification is needed
    """
    # Vague patterns that need clarification
    vague_patterns = [
        r"^change\s+(?:the|it|this|that)?\s*$",
        r"^update\s+(?:the|it|this|that)?\s*$",
        r"^modify\s+(?:the|it|this|that)?\s*$",
        r"^fix\s+(?:the|it|this|that)?\s*$",
        r"^change\s+(?:the\s+)?database\s*$",
        r"^use\s+(?:a\s+)?different\s*$",
        r"^switch\s+(?:the|it|this)?\s*$",
    ]

    user_lower = user_message.lower().strip()

    # Very short messages often need clarification
    if len(user_message.split()) <= 2:
        # Exception: simple commands that are clear
        clear_short_commands = ["help", "undo", "cancel", "clear", "export", "history"]
        if not any(cmd in user_lower for cmd in clear_short_commands):
            return True

    for pattern in vague_patterns:
        if re.match(pattern, user_lower):
            return True

    return False


def get_clarification_question(user_message: str) -> str:
    """
    Generate an appropriate clarification question based on the vague message.

    Args:
        user_message: The user's vague message

    Returns:
        str: A clarification question
    """
    user_lower = user_message.lower()

    clarification_prompts = {
        "database": "Which database would you like to use? For example:\n- PostgreSQL\n- MongoDB\n- MySQL\n- DynamoDB",
        "cloud": "Which cloud provider should we use?\n- AWS\n- Azure\n- GCP (Google Cloud)",
        "change": "What specifically would you like to change? For example:\n- Technology or tool changes\n- Add/remove features\n- Correct an assumption",
        "default": "Could you provide more details about what you'd like to change?\n\nFor example:\n- 'Use PostgreSQL instead of MongoDB'\n- 'Add real-time messaging'\n- 'The user count should be 50,000'"
    }

    if "database" in user_lower or "db" in user_lower:
        return clarification_prompts["database"]
    elif "cloud" in user_lower or "host" in user_lower or "deploy" in user_lower:
        return clarification_prompts["cloud"]
    elif "change" in user_lower or "update" in user_lower or "modify" in user_lower:
        return clarification_prompts["change"]
    else:
        return clarification_prompts["default"]


# ============================================================
# HYBRID INTENT CLASSIFICATION & CONTEXT MANAGEMENT
# ============================================================

# Constants for hybrid context window
RECENT_MESSAGE_COUNT = 5
OLDER_SUMMARY_TOKEN_THRESHOLD = 2000


async def build_hybrid_context(conversation: list[dict]) -> dict:
    """
    Build a hybrid context with:
    - Summarized older messages (if any and if > threshold)
    - Last 5 messages verbatim (recent context)

    This approach ensures:
    1. Recent conversation context is preserved exactly
    2. Older context is compressed to save tokens
    3. LLM always has enough context to understand conversation flow

    Args:
        conversation: List of message dicts with 'role' and 'content'

    Returns:
        {
            "older_summary": dict or list or None,
            "recent_messages": list[dict],
            "context_type": "full" | "hybrid" | "recent_only"
        }
    """
    if not conversation:
        return {
            "older_summary": None,
            "recent_messages": [],
            "context_type": "recent_only"
        }

    # If conversation is small enough, keep it all
    if len(conversation) <= RECENT_MESSAGE_COUNT:
        return {
            "older_summary": None,
            "recent_messages": conversation,
            "context_type": "recent_only"
        }

    # Split into older and recent
    older_messages = conversation[:-RECENT_MESSAGE_COUNT]
    recent_messages = conversation[-RECENT_MESSAGE_COUNT:]

    # Check if older messages need summarization
    older_token_count = await count_token(older_messages)

    if older_token_count > OLDER_SUMMARY_TOKEN_THRESHOLD:
        # Summarize older messages
        try:
            older_summary = await conversation_summary_llm(older_messages)
            logger.info(f"Summarized {len(older_messages)} older messages ({older_token_count} tokens)")
        except Exception as e:
            logger.warning(f"Failed to summarize older messages: {str(e)}")
            # Fall back to keeping older messages as-is
            older_summary = older_messages
    else:
        # Keep older messages verbatim if small enough
        older_summary = older_messages

    return {
        "older_summary": older_summary,
        "recent_messages": recent_messages,
        "context_type": "hybrid"
    }


async def classify_hybrid_intent(
    user_message: str,
    hybrid_context: dict,
    report_summary: dict
) -> dict:
    """
    Classify if a user message contains a question, suggestion, or both (hybrid).

    This runs on EVERY message to detect:
    - Pure questions about the report
    - Explicit suggestions for changes
    - Implicit suggestions embedded in questions
    - Hybrid queries that need both answering AND tracking

    Args:
        user_message: The user's latest message
        hybrid_context: Context from build_hybrid_context()
        report_summary: The compressed report summary

    Returns:
        {
            "has_question": bool,
            "question_content": str or None,
            "question_topic": str or None,
            "has_suggestion": bool,
            "suggestion_type": "explicit" | "implicit" | None,
            "suggestion_content": str or None,
            "suggestion_category": "modify_architecture" | "modify_requirements" | "correct_assumptions" | None,
            "is_hybrid": bool,
            "reasoning": str
        }
    """
    try:
        intent_prompt = ChatPromptTemplate.from_template(HYBRID_INTENT_CLASSIFIER_PROMPT)
        parser = JsonOutputParser()
        chain = intent_prompt | llm_router | parser

        # Format recent messages for the prompt with emphasis on last assistant message
        recent_msgs_formatted = ""
        messages = hybrid_context.get("recent_messages", [])

        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:1000]  # Increased from 500 for better context

            # Format messages neutrally - let LLM determine context naturally
            if role == "assistant" and i == len(messages) - 1:
                recent_msgs_formatted += f"\n[PREVIOUS ASSISTANT MESSAGE]\n"
                recent_msgs_formatted += f"assistant: {content}\n"
                recent_msgs_formatted += f"[END PREVIOUS MESSAGE]\n\n"
            else:
                recent_msgs_formatted += f"{role}: {content}\n"

        input_dict = {
            "report_summary": report_summary,
            "recent_messages": recent_msgs_formatted if recent_msgs_formatted else "No previous messages",
            "user_message": user_message,
            "pending_actions": "None"  # Required by MULTI_INTENT_CLASSIFIER_PROMPT
        }

        response = await chain.ainvoke(input_dict)
        logger.info(f"Hybrid intent classification: is_hybrid={response.get('is_hybrid', False)}")
        return response

    except Exception as e:
        logger.error(f"Error in hybrid intent classification: {str(e)}")
        # Return safe default - treat as general discussion
        return {
            "has_question": False,
            "question_content": None,
            "question_topic": None,
            "has_suggestion": False,
            "suggestion_type": None,
            "suggestion_content": None,
            "suggestion_category": None,
            "is_hybrid": False,
            "reasoning": f"Classification failed: {str(e)}"
        }


async def generate_hybrid_response(
    report_summary: dict,
    hybrid_context: dict,
    user_message: str,
    intent: dict,
    retrieved_context: str = "N/A"
) -> str:
    """
    Generate a response for hybrid queries that:
    1. Answers the question FIRST using report context
    2. Acknowledges the suggestion
    3. Asks if user wants to track the suggestion as a requirement

    Args:
        report_summary: Compressed report summary
        hybrid_context: Context from build_hybrid_context()
        user_message: The user's latest message
        intent: Classification result from classify_hybrid_intent()
        retrieved_context: Optional vector-retrieved content for answering

    Returns:
        str: The composite response text
    """
    try:
        response_prompt = ChatPromptTemplate.from_template(HYBRID_RESPONSE_PROMPT)
        parser = StrOutputParser()
        chain = response_prompt | llm_response | parser

        # Format recent messages
        recent_msgs_formatted = ""
        for msg in hybrid_context.get("recent_messages", []):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:500]
            recent_msgs_formatted += f"{role}: {content}\n"

        input_dict = {
            "report_summary": report_summary,
            "recent_messages": recent_msgs_formatted if recent_msgs_formatted else "No previous messages",
            "user_message": user_message,
            "question_content": intent.get("question_content", user_message),
            "suggestion_content": intent.get("suggestion_content", ""),
            "retrieved_context": retrieved_context
        }

        response = await chain.ainvoke(input_dict)
        logger.info(f"Generated hybrid response for question + suggestion")
        return response

    except Exception as e:
        logger.error(f"Error generating hybrid response: {str(e)}")
        raise


# ============================================================
# MULTI-INTENT CLASSIFICATION WITH PENDING ACTIONS
# ============================================================

def extract_pending_actions(messages: list, max_pending: int = 5) -> list:
    """
    Extract ALL pending actions from recent messages.

    FIXED: Now collects ALL pending actions instead of stopping at the first one.
    This is critical for handling "yes to both" and similar confirmations.

    Searches through recent assistant messages for:
    - pending_suggestion fields (from hybrid responses)
    - Rollback confirmation prompts
    - Clear all changes prompts
    - Other pending confirmations

    Args:
        messages: List of recent message dicts (typically last 10)
        max_pending: Maximum number of pending actions to collect (default 5)

    Returns:
        list: List of pending actions, each with 'type', 'content', 'source', and 'message_index'
    """
    import re
    pending = []
    seen_contents = set()  # Track unique contents to avoid duplicates
    assistant_count = 0

    for idx, msg in enumerate(reversed(messages)):
        if msg.get("role") != "assistant":
            continue

        assistant_count += 1
        original_idx = len(messages) - 1 - idx  # Index in original list

        # Check for pending_suggestion field (from hybrid responses)
        ps = msg.get("pending_suggestion", {})
        if ps and ps.get("awaiting_confirmation"):
            content = ps.get("content", "")
            # Avoid duplicates
            if content and content not in seen_contents:
                pending.append({
                    "type": ps.get("category", "modify_architecture"),
                    "content": content,
                    "source": "hybrid_suggestion",
                    "original_suggestion": ps,
                    "message_index": original_idx
                })
                seen_contents.add(content)
            # DON'T break - continue to find more pending actions

        # Check for rollback confirmation in content
        content = msg.get("content", "")
        if "CONFIRM ROLLBACK" in content.upper() or "confirm rollback" in content.lower():
            version_match = re.search(r'version\s*(\d+)', content, re.IGNORECASE)
            version = version_match.group(1) if version_match else "unknown"
            rollback_content = f"Rollback to version {version}"
            if rollback_content not in seen_contents:
                pending.append({
                    "type": "rollback_to_version",
                    "content": rollback_content,
                    "source": "rollback_confirmation",
                    "version": version,
                    "message_index": original_idx
                })
                seen_contents.add(rollback_content)
            # DON'T break - continue to find more

        # Check for clear all changes confirmation
        elif "clear all changes" in content.lower() or "discard all" in content.lower():
            if "?" in content or "confirm" in content.lower():
                clear_content = "Clear all pending changes"
                if clear_content not in seen_contents:
                    pending.append({
                        "type": "clear_all_changes",
                        "content": clear_content,
                        "source": "clear_confirmation",
                        "message_index": original_idx
                    })
                    seen_contents.add(clear_content)
                # DON'T break - continue to find more

        # Check for general confirmation prompts (only if no specific pending found in this message)
        elif "would you like me to" in content.lower() and "?" in content:
            # Don't add generic offers if we already have this message's pending_suggestion
            if not ps or not ps.get("awaiting_confirmation"):
                offer_content = content[:200]
                if offer_content not in seen_contents:
                    pending.append({
                        "type": "pending_offer",
                        "content": offer_content,
                        "source": "assistant_offer",
                        "message_index": original_idx
                    })
                    seen_contents.add(offer_content)
            # DON'T break - continue to find more

        # Stop after checking max_pending assistant messages or if we have enough
        if len(pending) >= max_pending or assistant_count >= 10:
            break

    return pending


async def classify_multi_intent(
    user_message: str,
    hybrid_context: dict,
    report_summary: dict,
    pending_actions: list = None
) -> dict:
    """
    Classify all intents in a user message, including confirmation detection.

    This is an enhanced version of classify_hybrid_intent that:
    1. Checks for pending actions that may be confirmed/declined
    2. Identifies multiple intents in a single message
    3. Prioritizes intents for sequential processing
    4. Returns actionable classification for the processing flow

    Args:
        user_message: The user's latest message
        hybrid_context: Context from build_hybrid_context()
        report_summary: The compressed report summary
        pending_actions: List of pending actions from extract_pending_actions()

    Returns:
        dict: Classification with intents, primary_intent, and pending_action_to_execute
    """
    if pending_actions is None:
        pending_actions = []

    try:
        intent_prompt = ChatPromptTemplate.from_template(MULTI_INTENT_CLASSIFIER_PROMPT)
        parser = JsonOutputParser()
        chain = intent_prompt | llm_router | parser

        # Format recent messages for the prompt with emphasis on last assistant message
        recent_msgs_formatted = ""
        messages = hybrid_context.get("recent_messages", [])

        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:1000]  # Increased from 500 for better context

            # Format messages neutrally - let LLM determine context naturally
            # The last assistant message is typically the last one before the current user message
            if role == "assistant" and i == len(messages) - 1:
                recent_msgs_formatted += f"\n[PREVIOUS ASSISTANT MESSAGE]\n"
                recent_msgs_formatted += f"assistant: {content}\n"
                recent_msgs_formatted += f"[END PREVIOUS MESSAGE]\n\n"
            else:
                recent_msgs_formatted += f"{role}: {content}\n"

        # Format pending actions for the prompt
        pending_actions_formatted = "None"
        if pending_actions:
            pending_actions_formatted = str(pending_actions)

        input_dict = {
            "report_summary": report_summary,
            "recent_messages": recent_msgs_formatted if recent_msgs_formatted else "No previous messages",
            "pending_actions": pending_actions_formatted,
            "user_message": user_message
        }

        response = await chain.ainvoke(input_dict)

        # Log the classification result
        primary_intent = response.get("primary_intent", "unknown")
        has_pending = response.get("has_pending_action", False)
        logger.info(f"Multi-intent classification: primary={primary_intent}, has_pending={has_pending}, intents={len(response.get('intents', []))}")

        return response

    except Exception as e:
        logger.error(f"Error in multi-intent classification: {str(e)}")
        # Return safe default - treat as general discussion
        return {
            "intents": [{
                "type": "question",
                "content": user_message,
                "action": "general_discussion",
                "requires_confirmation": False,
                "priority": 1
            }],
            "primary_intent": "question",
            "has_pending_action": False,
            "pending_action_to_execute": None,
            "reasoning": f"Classification failed, defaulting to general discussion: {str(e)}"
        }


def is_short_affirmative(message: str) -> bool:
    """Check if message is a short affirmative response."""
    affirmatives = [
        "yes", "yeah", "yep", "yup", "ok", "okay", "sure",
        "go ahead", "do it", "proceed", "confirm", "please",
        "alright", "right", "correct", "absolutely", "definitely"
    ]
    msg_lower = message.lower().strip()
    words = msg_lower.split()

    # Must be short (1-5 words)
    if len(words) > 5:
        return False

    return any(aff in msg_lower for aff in affirmatives)


def is_short_negative(message: str) -> bool:
    """Check if message is a short negative response."""
    negatives = [
        "no", "nope", "nah", "skip", "cancel", "nevermind",
        "never mind", "stop", "don't", "dont", "not now"
    ]
    msg_lower = message.lower().strip()
    words = msg_lower.split()

    # Must be short (1-5 words)
    if len(words) > 5:
        return False

    return any(neg in msg_lower for neg in negatives)


# ============================================================
# UNIFIED INTENT CLASSIFICATION
# ============================================================

async def classify_unified_intent(
    user_message: str,
    hybrid_context: dict,
    report_summary: dict,
    pending_actions: list = None,
    last_assistant_message: str = None
) -> dict:
    """
    UNIFIED classification function that detects ALL intents in a single LLM call.

    This replaces the separate calls to:
    - classify_hybrid_intent() (which passed pending_actions="None")
    - classify_multi_intent() (which was only called if pending_actions existed)

    Key improvements:
    1. ALWAYS passes pending_actions for context
    2. Detects ALL intents (questions, suggestions, confirmations, commands)
    3. Returns structured list with priorities
    4. Handles "yes, and also add X" correctly

    Args:
        user_message: The user's latest message
        hybrid_context: Context from build_hybrid_context()
        report_summary: The compressed report summary
        pending_actions: List of pending actions (ALWAYS pass this!)
        last_assistant_message: Optional - the previous assistant message for clarification detection

    Returns:
        {
            "intents": [
                {
                    "type": "question|explicit_suggestion|implicit_suggestion|confirmation|decline|command|clarification_response",
                    "content": "...",
                    "action": "...",
                    "priority": 1|2|3,
                    "requires_confirmation": bool
                }
            ],
            "primary_intent": "...",
            "is_hybrid": bool,
            "has_question": bool,
            "has_suggestion": bool,
            "pending_actions_to_confirm": [...],
            "is_continuation": bool,
            "continuation_context": {...} or None,
            "reasoning": "..."
        }
    """
    if pending_actions is None:
        pending_actions = []

    try:
        intent_prompt = ChatPromptTemplate.from_template(MULTI_INTENT_CLASSIFIER_PROMPT)
        parser = JsonOutputParser()
        chain = intent_prompt | llm_router | parser

        # Format recent messages
        recent_msgs_formatted = ""
        messages = hybrid_context.get("recent_messages", [])

        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:1000]

            if role == "assistant" and i == len(messages) - 1:
                recent_msgs_formatted += f"\n[PREVIOUS ASSISTANT MESSAGE]\n"
                recent_msgs_formatted += f"assistant: {content}\n"
                recent_msgs_formatted += f"[END PREVIOUS MESSAGE]\n\n"
            else:
                recent_msgs_formatted += f"{role}: {content}\n"

        # ALWAYS format pending actions (never "None" if we have any)
        pending_actions_formatted = "None"
        if pending_actions:
            # Format for better LLM understanding
            formatted_list = []
            for i, pa in enumerate(pending_actions):
                formatted_list.append({
                    "index": i,
                    "type": pa.get("type", "unknown"),
                    "content": pa.get("content", ""),
                    "source": pa.get("source", "unknown")
                })
            pending_actions_formatted = str(formatted_list)

        input_dict = {
            "report_summary": report_summary,
            "recent_messages": recent_msgs_formatted if recent_msgs_formatted else "No previous messages",
            "pending_actions": pending_actions_formatted,
            "user_message": user_message
        }

        response = await chain.ainvoke(input_dict)

        # Enrich the response with additional computed fields
        intents = response.get("intents", [])
        intent_types = [i.get("type", "") for i in intents]

        # Compute hybrid-related flags
        has_question = any(t == "question" for t in intent_types)
        has_suggestion = any(t in ["explicit_suggestion", "implicit_suggestion"] for t in intent_types)
        has_confirmation = any(t == "confirmation" for t in intent_types)
        is_hybrid = has_question and has_suggestion

        # Extract suggestion details for backward compatibility
        question_intent = next((i for i in intents if i.get("type") == "question"), None)
        suggestion_intent = next((i for i in intents if i.get("type") in ["explicit_suggestion", "implicit_suggestion"]), None)

        # Determine which pending actions should be confirmed
        pending_actions_to_confirm = []
        if has_confirmation and pending_actions:
            # Check if user is confirming all ("yes to both") or specific one
            user_lower = user_message.lower()
            if "both" in user_lower or "all" in user_lower:
                pending_actions_to_confirm = pending_actions
            else:
                # Default to most recent pending action
                pending_actions_to_confirm = [pending_actions[0]] if pending_actions else []

        # Build enriched response
        enriched_response = {
            **response,
            "is_hybrid": is_hybrid,
            "has_question": has_question,
            "has_suggestion": has_suggestion,
            "has_confirmation": has_confirmation,
            "question_content": question_intent.get("content", "") if question_intent else "",
            "suggestion_content": suggestion_intent.get("content", "") if suggestion_intent else "",
            "suggestion_type": suggestion_intent.get("type", "") if suggestion_intent else "",
            "suggestion_category": suggestion_intent.get("action", "modify_architecture") if suggestion_intent else "",
            "pending_actions_to_confirm": pending_actions_to_confirm,
            "pending_actions_provided": len(pending_actions)
        }

        logger.info(f"Unified classification: primary={enriched_response.get('primary_intent')}, "
                   f"is_hybrid={is_hybrid}, has_confirmation={has_confirmation}, "
                   f"intents={len(intents)}, pending_to_confirm={len(pending_actions_to_confirm)}")

        return enriched_response

    except Exception as e:
        logger.error(f"Error in unified intent classification: {str(e)}")
        # Return safe default
        return {
            "intents": [{
                "type": "question",
                "content": user_message,
                "action": "general_discussion",
                "requires_confirmation": False,
                "priority": 1
            }],
            "primary_intent": "question",
            "is_hybrid": False,
            "has_question": True,
            "has_suggestion": False,
            "has_confirmation": False,
            "pending_actions_to_confirm": [],
            "pending_actions_provided": len(pending_actions) if pending_actions else 0,
            "reasoning": f"Classification failed, defaulting to general discussion: {str(e)}"
        }


async def process_intents_by_priority(
    intents: list,
    pending_actions: list,
    context: dict,
    chat_history_id: str,
    db
) -> dict:
    """
    Process all detected intents in priority order.

    Priority order:
    1. Confirmations (handle pending actions first)
    2. Questions (need to be answered)
    3. Explicit suggestions (auto-track)
    4. Implicit suggestions (offer to track)
    5. Commands (execute)

    Args:
        intents: List of classified intents
        pending_actions: List of pending actions to potentially confirm
        context: Contains report_summary, hybrid_context, etc.
        chat_history_id: For database operations
        db: Database session

    Returns:
        {
            "confirmation_results": [...],
            "question_results": [...],
            "suggestion_results": [...],
            "command_results": [...],
            "tracked_changes": [...],
            "pending_suggestions": [...]  # Implicit suggestions awaiting confirmation
        }
    """
    results = {
        "confirmation_results": [],
        "question_results": [],
        "suggestion_results": [],
        "command_results": [],
        "tracked_changes": [],
        "pending_suggestions": []
    }

    # Sort intents by priority
    priority_map = {
        "confirmation": 1,
        "decline": 1,
        "question": 2,
        "explicit_suggestion": 3,
        "implicit_suggestion": 4,
        "command": 5,
        "clarification_response": 2
    }

    sorted_intents = sorted(intents, key=lambda x: priority_map.get(x.get("type", ""), 10))

    for intent in sorted_intents:
        intent_type = intent.get("type", "")

        if intent_type == "confirmation":
            # Track all pending actions that user is confirming
            for pa in pending_actions:
                results["confirmation_results"].append({
                    "action": "confirmed",
                    "content": pa.get("content", ""),
                    "type": pa.get("type", "modify_architecture")
                })
                results["tracked_changes"].append(pa)

        elif intent_type == "decline":
            results["confirmation_results"].append({
                "action": "declined",
                "content": "User declined pending suggestion"
            })

        elif intent_type == "question":
            results["question_results"].append({
                "content": intent.get("content", ""),
                "needs_answer": True
            })

        elif intent_type == "explicit_suggestion":
            # Auto-track explicit suggestions
            results["suggestion_results"].append({
                "content": intent.get("content", ""),
                "action": intent.get("action", "modify_architecture"),
                "auto_track": True
            })
            results["tracked_changes"].append({
                "type": intent.get("action", "modify_architecture"),
                "content": intent.get("content", ""),
                "source": "explicit_suggestion"
            })

        elif intent_type == "implicit_suggestion":
            # Don't auto-track, offer to track
            results["suggestion_results"].append({
                "content": intent.get("content", ""),
                "action": intent.get("action", "modify_architecture"),
                "auto_track": False
            })
            results["pending_suggestions"].append({
                "content": intent.get("content", ""),
                "category": intent.get("action", "modify_architecture"),
                "awaiting_confirmation": True
            })

        elif intent_type == "command":
            results["command_results"].append({
                "command": intent.get("action", ""),
                "content": intent.get("content", "")
            })

        elif intent_type == "clarification_response":
            # Treat as tracked change based on context
            results["suggestion_results"].append({
                "content": intent.get("content", ""),
                "action": intent.get("action", "modify_architecture"),
                "auto_track": True,
                "from_clarification": True
            })

    return results


def get_last_assistant_message(chat_context: dict) -> str:
    """
    Extract the last assistant message from chat context.

    Args:
        chat_context: The full chat context dict

    Returns:
        str: The content of the last assistant message, or empty string
    """
    messages = chat_context.get("message", [])
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg.get("content", "")
    return ""


# ============================================================
# SEMANTIC INTENT CLASSIFICATION (Replaces keyword-based)
# ============================================================


async def classify_semantic_intent(
    user_message: str,
    pending_actions: list,
    report_summary: dict,
    recent_messages: list
) -> dict:
    """
    Semantic intent classification that understands MEANING, not keywords.

    This is the new classification function that replaces keyword-based
    detection with LLM-based semantic understanding.

    Key improvements:
    1. No hardcoded word lists (no "yes", "yeah", "yep" matching)
    2. Pending actions passed WITH IDs for explicit mapping
    3. Distinguishes architecture_challenge from question
    4. Handles compound intents (yes, but...)
    5. Returns confirmation_map with specific action IDs

    Args:
        user_message: The user's latest message
        pending_actions: List of pending actions with IDs (from ConversationState)
        report_summary: The compressed report summary
        recent_messages: Recent conversation messages

    Returns:
        {
            "intents": [...],
            "primary_intent": str,
            "confirmation_map": {"PA-001": "confirmed|declined"},
            "requires_architecture_defense": bool,
            "defense_topic": str or None,
            "primary_response_strategy": str,
            "reasoning": str
        }
    """
    try:
        intent_prompt = ChatPromptTemplate.from_template(SEMANTIC_INTENT_CLASSIFIER_PROMPT)
        parser = JsonOutputParser()
        chain = intent_prompt | llm_router | parser

        # Format recent messages for context
        recent_msgs_formatted = ""
        for msg in recent_messages[-5:]:  # Last 5 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:800]
            recent_msgs_formatted += f"{role}: {content}\n"

        # Format pending actions with IDs
        pending_formatted = "None"
        if pending_actions:
            formatted = []
            for pa in pending_actions:
                formatted.append({
                    "id": pa.get("action_id") or pa.get("id", "unknown"),
                    "type": pa.get("action_type") or pa.get("type", "suggestion"),
                    "content": pa.get("content", ""),
                    "category": pa.get("category", "")
                })
            pending_formatted = str(formatted)

        input_dict = {
            "report_summary": str(report_summary)[:3000],
            "recent_messages": recent_msgs_formatted or "No previous messages",
            "pending_actions": pending_formatted,
            "user_message": user_message
        }

        response = await chain.ainvoke(input_dict)

        # Ensure required fields exist
        if "intents" not in response:
            response["intents"] = []
        if "primary_intent" not in response:
            response["primary_intent"] = "question"
        if "confirmation_map" not in response:
            response["confirmation_map"] = {}
        if "requires_architecture_defense" not in response:
            response["requires_architecture_defense"] = False
        if "primary_response_strategy" not in response:
            # Derive from primary_intent
            strategy_map = {
                "confirmation": "confirm_action",
                "decline": "decline_action",
                "architecture_challenge": "defend_architecture",
                "question": "answer_question",
                "explicit_suggestion": "track_change",
                "implicit_suggestion": "track_change",
                "command": "process_command"
            }
            response["primary_response_strategy"] = strategy_map.get(
                response["primary_intent"], "answer_question"
            )

        # Add user_message to response for handlers
        response["user_message"] = user_message

        logger.info(f"Semantic classification: primary={response.get('primary_intent')}, "
                   f"strategy={response.get('primary_response_strategy')}, "
                   f"defense={response.get('requires_architecture_defense')}")

        return response

    except Exception as e:
        logger.error(f"Error in semantic classification: {str(e)}")
        # Safe default
        return {
            "intents": [{
                "type": "question",
                "content": user_message,
                "action": "general_discussion",
                "priority": 1
            }],
            "primary_intent": "question",
            "confirmation_map": {},
            "requires_architecture_defense": False,
            "defense_topic": None,
            "primary_response_strategy": "answer_question",
            "user_message": user_message,
            "reasoning": f"Classification failed: {str(e)}"
        }


async def generate_architecture_defense(
    report_summary: dict,
    challenge_topic: str,
    user_message: str,
    architecture_context: str,
    trade_offs: str,
    recent_messages: list
) -> str:
    """
    Generate a response defending an architecture decision.

    Called when the semantic classifier detects an architecture_challenge
    intent. Explains WHY the choice was made with specific reasoning.

    Args:
        report_summary: The full report summary
        challenge_topic: What specifically is being challenged
        user_message: The user's original message
        architecture_context: Relevant architecture details
        trade_offs: Trade-offs that were considered
        recent_messages: Recent conversation for context

    Returns:
        str: A natural, conversational defense response
    """
    try:
        defense_prompt = ChatPromptTemplate.from_template(ARCHITECTURE_DEFENSE_PROMPT)
        parser = StrOutputParser()
        chain = defense_prompt | llm_response | parser

        # Format recent messages
        recent_formatted = ""
        for msg in recent_messages[-3:]:
            role = msg.get("role", "")
            content = msg.get("content", "")[:500]
            recent_formatted += f"{role}: {content}\n"

        input_dict = {
            "challenge_topic": challenge_topic,
            "user_message": user_message,
            "architecture_context": architecture_context or "Not specified in report",
            "trade_offs": trade_offs or "Trade-offs were considered during design",
            "report_summary": str(report_summary)[:2000],
            "recent_messages": recent_formatted or "No recent messages"
        }

        response = await chain.ainvoke(input_dict)
        logger.info(f"Generated architecture defense for: {challenge_topic}")
        return response

    except Exception as e:
        logger.error(f"Error generating architecture defense: {str(e)}")
        # Fallback response
        return f"That's a good question about {challenge_topic}. The current design was chosen based on the requirements and trade-offs considered during analysis. Would you like me to explain the specific reasoning, or would you prefer to track this as a potential modification?"
