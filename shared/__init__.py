"""
Shared modules for multi-bot architecture.
"""

from shared.protocol import MessageType, Message, parse_message, format_task_request
from shared.state_manager import StateManager, TaskState

__all__ = [
    "MessageType",
    "Message", 
    "parse_message",
    "format_task_request",
    "StateManager",
    "TaskState"
]
