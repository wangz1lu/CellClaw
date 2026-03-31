"""
Data Models for Multi-Agent System
==================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class AgentType(Enum):
    """Agent types in the system"""
    ORCHESTRATOR = "orchestrator"
    BASE = "base"
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    EXECUTOR = "executor"


class MessageType(Enum):
    """Message types between agents"""
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"


class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanStatus(Enum):
    """Execution plan status"""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentConfig:
    """
    Configuration for an agent.
    Supports custom API keys per agent.
    """
    name: str
    agent_type: AgentType
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: Optional[str] = None
    
    @classmethod
    def default_for(cls, agent_type: AgentType) -> "AgentConfig":
        """Create default config for an agent type"""
        defaults = {
            AgentType.ORCHESTRATOR: {
                "name": "orchestrator",
                "temperature": 0.7,
                "max_tokens": 4096,
            },
            AgentType.PLANNER: {
                "name": "planner", 
                "temperature": 0.5,
                "max_tokens": 4096,
            },
            AgentType.CODER: {
                "name": "coder",
                "temperature": 0.3,
                "max_tokens": 8192,
            },
            AgentType.REVIEWER: {
                "name": "reviewer",
                "temperature": 0.3,
                "max_tokens": 4096,
            },
            AgentType.EXECUTOR: {
                "name": "executor",
                "temperature": 0.2,
                "max_tokens": 2048,
            },
            AgentType.BASE: {
                "name": "base",
                "temperature": 0.5,
                "max_tokens": 4096,
            },
        }
        return cls(agent_type=agent_type, **defaults.get(agent_type, {}))


@dataclass
class AgentMessage:
    """
    Message passed between agents.
    """
    from_agent: str
    to_agent: str
    type: MessageType
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "type": self.type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
        }


@dataclass
class TaskStep:
    """
    A single step in an execution plan.
    """
    id: str
    description: str
    code: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    skill_id: Optional[str] = None  # If this step uses a specific skill
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "code": self.code,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "skill_id": self.skill_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


@dataclass
class ExecutionPlan:
    """
    A plan for executing a user's task.
    Contains multiple task steps.
    """
    plan_id: str
    user_id: str
    original_task: str
    steps: list[TaskStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.CREATED
    current_step: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    error_summary: Optional[str] = None
    
    def add_step(self, step: TaskStep) -> None:
        step.id = f"{self.plan_id}_step_{len(self.steps) + 1}"
        self.steps.append(step)
    
    def get_current_step(self) -> Optional[TaskStep]:
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None
    
    def advance_step(self) -> bool:
        """Move to next step. Returns True if there are more steps."""
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self.updated_at = datetime.now()
            return True
        return False
    
    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "user_id": self.user_id,
            "original_task": self.original_task,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "current_step": self.current_step,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result_summary": self.result_summary,
            "error_summary": self.error_summary,
        }


@dataclass
class Intent:
    """User intent parsed from message"""
    original: str
    is_simple_task: bool = False
    intent_type: str = "unknown"
    skill_needed: str = None
    confidence: float = 0.0


@dataclass
class ServerInfo:
    """
    Server connection information.
    Managed by BaseAgent.
    """
    server_id: str
    host: str
    user: str
    port: int = 22
    password: Optional[str] = None  # Encrypted
    key_file: Optional[str] = None
    workdir: str = "~"
    conda_env: Optional[str] = None
    conda_path: Optional[str] = None


@dataclass
class UserContext:
    """
    Per-user context maintained by BaseAgent.
    """
    user_id: str
    servers: dict[str, ServerInfo] = field(default_factory=dict)
    active_server: Optional[str] = None
    workdir: Optional[str] = None
    conda_envs: list[dict] = field(default_factory=list)
    conversation_history: list[dict] = field(default_factory=list)
    
    def get_active_server(self) -> Optional[ServerInfo]:
        if self.active_server:
            return self.servers.get(self.active_server)
        return None
