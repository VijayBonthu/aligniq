"""
LangChain-based chat agent with tool calling for /chat-with-doc endpoint.

This module provides a tool-calling agent that replaces the current
2-step classification-then-execute architecture with a single LLM
call that can orchestrate multi-step operations using tools.
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage
)
from typing import Dict, Any, List, Optional
import json
from config import settings
from utils.chat_tools import get_all_tools, tool_context, TOOL_SYSTEM_PROMPT
from utils.logger import logger


class ToolChatAgent:
    """
    Chat agent that uses LangChain tools for document interaction.

    This agent binds tools to the LLM and handles the tool-calling loop,
    allowing the LLM to decide which tools to call and in what order.
    """

    def __init__(self, chat_history_id: str, db, user_id: str = None):
        """
        Initialize the tool chat agent.

        Args:
            chat_history_id: The chat history ID for the current conversation
            db: Database session for tool operations
            user_id: The user ID for operations that require it (e.g., regenerate_report)
        """
        self.chat_history_id = chat_history_id
        self.db = db
        self.user_id = user_id

        # Set context for tools to access
        tool_context.chat_history_id = chat_history_id
        tool_context.db = db
        tool_context.user_id = user_id

        # Initialize tools and create tool map for execution
        self.tools = get_all_tools()
        self.tool_map = {tool.name: tool for tool in self.tools}

        # Initialize LLM with tools bound
        self.llm = ChatOpenAI(
            model=settings.SUMMARIZATION_MODEL or "gpt-4o-mini",
            temperature=0.3,
            api_key=settings.OPENAI_CHATGPT
        ).bind_tools(self.tools)

        logger.info(f"ToolChatAgent initialized with {len(self.tools)} tools for chat {chat_history_id}")

    async def chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict]] = None,
        report_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process user message with tool calling.

        The LLM will decide which tools to call based on the user's request,
        execute them, and formulate a response.

        Args:
            user_message: The user's message
            conversation_history: Optional list of previous messages
            report_context: Optional summary of the current report for context

        Returns:
            Dict with:
                - response: The assistant's response text
                - tools_called: List of tools that were called
                - iterations: Number of LLM calls made
                - action: Optional action flag (e.g., "regenerate_triggered")
        """
        # Build initial messages
        messages = self._build_messages(user_message, conversation_history, report_context)

        # Track tool calls for response metadata
        tools_called = []
        max_iterations = 10  # Prevent infinite loops
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                # Call LLM
                response = await self.llm.ainvoke(messages)
            except Exception as e:
                logger.error(f"LLM call error in iteration {iteration}: {str(e)}")
                return {
                    "response": "I encountered an error processing your request. Please try again.",
                    "tools_called": tools_called,
                    "iterations": iteration,
                    "error": str(e)
                }

            # Check for tool calls
            if not response.tool_calls:
                # No more tool calls - return final response
                logger.info(f"Chat completed in {iteration} iteration(s), {len(tools_called)} tool calls")
                return {
                    "response": response.content or "I've processed your request.",
                    "tools_called": tools_called,
                    "iterations": iteration
                }

            # Process tool calls
            messages.append(response)  # Add AI message with tool calls

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                logger.info(f"Executing tool: {tool_name} with args: {json.dumps(tool_args)[:200]}")
                tools_called.append({"tool": tool_name, "args": tool_args})

                # Execute tool
                result = await self._execute_tool(tool_name, tool_args)

                # Add tool result to messages
                messages.append(ToolMessage(
                    content=result,
                    tool_call_id=tool_call["id"]
                ))

        # Max iterations reached
        logger.warning(f"Max iterations ({max_iterations}) reached for chat {self.chat_history_id}")
        return {
            "response": "I've processed multiple steps but reached my limit. Here's what I found so far.",
            "tools_called": tools_called,
            "iterations": iteration,
            "warning": "max_iterations_reached"
        }

    def _build_messages(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict]] = None,
        report_context: Optional[str] = None
    ) -> List:
        """Build the initial message list for the LLM."""
        messages = []

        # System prompt with optional report context
        system_content = TOOL_SYSTEM_PROMPT
        if report_context:
            system_content += f"\n\n## Current Report Context\n{report_context}"

        messages.append(SystemMessage(content=system_content))

        # Add conversation history (last 5 messages for context)
        if conversation_history:
            for msg in conversation_history[-5:]:
                role = msg.get("role", "")
                content = msg.get("content", "")

                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        # Add current user message
        messages.append(HumanMessage(content=user_message))

        return messages

    async def _execute_tool(self, tool_name: str, tool_args: Dict) -> str:
        """Execute a tool and return its result as a string."""
        try:
            tool = self.tool_map.get(tool_name)

            if not tool:
                logger.error(f"Unknown tool: {tool_name}")
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

            # Execute the tool (all our tools are async)
            result = await tool.ainvoke(tool_args)

            return result

        except Exception as e:
            logger.error(f"Tool execution error: {tool_name} - {str(e)}")
            return json.dumps({"error": f"Tool error: {str(e)}"})


