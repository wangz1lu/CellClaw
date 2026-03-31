"""
OrchestratorAgent - Main Coordinator
====================================

Coordinates all agents in the multi-agent system.
User communicates ONLY with Orchestrator - it's the face of the system.
Executor Agent reports back independently.

Two modes:
- Natural conversation: LLM chats with user (not a task)
- Task execution: Multi-agent flow (Planner → Coder → Reviewer → Executor)
"""

from __future__ import annotations
import os
import json
import logging
import asyncio
from typing import Optional, Callable
from dataclasses import dataclass
import secrets

from agents.base import BaseAgent
from agents.memory import SharedMemory, TaskMemory, get_shared_memory
from agents.models import (
    AgentConfig, AgentType, UserContext, 
    TaskStep, ExecutionPlan, PlanStatus, TaskStatus, Intent
)

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """
    OrchestratorAgent - The ONLY agent users talk to.
    
    Responsibilities:
    - LLM-based intent understanding
    - Route to conversation or task flow
    - Coordinate task execution
    - Return responses to user
    
    Executor Agent reports back to user INDEPENDENTLY via callbacks.
    """

    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig.default_for(AgentType.ORCHESTRATOR)
        self.name = self.config.name

        # LLM configuration
        self._api_key = os.getenv("OMICS_LLM_API_KEY")
        self._base_url = os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        self._model = os.getenv("OMICS_LLM_MODEL", "deepseek-chat")

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

        logger.info(f"OrchestratorAgent initialized with LLM: {self._model}")

    def set_notify_callback(self, callback: Callable):
        """Set callback for user notifications"""
        self._notify_callback = callback
        # Also set it for executor
        self.executor.set_user_notify_callback(callback)

    # ───────────────────────────────────────────────────────────────
    # LLM Integration
    # ───────────────────────────────────────────────────────────────

    async def _call_llm(self, prompt: str, system: str = None) -> str:
        """
        Call LLM API.
        
        Args:
            prompt: User prompt
            system: Optional system prompt
            
        Returns:
            LLM response text
        """
        import aiohttp
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,  # Lower temp for more consistent outputs
        }
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        logger.error(f"LLM API error: {resp.status} - {error}")
                        return None
                    
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
        except asyncio.TimeoutError:
            logger.error("LLM API timeout")
            return None
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return None

    async def _llm_understand_intent(self, message: str) -> str:
        """
        Use LLM to understand if user is:
        - "task": wants to execute a task
        - "conversation": just chatting
        
        Returns:
            "task" or "conversation"
        """
        system_prompt = """You are an intent classifier for a bioinformatics assistant.

Classify the user message into ONE of these categories:
- "task": User wants to execute a bioinformatics analysis task (e.g., "帮我做差异分析", "跑一下SCTransform", "生成可视化")
- "conversation": User is just chatting, asking about capabilities, or saying hello/goodbye (e.g., "你好", "你会什么", "谢谢", "你是谁")

Rules:
- If user describes something they want DONE -> task
- If user asks what you CAN do -> conversation  
- If user greets or says goodbye -> conversation
- If user says thanks -> conversation

Respond with ONLY the category word, nothing else."""

        response = await self._call_llm(message, system=system_prompt)
        
        if response:
            response = response.strip().lower()
            if response in ["task", "conversation"]:
                logger.info(f"LLM intent: {response}")
                return response
        
        # Fallback: use keyword-based detection
        logger.warning("LLM intent detection failed, using fallback")
        return self._fallback_intent_detection(message)

    def _fallback_intent_detection(self, message: str) -> str:
        """
        Fallback keyword-based intent detection.
        Used when LLM is unavailable.
        """
        msg_lower = message.lower()
        
        # Task indicators
        task_keywords = ["帮我", "做", "跑", "分析", "生成", "计算", "执行", "处理"]
        for kw in task_keywords:
            if kw in msg_lower:
                return "task"
        
        # Default to conversation
        return "conversation"

    async def _llm_converse(self, message: str, user_id: str) -> str:
        """
        LLM-based natural conversation (not a task).
        """
        context = self.base.build_context_for_llm(user_id)
        
        system_prompt = """You are CellClaw, a professional and friendly bioinformatics analysis assistant.

Your personality:
- Professional and reliable
- Helpful and proactive
- Speak in the user's language (Chinese or English)
- You can help with: single-cell analysis (scRNA, snRNA), differential expression, cell annotation, batch correction, visualization

You should:
- Answer questions about your capabilities naturally
- Greet users warmly
- Thank users politely
- Explain what you can do when asked
- NOT generate code or submit tasks

Be conversational and natural."""

        user_prompt = f"User said: {message}\n\nContext: {context}"
        
        response = await self._call_llm(user_prompt, system=system_prompt)
        
        if response:
            return response
        
        # Fallback if LLM fails
        return self._fallback_conversation(message)

    def _fallback_conversation(self, message: str) -> str:
        """
        Fallback conversation when LLM is unavailable.
        """
        msg_lower = message.lower()
        
        # Simple pattern matching fallback
        if any(g in msg_lower for g in ["你好", "hi", "hello", "嗨"]):
            return "你好！我是 CellClaw，你的生物信息分析助手。有什么我可以帮你的吗？"
        
        if any(t in msg_lower for t in ["谢谢", "thanks"]):
            return "不客气！有问题随时问我。"
        
        if "技能" in message or "能做什么" in message:
            return "我可以帮你做：\n- 单细胞数据分析（scRNA, snRNA）\n- 差异表达分析\n- 细胞类型注释\n- 批次效应校正\n- 数据可视化\n\n直接告诉我你想做什么就行！"
        
        if "你是谁" in message:
            return "我是 CellClaw，一个专注于生物信息学分析的 AI 助手。"
        
        return "明白了！告诉我你想做什么分析？"

    # ───────────────────────────────────────────────────────────────
    # Main Processing
    # ───────────────────────────────────────────────────────────────

    async def process(self, message: str, user_id: str, channel_id: str = None) -> str:
        """
        Main entry point for processing user messages.
        User ONLY talks to Orchestrator.
        
        Flow:
        1. LLM understands intent (task vs conversation)
        2. Route to appropriate handler
        
        Returns:
            str: Response to send to user
        """
        logger.info(f"Orchestrator: Processing '{message[:50]}...' for user {user_id}")

        # Add to history
        self.base.add_to_history(user_id, "user", message)

        # Step 1: LLM understands intent
        intent_type = await self._llm_understand_intent(message)
        logger.info(f"Intent detected: {intent_type}")

        # Step 2: Route based on intent
        if intent_type == "task":
            # Task flow: understand → plan → execute
            response = await self._handle_task(message, user_id, channel_id)
        else:
            # Conversation flow: LLM chats naturally
            response = await self._llm_converse(message, user_id)

        # Add to history
        self.base.add_to_history(user_id, "assistant", response)

        return response

    async def _handle_task(self, message: str, user_id: str, channel_id: str) -> str:
        """
        Handle task execution: understand → plan → execute.
        """
        # Understand task details via Planner
        intent = await self.planner.understand(message, user_id)
        
        logger.info(f"Task intent: {intent.intent_type}, simple={intent.is_simple_task}, skill={intent.skill_needed}")

        # Route to simple or complex handler
        if intent.is_simple_task:
            return await self._handle_simple(message, intent, user_id, channel_id)
        else:
            return await self._handle_complex(message, intent, user_id, channel_id)

    async def _handle_simple(self, message: str, intent, user_id: str, channel_id: str = None) -> str:
        """Handle simple tasks: generate → review → submit → return"""
        logger.info(f"Orchestrator: Simple task - {intent.intent_type}")

        # For query-type tasks, don't generate code or submit jobs
        if intent.intent_type == "query":
            return await self._handle_query(message, user_id)
        
        if intent.intent_type == "management":
            return await self._handle_management(message, user_id)

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
            return f"代码审查未通过:\n{issues}"

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
        skill_info = f"使用 Skill: {intent.skill_needed}\n" if intent.skill_needed else "未调用 Skill\n"

        return (
            f"任务已提交\n"
            f"{skill_info}"
            f"任务 PID: `{job_id}`\n"
            f"描述: {message}\n"
            f"Executor 正在执行，完成后会通知你"
        )

    async def _handle_query(self, message: str, user_id: str) -> str:
        """Handle query-type simple tasks without submitting jobs"""
        msg_lower = message.lower()
        
        if any(k in msg_lower for k in ["job", "任务", "状态"]):
            # Get job status
            jobs = self.executor.get_active_jobs(user_id)
            if not jobs:
                return "当前没有运行中的任务"
            
            lines = ["运行中的任务:"]
            for job in jobs:
                lines.append(f"- {job.description}: {job.status} ({job.progress:.0%})")
            return "\n".join(lines)
        
        if "list" in msg_lower or "服务器" in message:
            # List servers
            server_config = self.base.get_server_config(user_id)
            if not server_config:
                return "没有配置的服务器。告诉我你的服务器信息，我会保存。"
            return f"已配置服务器: {list(server_config.keys())}"
        
        # Default query response
        return f"查询: {message}\n\n告诉我你想做什么分析任务？"
    
    async def _handle_management(self, message: str, user_id: str) -> str:
        """Handle management-type simple tasks"""
        return f"管理操作: {message}\n\n请告诉我具体想做什么？"

    async def _handle_complex(self, message: str, intent, user_id: str, channel_id: str = None) -> str:
        """Handle complex tasks: create plan → execute steps"""
        logger.info(f"Orchestrator: Complex task - {intent.intent_type}")

        # Create plan
        plan = self.planner.create_plan(message, intent, user_id)
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
            f"任务计划已创建\n"
            f"步骤数: {len(plan.steps)}\n"
            f"技能: {intent.skill_needed or '通用'}\n"
            f"Executor 正在执行各步骤，完成后会通知你"
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
