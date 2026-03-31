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
        
        # All agents get ssh_manager for real context
        self.planner = PlannerAgent(shared_memory=self.shared_memory, ssh_manager=None)
        self.coder = CoderAgent(shared_memory=self.shared_memory, ssh_manager=None)
        self.reviewer = ReviewerAgent(shared_memory=self.shared_memory, ssh_manager=None)

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
        """Set SSH manager for real server data - propagates to all agents"""
        self._ssh_manager = ssh_manager
        # Propagate to all internal agents
        if hasattr(self, 'planner'):
            self.planner.base._ssh_manager = ssh_manager
        if hasattr(self, 'coder'):
            self.coder.base._ssh_manager = ssh_manager
        if hasattr(self, 'reviewer'):
            self.reviewer.base._ssh_manager = ssh_manager
        logger.info("SSH manager propagated to all agents")

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
    # Context Building
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
    # Intent Classification
    # ───────────────────────────────────────────────────────────────

    def _classify_intent(self, message: str, user_id: str) -> dict:
        """
        Classify user intent like original single-agent NL Router.
        """
        msg = message.strip()
        msg_lower = msg.lower()
        
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
        if any(kw in msg_lower for kw in ["新建", "创建", "mkdir", "删除", "移动", "复制"]):
            return {"action": "file_operation", "params": {"operation": msg}, "raw": msg}
        
        # ── Query / check info ─────────────────────────────────────────
        if any(kw in msg_lower for kw in ["多少", "几个", "有没有", "是什么", "平均", "最多", "最少", "查看", "看看", "告诉我", "查一下", "目前", "当前", "我们"]):
            # Must be about directory/path/workdir to be query
            if any(k in msg_lower for k in ["目录", "路径", "工作", "项目", "folder", "path"]):
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
        if any(k in msg_lower for k in ["qc", "质控", "过滤", "quality"]):
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

        # Classify intent
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
            response = await self._llm_chat(message, user_id)
        elif intent["action"] == "llm_chat":
            response = await self._llm_chat(intent["params"]["message"], user_id)
        else:
            response = await self._llm_chat(message, user_id)

        self.base.add_to_history(user_id, "assistant", response)
        return response

    # ───────────────────────────────────────────────────────────────
    # Handlers - REAL execution via SSH
    # ───────────────────────────────────────────────────────────────

    async def _handle_status(self, user_id: str) -> str:
        """Handle status query - REAL status via SSH Manager."""
        if not self._ssh_manager:
            return "未连接到服务器"
        return self._ssh_manager.get_session_summary(user_id)

    async def _handle_help(self, user_id: str) -> str:
        """Handle help request - returns actual command help."""
        if hasattr(self, '_ssh_manager') and self._ssh_manager and hasattr(self._ssh_manager, '_dispatcher'):
            return self._ssh_manager._dispatcher._global_help()
        
        # Fallback help
        return """CellClaw 使用指南

【分析命令】
- 帮我做差异分析 → 提交差异分析任务
- 帮我做QC → 提交质量控制任务
- 帮我跑SCTransform → 提交SCTransform分析
- 完整分析 → 从头到尾完整流程

【文件操作】
- 新建文件夹xxx → 在当前目录创建文件夹
- 查看当前目录 → 显示目录内容
- 切换到xxx目录 → 切换工作目录

【系统命令】
- /server add → 添加服务器
- /server use xxx → 切换服务器
- /env list → 查看conda环境
- /env use xxx → 切换conda环境
- /status → 查看当前状态

直接用自然语言描述你想做的事就行！"""

    async def _handle_query(self, params: dict, user_id: str) -> str:
        """
        Handle data query - NEVER fabricate critical info.
        Only return REAL data from SSH registry. If unknown, say so.
        """
        if not self._ssh_manager:
            return "抱歉，未连接到服务器。请先配置服务器。"
        
        question = params.get("question", "")
        msg_lower = question.lower()
        
        # Get session context
        try:
            session = self._ssh_manager._registry.get_session(user_id)
            workdir = session.active_project_path if session and session.active_project_path else "~"
            conda_env = session.active_conda_env if session else None
        except:
            workdir = "~"
            conda_env = None
        
        # File count query
        if any(k in msg_lower for k in ["多少", "几个"]) and "文件" in msg_lower:
            cmd = "find " + workdir + " -type f 2>/dev/null | wc -l"
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return "当前目录共有 " + result.stdout.strip() + " 个文件"
        
        # List directory
        if any(k in msg_lower for k in ["有什么", "列出", "查看", "ls"]):
            target = self._extract_path(question, workdir)
            cmd = "ls -lah " + target
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return "目录 " + target + " 内容:\n" + result.stdout
            return "无法查看目录"
        
        # Conda environments
        if "conda" in msg_lower or "环境" in msg_lower:
            cmd = "conda env list 2>/dev/null || echo 'conda not found'"
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return "Conda 环境:\n" + result.stdout
        
        # Current directory - MUST get REAL workdir from registry
        if ("当前" in msg_lower or "目前" in msg_lower) and ("目录" in msg_lower or "路径" in msg_lower or "项目" in msg_lower or "工作" in msg_lower):
            if self._ssh_manager:
                try:
                    session = self._ssh_manager._registry.get_session(user_id)
                    real_workdir = session.active_project_path if session else None
                    if real_workdir:
                        return "当前工作目录: " + real_workdir
                except:
                    pass
            # NEVER fabricate - if we don't know, say so
            return "暂未设置工作目录，请先用 /project set <路径> 设置"

        # Default: NEVER fabricate, use LLM only for non-critical info
        return await self._llm_query(question, require_real_data=False)
        
        # Jobs status
        if "任务" in msg_lower or "job" in msg_lower:
            jobs = self.executor.get_active_jobs(user_id)
            if jobs:
                lines = ["运行中的任务 (" + str(len(jobs)) + "):"]
                for j in jobs:
                    lines.append("- " + j.description + ": " + j.status)
                return "\n".join(lines)
            return "当前没有运行中的任务"
        
        # Fallback to LLM
        return await self._llm_query(question)

    def _extract_path(self, text: str, default: str) -> str:
        """Extract path from text."""
        patterns = [r'[/~][^\s]+', r'到\s*([^\s]+)', r'目录\s*([^\s]+)']
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return default

    async def _llm_query(self, question: str, require_real_data: bool = True) -> str:
        """
        Use LLM to answer query - but NEVER fabricate critical server info.
        """
        msg_lower = question.lower()
        
        # Check if asking about CRITICAL info (server/workdir/conda)
        critical_keywords = ["目录", "路径", "工作", "项目", "服务器", "conda", "环境", "server"]
        if require_real_data and any(k in msg_lower for k in critical_keywords):
            # This is critical info - we should have it or say we don't
            if self._ssh_manager:
                try:
                    session = self._ssh_manager._registry.get_session(user_id)
                    if session:
                        parts = []
                        if session.active_project_path:
                            parts.append("工作目录: " + session.active_project_path)
                        if session.active_server_id:
                            parts.append("服务器: " + session.active_server_id)
                        if session.active_conda_env:
                            parts.append("Conda环境: " + session.active_conda_env)
                        if parts:
                            return "\n".join(parts)
                except:
                    pass
            return "抱歉，我无法获取该信息。请确认已连接服务器并设置工作目录。"
        
        # Non-critical info - can use LLM
        context = self._build_context("user")
        prompt = "用户问: " + question + "\n\n当前用户环境:\n" + context + "\n\n请直接简洁回答用户问题。"
        response = await self._call_llm(prompt, system="你是生物信息分析助手，直接简洁回答用户问题。")
        return response if response else "抱歉，我无法回答这个问题。"

    async def _handle_read_script(self, params: dict, user_id: str) -> str:
        """Handle read script request."""
        return "请告诉我脚本的完整路径，我帮你读取。"

    async def _handle_modify_script(self, params: dict, user_id: str) -> str:
        """Handle modify script request."""
        return "请告诉我脚本的完整路径和要修改的内容。"

    async def _handle_file_operation(self, params: dict, user_id: str) -> str:
        """Handle file operations - REAL execution via SSH."""
        if not self._ssh_manager:
            return "抱歉，未连接到服务器。请先配置服务器。"
        
        operation = params.get("operation", "")
        msg_lower = operation.lower()
        
        # Get workdir
        try:
            session = self._ssh_manager._registry.get_session(user_id)
            workdir = session.active_project_path if session and session.active_project_path else "~/"
        except:
            workdir = "~/"
        
        # mkdir
        if "新建" in operation or "创建" in operation or "mkdir" in msg_lower:
            folder_name = self._extract_folder_name(operation)
            target_path = workdir + "/" + folder_name
            cmd = "mkdir -p " + target_path
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return "已创建文件夹: " + target_path
            return "创建失败: " + (result.stderr if result else "未知错误")
        
        # rm
        if "删除" in operation or "rm" in msg_lower:
            target = self._extract_target(operation, workdir)
            cmd = "rm -rf " + target
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return "已删除: " + target
            return "删除失败: " + (result.stderr if result else "未知错误")
        
        # ls
        if "查看" in operation or "ls" in msg_lower or "列出" in operation:
            target = self._extract_target(operation, workdir)
            cmd = "ls -lah " + target
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return "目录内容 (" + target + "):\n" + result.stdout
            return "查看失败: " + (result.stderr if result else "未知错误")
        
        # cd / workdir
        if "切换" in operation or "cd " in msg_lower:
            new_workdir = self._extract_target(operation, workdir)
            try:
                self._ssh_manager._registry.set_workdir(user_id, new_workdir)
                return "已切换到目录: " + new_workdir
            except Exception as e:
                return "切换失败: " + str(e)
        
        return "支持的操作: 新建文件夹, 删除, 查看目录, 切换目录"

    def _extract_folder_name(self, operation: str) -> str:
        """Extract folder name."""
        patterns = [r'[的新建创建]*文件夹 ?([^\s]+)', r'[的新建创建]* ?([^\s]+) ?文件夹', r'mkdir\s+([^\s]+)']
        for pattern in patterns:
            match = re.search(pattern, operation)
            if match:
                return match.group(1).strip()
        return "untitled"

    def _extract_target(self, operation: str, default: str) -> str:
        """Extract target path."""
        patterns = [r'[/~][^\s]+', r'到(.+?)(?:$|\s)', r'目录\s*([^\s]+)']
        for p in patterns:
            m = re.search(p, operation)
            if m:
                return m.group(1).strip()
        return default

    async def _handle_analyze(self, params: dict, user_id: str) -> str:
        """
        Handle analysis - FULL multi-agent flow.
        """
        question = params.get("question", "")
        intent = await self.planner.understand(question, user_id)
        
        if intent.is_simple_task:
            return await self._handle_simple_analysis(intent, question, user_id)
        else:
            return await self._handle_complex_analysis(intent, question, user_id)

    async def _handle_simple_analysis(self, intent, question: str, user_id: str) -> str:
        """Handle simple analysis - single step."""
        code_result = await self.coder.generate(
            task_description=question,
            skill_id=intent.skill_needed,
            language="R"
        )
        review_result = await self.reviewer.check(code_result.code, code_result.language)
        if not review_result.can_execute:
            issues = "\n".join([f"- [{i.severity}] {i.category}: {i.message}" for i in review_result.issues])
            return "代码审查未通过:\n" + issues
        script_path = await self.coder.save_script(code_result.code, code_result.language)
        job_id = await self.executor.submit(
            script_path=script_path,
            user_id=user_id,
            channel_id=None,
            description=question,
            skill_used=intent.skill_needed
        )
        skill_info = "使用技能: " + intent.skill_needed if intent.skill_needed else ""
        return "已提交分析任务\n" + skill_info + "\n任务ID: " + job_id + "\n描述: " + question + "\n执行完成后会通知你"

    async def _handle_complex_analysis(self, intent, question: str, user_id: str) -> str:
        """Handle complex analysis - multiple steps."""
        plan = self.planner.create_plan(question, intent, user_id)
        self._plans[plan.plan_id] = plan
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
        return "已提交复杂分析任务\n步骤数: " + str(len(plan.steps)) + "\n技能: " + (intent.skill_needed or "通用") + "\n执行完成后会通知你"

    async def _handle_full_pipeline(self, params: dict, user_id: str) -> str:
        """Handle full pipeline."""
        return "完整分析流程正在开发中..."

    # ───────────────────────────────────────────────────────────────
    # LLM Chat - knows identity
    # ───────────────────────────────────────────────────────────────

    async def _llm_chat(self, message: str, user_id: str) -> str:
        """
        LLM chat - knows identity like original single agent.
        """
        context = self._build_context(user_id)
        
        system_prompt = (
            "你是一个专业的生物信息分析助手，名叫 CellClaw。\n\n"
            "你的身份和能力：\n"
            "- 你可以通过SSH连接用户的服务器\n"
            "- 你可以执行数据分析任务\n"
            "- 你可以读写文件、管理文件夹\n"
            "- 你知道用户的服务器、工作目录、conda环境配置\n\n"
            "当前用户环境：\n"
            "{context}\n\n"
            "你应该：\n"
            "- 专业、友好、乐于助人\n"
            "- 用用户语言交流（中文或英文）\n"
            "- 直接回答用户问题\n"
            "- 主动提供帮助\n"
        )
        
        response = await self._call_llm(message, system=system_prompt.format(context=context))
        
        if response:
            return response
        
        # Fallback
        msg_lower = message.lower()
        if any(g in msg_lower for g in ["你好", "hi", "hello", "嗨", "在吗"]):
            return "你好！我是 CellClaw，你的生物信息分析助手。有什么可以帮你的？"
        if "谢谢" in msg_lower:
            return "不客气！有问题随时问我。"
        if "再见" in msg_lower or "拜拜" in msg_lower:
            return "再见！"
        return "抱歉，我现在无法回答。请稍后重试。"

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
