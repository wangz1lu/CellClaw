"""
OrchestratorAgent - Main Coordinator
====================================

Redesigned to match original single-agent behavior:
- Conversation mode: LLM chat with full context (knows who it is)
- Task mode: Route to appropriate handler like original NL Router

Flow:
用户消息 → classify_intent() → task/conversation
    ├── task → route_task() → specific handler
    └── conversation → llm_chat() → LLM with identity
"""

from __future__ import annotations
import os
import re
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
    OrchestratorAgent - Single interface for user communication.
    
    Mimics original single-agent behavior:
    - Can chat naturally (conversation mode)
    - Can execute tasks (task mode) like the original NL Router
    
    Executor Agent reports back independently via callbacks.
    """

    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig.default_for(AgentType.ORCHESTRATOR)
        self.name = self.config.name

        # LLM configuration
        self._api_key = os.getenv("OMICS_LLM_API_KEY")
        self._base_url = os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        self._model = os.getenv("OMICS_LLM_MODEL", "deepseek-chat")

        # Initialize base agent
        self.base = BaseAgent()

        # Internal agents for task execution
        from agents.planner import PlannerAgent
        from agents.coder import CoderAgent
        from agents.reviewer import ReviewerAgent
        
        # Shared memory
        self.shared_memory = get_shared_memory()
        
        self.planner = PlannerAgent(shared_memory=self.shared_memory)
        self.coder = CoderAgent(shared_memory=self.shared_memory)
        self.reviewer = ReviewerAgent(shared_memory=self.shared_memory)

        # Executor for job submission
        from agents.executor import ExecutorAgent
        self.executor = ExecutorAgent()
        self.executor.set_notify_callback(self.on_executor_event)
        
        # User notification callback
        self._notify_callback: Optional[Callable] = None
        
        # Real data sources (injected later)
        self._ssh_manager = None
        self._job_tracker = None
        
        # Active plans
        self._plans: dict[str, ExecutionPlan] = {}

        logger.info(f"OrchestratorAgent initialized (single-agent compatible)")

    def set_notify_callback(self, callback: Callable):
        """Set callback for user notifications"""
        self._notify_callback = callback
        self.executor.set_user_notify_callback(callback)

    def set_ssh_manager(self, ssh_manager):
        """Set SSH manager for real server data"""
        self._ssh_manager = ssh_manager

    def set_job_tracker(self, job_tracker):
        """Set job tracker for real job data"""
        self._job_tracker = job_tracker

    # ───────────────────────────────────────────────────────────────
    # LLM Integration
    # ───────────────────────────────────────────────────────────────

    async def _call_llm(self, prompt: str, system: str = None) -> str:
        """Call LLM API."""
        import aiohttp
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.7,
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
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return None

    # ───────────────────────────────────────────────────────────────
    # Context Building (like original single agent)
    # ───────────────────────────────────────────────────────────────

    def _build_context(self, user_id: str) -> str:
        """Build context from real data sources."""
        parts = []
        
        if self._ssh_manager and hasattr(self._ssh_manager, '_registry'):
            try:
                # Servers
                servers = self._ssh_manager._registry.list_servers(user_id)
                if servers:
                    server_lines = []
                    for cfg in servers:
                        server_lines.append(f"  - {cfg.server_id}: {cfg.username}@{cfg.host}:{cfg.port}")
                    parts.append("用户配置的服务器:\n" + "\n".join(server_lines))
                
                # Session info
                session = self._ssh_manager._registry.get_session(user_id)
                if session:
                    if session.active_project_path:
                        parts.append("当前工作目录: " + session.active_project_path)
                    if session.active_conda_env:
                        parts.append("当前conda环境: " + session.active_conda_env)
                    if session.active_server_id:
                        parts.append("当前服务器: " + session.active_server_id)
            except Exception as e:
                logger.warning(f"Failed to get SSH context: {e}")
        
        # Active jobs
        try:
            jobs = self.executor.get_active_jobs(user_id)
            if jobs:
                parts.append("运行中的任务: " + str(len(jobs)))
        except:
            pass
        
        return "\n\n".join(parts) if parts else "无"

    # ───────────────────────────────────────────────────────────────
    # Intent Classification (like original NL Router)
    # ───────────────────────────────────────────────────────────────

    def _classify_intent(self, message: str, user_id: str) -> dict:
        """
        Classify user intent like original single-agent NL Router.
        Returns dict with action type and params.
        """
        msg = message.strip()
        msg_lower = msg.lower()
        session = None
        
        if self._ssh_manager and hasattr(self._ssh_manager, '_registry'):
            session = self._ssh_manager._registry.get_session(user_id)
        
        # ── Status / session queries ───────────────────────────────────
        if any(kw in msg_lower for kw in ["我的状态", "当前状态", "/status", "session", "状态"]):
            return {"action": "status", "params": {}, "raw": msg}
        
        # ── Help ──────────────────────────────────────────────────────
        if any(kw in msg_lower for kw in ["怎么用", "help", "帮助", "有什么功能", "你会什么"]):
            return {"action": "help", "params": {}, "raw": msg}
        
        # ── File/script operations ────────────────────────────────────
        if any(kw in msg_lower for kw in ["读一下", "看一下", "解释", "查看脚本", "看看这个脚本"]):
            return {"action": "read_script", "params": {"path": None}, "raw": msg}
        
        # ── Modify script ─────────────────────────────────────────────
        if any(kw in msg_lower for kw in ["修改", "优化", "加上", "加一个", "添加", "改成"]):
            return {"action": "modify_script", "params": {"instruction": msg}, "raw": msg}
        
        # ── Create folder / file operations ────────────────────────────
        if any(kw in msg_lower for kw in ["新建", "创建", "mkdir", "删除", "删除", "移动", "复制"]):
            return {"action": "file_operation", "params": {"operation": msg}, "raw": msg}
        
        # ── Query / check info ─────────────────────────────────────────
        if any(kw in msg_lower for kw in ["多少", "几个", "有没有", "是什么", "平均", "最多", "最少", "查看", "看看", "告诉我", "查一下"]):
            return {"action": "query", "params": {"question": msg}, "raw": msg}
        
        # ── Analysis tasks ─────────────────────────────────────────────
        analysis_type = self._detect_analysis_type(msg_lower)
        if analysis_type:
            return {
                "action": "analyze",
                "params": {
                    "analysis_type": analysis_type,
                    "question": msg,
                },
                "raw": msg
            }
        
        # ── Full pipeline ─────────────────────────────────────────────
        if any(kw in msg_lower for kw in ["完整", "全流程", "从头", "全套", "完整分析", "从0开始", "从零开始"]):
            return {"action": "full_pipeline", "params": {"question": msg}, "raw": msg}
        
        # ── Conversational / casual ────────────────────────────────────
        if any(kw in msg_lower for kw in ["你好", "hi", "hello", "嗨", "在吗", "谢谢", "再见", "拜拜", "你是谁"]):
            return {"action": "conversation", "params": {}, "raw": msg}
        
        # ── Default: LLM chat ─────────────────────────────────────────
        return {"action": "llm_chat", "params": {"message": msg}, "raw": msg}

    def _detect_analysis_type(self, msg_lower: str) -> Optional[str]:
        """Detect analysis type from message."""
        if any(k in msg_lower for k in ["qc", "质控", "过滤", "quality", "质控"]):
            return "qc"
        if any(k in msg_lower for k in ["cluster", "聚类", "umap", "tsne", "降维"]):
            return "cluster"
        if any(k in msg_lower for k in ["注释", "annotate", "cell type", "细胞类型", "celltype"]):
            return "annotate"
        if any(k in msg_lower for k in ["差异", "deg", "differential", "marker gene", "marker"]):
            return "deg"
        if any(k in msg_lower for k in ["轨迹", "trajectory", "pseudotime"]):
            return "trajectory"
        if any(k in msg_lower for k in ["批次", "batch", "integration", "整合", "harmony"]):
            return "batch_integration"
        if any(k in msg_lower for k in ["可视化", "画图", "plot", "visualization", "chart"]):
            return "visualization"
        if any(k in msg_lower for k in ["sce", "seurat", "scanpy", "单细胞", "scrna", "snrna"]):
            return "single_cell"
        return None

    # ───────────────────────────────────────────────────────────────
    # Main Processing
    # ───────────────────────────────────────────────────────────────

    async def process(self, message: str, user_id: str, channel_id: str = None) -> str:
        """
        Main entry point - matches original single-agent flow.
        """
        logger.info(f"Orchestrator: '{message[:50]}...' user={user_id}")

        # Add to history
        self.base.add_to_history(user_id, "user", message)

        # Classify intent like original NL Router
        intent = self._classify_intent(message, user_id)
        logger.info(f"Action: {intent['action']}")

        # Route to appropriate handler
        if intent["action"] == "status":
            response = await self._handle_status(user_id)
        elif intent["action"] == "help":
            response = await self._handle_help(user_id)
        elif intent["action"] == "read_script":
            response = await self._handle_read_script(intent["params"], user_id)
        elif intent["action"] == "modify_script":
            response = await self._handle_modify_script(intent["params"], user_id)
        elif intent["action"] == "file_operation":
            response = await self._handle_file_operation(intent["params"], user_id)
        elif intent["action"] == "query":
            response = await self._handle_query(intent["params"], user_id)
        elif intent["action"] == "analyze":
            response = await self._handle_analyze(intent["params"], user_id)
        elif intent["action"] == "full_pipeline":
            response = await self._handle_full_pipeline(intent["params"], user_id)
        elif intent["action"] == "conversation":
            response = await self._llm_chat(message, user_id, is_conversation=True)
        elif intent["action"] == "llm_chat":
            response = await self._llm_chat(intent["params"]["message"], user_id, is_conversation=False)
        else:
            response = await self._llm_chat(message, user_id, is_conversation=False)

        self.base.add_to_history(user_id, "assistant", response)
        return response

    # ───────────────────────────────────────────────────────────────
    # Handlers (like original single agent)
    # ───────────────────────────────────────────────────────────────

    async def _handle_status(self, user_id: str) -> str:
        """Handle status query - like original single agent."""
        context = self._build_context(user_id)
        
        system_prompt = """你是一个专业的生物信息分析助手 CellClaw。

