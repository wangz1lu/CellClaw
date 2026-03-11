"""
/server command handlers
=========================
Handles all /server sub-commands:
  add, list, use, test, remove, info
"""

from __future__ import annotations
import logging
from typing import Optional

from ..ssh.manager import SSHManager
from .parser import ParsedCommand
from .result import CommandResult

logger = logging.getLogger(__name__)

# Temporary store for pending password-auth server registrations
# Key: discord_user_id → pending ServerConfig kwargs
_PENDING_PASSWORD_REG: dict[str, dict] = {}


class ServerCommandHandler:

    def __init__(self, ssh_manager: SSHManager):
        self._mgr = ssh_manager

    async def handle(
        self,
        cmd: ParsedCommand,
        discord_user_id: str,
    ) -> CommandResult:
        """Route to the appropriate /server sub-command."""
        action = cmd.action

        if action == "add":
            return await self._add(cmd, discord_user_id)
        elif action == "list":
            return self._list(discord_user_id)
        elif action == "use":
            return await self._use(cmd, discord_user_id)
        elif action == "test":
            return await self._test(cmd, discord_user_id)
        elif action == "remove":
            return self._remove(cmd, discord_user_id)
        elif action == "info":
            return await self._info(cmd, discord_user_id)
        else:
            return CommandResult.info(self._help())

    # ------------------------------------------------------------------ #
    # /server add
    # ------------------------------------------------------------------ #

    async def _add(
        self, cmd: ParsedCommand, discord_user_id: str
    ) -> CommandResult:
        """
        /server add --name mylab --host 10.0.0.5 --user ubuntu
                    [--port 22] [--key ~/.ssh/id_rsa] [--password]
                    [--note "lab GPU server"]
        """
        name = cmd.flag("name") or cmd.first_arg()
        host = cmd.flag("host") or cmd.flag("h")
        user = cmd.flag("user") or cmd.flag("u") or cmd.flag("username")
        port = int(cmd.flag("port") or cmd.flag("p") or "22")
        key_path = cmd.flag("key") or cmd.flag("k")
        use_password = cmd.flag("password") == "true" or cmd.flag("pw") == "true"
        notes = cmd.flag("note") or cmd.flag("notes")

        # Validate required fields
        missing = []
        if not name:
            missing.append("`--name`")
        if not host:
            missing.append("`--host`")
        if not user:
            missing.append("`--user`")
        if missing:
            return CommandResult.err(
                f"缺少必填参数：{', '.join(missing)}\n\n"
                + self._add_usage()
            )

        # Validate name format
        if not name.replace("-", "").replace("_", "").isalnum():
            return CommandResult.err(
                f"服务器名称 `{name}` 只能包含字母、数字、短横线和下划线"
            )

        # Password auth: need to collect password via DM
        if use_password and not key_path:
            _PENDING_PASSWORD_REG[discord_user_id] = {
                "server_id": name, "host": host, "username": user,
                "port": port, "auth_type": "password", "notes": notes,
            }
            return CommandResult.needs_password(name)

        # Key auth (default)
        auth_type = "password" if use_password else "key"

        try:
            ok, msg = await self._mgr.add_server(
                discord_user_id=discord_user_id,
                server_id=name,
                host=host,
                username=user,
                port=port,
                auth_type=auth_type,
                key_path=key_path,
                notes=notes,
            )
            return CommandResult.ok(msg) if ok else CommandResult.err(msg)
        except Exception as e:
            logger.exception(f"add_server failed for {discord_user_id}")
            return CommandResult.err(str(e))

    async def handle_dm_password(
        self,
        discord_user_id: str,
        password: str,
    ) -> CommandResult:
        """
        Called when a user responds to the DM password prompt.
        Completes a pending password-auth server registration.
        """
        pending = _PENDING_PASSWORD_REG.pop(discord_user_id, None)
        if not pending:
            return CommandResult.err("没有待完成的服务器注册。")

        try:
            ok, msg = await self._mgr.add_server(
                discord_user_id=discord_user_id,
                password=password,
                **pending,
            )
            return CommandResult.ok(msg) if ok else CommandResult.err(msg)
        except Exception as e:
            return CommandResult.err(str(e))

    def has_pending_password(self, discord_user_id: str) -> bool:
        return discord_user_id in _PENDING_PASSWORD_REG

    # ------------------------------------------------------------------ #
    # /server list
    # ------------------------------------------------------------------ #

    def _list(self, discord_user_id: str) -> CommandResult:
        text = self._mgr.list_servers(discord_user_id)
        return CommandResult.info(text)

    # ------------------------------------------------------------------ #
    # /server use
    # ------------------------------------------------------------------ #

    async def _use(
        self, cmd: ParsedCommand, discord_user_id: str
    ) -> CommandResult:
        """
        /server use <name>
        """
        name = cmd.first_arg() or cmd.flag("name")
        if not name:
            return CommandResult.err(
                "请指定服务器名称。\n用法：`/server use <name>`"
            )
        ok, msg = await self._mgr.switch_server(discord_user_id, name)
        return CommandResult.ok(msg) if ok else CommandResult.err(msg)

    # ------------------------------------------------------------------ #
    # /server test
    # ------------------------------------------------------------------ #

    async def _test(
        self, cmd: ParsedCommand, discord_user_id: str
    ) -> CommandResult:
        """
        /server test [name]
        """
        name = cmd.first_arg() or cmd.flag("name")
        msg = await self._mgr.test_server(discord_user_id, name)
        if "✅" in msg:
            return CommandResult.ok(msg)
        return CommandResult.err(msg)

    # ------------------------------------------------------------------ #
    # /server remove
    # ------------------------------------------------------------------ #

    def _remove(
        self, cmd: ParsedCommand, discord_user_id: str
    ) -> CommandResult:
        """
        /server remove <name>
        """
        name = cmd.first_arg() or cmd.flag("name")
        if not name:
            return CommandResult.err(
                "请指定要移除的服务器名称。\n用法：`/server remove <name>`"
            )
        ok, msg = self._mgr.remove_server(discord_user_id, name)
        return CommandResult.ok(msg) if ok else CommandResult.err(msg)

    # ------------------------------------------------------------------ #
    # /server info
    # ------------------------------------------------------------------ #

    async def _info(
        self, cmd: ParsedCommand, discord_user_id: str
    ) -> CommandResult:
        """
        /server info [name]  — show hardware info for a server
        """
        name = cmd.first_arg() or cmd.flag("name")
        try:
            result = await self._mgr.run(
                discord_user_id,
                (
                    "echo '=== CPU ===' && nproc && "
                    "echo '=== MEM ===' && free -h | head -2 && "
                    "echo '=== DISK ===' && df -h / | tail -1 && "
                    "echo '=== GPU ===' && "
                    "(nvidia-smi --query-gpu=name,memory.total,memory.free "
                    "--format=csv,noheader 2>/dev/null || echo 'No GPU / nvidia-smi not found')"
                ),
                server_id=name,
                timeout=20,
            )
            return CommandResult.info(
                f"🖥️  **服务器信息**\n```\n{result.output}\n```"
            )
        except Exception as e:
            return CommandResult.err(str(e))

    # ------------------------------------------------------------------ #
    # Help text
    # ------------------------------------------------------------------ #

    def _help(self) -> str:
        return (
            "🖥️  **`/server` 命令帮助**\n\n"
            "```\n"
            "/server add  --name <id> --host <IP/域名> --user <用户名>\n"
            "             [--port 22] [--key <私钥路径>] [--password]\n"
            "             [--note '备注']\n\n"
            "/server list              # 列出所有已注册服务器\n"
            "/server use  <name>       # 切换当前工作服务器\n"
            "/server test [name]       # 测试连接\n"
            "/server info [name]       # 查看服务器硬件信息（CPU/内存/磁盘/GPU）\n"
            "/server remove <name>     # 移除服务器\n"
            "```\n\n"
            "**示例：**\n"
            "```\n"
            "# 密钥认证（推荐）\n"
            "/server add --name mylab --host 10.0.0.5 --user ubuntu --key ~/.ssh/id_rsa\n\n"
            "# 密码认证\n"
            "/server add --name cloud1 --host gpu.lab.com --user root --password\n"
            "```"
        )

    def _add_usage(self) -> str:
        return (
            "**用法：**\n"
            "```\n"
            "/server add --name <名称> --host <地址> --user <用户名>\n"
            "            [--port 22] [--key <私钥路径>]\n"
            "```"
        )
