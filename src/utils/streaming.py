"""
SSE streaming infrastructure for chat responses.
Provides event types and streaming utilities for real-time chat.
"""
from typing import Any, Dict
from dataclasses import dataclass
from enum import Enum
import json


class StreamEventType(Enum):
    """Event types for SSE streaming."""
    # Connection events
    STREAM_START = "stream_start"
    STREAM_END = "stream_end"

    # Content events
    TOKEN = "token"              # Individual token/chunk
    CONTENT_BLOCK = "content"    # Larger content block

    # Tool events
    TOOL_START = "tool_start"    # Tool execution started
    TOOL_RESULT = "tool_result"  # Tool completed
    TOOL_ERROR = "tool_error"    # Tool failed

    # Status events
    THINKING = "thinking"        # LLM is processing
    ERROR = "error"              # Error occurred


@dataclass
class StreamEvent:
    """Structured SSE event."""
    event_type: StreamEventType
    data: Dict[str, Any]

    def to_sse(self) -> str:
        """Format as Server-Sent Event string."""
        return f"event: {self.event_type.value}\ndata: {json.dumps(self.data)}\n\n"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event": self.event_type.value,
            "data": self.data
        }


def create_stream_event(event_type: StreamEventType, **kwargs) -> StreamEvent:
    """Helper to create stream events with keyword arguments."""
    return StreamEvent(event_type=event_type, data=kwargs)


def format_sse_event(event_type: str, data: dict) -> str:
    """Format data as Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# Pre-built event creators for convenience
def stream_start(chat_history_id: str) -> StreamEvent:
    """Create a stream start event."""
    return StreamEvent(
        event_type=StreamEventType.STREAM_START,
        data={"chat_history_id": chat_history_id}
    )


def stream_end(content: str, tools_called: list = None, iterations: int = 1) -> StreamEvent:
    """Create a stream end event."""
    return StreamEvent(
        event_type=StreamEventType.STREAM_END,
        data={
            "content": content,
            "tools_called": tools_called or [],
            "iterations": iterations
        }
    )


def token_event(token: str, accumulated: str = None) -> StreamEvent:
    """Create a token event for streaming text."""
    data = {"token": token}
    if accumulated is not None:
        data["accumulated"] = accumulated
    return StreamEvent(event_type=StreamEventType.TOKEN, data=data)


def thinking_event(message: str, iteration: int = 1) -> StreamEvent:
    """Create a thinking status event."""
    return StreamEvent(
        event_type=StreamEventType.THINKING,
        data={"message": message, "iteration": iteration}
    )


def tool_start_event(tool_name: str, args: dict = None) -> StreamEvent:
    """Create a tool start event."""
    return StreamEvent(
        event_type=StreamEventType.TOOL_START,
        data={"tool": tool_name, "args": args or {}}
    )


def tool_result_event(tool_name: str, result: str, success: bool = True) -> StreamEvent:
    """Create a tool result event."""
    # Truncate result if too long
    truncated_result = result[:500] if len(result) > 500 else result
    return StreamEvent(
        event_type=StreamEventType.TOOL_RESULT,
        data={
            "tool": tool_name,
            "result": truncated_result,
            "success": success
        }
    )


def tool_error_event(tool_name: str, error: str) -> StreamEvent:
    """Create a tool error event."""
    return StreamEvent(
        event_type=StreamEventType.TOOL_ERROR,
        data={"tool": tool_name, "error": error}
    )


def error_event(message: str, error_detail: str = None) -> StreamEvent:
    """Create a general error event."""
    data = {"message": message}
    if error_detail:
        data["error"] = error_detail
    return StreamEvent(event_type=StreamEventType.ERROR, data=data)