用户请求查看当前状态。请根据以下上下文信息回答：

{context}

回答格式：
- 当前服务器（如有）
- 当前工作目录
- 当前conda环境
- 运行中的任务数量

简洁明了地回答。"""

        return system_prompt.format(context=context) if context != "无" else "暂无配置信息"

    async def _handle_help(self, user_id: str) -> str:
        """Handle help request."""
        system_prompt = """你是一个专业的生物信息分析助手 CellClaw。

你可以帮助用户：
- 做单细胞数据分析（scRNA, snRNA）
- 差异表达分析
- 细胞类型注释
- 批次效应校正
- 数据可视化
- 读取和修改脚本
- 管理服务器和conda环境

你可以直接用自然语言和我交流，例如：
- "帮我做差异分析"
- "查看当前工作目录"
- "新建一个文件夹"
- "跑一下QC分析"

有什么我可以帮你的？"""

        return system_prompt

    async def _handle_query(self, params: dict, user_id: str) -> str:
        """Handle query - use LLM to answer from context."""
        question = params.get("question", "")
        context = self._build_context(user_id)
        
        prompt = f"""用户问: {question}

当前用户环境信息：
{context}

请根据以上信息直接回答用户的问题。如果信息不足，请说明。"""
        
        response = await self._call_llm(prompt, system="你是一个专业的生物信息分析助手，直接回答用户问题。")
        return response if response else "抱歉，我无法回答这个问题。"

    async def _handle_read_script(self, params: dict, user_id: str) -> str:
        """Handle read script request."""
        return "请告诉我脚本的完整路径，我帮你读取。"

    async def _handle_modify_script(self, params: dict, user_id: str) -> str:
        """Handle modify script request."""
        return "请告诉我脚本的完整路径和要修改的内容。"

    async def _handle_file_operation(self, params: dict, user_id: str) -> str:
        """Handle file operations like mkdir."""
        operation = params.get("operation", "")
        
        # Extract the actual operation
        if "新建" in operation or "创建" in operation or "mkdir" in operation.lower():
            # Extract folder name
            folder_match = re.search(r'[的新建创建]*([^\s]+)', operation.replace("文件夹", ""))
            folder_name = folder_match.group(1) if folder_match else "test"
            
            # Get workdir from context
            workdir = "~/"
            if self._ssh_manager:
                try:
                    session = self._ssh_manager._registry.get_session(user_id)
                    if session and session.active_project_path:
                        workdir = session.active_project_path
                except:
                    pass
            
            # Submit the mkdir job
            script = f"mkdir -p {workdir}/{folder_name}"
            job_id = await self.executor.submit(
                script_path=None,  # Will use shell command
                user_id=user_id,
                channel_id=None,
                description=f"创建文件夹 {folder_name}",
                skill_used=None
            )
            
            return f"正在创建文件夹 {folder_name} 在 {workdir}..."
        
        return "请告诉我要执行什么文件操作？"

    async def _handle_analyze(self, params: dict, user_id: str) -> str:
        """Handle analysis request - submit job like original."""
        analysis_type = params.get("analysis_type", "general")
        question = params.get("question", "")
        
        # Build context for analysis
        context = self._build_context(user_id)
        
        prompt = f"""用户请求分析: {question}

