"""
Message Protocol for Multi-Bot Communication
=============================================

Defines message types, parsing utilities, and formatting for inter-bot communication.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
import json
import re
import time


class MessageType(str, Enum):
    """Message types for inter-bot communication."""
    
    # Task lifecycle
    TASK_REQUEST = "task_request"           # leader → orchestrator
    TASK_CANCEL = "task_cancel"             # leader → orchestrator
    TASK_RESPONSE = "task_response"         # orchestrator → leader
    
    # Sub-task dispatch
    SUBTASK_REQUEST = "subtask_request"      # orchestrator → sub-agent
    SUBTASK_RESPONSE = "subtask_response"   # sub-agent → orchestrator
    
    # Code flow
    CODE_GENERATED = "code_generated"
    CODE_REVIEW_REQUEST = "code_review_request"
    CODE_REVIEW_RESPONSE = "code_review_response"
    CODE_REVISION_REQUEST = "code_revision_request"
    
    # Execution
    EXECUTE_REQUEST = "execute_request"
    EXECUTE_RESPONSE = "execute_response"
    
    # Notifications (push to leader)
    NOTIFY_START = "notify_start"
    NOTIFY_PROGRESS = "notify_progress"
    NOTIFY_COMPLETED = "notify_completed"
    NOTIFY_FAILED = "notify_failed"
    
    # Heartbeat / ping
    PING = "ping"
    PONG = "pong"


class AgentRole(str, Enum):
    """Agent roles in the system."""
    ORCHESTRATOR = "orchestrator"
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    EXECUTOR = "executor"


@dataclass
class Message:
    """Parsed message from Discord."""
    
    type: MessageType
    sender: str                    # Discord user/bot ID
    sender_name: str               # Display name
    content: str
    channel_id: str
    guild_id: Optional[str] = None
    
    # Routing
    mentioned_bots: List[str] = field(default_factory=list)  # [@bot1, @bot2]
    reply_to: Optional[str] = None
    
    # Task context
    task_id: Optional[str] = None
    
    # Raw
    raw_content: str = ""


@dataclass 
class TaskRequest:
    """Task request from leader."""
    task_id: str
    task_description: str
    skill_needed: Optional[str] = None
    leader_id: str
    channel_id: str
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class SubTask:
    """Sub-task dispatched to an agent."""
    task_id: str
    subtask_id: str
    assigned_to: AgentRole
    instruction: str
    payload: dict = field(default_factory=dict)  # Additional data
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    status: str = "pending"  # pending, in_progress, done, failed


def parse_message(
    content: str,
    sender_id: str,
    sender_name: str,
    channel_id: str,
    guild_id: Optional[str] = None
) -> Message:
    """
    Parse a Discord message into a structured Message.
    
    Extracts:
    - @mentions
    - Message type
    - Task ID
    """
    raw_content = content
    content = content.strip()
    
    # Extract @mentions
    mentioned_bots = re.findall(r'@(\w+)', content)
    
    # Determine message type from content patterns
    msg_type = _infer_message_type(content)
    
    # Extract task_id if present
    task_id = _extract_task_id(content)
    
    # Extract reply_to (if replying to a specific message)
    reply_to = None
    if content.startswith('>'):
        # Quoted message format
        pass
    
    return Message(
        type=msg_type,
        sender=sender_id,
        sender_name=sender_name,
        content=content,
        channel_id=channel_id,
        guild_id=guild_id,
        mentioned_bots=mentioned_bots,
        reply_to=reply_to,
        task_id=task_id,
        raw_content=raw_content
    )


def _infer_message_type(content: str) -> MessageType:
    """Infer message type from content."""
    content_lower = content.lower()
    
    # Notification types
    if "完成" in content and ("✓" in content or "✅" in content):
        return MessageType.NOTIFY_COMPLETED
    if "失败" in content or "❌" in content:
        return MessageType.NOTIFY_FAILED
    if "开始" in content or "启动" in content:
        return MessageType.NOTIFY_START
    if "进度" in content or "进行中" in content:
        return MessageType.NOTIFY_PROGRESS
    
    # Request types
    if "审查通过" in content or "review passed" in content_lower:
        return MessageType.CODE_REVIEW_RESPONSE
    if "需要修改" in content or "修改" in content:
        return MessageType.CODE_REVISION_REQUEST
    if "代码完成" in content or "code generated" in content_lower:
        return MessageType.CODE_GENERATED
    if "计划完成" in content or "plan completed" in content_lower:
        return MessageType.SUBTASK_RESPONSE
    if "任务完成" in content or "执行完成" in content:
        return MessageType.EXECUTE_RESPONSE
    if "ping" in content_lower:
        return MessageType.PING
    if "pong" in content_lower:
        return MessageType.PONG
    
    # Default: subtask response for bot replies
    return MessageType.SUBTASK_RESPONSE


def _extract_task_id(content: str) -> Optional[str]:
    """Extract task ID from message."""
    # Look for patterns like [task:abc123] or task_id: abc123
    patterns = [
        r'\[task:([^\]]+)\]',
        r'task[_\s]?id:?\s*(\w+)',
        r'#(\w{8,})',  # Hash-like ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def format_task_request(task: TaskRequest, mention_leader: bool = True) -> str:
    """Format a task request message for Discord."""
    lines = [
        f"📋 **New Task**" if mention_leader else "📋 **Task**",
        f"",
        f"**Task ID**: `{task.task_id}`",
        f"**Description**: {task.task_description}",
    ]
    
    if task.skill_needed:
        lines.append(f"**Skill**: `{task.skill_needed}`")
    
    lines.append(f"")
    lines.append(f"_Submit time: {task.created_at}_")
    
    return "\n".join(lines)


def format_subtask_request(
    subtask: SubTask,
    recipient: AgentRole,
    reply_to: Optional[str] = None
) -> str:
    """Format a subtask request message for Discord."""
    lines = []
    
    if reply_to:
        lines.append(f"> {reply_to}")
    
    lines.append(f"@{'planner' if recipient == AgentRole.PLANNER else recipient.value}")
    lines.append(f"")
    lines.append(f"**New Subtask**")
    lines.append(f"")
    lines.append(f"**Task ID**: `{subtask.task_id}`")
    lines.append(f"**Subtask ID**: `{subtask.subtask_id}`")
    lines.append(f"")
    lines.append(f"**Instruction**:")
    lines.append(f"{subtask.instruction}")
    
    if subtask.payload:
        lines.append(f"")
        lines.append(f"**Payload**:")
        for k, v in subtask.payload.items():
            lines.append(f"- {k}: `{v}`")
    
    return "\n".join(lines)


def format_progress_message(task_id: str, step: str, detail: str) -> str:
    """Format a progress notification."""
    return (
        f"📋 **Progress**\n"
        f"Task: `{task_id}`\n"
        f"**{step}**: {detail}"
    )


def format_completion_message(
    task_id: str,
    result_files: List[str],
    job_id: Optional[str] = None
) -> str:
    """Format a task completion notification."""
    lines = [
        f"✅ **Task Completed**",
        f"Task ID: `{task_id}`",
    ]
    
    if job_id:
        lines.append(f"Job ID: `{job_id}`")
    
    if result_files:
        lines.append(f"")
        lines.append(f"**Result Files**:")
        for f in result_files:
            lines.append(f"- `{f}`")
    
    return "\n".join(lines)


def format_error_message(task_id: str, error: str) -> str:
    """Format an error notification."""
    return (
        f"❌ **Task Failed**\n"
        f"Task ID: `{task_id}`\n"
        f"**Error**: {error}"
    )


# Protocol version for compatibility
PROTOCOL_VERSION = "2.0.0"
