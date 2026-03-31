"""
BaseAgent - Foundation for Multi-Agent System
=============================================

Manages:
- Server connections
- Working directories
- Conda environments
- User contexts
- Conversation history
"""

from __future__ import annotations
import os
import logging
from typing import Optional, Any
from dataclasses import dataclass, field

from agents.models import AgentConfig, AgentType, UserContext, ServerInfo
from agents.memory import SharedMemory, TaskMemory, get_shared_memory

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    BaseAgent provides foundational information to all other agents.
    
    It maintains:
    - Server connection info per user
    - Working directory per user
    - Conda environments per user
    - User contexts
    """
    
    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig.default_for(AgentType.BASE)
        self.name = self.config.name
        self._user_contexts: dict[str, UserContext] = {}
        
        # Shared memory (cross-agent knowledge)
        self.shared_memory = get_shared_memory()
        
        # Load default API config from environment
        self._api_key = self.config.api_key or os.getenv("OMICS_LLM_API_KEY")
        self._base_url = self.config.base_url or os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        self._model = self.config.model or os.getenv("OMICS_LLM_MODEL", "deepseek-chat")
    
    # ───────────────────────────────────────────────────────────────
    # User Context Management
    # ───────────────────────────────────────────────────────────────
    
    def get_user_context(self, user_id: str) -> UserContext:
        """Get or create user context"""
        if user_id not in self._user_contexts:
            self._user_contexts[user_id] = UserContext(user_id=user_id)
        return self._user_contexts[user_id]
    
    def update_user_context(self, user_id: str, **kwargs) -> None:
        """Update user context fields"""
        ctx = self.get_user_context(user_id)
        for key, value in kwargs.items():
            if hasattr(ctx, key):
                setattr(ctx, key, value)
    
    # ───────────────────────────────────────────────────────────────
    # Server Information
    # ───────────────────────────────────────────────────────────────
    
    def add_server(self, user_id: str, server: ServerInfo) -> None:
        """Add a server for a user"""
        ctx = self.get_user_context(user_id)
        ctx.servers[server.server_id] = server
        if ctx.active_server is None:
            ctx.active_server = server.server_id
        logger.info(f"Added server {server.server_id} for user {user_id}")
    
    def set_active_server(self, user_id: str, server_id: str) -> bool:
        """Set active server for user"""
        ctx = self.get_user_context(user_id)
        if server_id in ctx.servers:
            ctx.active_server = server_id
            return True
        return False
    
    def get_active_server(self, user_id: str) -> Optional[ServerInfo]:
        """Get active server for user"""
        ctx = self.get_user_context(user_id)
        return ctx.get_active_server()
    
    def get_server_info(self, user_id: str, server_id: str = None) -> Optional[ServerInfo]:
        """Get server info by ID"""
        ctx = self.get_user_context(user_id)
        if server_id:
            return ctx.servers.get(server_id)
        return ctx.get_active_server()
    
    # ───────────────────────────────────────────────────────────────
    # Working Directory
    # ───────────────────────────────────────────────────────────────
    
    def get_workdir(self, user_id: str) -> Optional[str]:
        """Get working directory for user"""
        ctx = self.get_user_context(user_id)
        if ctx.workdir:
            return ctx.workdir
        server = ctx.get_active_server()
        return server.workdir if server else None
    
    def set_workdir(self, user_id: str, workdir: str) -> None:
        """Set working directory for user"""
        ctx = self.get_user_context(user_id)
        ctx.workdir = workdir
        logger.info(f"Set workdir for {user_id}: {workdir}")
    
    # ───────────────────────────────────────────────────────────────
    # Conda Environments
    # ───────────────────────────────────────────────────────────────
    
    def get_conda_envs(self, user_id: str) -> list[dict]:
        """Get available conda environments for user"""
        ctx = self.get_user_context(user_id)
        return ctx.conda_envs
    
    def set_conda_envs(self, user_id: str, envs: list[dict]) -> None:
        """Set conda environments for user"""
        ctx = self.get_user_context(user_id)
        ctx.conda_envs = envs
        logger.info(f"Set {len(envs)} conda envs for {user_id}")
    
    def get_active_conda_env(self, user_id: str) -> Optional[str]:
        """Get active conda environment"""
        ctx = self.get_user_context(user_id)
        server = ctx.get_active_server()
        return server.conda_env if server else None
    
    def set_active_conda_env(self, user_id: str, env_name: str) -> None:
        """Set active conda environment"""
        ctx = self.get_user_context(user_id)
        if ctx.active_server and ctx.active_server in ctx.servers:
            ctx.servers[ctx.active_server].conda_env = env_name
    
    # ───────────────────────────────────────────────────────────────
    # Conversation History
    # ───────────────────────────────────────────────────────────────
    
    def add_to_history(self, user_id: str, role: str, content: str) -> None:
        """Add message to conversation history"""
        ctx = self.get_user_context(user_id)
        ctx.conversation_history.append({"role": role, "content": content})
        # Keep last 50 messages
        if len(ctx.conversation_history) > 50:
            ctx.conversation_history = ctx.conversation_history[-50:]
    
    def get_history(self, user_id: str, max_messages: int = 20) -> list[dict]:
        """Get conversation history"""
        ctx = self.get_user_context(user_id)
        return ctx.conversation_history[-max_messages:]
    
    # ───────────────────────────────────────────────────────────────
    # LLM API Access
    # ───────────────────────────────────────────────────────────────
    
    def get_llm_config(self) -> dict[str, str]:
        """Get LLM configuration for this agent"""
        return {
            "api_key": self._api_key,
            "base_url": self._base_url,
            "model": self._model,
            "temperature": str(self.config.temperature),
            "max_tokens": str(self.config.max_tokens),
        }
    
    def set_api_key(self, api_key: str) -> None:
        """Set API key for this agent"""
        self._api_key = api_key
    
    def set_model(self, model: str) -> None:
        """Set model for this agent"""
        self._model = model
    
    # ───────────────────────────────────────────────────────────────
    # Context Building
    # ───────────────────────────────────────────────────────────────
    
    def build_context_for_llm(self, user_id: str, include_history: bool = True) -> str:
        """
        Build context string for LLM prompts.
        Includes server info, workdir, conda envs, etc.
        """
        ctx = self.get_user_context(user_id)
        parts = []
        
        # Server info
        server = ctx.get_active_server()
        if server:
            parts.append(f"[Server: {server.user}@{server.host}:{server.port}]")
            parts.append(f"[Workdir: {self.get_workdir(user_id) or server.workdir}]")
        
        # Conda envs
        if ctx.conda_envs:
            env_names = [e.get("name", "?") for e in ctx.conda_envs]
            parts.append(f"[Conda Envs: {', '.join(env_names)}]")
        
        # Active conda env
        active_env = self.get_active_conda_env(user_id)
        if active_env:
            parts.append(f"[Active Conda Env: {active_env}]")
        
        # History summary
        if include_history and ctx.conversation_history:
            recent = ctx.conversation_history[-5:]
            history_summary = "\n".join([f"[{m['role']}] {m['content'][:100]}" for m in recent])
            parts.append(f"\n[Recent History]\n{history_summary}")
        
        return "\n".join(parts)
    
    def get_shared_memory(self) -> SharedMemory:
        """Get the shared memory instance"""
        return self.shared_memory
    
    def get_task_memory(self, plan_id: str) -> TaskMemory:
        """Get or create task-specific memory"""
        if not hasattr(self, '_task_memories'):
            self._task_memories = {}
        if plan_id not in self._task_memories:
            self._task_memories[plan_id] = TaskMemory(plan_id)
        return self._task_memories[plan_id]
    
    def __repr__(self) -> str:
        return f"<BaseAgent: {self.name}>"