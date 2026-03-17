"""
Discord Command Dispatcher
===========================
The single entry point for all Discord command processing in CellClaw.

Usage (from the Agent layer):
    dispatcher = CommandDispatcher(ssh_manager)

    # For slash-style commands
    result = await dispatcher.dispatch(message, discord_user_id, is_dm=False)

    # For DM password responses
    result = await dispatcher.handle_dm(message, discord_user_id)
"""

from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Optional

from ssh.manager import SSHManager
from .parser import CommandParser, ParsedCommand
from .result import CommandResult
from .handlers_server import ServerCommandHandler
from .handlers_ops import (
    EnvCommandHandler,
    JobCommandHandler,
    ProjectCommandHandler,
    StatusCommandHandler,
)

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """
    Routes parsed commands to the appropriate handler.
    Also handles DM-based password collection flows.
    """

    def __init__(self, ssh_manager: Optional[SSHManager] = None):
        self._mgr = ssh_manager or SSHManager()
        self._parser = CommandParser()

        # Handlers
        self._server = ServerCommandHandler(self._mgr)
        self._env = EnvCommandHandler(self._mgr)
        self._project = ProjectCommandHandler(self._mgr)
        self._job = JobCommandHandler(self._mgr)
        self._status_handler = StatusCommandHandler(self._mgr)

    async def dispatch(
        self,
        message: str,
        discord_user_id: str,
        is_dm: bool = False,
    ) -> Optional[CommandResult]:
        """
        Process an incoming Discord message.

        Returns:
            CommandResult if the message was a recognized slash command.
            None if the message should be handled by the NL agent layer.
        """
        # DM: check for pending password collection first
        if is_dm and self._server.has_pending_password(discord_user_id):
            return await self._server.handle_dm_password(discord_user_id, message.strip())

        # Try to parse as a slash command
        cmd = self._parser.parse(message)
        if cmd is None:
            return None  # Pass to NL agent

        # Route by group
        try:
            return await self._route(cmd, discord_user_id)
        except Exception as e:
            logger.exception(f"Command dispatch error for {discord_user_id}: {message}")
            return CommandResult.err(f"内部错误：{e}")

    async def _route(
        self, cmd: ParsedCommand, discord_user_id: str
    ) -> CommandResult:
        group = cmd.group

        if group == "server":
            return await self._server.handle(cmd, discord_user_id)

        elif group == "env":
            return await self._env.handle(cmd, discord_user_id)

        elif group == "project":
            return await self._project.handle(cmd, discord_user_id)

        elif group == "job":
            return await self._job.handle(cmd, discord_user_id)

        elif group in ("status", "whoami", "session"):
            return await self._status_handler.handle(cmd, discord_user_id)

        elif group == "help":
            return CommandResult.info(self._global_help())

        elif group in ("memory", "mem"):
            return await self._handle_memory_cmd(cmd, discord_user_id)

        elif group in ("skill", "skills"):
            return await self._handle_skill_cmd(cmd, discord_user_id)

        else:
            return CommandResult.info(
                f"❓ 未知命令 `/{group}`\n"
                f"发送 `/help` 查看所有命令，或直接用自然语言描述你想做的分析。"
            )

    async def _handle_skill_cmd(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        """
        /skill list          — list all installed skills
        /skill info <id>     — show full SKILL.md for a skill
        """
        from core.llm import get_llm_client
        llm = get_llm_client()
        loader = llm.skill_loader

        action   = cmd.first_arg() or "list"
        skill_id = cmd.rest_after_first().strip()

        if action == "list":
            skills = loader.list_skills()
            if not skills:
                return CommandResult.info("📭 暂无已安装的 Skill。")
            lines = ["🔬 **已安装的分析 Skill**\n"]
            for s in skills:
                lines.append(f"**ID: `{s.skill_id}`** — {s.name}")
                if s.scope:
                    lines.append(f"  适用场景: {s.scope}")
                if s.triggers:
                    lines.append(f"  触发词: {', '.join(s.triggers[:5])}")
                scripts = s.list_templates()
                if scripts:
                    lines.append(f"  模板脚本: `{'`, `'.join(scripts)}`")
                lines.append("")
            lines.append("─────────────────")
            lines.append("📌 **使用方式：**")
            lines.append("`/skill info <id>` — 查看完整知识库")
            lines.append("`/skill use <id> <你的需求>` — 直接让 Agent 用此 Skill 分析")
            lines.append('**自然语言触发**：直接说"帮我跑细胞通讯"也会自动激活对应 Skill')
            return CommandResult.info("\n".join(lines))

        elif action == "info":
            if not skill_id:
                return CommandResult.err(
                    "请指定 Skill ID：`/skill info <id>`\n"
                    "用 `/skill list` 查看所有可用 Skill 及其 ID"
                )
            skill = loader.get(skill_id)
            if not skill:
                available = ", ".join(f"`{s}`" for s in loader.skill_ids())
                return CommandResult.err(f"❌ 未找到 Skill: `{skill_id}`\n可用 ID: {available or '无'}")
            content = skill.load_full()
            if len(content) > 1700:
                content = content[:1700] + f"\n\n...(内容过长，共{len(content)}字符)\n用 `/skill use {skill_id} <需求>` 让 Agent 读取完整知识库并分析"
            return CommandResult.info(f"📖 **Skill: {skill.name}** (`{skill_id}`)\n\n{content}")

        elif action in ("use", "run"):
            # /skill use <skill_id> <user request>
            # Parse: first word after 'use' = skill_id, rest = task description
            parts = skill_id.split(None, 1)
            actual_id = parts[0] if parts else ""
            user_task = parts[1] if len(parts) > 1 else ""

            if not actual_id:
                return CommandResult.err(
                    "用法：`/skill use <id> <你的需求>`\n"
                    "例如：`/skill use ccc_cellchat 帮我分析 F7.rds 的细胞通讯`\n"
                    "用 `/skill list` 查看所有 Skill ID"
                )
            skill = loader.get(actual_id)
            if not skill:
                available = ", ".join(f"`{s}`" for s in loader.skill_ids())
                return CommandResult.err(f"❌ 未找到 Skill: `{actual_id}`\n可用 ID: {available or '无'}")

            if not user_task:
                user_task = f"使用 {skill.name} 进行分析"

            # Return a special CommandResult that tells the caller to route to LLM
            # with skill forcibly injected into context
            return CommandResult(
                success=True,
                text=None,  # signal: route to agent
                extra={"force_skill_id": actual_id, "nl_message": user_task},
            )

        else:
            return CommandResult.info(
                "**Skill 命令：**\n"
                "`/skill list` — 列出所有已安装的分析 Skill（含 ID）\n"
                "`/skill info <id>` — 查看某个 Skill 的详细知识库\n"
                "`/skill use <id> <需求>` — 强制激活 Skill 并让 Agent 执行\n\n"
                '💡 **自然语言也可以自动触发 Skill**，说"帮我跑细胞通讯"无需显式命令'
            )

    async def _handle_memory_cmd(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        """
        /memory show       — show MEMORY.md
        /memory today      — show today's daily log
        /memory clear      — clear conversation history
        /memory note <text> — manually write to MEMORY.md
        """
        from core.memory import MemoryManager
        data_dir = os.environ.get("OMICSCLAW_DATA", str(Path(__file__).parent.parent / "data"))
        mem_mgr  = MemoryManager(data_dir)
        mem      = mem_mgr.get(discord_user_id)

        action = cmd.first_arg() or "show"

        if action == "show":
            content = mem.read_memory()
            if not content:
                return CommandResult.info("📭 长期记忆为空。和我对话后，我会自动记录重要信息。")
            # Truncate for Discord 2000 char limit
            if len(content) > 1800:
                content = content[:1800] + "\n...(内容过长，已截断)"
            return CommandResult.info(f"🧠 **长期记忆（MEMORY.md）**\n\n{content}")

        elif action == "today":
            content = mem.read_today()
            if not content:
                return CommandResult.info("📭 今日日志为空。")
            if len(content) > 1800:
                content = content[:1800] + "\n...(已截断)"
            return CommandResult.info(f"📅 **今日日志**\n\n{content}")

        elif action == "clear":
            mem.clear_history()
            return CommandResult.ok("✅ 对话历史已清除（长期记忆保留）")

        elif action == "note":
            note = cmd.rest_after_first()
            if not note:
                return CommandResult.err("请提供笔记内容：`/memory note 你想记录的内容`")
            from datetime import datetime, timezone, timedelta
            ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
            mem.append_memory(f"\n### [{ts}] 手动记录\n{note}")
            return CommandResult.ok(f"✅ 已记录到长期记忆：{note[:100]}")

        else:
            return CommandResult.info(
                "**记忆管理命令：**\n"
                "`/memory show` — 查看长期记忆\n"
                "`/memory today` — 查看今日日志\n"
                "`/memory clear` — 清除对话历史\n"
                "`/memory note <内容>` — 手动添加笔记"
            )

    def _global_help(self) -> str:
        return (
            "🧬 **CellClaw 命令帮助**\n\n"
            "**服务器管理**\n"
            "```\n"
            "/server add  --name <id> --host <IP> --user <用户名> --port <端口> [--key <路径>] [--password true]\n"
            "/server list\n"
            "/server use  <name>\n"
            "/server test [name]\n"
            "/server info [name]\n"
            "/server remove <name>\n"
            "```\n"
            "**环境管理**\n"
            "```\n"
            "/env list\n"
            "/env use  <name>\n"
            "/env scan <name>\n"
            "```\n"
            "**项目管理**\n"
            "```\n"
            "/project set  <path>\n"
            "/project ls   [path]\n"
            "/project find [path]\n"
            "/project info <file.h5ad>\n"
            "```\n"
            "**任务管理**\n"
            "```\n"
            "/job list\n"
            "/job set   <任务描述>      — 提交后台任务执行\n"
            "/job status <job_id>\n"
            "/job log    <job_id>\n"
            "/job cancel <job_id>\n"
            "```\n"
            '💡 也可直接说"挂后台"/"提交任务"让 Agent 后台执行\n\n'
            "**分析 Skill**\n"
            "```\n"
            "/skill list                        — 列出所有已安装的 Skill（含 ID、触发词）\n"
            "/skill info <skill_id>             — 查看 Skill 完整知识库\n"
            "/skill use  <skill_id> <你的需求>  — 强制激活 Skill，Agent 直接执行\n"
            "/skill run  <skill_id> <你的需求>  — 同 /skill use\n"
            "```\n"
            '💡 无需显式命令：直接说"帮我跑细胞通讯"会自动激活对应 Skill\n\n'
            "**记忆管理**\n"
            "```\n"
            "/memory show             — 查看我对你的长期记忆\n"
            "/memory today            — 查看今日操作日志\n"
            "/memory clear            — 清除对话历史（长期记忆保留）\n"
            "/memory note <内容>      — 手动写入长期记忆\n"
            "```\n"
            "**会话信息**\n"
            "```\n"
            "/status\n"
            "```\n\n"
            "💡 也可以直接用自然语言，例如：\n"
            "> 帮我分析 ~/data/pbmc.h5ad 做 UMAP 聚类\n"
            "> 你会哪些分析？\n"
            "> cluster 3 里有多少个细胞？\n"
            "> 帮我从头做完整的单细胞分析流程\n"
            "> 记住：我们的数据在 /data/project_A/"
        )

    @property
    def ssh_manager(self) -> SSHManager:
        return self._mgr
