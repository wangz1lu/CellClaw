"""
OmicsClaw Agent — Core Entry Point
=====================================
Unified dispatcher: slash commands → SSH Manager
                    natural language → NL Router → SSH Manager
                    file uploads    → auto-detect & register

Architecture:
    Discord message
        │
        ▼
    OmicsClawAgent.handle_message()
        ├── [slash cmd]   → CommandDispatcher → SSH layer
        ├── [file upload] → handle_upload()
        └── [NL text]     → NLRouter → intent → SSH layer → results

All results are returned as AgentResponse, which the channel adapter
(Discord) renders into messages + file attachments.
"""

from __future__ import annotations
import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..omics_discord.dispatcher import CommandDispatcher
from ..omics_discord.result import CommandResult, ResultType
from ..ssh.manager import SSHManager
from ..ssh.models import JobStatus
from .nl_router import NLRouter
from .code_generator import CodeGenerator
from .llm import get_llm_client, ToolCall
from .memory import MemoryManager
from .session_store import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """
    Unified response object returned to the Discord adapter.

    text:       Main message (markdown)
    figures:    Local file paths to send as attachments
    ephemeral:  Only visible to invoking user (if platform supports)
    dm_user_id: If set, send a DM to this user instead of channel
    dm_text:    Content of the DM
    job_id:     If a background job was submitted
    poll_secs:  How often to poll job (0 = no polling)
    """
    text: str
    figures: list[str] = field(default_factory=list)
    ephemeral: bool = False
    dm_user_id: Optional[str] = None
    dm_text: Optional[str] = None
    job_id: Optional[str] = None
    poll_secs: int = 0


