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
            return CommandResult.err(f"Internal error：{e}")

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
                return CommandResult.info("📭 No skills installed yet。")
            lines = ["🔬 **已安装的分析 Skill**\n"]
            for s in skills:
                lines.append(f"**ID: `{s.skill_id}`** — {s.name}")
                if s.scope:
                    lines.append(f"  Scope: {s.scope}")
                if s.triggers:
                    lines.append(f"  Triggers: {', '.join(s.triggers[:5])}")
                scripts = s.list_templates()
                if scripts:
                    lines.append(f"  模板脚本: `{'`, `'.join(scripts)}`")
                lines.append("")
            return CommandResult.info("\n".join(lines))

        elif action == "info":
            # Redirect to use with info flag
            if not skill_id:
                return CommandResult.err("Please specify a skill ID. Use `/skill list` to see all skills.")
            cmd = ParsedCommand(group="skill", action="use", args=[skill_id], flags={}, raw=f"/skill use {skill_id}")
            return await self._handle_skill_cmd(cmd, discord_user_id)
            skill = loader.get(skill_id)
            if not skill:
                available = ", ".join(f"`{s}`" for s in loader.skill_ids())
                return CommandResult.err(f"❌ Skill not found: `{skill_id}`\nAvailable IDs: {available or 'none'}")
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
                    "Use `/skill list` to see all Skill IDs"
                )
            skill = loader.get(actual_id)
            if not skill:
                available = ", ".join(f"`{s}`" for s in loader.skill_ids())
                return CommandResult.err(f"❌ Skill not found: `{actual_id}`\nAvailable IDs: {available or 'none'}")

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
                "`/skill info <id>` — View skill details\n"
                "`/skill use <id> <需求>` — Force activate skill 并让 Agent 执行\n\n"
                '💡 **自然语言也可以自动触发 Skill**，说"帮我跑细胞通讯"none需显式命令'
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
            return CommandResult.info(f"🧠 **Long-term Memory (MEMORY.md)**\n\n{content}")

        elif action == "today":
            content = mem.read_today()
            if not content:
                return CommandResult.info("📭 Today's Log为空。")
            if len(content) > 1800:
                content = content[:1800] + "\n...(已截断)"
            return CommandResult.info(f"📅 **Today's Log**\n\n{content}")

        elif action == "clear":
            mem.clear_history()
            return CommandResult.ok("✅ 对话历史已清除（长期记忆保留）")

        elif action == "note":
            note = cmd.rest_after_first()
            if not note:
                return CommandResult.err("请提供笔记内容：`/memory note 你想记录的内容`")
            from datetime import datetime, timezone, timedelta
            ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
            mem.append_memory(f"\n### [{ts}] Manual Note\n{note}")
            return CommandResult.ok(f"✅ Saved to long-term memory：{note[:100]}")

        else:
            return CommandResult.info(
                "**记忆管理命令：**\n"
                "`/memory show` — 查看长期记忆\n"
                "`/memory today` — 查看Today's Log\n"
                "`/memory clear` — 清除对话历史\n"
                "`/memory note <内容>` — 手动添加笔记"
            )

    def _global_help(self) -> str:
        return (
            "🧬 **CellClaw Commands**\n\n"
            "**Server Management**\n"
            "```\n"
            "/server add --name <id> --host <IP> --user <user> --port <port> [--key <path>] [--password true]\n"
            "/server list\n"
            "/server use <name>\n"
            "/server test [name]\n"
            "/server info [name]\n"
            "/server remove <name>\n"
            "```\n"
            "**Project**\n"
            "```\n"
            "/project set <path>\n"
            "/project ls [path]\n"
            "/project info <file.h5ad>\n"
            "```\n"
            "**Job Management**\n"
            "```\n"
            "/job list\n"
            "/job set <description> — Submit background job\n"
            "/job status <job_id>\n"
            "/job log <job_id>\n"
            "/job cancel <job_id>\n"
            "```\n"
            "**Skills**\n"
            "```\n"
            "/skill list — List all installed skills\n"
            "/skill use <skill_id> <task> — Force activate skill\n"
            "```\n"
            "**Memory**\n"
            "```\n"
            "/memory show — View long-term memory\n"
            "/memory today — View today's logs\n"
            "/memory clear — Clear chat history\n"
            "/memory note <content> — Write to memory\n"
            "```\n"
            "**Session**\n"
            "```\n"
            "/status\n"
            "```"
        )

    @property
    def ssh_manager(self) -> SSHManager:
        return self._mgr
