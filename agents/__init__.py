"""
CellClaw Multi-Agent System
===========================

Architecture:
- Orchestrator: Coordination and flow control
- Base: Server info, environment, workdir management
- Planner: Task understanding and decomposition
- Coder: Code generation
- Reviewer: Code review
- Executor: Execution monitoring
"""

from agents.base import BaseAgent
from agents.models import AgentConfig, AgentMessage, TaskStep, ExecutionPlan

__all__ = [
    "BaseAgent",
    "AgentConfig",
    "AgentMessage",
    "TaskStep",
    "ExecutionPlan",
]

__version__ = "2.0.0"
