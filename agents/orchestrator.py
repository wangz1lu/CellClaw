"""
OrchestratorAgent - Main Coordinator
====================================

LLM classifies intent into handlers:
- conversation: Direct chat
- status: Return status
- help: Return help
- query: Return information
- file_operation: SSH file operations
- easy_task: Direct execution via SSH (downloads, simple commands)
- analyze: Multi-agent flow (Planner→Coder→Reviewer→Executor)

For analyze, user is asked to confirm before execution.
"""

from __future__ import annotations
import os
import re
import logging
import asyncio
from typing import Optional, Callable

from agents.base import BaseAgent
from agents.memory import SharedMemory, get_shared_memory
from agents.models import (
    AgentConfig, AgentType, TaskStep, ExecutionPlan, TaskStatus, Intent
)

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """
    OrchestratorAgent - Single interface for user communication.
    
    LLM decides which handler to use:
    - conversation: Greetings, casual chat
    - status: Current server/workdir/conda/env/jobs
    - help: How to use
    - query: Questions about data/info
    - file_operation: SSH file operations (mkdir, rm, ls)
    - easy_task: Simple tasks executed directly (download, curl, wget)
    - analyze: Complex tasks via multi-agent (analysis, QC, etc.)
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

        # Internal agents for complex tasks
        from agents.planner import PlannerAgent
        from agents.coder import CoderAgent
        from agents.reviewer import ReviewerAgent
        from agents.executor import ExecutorAgent

        self.shared_memory = get_shared_memory()
        self.planner = PlannerAgent(shared_memory=self.shared_memory, ssh_manager=None)
        self.coder = CoderAgent(shared_memory=self.shared_memory, ssh_manager=None)
        self.reviewer = ReviewerAgent(shared_memory=self.shared_memory, ssh_manager=None)
        self.executor = ExecutorAgent()
        self.executor.set_notify_callback(self.on_executor_event)

        # User notification callback
        self._notify_callback: Optional[Callable] = None

        # Real data sources
        self._ssh_manager = None
        self._job_tracker = None

        # Pending task for confirmation
        self._pending_task: dict = {}

        logger.info(f"OrchestratorAgent initialized")

    def set_notify_callback(self, callback: Callable):
        """Set callback for user notifications"""
        self._notify_callback = callback
        self.executor.set_user_notify_callback(callback)

    def set_ssh_manager(self, ssh_manager):
        """Set SSH manager and propagate to agents"""
        self._ssh_manager = ssh_manager
        if hasattr(self, 'planner'):
            self.planner.base._ssh_manager = ssh_manager
        if hasattr(self, 'coder'):
            self.coder.base._ssh_manager = ssh_manager
        if hasattr(self, 'reviewer'):
            self.reviewer.base._ssh_manager = ssh_manager
        logger.info("SSH manager propagated to all agents")

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
            "temperature": 0.3,
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
                servers = self._ssh_manager._registry.list_servers(user_id)
                if servers:
                    parts.append(f"服务器: {len(servers)} 台已配置")

                session = self._ssh_manager._registry.get_session(user_id)
                if session:
                    if session.active_server_id:
                        parts.append(f"当前服务器: {session.active_server_id}")
                    if session.active_project_path:
                        parts.append(f"当前工作目录: {session.active_project_path}")
                    if session.active_conda_env:
                        parts.append(f"Conda环境: {session.active_conda_env}")
            except:
                pass

        try:
            jobs = self.executor.get_active_jobs(user_id)
            if jobs:
                parts.append(f"运行中任务: {len(jobs)}")
        except:
            pass

        return "\n".join(parts) if parts else "无配置信息"

    # ───────────────────────────────────────────────────────────────
    # Main Processing
    # ───────────────────────────────────────────────────────────────

    async def process(self, message: str, user_id: str, channel_id: str = None) -> str:
        """Main entry point - LLM classifies and routes to handlers."""
        logger.info(f"Orchestrator: '{message[:50]}...' user={user_id}")

        self.base.add_to_history(user_id, "user", message)

        # Check if user confirmed a pending task
        if self._pending_task.get(user_id):
            if any(k in message.lower() for k in ["是", "好的", "确认", "继续", "yes", "go", "do"]):
                pending = self._pending_task.pop(user_id, None)
                if pending:
                    return await self._execute_analyze(pending, user_id)

            # User didn't confirm, clear pending
            self._pending_task.pop(user_id, None)

        # LLM classifies intent
        intent = await self._classify_intent(message, user_id)
        logger.info(f"Intent: {intent}")

        handler = intent.get("handler")
        params = intent.get("params", {})

        # Route to appropriate handler
        if handler == "conversation":
            response = await self._handle_conversation(message, user_id)
        elif handler == "status":
            response = await self._handle_status(user_id)
        elif handler == "help":
            response = await self._handle_help(user_id)
        elif handler == "query":
            response = await self._handle_query(params, user_id)
        elif handler == "file_operation":
            response = await self._handle_file_operation(params, user_id)
        elif handler == "easy_task":
            response = await self._handle_easy_task(params, user_id)
        elif handler == "analyze":
            response = await self._handle_analyze_intent(message, params, user_id)
        else:
            response = await self._handle_conversation(message, user_id)

        self.base.add_to_history(user_id, "assistant", response)
        return response

    async def _classify_intent(self, message: str, user_id: str) -> dict:
        """
        LLM classifies user message into handler type.
        """
        context = self._build_context(user_id)

        prompt = (
            "分析用户消息，选择正确的处理器：\n\n"
            "处理器选项：\n"
            "- conversation: 问好、谢谢、再见、闲聊\n"
            "- status: 问当前状态（服务器/工作目录/conda/任务数）\n"
            "- help: 问怎么用、有什么功能\n"
            "- query: 问信息问题（多少/是什么/查看）\n"
            "- file_operation: 文件操作（新建/删除/查看文件夹）\n"
            "- easy_task: 简单任务直接执行（下载文件/运行简单命令）\n"
            "- analyze: 复杂任务（分析/处理/计算）需要多步骤\n\n"
            "判断：\n"
            "- '你好/谢谢/你是谁' -> conversation\n"
            "- '当前状态/有几台服务器' -> status\n"
            "- '怎么用/help' -> help\n"
            "- '是什么/有多少/查看' -> query\n"
            "- '新建文件夹/删除/ls' -> file_operation\n"
            "- '帮我下载/curl/wget/运行命令' -> easy_task\n"
            "- '帮我做分析/跑流程/处理数据/差异分析' -> analyze\n\n"
            "用户消息: " + message + "\n\n"
            "返回格式：handler=xxx, params=xxx\n"
            "只返回一个选项。"
        )

        response = await self._call_llm(prompt)

        if not response:
            return {"handler": "conversation", "params": {}}

        response = response.lower()

        # Parse response
        if "conversation" in response:
            return {"handler": "conversation", "params": {"message": message}}
        elif "status" in response:
            return {"handler": "status", "params": {}}
        elif "help" in response:
            return {"handler": "help", "params": {}}
        elif "query" in response:
            return {"handler": "query", "params": {"question": message}}
        elif "file_operation" in response:
            return {"handler": "file_operation", "params": {"operation": message}}
        elif "easy_task" in response:
            return {"handler": "easy_task", "params": {"task": message}}
        elif "analyze" in response:
            return {"handler": "analyze", "params": {"task": message}}
        else:
            return {"handler": "conversation", "params": {"message": message}}

    # ───────────────────────────────────────────────────────────────
    # Handlers
    # ───────────────────────────────────────────────────────────────

    async def _handle_conversation(self, message: str, user_id: str) -> str:
        """Handle casual conversation."""
        msg_lower = message.lower()

        if any(g in msg_lower for g in ["你好", "hi", "hello", "嗨", "在吗"]):
            return "你好！我是 CellClaw，你的生物信息分析助手。有什么可以帮你的？"
        if "谢谢" in msg_lower:
            return "不客气！有问题随时问我。"
        if "再见" in msg_lower or "拜拜" in msg_lower:
            return "再见！"
        if "你是谁" in msg_lower:
            return "我是 CellClaw，一个专注于生物信息学分析的 AI 助手。"

        # Use LLM for other conversation
        prompt = "用户: " + message + " 请简洁回应。"
        response = await self._call_llm(prompt)
        return response if response else "我明白了。"

    async def _handle_status(self, user_id: str) -> str:
        """Return real status from SSH registry."""
        if not self._ssh_manager:
            return "未连接到服务器"

        return self._ssh_manager.get_session_summary(user_id)

    async def _handle_help(self, user_id: str) -> str:
        """Return help text."""
        return """CellClaw 使用指南