当前环境：
{context}

分析类型: {analysis_type}

请先用Planner理解任务，创建计划，然后提交给Executor执行。
这是一个分析任务，需要：
1. 理解用户想要的分析
2. 生成代码
3. 提交执行"""

        # Use planner to understand
        intent = await self.planner.understand(question, user_id)
        
        # Route to simple or complex handler
        if intent.is_simple_task:
            return await self._handle_simple_analysis(intent, question, user_id)
        else:
            return await self._handle_complex_analysis(intent, question, user_id)

    async def _handle_simple_analysis(self, intent, question: str, user_id: str) -> str:
        """Handle simple analysis - single step."""
        # Generate code
        code_result = await self.coder.generate(
            task_description=question,
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

        # Submit to Executor
        job_id = await self.executor.submit(
            script_path=script_path,
            user_id=user_id,
            channel_id=None,
            description=question,
            skill_used=intent.skill_needed
        )

        skill_info = f"使用技能: {intent.skill_needed}" if intent.skill_needed else ""
        return (
            f"已提交分析任务\n"
            f"{skill_info}\n"
            f"任务ID: {job_id}\n"
            f"描述: {question}\n"
            f"执行完成后会通知你"
        )

    async def _handle_complex_analysis(self, intent, question: str, user_id: str) -> str:
        """Handle complex analysis - multiple steps."""
        # Create plan
        plan = self.planner.create_plan(question, intent, user_id)
        self._plans[plan.plan_id] = plan

        # Submit each step
        for i, step in enumerate(plan.steps):
            code_result = await self.coder.generate(
                task_description=step.description,
                skill_id=step.skill_id or intent.skill_needed,
                language="R"
            )

            review_result = await self.reviewer.check(code_result.code, code_result.language)

            if not review_result.can_execute:
                code_result.code = await self.reviewer.fix(code_result.code, review_result.issues)

            script_path = await self.coder.save_script(code_result.code, code_result.language)

            await self.executor.submit(
                script_path=script_path,
                user_id=user_id,
                channel_id=None,
                description=step.description,
                skill_used=step.skill_id
            )

            step.status = TaskStatus.RUNNING

        return (
            f"已提交复杂分析任务\n"
            f"步骤数: {len(plan.steps)}\n"
            f"技能: {intent.skill_needed or '通用'}\n"
            f"执行完成后会通知你"
        )

    async def _handle_full_pipeline(self, params: dict, user_id: str) -> str:
        """Handle full pipeline request."""
        return "完整分析流程正在开发中..."

    # ───────────────────────────────────────────────────────────────
    # LLM Chat (like original single agent)
    # ───────────────────────────────────────────────────────────────

    async def _llm_chat(self, message: str, user_id: str, is_conversation: bool = False) -> str:
        """
        LLM chat with full context - like original single agent's LLM chat.
        """
        context = self._build_context(user_id)
        
        if is_conversation:
            # Pure conversation - knows who it is
            system_prompt = """你是一个专业的生物信息分析助手，名叫 CellClaw。

