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
from agents.planner import PlannerAgent
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
from agents.client import MultiAgentClient
from agents.memory import SharedMemory, TaskMemory, get_shared_memory

from agents.websocket_manager import (
    WebSocketManager,
    ConnectionManager,
    WSMessage,
    EventType,
    get_websocket_manager,
    init_websocket_manager
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
    
    # Memory (Cross-Agent Knowledge Sharing)
    "SharedMemory",
    "TaskMemory",
    "KnowledgeEntry",
    "SkillKnowledge",
    "get_shared_memory",
    
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
    
    # Client
    "MultiAgentClient",
    
    # WebSocket
    "WebSocketManager",
    "ConnectionManager",
    "WSMessage",
    "EventType",
    "get_websocket_manager",
    "init_websocket_manager",
]

__version__ = "2.0.0"
