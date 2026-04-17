"""
Streaming version of ToolChatAgent using LangChain's astream_events.

This module provides a streaming chat agent that yields SSE events for
real-time token streaming and tool execution status.
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage
)
from typing import Dict, Any, List, Optional, AsyncGenerator
import json
from config import settings
from utils.chat_tools import get_all_tools, tool_context, TOOL_SYSTEM_PROMPT
from utils.logger import logger
from utils.streaming import (
    StreamEvent,
    StreamEventType,
    stream_start,
    stream_end,
    token_event,
    thinking_event,
    tool_start_event,
    tool_result_event,
    tool_error_event,
    error_event
)


class StreamingToolChatAgent:
    """
    Streaming chat agent using LangChain's astream_events.

    Yields SSE events for tokens, tool calls, and results, providing
    real-time visibility into what the AI is doing.
    """

    def __init__(self, chat_history_id: str, db, user_id: str = None):
        """
        Initialize the streaming tool chat agent.

        Args:
            chat_history_id: The chat history ID for the current conversation
            db: Database session for tool operations
            user_id: The user ID for operations that require it
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

        # Initialize LLM with streaming enabled and tools bound
        self.llm = ChatOpenAI(
            model=settings.SUMMARIZATION_MODEL or "gpt-4o-mini",
            temperature=0.3,
            api_key=settings.OPENAI_CHATGPT,
            streaming=True  # Enable streaming
        ).bind_tools(self.tools)

        logger.info(f"StreamingToolChatAgent initialized with {len(self.tools)} tools for chat {chat_history_id}")

    async def stream_chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict]] = None,
        report_context: Optional[str] = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream chat response with tool calling.

        Yields StreamEvent objects for each event type:
        - STREAM_START: Connection established
        - THINKING: Processing status
        - TOKEN: Individual tokens for real-time display
        - TOOL_START: Tool execution started
        - TOOL_RESULT: Tool completed
        - TOOL_ERROR: Tool failed
        - ERROR: General error
        - STREAM_END: Response complete

        Args:
            user_message: The user's message
            conversation_history: Optional list of previous messages
            report_context: Optional summary of the current report

        Yields:
            StreamEvent objects
        """
        messages = self._build_messages(user_message, conversation_history, report_context)
        tools_called = []
        max_iterations = 10
        iteration = 0

        # Emit stream start
        yield stream_start(self.chat_history_id)

        while iteration < max_iterations:
            iteration += 1
            accumulated_content = ""
            tool_calls_pending = []

            # Emit thinking status
            yield thinking_event(
                message=f"Processing{'...' if iteration == 1 else f' (iteration {iteration})...'}",
                iteration=iteration
            )

            try:
                # Stream LLM response using astream_events
                async for event in self.llm.astream_events(messages, version="v2"):
                    event_kind = event.get("event", "")

                    if event_kind == "on_chat_model_stream":
                        # Token streaming
                        chunk = event.get("data", {}).get("chunk")
                        if chunk:
                            # Handle content tokens
                            if hasattr(chunk, 'content') and chunk.content:
                                accumulated_content += chunk.content
                                yield token_event(
                                    token=chunk.content,
                                    accumulated=accumulated_content
                                )

                            # Check for tool call chunks
                            if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                                for tc_chunk in chunk.tool_call_chunks:
                                    # Track partial tool calls
                                    if tc_chunk.get("index") is not None:
                                        idx = tc_chunk["index"]
                                        while len(tool_calls_pending) <= idx:
                                            tool_calls_pending.append({
                                                "id": "",
                                                "name": "",
                                                "args": ""
                                            })

                                        if tc_chunk.get("id"):
                                            tool_calls_pending[idx]["id"] = tc_chunk["id"]
                                        if tc_chunk.get("name"):
                                            tool_calls_pending[idx]["name"] = tc_chunk["name"]
                                        if tc_chunk.get("args"):
                                            tool_calls_pending[idx]["args"] += tc_chunk["args"]

                    elif event_kind == "on_chat_model_end":
                        # Final response - extract tool calls from the final message
                        output = event.get("data", {}).get("output")
                        if output and hasattr(output, 'tool_calls') and output.tool_calls:
                            tool_calls_pending = output.tool_calls

            except Exception as e:
                logger.error(f"LLM streaming error in iteration {iteration}: {str(e)}")
                yield error_event(
                    message="Error processing request",
                    error_detail=str(e)
                )
                return

            # Check if we have tool calls to process
            has_tool_calls = False
            if tool_calls_pending:
                # Check if any tool call has a valid name
                for tc in tool_calls_pending:
                    if isinstance(tc, dict):
                        if tc.get("name"):
                            has_tool_calls = True
                            break
                    elif hasattr(tc, 'get') and tc.get("name"):
                        has_tool_calls = True
                        break
                    elif hasattr(tc, 'name') and tc.name:
                        has_tool_calls = True
                        break

            # If no tool calls, we're done
            if not has_tool_calls:
                yield stream_end(
                    content=accumulated_content,
                    tools_called=tools_called,
                    iterations=iteration
                )
                return

            # Process tool calls
            # Add AI message with tool calls to message history
            ai_message_content = accumulated_content or ""

            # Convert pending tool calls to proper format
            formatted_tool_calls = []
            for tc in tool_calls_pending:
                if isinstance(tc, dict):
                    tool_call = {
                        "id": tc.get("id", f"call_{len(formatted_tool_calls)}"),
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {})
                    }
                    # Parse args if it's a string
                    if isinstance(tool_call["args"], str):
                        try:
                            tool_call["args"] = json.loads(tool_call["args"]) if tool_call["args"] else {}
                        except json.JSONDecodeError:
                            tool_call["args"] = {}
                    formatted_tool_calls.append(tool_call)
                else:
                    # Handle LangChain tool call objects
                    formatted_tool_calls.append({
                        "id": getattr(tc, 'id', f"call_{len(formatted_tool_calls)}"),
                        "name": getattr(tc, 'name', ''),
                        "args": getattr(tc, 'args', {})
                    })

            # Create AI message with tool calls
            ai_message = AIMessage(
                content=ai_message_content,
                tool_calls=formatted_tool_calls
            )
            messages.append(ai_message)

            # Execute each tool
            for tool_call in formatted_tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                tool_id = tool_call.get("id", "")

                if not tool_name:
                    continue

                # Emit tool start event
                yield tool_start_event(tool_name, tool_args)

                tools_called.append({"tool": tool_name, "args": tool_args})

                # Execute the tool
                try:
                    result = await self._execute_tool(tool_name, tool_args)

                    # Emit tool result event
                    yield tool_result_event(tool_name, result, success=True)

                    # Add tool result to messages
                    messages.append(ToolMessage(
                        content=result,
                        tool_call_id=tool_id
                    ))

                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Tool execution error: {tool_name} - {error_msg}")

                    # Emit tool error event
                    yield tool_error_event(tool_name, error_msg)

                    # Add error result to messages
                    messages.append(ToolMessage(
                        content=json.dumps({"error": error_msg}),
                        tool_call_id=tool_id
                    ))

        # Max iterations reached
        logger.warning(f"Max iterations ({max_iterations}) reached for streaming chat {self.chat_history_id}")
        yield stream_end(
            content=accumulated_content if accumulated_content else "I've processed multiple steps but reached my limit.",
            tools_called=tools_called,
            iterations=iteration
        )

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


async def stream_chat_with_doc(
    chat_history_id: str,
    user_message: str,
    db,
    conversation_history: Optional[List[Dict]] = None,
    report_context: Optional[str] = None,
    user_id: Optional[str] = None
) -> AsyncGenerator[StreamEvent, None]:
    """
    Streaming chat endpoint using LangChain tool calling.

    This is a streaming alternative to chat_with_doc_v2. Instead of
    returning a complete response, it yields StreamEvent objects for
    real-time display.

    Args:
        chat_history_id: The chat history ID
        user_message: The user's message
        db: Database session
        conversation_history: Optional list of previous messages
        report_context: Optional report summary for context
        user_id: The user ID for operations

    Yields:
        StreamEvent objects for real-time display
    """
    try:
        agent = StreamingToolChatAgent(chat_history_id, db, user_id=user_id)
        async for event in agent.stream_chat(user_message, conversation_history, report_context):
            yield event

    except Exception as e:
        logger.error(f"Error in stream_chat_with_doc: {str(e)}")
        yield error_event(
            message="Streaming error occurred",
            error_detail=str(e)
        )
