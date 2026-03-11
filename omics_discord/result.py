"""
Command Result
==============
Standardized return type from all command handlers.
The Agent layer renders this into Discord messages.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ResultType(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    INFO = "info"
    PENDING = "pending"     # async task submitted, not yet complete
    PROMPT = "prompt"       # need more input from user (e.g. password)


@dataclass
class CommandResult:
    """
    Unified return type for all Discord command handlers.

    Attributes:
        type:           Outcome classification
        text:           Main message text (markdown supported)
        figures:        Local file paths to attach as images/files
        ephemeral:      If True, only visible to the invoking user (where supported)
        needs_dm:       If True, agent should DM the user (e.g. to collect password)
        dm_prompt:      The DM message to send
        job_id:         Set for PENDING results (background job submitted)
        poll_interval:  Seconds between polls for PENDING jobs
    """
    type: ResultType
    text: str
    figures: list[str] = field(default_factory=list)
    ephemeral: bool = False
    needs_dm: bool = False
    dm_prompt: Optional[str] = None
    job_id: Optional[str] = None
    poll_interval: int = 30

    @classmethod
    def ok(cls, text: str, figures: list[str] = None) -> "CommandResult":
        return cls(type=ResultType.SUCCESS, text=text, figures=figures or [])

    @classmethod
    def err(cls, text: str) -> "CommandResult":
        return cls(type=ResultType.ERROR, text=f"❌ {text}")

    @classmethod
    def info(cls, text: str) -> "CommandResult":
        return cls(type=ResultType.INFO, text=text)

    @classmethod
    def pending(cls, text: str, job_id: str, poll_interval: int = 30) -> "CommandResult":
        return cls(
            type=ResultType.PENDING,
            text=text,
            job_id=job_id,
            poll_interval=poll_interval,
        )

    @classmethod
    def needs_password(cls, server_id: str) -> "CommandResult":
        return cls(
            type=ResultType.PROMPT,
            text=f"🔑 请通过**私信**告诉我服务器 `{server_id}` 的 SSH 密码。\n我已向你发送私信。",
            needs_dm=True,
            dm_prompt=(
                f"请发送服务器 `{server_id}` 的 SSH 密码。\n"
                f"⚠️ 密码将使用 AES-256 加密存储，不会明文保存。\n"
                f"格式：直接发送密码即可。"
            ),
            ephemeral=True,
        )