class OmicsClawAgent:
    """
    Main OmicsClaw agent.
    Instantiated once; stateless per-message (state lives in SSHManager/Registry).
    """

    def __init__(self, workspace_dir: Optional[str] = None):
        self._workspace = Path(workspace_dir or tempfile.mkdtemp(prefix="omicsclaw_"))
        self._workspace.mkdir(parents=True, exist_ok=True)

        self._ssh        = SSHManager()
        self._dispatcher = CommandDispatcher(self._ssh)
        self._nl_router  = NLRouter(self._ssh)
        self._code_gen   = CodeGenerator()

        # Memory: daily logs + MEMORY.md (per user)
        self._memory  = MemoryManager(str(self._workspace))
        # Session: persistent JSONL transcript (per user) — like OpenClaw
        self._sessions = SessionManager(str(self._workspace))

        # Tracks active job polling tasks per user
        self._poll_tasks: dict[str, asyncio.Task] = {}

        logger.info(f"OmicsClawAgent initialized | workspace={self._workspace}")

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #

    async def handle_message(
        self,
        message: str,
        discord_user_id: str,
        attachments: Optional[list[str]] = None,
        is_dm: bool = False,
        channel_id: Optional[str] = None,
    ) -> AgentResponse:
        """
        Process an incoming Discord message and return an AgentResponse.

        Args:
            message:          Raw message text
            discord_user_id:  Discord user snowflake ID
            attachments:      List of local file paths (already downloaded)
            is_dm:            Whether this is a DM (affects password collection)
            channel_id:       Source channel (for job completion notifications)
        """
        # 1. Handle file uploads first
        if attachments:
            upload_response = await self._handle_uploads(attachments, discord_user_id)
            if upload_response:
                return upload_response

        # 2. Try slash command dispatcher
        cmd_result = await self._dispatcher.dispatch(message, discord_user_id, is_dm=is_dm)
        if cmd_result is not None:
            response = self._cmd_result_to_response(cmd_result, discord_user_id)
            return response

        # 3. Natural language → agent loop
        session = self._sessions.get(discord_user_id)

        # Auto-compact if history is getting too long
        if session.needs_compaction():
            await self._compact_session(discord_user_id, session)

        # Persist user message
        session.add({"role": "user", "content": message})

        # Run agent
        response = await self._handle_nl(message, discord_user_id, channel_id)

        # Persist assistant reply
        if response.text:
            session.add({"role": "assistant", "content": response.text})

        return response

    # ------------------------------------------------------------------ #
    # File upload handling
    # ------------------------------------------------------------------ #

    async def _handle_uploads(
        self, file_paths: list[str], discord_user_id: str
    ) -> Optional[AgentResponse]:
        """
        When a user uploads a file, try to auto-detect its type and
        register it in the session context.
        """
        lines = []
        for path in file_paths:
            ext = Path(path).suffix.lower()
            name = Path(path).name

            if ext in (".h5ad", ".h5", ".loom"):
                lines.append(
                    f"📂 检测到单细胞数据文件：`{name}`\n"
                    f"   格式：{ext} | 路径：`{path}`\n"
                    f"   💡 发送 `/project info {path}` 查看数据详情，"
                    f'或直接说"帮我分析这个文件"'
                )
            elif ext in (".rds", ".robj"):
                lines.append(
                    f"📂 检测到 R 数据文件：`{name}`\n"
                    f"   💡 直接说'帮我用 Seurat 分析这个文件'"
                )
            elif ext in (".py", ".r", ".rmd", ".sh"):
                lines.append(
                    f"📜 检测到脚本文件：`{name}`\n"
                    f"   💡 直接说'帮我读懂这个脚本'或'帮我优化这个脚本'"
                )
            elif ext in (".csv", ".tsv", ".txt"):
                lines.append(
                    f"📊 检测到数据表格：`{name}`\n"
                    f"   💡 告诉我你想用这个文件做什么分析"
                )
            else:
                lines.append(f"📎 收到文件：`{name}`（{ext}）")

        if lines:
            return AgentResponse(text="\n\n".join(lines))
        return None

    # ------------------------------------------------------------------ #
    # Natural language handling
    # ------------------------------------------------------------------ #

    async def _handle_nl(
        self,
        message: str,
        discord_user_id: str,
        channel_id: Optional[str],
    ) -> AgentResponse:
        """
        All natural language messages go directly to LLM Agent.
        The LLM decides what tools to call (shell/python/read_file/write_file/list_dir).
        """
        return await self._handle_llm_chat(message, discord_user_id)

        # ── Quick query (synchronous) ──────────────────────────────────
        if action == "query":
            return await self._handle_query(params, discord_user_id)

        # ── Script read/modify ─────────────────────────────────────────
        elif action == "read_script":
            return await self._handle_read_script(params, discord_user_id)

        # ── Long analysis (background job) ────────────────────────────
        elif action in ("analyze", "full_pipeline", "run_script"):
            return await self._handle_analysis(
                action, params, discord_user_id, channel_id
            )

        # ── Environment setup ──────────────────────────────────────────
        elif action == "setup_env":
            return await self._handle_env_setup(params, discord_user_id)

        # ── Status / help ──────────────────────────────────────────────
        elif action == "status":
            text = self._ssh.get_session_summary(discord_user_id)
            return AgentResponse(text=text)

        elif action == "help":
            return AgentResponse(text=self._dispatcher._global_help())

        elif action == "llm_chat":
            return await self._handle_llm_chat(
                params.get("message", message),
                discord_user_id,
                context_filepath=params.get("filepath"),
            )

        else:
            llm = get_llm_client()
            if llm.enabled:
                return await self._handle_llm_chat(message, discord_user_id)
            return AgentResponse(
                text=(
                    "🧬 我理解你想做生信分析！请告诉我更多细节，例如：\n"
                    "- 数据文件在哪里？（路径）\n"
                    "- 想用哪个 conda 环境？\n"
                    "- 想做什么分析？（QC / 聚类 / 差异表达 / 空间转录组...）\n\n"
                    "或者发送 `/help` 查看所有命令。"
                )
            )

    # ------------------------------------------------------------------ #
    # Action handlers
    # ------------------------------------------------------------------ #

    async def _handle_query(
        self, params: dict, discord_user_id: str
    ) -> AgentResponse:
        """
        Handle a quick data query (synchronous, < 60s).
        e.g. "cluster 3 有多少细胞？"
        """
        filepath = params.get("filepath")
        question = params.get("question", "")
        conda_env = params.get("conda_env")

        if not filepath:
            # Try to use session context
            session = self._ssh._registry.get_session(discord_user_id)
            if not session.active_project_path:
                return AgentResponse(
                    text="❓ 请先用 `/project set <path>` 设置项目目录，"
                         "或在问题中指定文件路径。"
                )

        # Generate a query script
        query_code = self._code_gen.generate_query(
            filepath=filepath,
            question=question,
            conda_env=conda_env,
        )

        try:
            result = await self._ssh.run_python(
                discord_user_id=discord_user_id,
                code=query_code,
                conda_env=conda_env,
                timeout=60,
            )
            answer = result.output or "(无输出)"
            return AgentResponse(text=f"📊 **查询结果：**\n```\n{answer}\n```")
        except ValueError as e:
            return AgentResponse(text=f"❌ {e}")
        except Exception as e:
            logger.exception("Query failed")
            return AgentResponse(text=f"❌ 查询出错：{e}")

    async def _handle_read_script(
        self, params: dict, discord_user_id: str
    ) -> AgentResponse:
        """Read and explain an existing script."""
        script_path = params.get("path", "")
        action = params.get("action", "read")   # read | optimize | modify

        try:
            content = await self._ssh.read_script(
                discord_user_id, script_path, max_lines=150
            )
        except ValueError as e:
            return AgentResponse(text=f"❌ {e}")

        if not content or "(file not found" in content:
            return AgentResponse(text=f"❌ 文件不存在：`{script_path}`")

        if action == "read":
            # Truncate for Discord
            preview = content[:1500] + ("..." if len(content) > 1500 else "")
            return AgentResponse(
                text=(
                    f"📜 **`{script_path}` 内容预览（前150行）：**\n"
                    f"```python\n{preview}\n```\n\n"
                    f"💡 告诉我你想对这个脚本做什么修改，"
                    f"或者说'帮我解释这段代码'"
                )
            )
        return AgentResponse(
            text=f"📜 已读取 `{script_path}`（{len(content.splitlines())} 行）\n"
                 f"告诉我你想怎么修改。"
        )

    async def _handle_analysis(
        self,
        action: str,
        params: dict,
        discord_user_id: str,
        channel_id: Optional[str],
    ) -> AgentResponse:
        """
        Submit a long-running analysis as a background job.
        Returns immediately with job ID; polls and notifies on completion.
        """
        filepath = params.get("filepath", "")
        analysis_type = params.get("analysis_type", "full")
        conda_env = params.get("conda_env")
        workdir = params.get("workdir")
        result_dir = params.get("result_dir") or (
            str(Path(filepath).parent / "omicsclaw_results") if filepath else None
        )

        if not filepath:
            return AgentResponse(
                text="❓ 请指定要分析的数据文件路径，例如：\n"
                     "> 帮我分析 `/data/pbmc/pbmc.h5ad`"
            )

        # Inspect the file first to tailor the script
        try:
            file_info = await self._ssh.inspect_h5ad(
                discord_user_id, filepath, conda_env
            )
        except Exception:
            file_info = {}

        if "error" in file_info:
            return AgentResponse(
                text=f"❌ 无法读取数据文件：{file_info['error']}"
            )

        # Generate the analysis script
        script = self._code_gen.generate_analysis(
            filepath=filepath,
            analysis_type=analysis_type,
            file_info=file_info,
            result_dir=result_dir,
            conda_env=conda_env,
        )

        # Result file patterns
        result_patterns = [
            f"{result_dir}/*.png",
            f"{result_dir}/*.csv",
            f"{result_dir}/*.txt",
        ] if result_dir else []

        try:
            job = await self._ssh.submit_analysis(
                discord_user_id=discord_user_id,
                script=script,
                script_ext="py",
                conda_env=conda_env,
                workdir=workdir,
                result_patterns=result_patterns,
            )
        except ValueError as e:
            return AgentResponse(text=f"❌ {e}")
        except Exception as e:
            logger.exception("Failed to submit analysis job")
            return AgentResponse(text=f"❌ 提交任务失败：{e}")

        # Estimate time
        n_cells = file_info.get("n_obs", 0)
        est_mins = max(2, n_cells // 5000)

        # Start background polling
        if channel_id:
            self._start_polling(job.job_id, discord_user_id, channel_id)

        return AgentResponse(
            text=(
                f"⏳ **分析任务已提交！**\n"
                f"  任务ID：`{job.job_id}`\n"
                f"  数据：`{filepath}`"
                + (f"（{n_cells:,} 细胞）" if n_cells else "")
                + f"\n  环境：`{conda_env or '默认'}`\n"
                f"  预计耗时：{est_mins} 分钟\n\n"
                f"完成后我会主动通知你 📬\n"
                f"查看进度：`/job log {job.job_id}`"
            ),
            job_id=job.job_id,
            poll_secs=30,
        )

    async def _handle_env_setup(
        self, params: dict, discord_user_id: str
    ) -> AgentResponse:
        """Create a conda environment with the required packages."""
        env_name = params.get("env_name", "omics_env")
        framework = params.get("framework", "scanpy")

        if framework == "scanpy":
            packages = "scanpy anndata squidpy leidenalg harmonypy cellrank scvi-tools"
        elif framework == "seurat":
            packages = "r-seurat r-harmony r-monocle3 bioconductor-scran"
        else:
            packages = "scanpy anndata squidpy r-seurat"

        script = (
            f"conda create -n {env_name} python=3.10 -y && "
            f"conda run -n {env_name} pip install {packages}"
        )

        try:
            job = await self._ssh.submit_analysis(
                discord_user_id=discord_user_id,
                script=script,
                script_ext="sh",
            )
        except ValueError as e:
            return AgentResponse(text=f"❌ {e}")

        return AgentResponse(
            text=(
                f"⏳ **正在创建 conda 环境 `{env_name}`...**\n"
                f"  框架：{framework}\n"
                f"  任务ID：`{job.job_id}`\n"
                f"  这通常需要 5-15 分钟，完成后我会通知你 📬"
            ),
            job_id=job.job_id,
            poll_secs=60,
        )

    # ------------------------------------------------------------------ #
    # Job polling
    # ------------------------------------------------------------------ #

    def _start_polling(
        self,
        job_id: str,
        discord_user_id: str,
        channel_id: str,
        interval: int = 30,
    ):
        """Start a background asyncio task that polls a job and notifies on completion."""
        key = f"{discord_user_id}:{job_id}"
        if key in self._poll_tasks:
            return

        task = asyncio.create_task(
            self._poll_loop(job_id, discord_user_id, channel_id, interval)
        )
        self._poll_tasks[key] = task
        task.add_done_callback(lambda t: self._poll_tasks.pop(key, None))

    async def _poll_loop(
        self,
        job_id: str,
        discord_user_id: str,
        channel_id: str,
        interval: int,
    ):
        """Poll a background job until completion, then notify the channel."""
        max_polls = 120   # 1 hour max at 30s intervals
        for _ in range(max_polls):
            await asyncio.sleep(interval)
            try:
                job = await self._ssh.poll_job(job_id, discord_user_id)
            except Exception as e:
                logger.warning(f"Poll error for {job_id}: {e}")
                continue

            if job.status == JobStatus.DONE:
                # Download results and notify
                local_files = await self._ssh.collect_job_results(
                    job_id, discord_user_id
                )
                await self._notify_done(
                    job_id, discord_user_id, channel_id, local_files
                )
                return

            elif job.status == JobStatus.FAILED:
                await self._notify_failed(
                    job_id, discord_user_id, channel_id, job.error_summary
                )
                return

        # Timeout
        logger.warning(f"Job {job_id} polling timed out after {max_polls} polls")

    async def _notify_done(
        self,
        job_id: str,
        discord_user_id: str,
        channel_id: str,
        local_files: list[str],
    ):
        """
        Notify a Discord channel that a job completed.
        The channel adapter must implement this callback;
        here we store it so the adapter can pick it up.
        """
        figures = [f for f in local_files if f.endswith(".png")]
        other = [f for f in local_files if not f.endswith(".png")]

        text = (
            f"✅ **任务 `{job_id}` 完成！**\n"
            f"<@{discord_user_id}>\n"
        )
        if figures:
            text += f"📊 已生成 {len(figures)} 张图表（见附件）\n"
        if other:
            text += f"📄 其他结果文件：" + "\n".join(f"`{f}`" for f in other)

        # LLM summary: try to find a log/txt result and summarize
        llm = get_llm_client()
        if llm.enabled:
            log_files = [f for f in local_files if f.endswith((".txt", ".log"))]
            if log_files:
                try:
                    import aiofiles
                    async with aiofiles.open(log_files[0]) as f:
                        result_text = await f.read()
                    summary = await llm.summarize_result(result_text)
                    if summary and not summary.startswith("[LLM"):
                        text += f"\n\n🤖 **AI 分析摘要：**\n{summary}"
                except Exception as e:
                    logger.warning(f"LLM summary failed: {e}")

        # Push to notification queue — the channel adapter polls this
        self._pending_notifications[channel_id] = AgentResponse(
            text=text, figures=figures
        )

    async def _notify_failed(
        self,
        job_id: str,
        discord_user_id: str,
        channel_id: str,
        error_summary: Optional[str],
    ):
        text = (
            f"❌ **任务 `{job_id}` 失败**\n"
            f"<@{discord_user_id}>\n"
        )
        if error_summary:
            text += f"**错误摘要：**\n```\n{error_summary}\n```\n"
            # LLM error diagnosis
            llm = get_llm_client()
            if llm.enabled:
                try:
                    diagnosis = await llm.explain_error(error_summary)
                    if diagnosis and not diagnosis.startswith("[LLM"):
                        text += f"\n🤖 **AI 错误诊断：**\n{diagnosis}\n"
                except Exception as e:
                    logger.warning(f"LLM error explain failed: {e}")
        text += f"查看完整日志：`/job log {job_id}`"

        self._pending_notifications[channel_id] = AgentResponse(text=text)

    # Notification queue: channel_id → AgentResponse
    _pending_notifications: dict[str, AgentResponse] = {}

    def pop_notification(self, channel_id: str) -> Optional[AgentResponse]:
        """Called by the channel adapter to pick up pending notifications."""
        return self._pending_notifications.pop(channel_id, None)

    def get_all_pending_notifications(self) -> dict[str, "AgentResponse"]:
        """
        Drain and return all pending notifications.
        Called by the Discord gateway polling loop.
        Returns a dict of {channel_id: AgentResponse} and clears the queue.
        """
        if not self._pending_notifications:
            return {}
        result = dict(self._pending_notifications)
        self._pending_notifications.clear()
        return result

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _compact_session(self, user_id: str, session) -> None:
        """Summarize old conversation history to keep token budget."""
        try:
            history = session.get_history(max_messages=50)
            if not history:
                return
            llm = get_llm_client()
            history_text = "\n".join(
                f"[{m['role']}] {str(m.get('content', ''))[:200]}"
                for m in history
            )
            summary = await llm.chat(
                user_message=(
                    f"请将以下对话历史压缩为简洁摘要（不超过500字），"
                    f"重点保留：执行过的任务、数据路径、分析结果、未完成的工作。\n\n{history_text}"
                )
            )
            session.compact(summary or "（对话历史已压缩）")
            logger.info(f"Session compacted for {user_id}")
        except Exception as e:
            logger.warning(f"Compaction failed for {user_id}: {e}")

    async def _handle_llm_chat(
        self,
        message: str,
        discord_user_id: str,
        context_filepath: Optional[str] = None,
    ) -> AgentResponse:
        """
        Agent mode with native function calling + persistent session history.

        Improvements over old version:
        - Uses OpenAI native function calling (tool_calls in assistant message)
        - History from persistent JSONL session store (survives restarts)
        - Memory context (MEMORY.md + daily log) injected into session_ctx
        - Auto skill injection based on message triggers
        """
        llm = get_llm_client()
        if not llm.enabled:
            return AgentResponse(text="⚠️ LLM 未配置（需要设置 OMICS_LLM_API_KEY）")

        mem     = self._memory.get(discord_user_id)
        session = self._sessions.get(discord_user_id)

        # ── 1. Build session context string ───────────────────────────────
        ctx_parts = []
        server_id = None
        conda_env = None
        workdir   = None
        try:
            ssh_session = self._ssh._registry.get_session(discord_user_id)
            server_id   = ssh_session.active_server_id
            conda_env   = ssh_session.active_conda_env
            workdir     = ssh_session.active_project_path
            if server_id:
                ctx_parts.append(f"当前服务器: {server_id}")
            if conda_env:
                ctx_parts.append(f"当前 conda 环境: {conda_env}")
            if workdir:
                ctx_parts.append(f"当前工作目录: {workdir}")
            if context_filepath:
                ctx_parts.append(f"当前文件: {context_filepath}")
            if not server_id:
                ctx_parts.append("⚠️ 未连接服务器，请先用 /server use <name> 选择服务器")
        except Exception:
            pass

        session_ctx = "\n".join(ctx_parts) if ctx_parts else ""

        # ── 2. Inject long-term memory ────────────────────────────────────
        memory_ctx = mem.build_context_for_llm(
            include_memory=True,
            include_today=True,
            max_memory_chars=800,
            max_today_chars=400,
        )
        if memory_ctx:
            session_ctx = (session_ctx + "\n\n" + memory_ctx) if session_ctx else memory_ctx

        # ── 3. Auto-inject relevant skill knowledge ───────────────────────
        try:
            loader          = llm.skill_loader
            relevant_skills = loader.find_relevant(message)
            if relevant_skills:
                for skill in relevant_skills[:1]:  # inject at most 1 skill
                    skill_content = skill.load_skill_md()
                    if len(skill_content) > 2500:
                        skill_content = skill_content[:2500] + "\n...(用 read_skill 获取完整内容)"
                    skill_block = f"## 已加载 Skill: {skill.skill_id} — {skill.name}\n{skill_content}"
                    session_ctx = (session_ctx + "\n\n" + skill_block) if session_ctx else skill_block
                    logger.info(f"Auto-injected skill: {skill.skill_id}")
        except Exception as e:
            logger.warning(f"Skill auto-injection failed: {e}")

        # ── 4. Load persistent conversation history ───────────────────────
        history = session.get_history(max_messages=16)

        # ── 5. Tool executor (wired to SSH layer) ─────────────────────────
        tool_log: list[str] = []

        async def execute_tool(tc: ToolCall) -> str:
            name = tc.tool   # ToolCall.tool is an alias for .name
            args = tc.params # ToolCall.params is an alias for .arguments

            # read_skill and remember don't need SSH
            if name == "read_skill":
                return await self._tool_read_skill(args, tool_log)
            if name == "remember":
                return self._tool_remember(args, mem, tool_log)

            # All other tools need an active server
            if not server_id:
                return "❌ 未连接服务器，请先执行 /server use <name>"

            if name == "shell":
                cmd = args.get("cmd", "")
                if not cmd:
                    return "❌ shell 工具缺少 cmd 参数"
                result = await self._ssh.run(discord_user_id, cmd, workdir=workdir)
                out = result.stdout or result.stderr or "(无输出)"
                tool_log.append(f"shell: `{cmd[:60]}` → {out[:80]}")
                return out

            elif name == "python":
                code = args.get("code", "")
                env  = args.get("conda_env") or conda_env or "base"
                if not code:
                    return "❌ python 工具缺少 code 参数"
                result = await self._ssh.run_python(
                    discord_user_id, code, conda_env=env, workdir=workdir
                )
                out = result.stdout or result.stderr or "(无输出)"
                tool_log.append(f"python({env}): {code[:50]}...")
                return out

            elif name == "read_file":
                path = args.get("path", "")
                if not path:
                    return "❌ read_file 工具缺少 path 参数"
                result = await self._ssh.run(discord_user_id, f"cat '{path}'")
                out = result.stdout or result.stderr or "(空文件)"
                if len(out) > 4000:
                    out = out[:4000] + f"\n...(已截断，共{len(out)}字符)"
                tool_log.append(f"read_file: {path}")
                return out

            elif name == "write_file":
                path    = args.get("path", "")
                content = args.get("content", "")
                if not path:
                    return "❌ write_file 工具缺少 path 参数"
                cmd = (
                    f"mkdir -p \"$(dirname '{path}')\" && "
                    f"cat > '{path}' << 'OMICS_HEREDOC_EOF'\n{content}\nOMICS_HEREDOC_EOF"
                )
                result = await self._ssh.run(discord_user_id, cmd, workdir=workdir)
                if result.exit_code == 0:
                    tool_log.append(f"write_file: {path}")
                    return f"✅ 文件已写入: {path}"
                return f"❌ 写入失败: {result.stderr}"

            elif name == "list_dir":
                path   = args.get("path", workdir or "~")
                result = await self._ssh.run(discord_user_id, f"ls -lah '{path}'")
                out    = result.stdout or result.stderr or "(空目录)"
                tool_log.append(f"list_dir: {path}")
                return out

            else:
                return f"❌ 未知工具: {name}"

        # ── 6. Run agent loop (native function calling) ───────────────────
        reply = await llm.agent_chat(
            user_message  = message,
            tool_executor = execute_tool,
            session_ctx   = session_ctx or None,
            history       = history,
            max_rounds    = 15,
        )

        if not reply or reply.startswith("[LLM"):
            return AgentResponse(text=f"❌ LLM 请求失败：{reply}")

        # ── 7. Persist tool calls to session JSONL ────────────────────────
        if tool_log:
            # Log to daily memory file
            mem.log(
                f"**问**: {message[:80]}\n"
                f"**操作**: {'; '.join(tool_log[:5])}\n"
                f"**答**: {reply[:150]}",
                "Agent操作"
            )

        return AgentResponse(text=reply)

    # ── Tool handler helpers ──────────────────────────────────────────────

    async def _tool_read_skill(self, args: dict, tool_log: list) -> str:
        skill_id = args.get("skill_id", "")
        template = args.get("template", "")
        loader   = get_llm_client().skill_loader

        if not skill_id:
            skills = loader.list_skills()
            if not skills:
                return "❌ 暂无已安装的 Skill"
            return "已安装的 Skill：\n" + "\n".join(
                f"  - {s.skill_id}: {s.name} ({s.scope})" for s in skills
            )

        skill = loader.get(skill_id)
        if not skill:
            return f"❌ Skill '{skill_id}' 不存在，可用: {', '.join(loader.skill_ids()) or '无'}"

        if template:
            content = skill.read_template(template)
            if content is None:
                return f"❌ 模板 '{template}' 不存在，可用: {skill.list_templates()}"
            tool_log.append(f"read_skill template: {skill_id}/{template}")
            return (
                f"[参考模板: {skill_id}/{template}]\n"
                f"⚠️ 必须根据用户实际数据修改路径、对象名、物种等参数，不要直接复制。\n\n"
                f"{content}"
            )

        content   = skill.load_skill_md()
        templates = skill.list_templates()
        tool_log.append(f"read_skill: {skill_id}")
        header = (
            f"[Skill 知识库: {skill_id} — {skill.name}]\n"
            f"请根据以下知识库内容和用户实际数据，编写定制化代码。\n"
        )
        if templates:
            header += f"可用参考模板: {', '.join(templates)}\n"
        return header + "\n" + content

    def _tool_remember(self, args: dict, mem, tool_log: list) -> str:
        content = args.get("content", "")
        section = args.get("section", "")
        if not content:
            return "❌ remember 工具缺少 content 参数"
        entry = f"\n### {section}\n{content}" if section else f"\n{content}"
        mem.append_memory(entry)
        tool_log.append(f"remember: {content[:60]}")
        return "✅ 已记录到长期记忆"

    # ------------------------------------------------------------------ #

    def _cmd_result_to_response(
        self, result: CommandResult, discord_user_id: str
    ) -> AgentResponse:
        """Convert a CommandResult into an AgentResponse."""
        resp = AgentResponse(
            text=result.text,
            figures=result.figures,
            ephemeral=result.ephemeral,
        )
        if result.needs_dm and result.dm_prompt:
            resp.dm_user_id = discord_user_id
            resp.dm_text = result.dm_prompt
        if result.job_id:
            resp.job_id = result.job_id
            resp.poll_secs = result.poll_interval
        return resp