【状态查询】
- 当前服务器/工作目录/conda环境

【文件操作】
- 新建文件夹xxx
- 删除xxx
- 查看目录内容

【简单任务】
- 帮我下载文件
- 运行xxx命令

【复杂分析任务】
- 帮我做差异分析
- 帮我跑SCTransform
- 帮我做细胞注释

直接告诉我你想做什么！"""

    async def _handle_query(self, params: dict, user_id: str) -> str:
        """Handle information queries - return real data."""
        question = params.get("question", "")
        msg_lower = question.lower()

        if not self._ssh_manager:
            return "未连接到服务器"

        # Get real data
        session = self._ssh_manager._registry.get_session(user_id)
        workdir = session.active_project_path if session and session.active_project_path else None

        # File count
        if any(k in msg_lower for k in ["多少", "几个"]) and "文件" in msg_lower:
            cmd = f"find {workdir or '.'} -type f 2>/dev/null | wc -l"
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return f"当前目录共有 {result.stdout.strip()} 个文件"

        # List directory
        if any(k in msg_lower for k in ["有什么", "列出", "查看", "ls"]):
            target = workdir or "."
            cmd = f"ls -lah {target}"
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return f"目录 {target} 内容:\n{result.stdout}"

        # Conda envs
        if "conda" in msg_lower or "环境" in msg_lower:
            cmd = "conda env list 2>/dev/null || echo 'conda not found'"
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return f"Conda环境:\n{result.stdout}"

        # Default - return context
        context = self._build_context(user_id)
        return f"当前信息:\n{context}"

    async def _handle_file_operation(self, params: dict, user_id: str) -> str:
        """Handle file operations via SSH."""
        if not self._ssh_manager:
            return "未连接到服务器"

        operation = params.get("operation", "")
        msg_lower = operation.lower()

        session = self._ssh_manager._registry.get_session(user_id)
        workdir = session.active_project_path if session and session.active_project_path else "~"

        # mkdir
        if "新建" in operation or "创建" in operation or "mkdir" in msg_lower:
            folder = self._extract_folder_name(operation)
            target = f"{workdir}/{folder}"
            cmd = f"mkdir -p {target}"
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return f"已创建文件夹: {target}"
            return f"创建失败: {result.stderr if result else '未知错误'}"

        # rm
        if "删除" in operation:
            target = self._extract_target(operation, workdir)
            cmd = f"rm -rf {target}"
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return f"已删除: {target}"
            return f"删除失败: {result.stderr if result else '未知错误'}"

        # ls
        if "查看" in operation or "ls" in msg_lower:
            target = self._extract_target(operation, workdir)
            cmd = f"ls -lah {target}"
            result = await self._ssh_manager.run(user_id, cmd)
            if result and result.success:
                return f"目录内容:\n{result.stdout}"
            return f"查看失败: {result.stderr if result else '未知错误'}"

        return "支持: 新建文件夹, 删除, 查看目录"

    async def _handle_easy_task(self, params: dict, user_id: str) -> str:
        """Handle simple tasks directly - no multi-agent needed."""
        if not self._ssh_manager:
            return "未连接到服务器"

        task = params.get("task", "")
        msg_lower = task.lower()

        session = self._ssh_manager._registry.get_session(user_id)
        workdir = session.active_project_path if session and session.active_project_path else "~"

        # Download task
        if "下载" in task or "wget" in msg_lower or "curl" in msg_lower:
            # Extract URL
            url_match = re.search(r'https?://[^\s]+', task)
            if url_match:
                url = url_match.group(0)
                filename = url.split("/")[-1] or "download"
                cmd = f"cd {workdir} && wget -O {filename} '{url}'"
                result = await self._ssh_manager.run(user_id, cmd, timeout=300)
                if result and result.success:
                    return f"下载完成: {workdir}/{filename}\n{result.stdout[-200:] if result.stdout else ''}"
                return f"下载失败: {result.stderr if result else '未知错误'}"
            return "请提供下载链接"

        # Default - run command
        return "该任务较复杂，建议使用 analyze 流程"

    async def _handle_analyze_intent(self, message: str, params: dict, user_id: str) -> str:
        """
        Handle complex analysis tasks - ask for confirmation first.
        User must confirm before multi-agent flow begins.
        """
        task = params.get("task", message)

        # Store pending task and ask for confirmation
        self._pending_task[user_id] = params

        return (
            f"分析任务: {task}\n\n"
            f"此为复杂任务，将启动多Agent协作模式：\n"
            f"1. Planner 理解任务并制定计划\n"
            f"2. Coder 生成代码\n"
            f"3. Reviewer 检查代码\n"
            f"4. Executor 提交执行\n\n"
            f"任务将在后台执行，完成后通知你。\n\n"
            f"是否继续？(是/好的/继续)"
        )

    async def _execute_analyze(self, params: dict, user_id: str) -> str:
        """
        Full pipeline: Planner → Coder → Reviewer → Executor
        
        1. Planner: Check skills, create plan, save plan.txt to workdir
        2. Coder: Write script to SSH workdir
        3. Reviewer: Read from SSH, check, Coder rewrites if needed
        4. Executor: Submit with nohup, sync status to Dashboard
        """
        task = params.get("task", "")
        
        # Notify starting
        await self._notify_progress("开始分析流程", "Planner 正在分析任务...")
        
        # Step 1: Planner
        intent = await self.planner.understand(task, user_id)
        
        # Check if existing skills can fulfill
        skill_needed = intent.skill_needed
        if skill_needed:
            plan_text = f"任务: {task}\n使用技能: {skill_needed}\n\n分析计划:\n"
            plan_text += f"1. 使用 {skill_needed} 技能\n"
            plan_text += f"2. 生成代码\n3. 审查代码\n4. 提交执行"
        else:
            plan_text = f"任务: {task}\n\n分析计划:\n1. 生成代码\n2. 审查代码\n3. 提交执行"
        
        # Save plan to workdir
        plan_path = await self._save_plan_to_workdir(user_id, plan_text, task)
        await self._notify_progress("计划已生成", f"计划文件: {plan_path}")
        
        # Step 2-3: Coder → Reviewer loop
        max_iterations = 3
        script_path = None
        code_result = None
        
        for i in range(max_iterations):
            # Coder generates
            code_result = await self.coder.generate(
                task_description=task,
                skill_id=skill_needed,
                language="R"
            )
            
            # Save to SSH workdir
            script_path = await self._save_script_to_ssh(user_id, code_result.code, code_result.language, task)
            await self._notify_progress(f"[Coder] 代码已生成 ({i+1}/3)", f"脚本: {script_path}")
            
            # Reviewer checks
            review_result = await self.reviewer.check(code_result.code, code_result.language)
            
            if review_result.can_execute:
                await self._notify_progress("[Reviewer] 审查通过", f"代码可执行")
                break
            else:
                issues = "\n".join([f"- [{issue.severity}] {issue.message}" for issue in review_result.issues])
                await self._notify_progress(f"[Reviewer] 需要修改 ({i+1}/3)", issues)
                # Ask Coder to fix
                code_result.code = await self.reviewer.fix(code_result.code, review_result.issues)
                # Save fixed version
                script_path = await self._save_script_to_ssh(user_id, code_result.code, code_result.language, task)
                continue
        
        if not code_result or not script_path:
            return "代码生成失败"
        
        # Step 4: Executor submits with nohup
        job_id = await self.executor.submit(
            script_path=script_path,
            user_id=user_id,
            channel_id=None,
            description=task,
            skill_used=skill_needed,
            script_content=code_result.code
        )
        
        return (
            "分析流程已完成\n\n"
            "计划文件: " + plan_path + "\n"
            "脚本位置: " + script_path + "\n"
            "任务 ID: " + job_id + "\n\n"
            "任务正在后台执行，完成后会通知你"
        )

    async def _save_plan_to_workdir(self, user_id: str, plan_text: str, task: str) -> str:
        """Save plan to SSH workdir."""
        import time
        import secrets
        
        plan_filename = f"plan_{secrets.token_hex(4)}.txt"
        
        if self._ssh_manager:
            try:
                session = self._ssh_manager._registry.get_session(user_id)
                workdir = session.active_project_path if session and session.active_project_path else "~/cellclaw_jobs"
                
                # Write to SSH
                full_path = f"{workdir}/{plan_filename}"
                cmd = f"echo '{plan_text}' > {full_path}"
                await self._ssh_manager.run(user_id, cmd)
                return full_path
            except:
                pass
        
        # Fallback - return local path
        return f"~/cellclaw_jobs/{plan_filename}"

    async def _save_script_to_ssh(self, user_id: str, code: str, language: str, task: str) -> str:
        """Coder writes script directly to SSH workdir."""
        import secrets
        
        ext = ".R" if language == "R" else ".py"
        filename = f"job_{secrets.token_hex(4)}{ext}"
        
        if self._ssh_manager:
            try:
                session = self._ssh_manager._registry.get_session(user_id)
                workdir = session.active_project_path if session and session.active_project_path else "~/cellclaw_jobs"
                
                full_path = f"{workdir}/{filename}"
                
                # Write script content to SSH via sftp or run command
                escaped_code = code.replace("'", "'\''").replace("\n", "\\n")
                cmd = f"cat > {full_path} << 'SCRIPT_EOF'\n{code}\nSCRIPT_EOF"
                await self._ssh_manager.run(user_id, cmd)
                
                logger.info(f"Saved script to SSH: {full_path}")
                return full_path
            except Exception as e:
                logger.error(f"Failed to save to SSH: {e}")
        
        return f"~/cellclaw_jobs/{filename}"

    async def _notify_progress(self, title: str, detail: str):
        """Notify progress to user via callback."""
        if self._notify_callback:
            self._notify_callback({
                "type": "progress",
                "title": title,
                "detail": detail,
                "message": f"📋 {title}\n{detail}"
            })

    async def _handle_simple_analysis(self, intent, task: str, user_id: str) -> str:
        """Handle simple analysis - single step."""
        code_result = await self.coder.generate(
            task_description=task,
            skill_id=intent.skill_needed,
            language="R"
        )

        review_result = await self.reviewer.check(code_result.code, code_result.language)
        if not review_result.can_execute:
            issues = "\n".join([f"- [{i.severity}] {i.category}: {i.message}" for i in review_result.issues])
            return f"代码审查未通过:\n{issues}"

        script_path = await self.coder.save_script(code_result.code, code_result.language)
        job_id = await self.executor.submit(
            script_path=script_path,
            user_id=user_id,
            channel_id=None,
            description=task,
            skill_used=intent.skill_needed
        )

        return (
            f"任务已提交\n"
            f"任务ID: {job_id}\n"
            f"描述: {task}\n"
            f"执行完成后会通知你"
        )

    async def _handle_complex_analysis(self, intent, task: str, user_id: str) -> str:
        """Handle complex analysis - multiple steps."""
        plan = self.planner.create_plan(task, intent, user_id)

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
            f"复杂任务已提交\n"
            f"步骤数: {len(plan.steps)}\n"
            f"各步骤执行完成后会通知你"
        )

    # ───────────────────────────────────────────────────────────────
    # Helpers
    # ───────────────────────────────────────────────────────────────

    def _extract_folder_name(self, text: str) -> str:
        patterns = [r'文件夹 ?([^\s]+)', r'创建 ?([^\s]+)', r'mkdir\s+([^\s]+)']
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1).strip()
        return "untitled"

    def _extract_target(self, text: str, default: str) -> str:
        patterns = [r'[/~][^\s]+', r'到\s*([^\s]+)']
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1).strip()
        return default

    # ───────────────────────────────────────────────────────────────
    # Executor Event Handler
    # ───────────────────────────────────────────────────────────────

    def on_executor_event(self, event: dict):
        """Handle executor notifications."""
        if self._notify_callback:
            self._notify_callback(event)

    def __repr__(self) -> str:
        return f"<OrchestratorAgent: {self.name}>"