async def chat_with_doc_v2(
    chat_history_id: str,
    user_message: str,
    db,
    conversation_history: Optional[List[Dict]] = None,
    report_context: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tool-based chat endpoint using LangChain.

    This is a drop-in replacement for the current chat_with_doc implementation.
    Instead of classifying intent and routing to handlers, it uses LLM tool
    calling to let the model decide what actions to take.

    Args:
        chat_history_id: The chat history ID
        user_message: The user's message
        db: Database session
        conversation_history: Optional list of previous messages
        report_context: Optional report summary for context
        user_id: The user ID for operations that require it (e.g., regenerate_report)

    Returns:
        Dict with response, tools_called, and optional action flag
    """
    try:
        agent = ToolChatAgent(chat_history_id, db, user_id=user_id)
        result = await agent.chat(user_message, conversation_history, report_context)

        # Check if regeneration was triggered
        if any(tc.get("tool") == "regenerate_report" for tc in result.get("tools_called", [])):
            result["action"] = "regenerate_triggered"

        # Check if clear all was triggered with confirmation
        clear_all_calls = [tc for tc in result.get("tools_called", [])
                          if tc.get("tool") == "clear_all_pending_changes"]
        for call in clear_all_calls:
            if call.get("args", {}).get("confirmed"):
                result["action"] = "changes_cleared"

        return result

    except Exception as e:
        logger.error(f"Error in chat_with_doc_v2: {str(e)}")
        return {
            "response": "I encountered an error processing your request. Please try again.",
            "tools_called": [],
            "iterations": 0,
            "error": str(e)
        }


async def get_report_context_summary(chat_history_id: str, db) -> Optional[str]:
    """
    Get a brief context summary of the current report for the agent.

    This provides the agent with awareness of the current report state
    without including the full report content.
    """
    try:
        from database_scripts import get_pending_changes, get_summary_report

        # Get pending changes count
        pending = await get_pending_changes(chat_history_id, db)
        pending_count = len(pending) if pending else 0

        # Get report status
        report = await get_summary_report(chat_history_id, db)

        if not report:
            return "No report has been generated yet."

        has_report = bool(report.report_content)
        version = getattr(report, 'version', 1)

        summary_parts = []

        if has_report:
            summary_parts.append(f"Report version {version} is available.")
        else:
            summary_parts.append("Report generation may be in progress.")

        if pending_count > 0:
            summary_parts.append(f"{pending_count} pending change(s) queued.")
            # Show first few change IDs
            if pending:
                change_ids = [c.get("id", "?") for c in pending[:3]]
                summary_parts.append(f"Recent: {', '.join(change_ids)}")
        else:
            summary_parts.append("No pending changes.")

        return " ".join(summary_parts)

    except Exception as e:
        logger.error(f"Error getting report context: {str(e)}")
        return None
