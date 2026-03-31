"""
OrchestratorAgent - Main Coordinator
====================================

Coordinates all agents in the multi-agent system.
User communicates ONLY with Orchestrator - it's the face of the system.
Executor Agent reports back independently.
"""

from __future__ import annotations
import os
import logging
import asyncio
from typing import Optional, Callable
from dataclasses import dataclass
import secrets

from agents.base import BaseAgent
from agents.memory import SharedMemory, TaskMemory, get_shared_memory
from agents.models import (
    AgentConfig, AgentType, UserContext, 
    TaskStep, ExecutionPlan, PlanStatus, TaskStatus
)

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    """User intent parsed from message"""
    original: str
    is_simple_task: bool = False
    intent_type: str = "unknown"
    skill_needed: Optional[str] = None
    confidence: float = 0.0


class OrchestratorAgent:
    """
    OrchestratorAgent - The ONLY agent users talk to.
    
    Responsibilities:
    - Understand user intent (via Planner)
    - Coordinate task execution
    - Return responses to user
    
    Executor Agent reports back to user INDEPENDENTLY via callbacks.
    """

    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig.default_for(AgentType.ORCHESTRATOR)
        self.name = self.config.name

        # Initialize base agent for context
        self.base = BaseAgent()

        # Internal agents (decision-making) - share memory
        from agents.planner import PlannerAgent
        from agents.coder import CoderAgent
        from agents.reviewer import ReviewerAgent
        
        # Shared memory for all agents
        self.shared_memory = get_shared_memory()
        
        # Initialize agents with shared memory
        self.planner = PlannerAgent(shared_memory=self.shared_memory)
        self.coder = CoderAgent(shared_memory=self.shared_memory)
        self.reviewer = ReviewerAgent(shared_memory=self.shared_memory)

        # Executor (external, has independent communication)
        from agents.executor import ExecutorAgent
        self.executor = ExecutorAgent()
        
        # Callback for executor to notify Orchestrator
        self.executor.set_notify_callback(self.on_executor_event)
        
        # User notification callback (Discord/WebSocket)
        self._notify_callback: Optional[Callable] = None
        
        # Active plans
        self._plans: dict[str, ExecutionPlan] = {}

        logger.info(f"OrchestratorAgent initialized")

    def set_notify_callback(self, callback: Callable):
        """Set callback for user notifications"""
        self._notify_callback = callback
        # Also set it for executor
        self.executor.set_user_notify_callback(callback)

    # ───────────────────────────────────────────────────────────────
    # Main Processing
    # ───────────────────────────────────────────────────────────────

    async def process(self, message: str, user_id: str, channel_id: str = None) -> str:
        """
        Main entry point for processing user messages.
        User ONLY talks to Orchestrator.
        
        Returns:
            str: Response to send to user
        """
        logger.info(f"Orchestrator: Processing '{message[:50]}...' for user {user_id}")

        # Add to history
        self.base.add_to_history(user_id, "user", message)

        # Step 1: Understand intent via Planner
        intent = await self.planner.understand(message, user_id)

        # Step 2: Handle based on complexity
        if intent.is_simple_task:
            response = await self._handle_simple(message, intent, user_id, channel_id)
        else:
            response = await self._handle_complex(message, intent, user_id, channel_id)

        # Add to history
        self.base.add_to_history(user_id, "assistant", response)

        return response

    async def _handle_simple(self, message: str, intent, user_id: str, channel_id: str = None) -> str:
        """Handle simple tasks: generate → review → submit → return"""
        logger.info(f"Orchestrator: Simple task - {intent.intent_type}")

        # Generate code
        code_result = await self.coder.generate(
            task_description=message,
            skill_id=intent.skill_needed,
            language="R"
        )

        # Review code
        review_result = await self.reviewer.check(code_result.code, code_result.language)

        if not review_result.can_execute:
            issues = "\n".join([f"- [{i.severity}] {i.category}: {i.message}" for i in review_result.issues])
            return f"❌ 代码审查未通过:\n{issues}"

        # Save script
        script_path = await self.coder.save_script(code_result.code, code_result.language)

        # Submit to Executor (Executor will notify user independently)
        job_id = await self.executor.submit(
            script_path=script_path,
            user_id=user_id,
            channel_id=channel_id,
            description=message,
            skill_used=intent.skill_needed
        )

        # Return immediate response
        skill_info = f"📌 使用 Skill: {intent.skill_needed}\n" if intent.skill_needed else "📌 未调用 Skill\n"

        return (
            f"✅ 任务已提交\n"
            f"{skill_info}"
            f"任务 PID: `{job_id}`\n"
            f"描述: {message}\n"
            f"⏳ Executor 正在执行，完成后会通知你"
        )

    async def _handle_complex(self, message: str, intent, user_id: str, channel_id: str = None) -> str:
        """Handle complex tasks: create plan → execute steps"""
        logger.info(f"Orchestrator: Complex task - {intent.intent_type}")

        # Create plan
        plan = await self.planner.create_plan(message, intent, user_id)
        self._plans[plan.plan_id] = plan

        # Execute plan steps
        for i, step in enumerate(plan.steps):
            logger.info(f"Orchestrator: Step {i+1}/{len(plan.steps)} - {step.description}")

            # Generate code for step
            code_result = await self.coder.generate(
                task_description=step.description,
                skill_id=step.skill_id or intent.skill_needed,
                language="R"
            )

            # Review
            review_result = await self.reviewer.check(code_result.code, code_result.language)

            if not review_result.can_execute:
                # Try to fix
                code_result.code = await self.reviewer.fix(code_result.code, review_result.issues)

            # Save and submit
            script_path = await self.coder.save_script(code_result.code, code_result.language)

            await self.executor.submit(
                script_path=script_path,
                user_id=user_id,
                channel_id=channel_id,
                description=step.description,
                skill_used=step.skill_id
            )

            step.status = TaskStatus.RUNNING

        return (
            f"📋 任务计划已创建\n"
            f"步骤数: {len(plan.steps)}\n"
            f"技能: {intent.skill_needed or '通用'}\n"
            f"⏳ Executor 正在执行各步骤，完成后会通知你"
        )

    # ───────────────────────────────────────────────────────────────
    # Executor Event Handler (Called by Executor independently)
    # ───────────────────────────────────────────────────────────────

    def on_executor_event(self, event: dict):
        """
        Executor calls this when it has something to report.
        This is the INDEPENDENT communication from Executor to user.
        
        Event types:
        - task_started: Job has started
        - progress: Job progress update
        - completed: Job finished successfully
        - failed: Job failed
        """
        event_type = event.get("type")
        user_id = event.get("user_id")
        message = event.get("message", "")

        logger.info(f"Orchestrator received executor event: {event_type} for user {user_id}")

        # Forward to user notification callback
        if self._notify_callback:
            self._notify_callback(event)
        else:
            # Log if no callback set
            logger.warning(f"No notify callback for executor event: {message}")

    # ───────────────────────────────────────────────────────────────
    # Plan Management
    # ───────────────────────────────────────────────────────────────

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get a plan by ID"""
        return self._plans.get(plan_id)

    def list_user_plans(self, user_id: str) -> list[ExecutionPlan]:
        """List all plans for a user"""
        return [p for p in self._plans.values() if p.user_id == user_id]

    # ───────────────────────────────────────────────────────────────
    # Context Access
    # ───────────────────────────────────────────────────────────────

    def get_user_context(self, user_id: str) -> UserContext:
        """Get user context from base agent"""
        return self.base.get_user_context(user_id)

    def build_context(self, user_id: str) -> str:
        """Build context string for LLM"""
        return self.base.build_context_for_llm(user_id)

    def __repr__(self) -> str:
        return f"<OrchestratorAgent: {self.name}>"