你是用户的生物信息分析助手，可以帮助用户：
- 做单细胞数据分析（scRNA, snRNA）
- 差异表达分析  
- 细胞类型注释
- 批次效应校正
- 数据可视化

你知道用户的环境信息（服务器、工作目录、conda环境）。

你和用户对话时应该：
- 专业、友好、乐于助人
- 用用户的语言交流
- 可以回答关于分析的问题
- 可以解释你在做什么

当前用户环境：
{context}

直接回答用户，不需要说"我知道了"之类的废话。"""
        else:
            # Task-related chat
            system_prompt = """你是一个专业的生物信息分析助手 CellClaw。

当前用户环境：
{context}

用户可能是在：
- 问问题
- 请求帮助
- 或者只是想聊天

请根据上下文直接回答。"""

        prompt = f"用户说: {message}"
        
        response = await self._call_llm(prompt, system=system_prompt.format(context=context))
        
        if response:
            return response
        
        # Fallback if LLM fails
        if is_conversation:
            if any(g in message.lower() for g in ["你好", "hi", "hello", "嗨"]):
                return "你好！我是 CellClaw，有什么可以帮你的？"
            if "谢谢" in message:
                return "不客气！"
        
        return "抱歉，我现在无法回答。"

    # ───────────────────────────────────────────────────────────────
    # Executor Event Handler
    # ───────────────────────────────────────────────────────────────

    def on_executor_event(self, event: dict):
        """Handle executor notifications."""
        event_type = event.get("type")
        user_id = event.get("user_id")
        message = event.get("message", "")

        logger.info(f"Orchestrator: executor event {event_type} for {user_id}")

        if self._notify_callback:
            self._notify_callback(event)

    def __repr__(self) -> str:
        return f"<OrchestratorAgent: {self.name}>"
