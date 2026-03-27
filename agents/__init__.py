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
- Integration: Connect with existing system
"""

from agents.base import BaseAgent
from agents.models import (
    AgentConfig, AgentType, MessageType,
    TaskStatus, PlanStatus,
    AgentMessage, TaskStep, ExecutionPlan,
    ServerInfo, UserContext
)
from agents.orchestrator import OrchestratorAgent, Intent
from agents.planner import PlannerAgent, IntentResult
from agents.coder import CoderAgent, CodeResult
from agents.reviewer import ReviewerAgent, ReviewIssue, ReviewResult
from agents.executor import ExecutorAgent, JobStatus
from agents.integration import MultiAgentSystem, IntegrationConfig
from agents.wrapper import (
    MultiAgentWrapper,
    create_multi_agent_wrapper,
    is_multi_agent_enabled,
    enable_multi_agent,
    disable_multi_agent
)

__all__ = [
    # Base
    "BaseAgent",
    
    # Models
    "AgentConfig",
    "AgentType", 
    "MessageType",
    "TaskStatus",
    "PlanStatus",
    "AgentMessage",
    "TaskStep",
    "ExecutionPlan",
    "ServerInfo",
    "UserContext",
    
    # Agents
    "OrchestratorAgent",
    "Intent",
    "PlannerAgent",
    "IntentResult",
    "CoderAgent",
    "CodeResult",
    "ReviewerAgent",
    "ReviewIssue",
    "ReviewResult",
    "ExecutorAgent",
    "JobStatus",
    
    # Integration
    "MultiAgentSystem",
    "IntegrationConfig",
    
    # Wrapper
    "MultiAgentWrapper",
    "create_multi_agent_wrapper",
    "is_multi_agent_enabled",
    "enable_multi_agent",
    "disable_multi_agent",
]

__version__ = "2.0.0"
