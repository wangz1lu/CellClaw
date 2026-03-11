"""
SSH Connection Pool
===================
Async SSH connections via asyncssh.
Maintains a pool of live connections keyed by (discord_user_id, server_id).
Automatically reconnects on stale connections.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Optional

import asyncssh

from .models import ServerConfig, ServerInfo, AuthType
from .vault import CredentialVault

logger = logging.getLogger(__name__)

# Idle connections are closed after this many seconds
_IDLE_TIMEOUT = 600  # 10 minutes


class SSHConnection:
    """Wraps an asyncssh SSHClientConnection with metadata."""

    def __init__(self, config: ServerConfig, conn: asyncssh.SSHClientConnection):
        self.config    = config
        self._conn     = conn
        self._lock     = asyncio.Lock()
        self.conda_bin = ""   # set after connect by _probe_conda()

    @property
    def raw(self) -> asyncssh.SSHClientConnection:
        return self._conn

    def is_closed(self) -> bool:
        return self._conn._transport is None or self._conn._transport.is_closing()  # type: ignore

    async def run(self, command: str, timeout: int = 30) -> asyncssh.SSHCompletedProcess:
        async with self._lock:
            return await asyncio.wait_for(
                self._conn.run(command, check=False),
                timeout=timeout
            )

    async def sftp(self) -> asyncssh.SFTPClient:
        return await self._conn.start_sftp_client()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


class SSHConnectionManager:
    """
    Async SSH connection pool.
    Usage:
        manager = SSHConnectionManager(vault)
        conn = await manager.get_connection(config, discord_user_id)
        result = await conn.run("ls -la")
    """

    def __init__(self, vault: CredentialVault):
        self._vault = vault
        self._pool: dict[str, SSHConnection] = {}

    def _pool_key(self, discord_user_id: str, server_id: str) -> str:
        return f"{discord_user_id}:{server_id}"

    async def get_connection(self, config: ServerConfig,
                             discord_user_id: str) -> SSHConnection:
        """Return a live SSH connection (from pool or newly created)."""
        key = self._pool_key(discord_user_id, config.server_id)
        existing = self._pool.get(key)
        if existing and not existing.is_closed():
            return existing

        conn = await self._connect(config, discord_user_id)
        self._pool[key] = conn
        return conn

    async def test_connection(self, config: ServerConfig,
                              discord_user_id: str) -> tuple[bool, str]:
        """
        Test if a server is reachable and credentials are valid.
        Returns (success, message).
        """
        try:
            conn = await self._connect(config, discord_user_id)
            result = await conn.run("echo ok", timeout=10)
            conn.close()
            return True, "连接成功 ✅"
        except asyncssh.PermissionDenied:
            return False, "❌ 认证失败：用户名/密码/密钥错误"
        except asyncssh.ConnectionLost:
            return False, "❌ 连接中断"
        except TimeoutError:
            return False, "❌ 连接超时，请检查 host/port 和防火墙"
        except Exception as e:
            return False, f"❌ 连接失败：{e}"

    async def close(self, discord_user_id: str, server_id: str):
        key = self._pool_key(discord_user_id, server_id)
        conn = self._pool.pop(key, None)
        if conn:
            conn.close()

    async def close_all(self):
        for conn in self._pool.values():
            conn.close()
        self._pool.clear()

    async def _connect(self, config: ServerConfig,
                       discord_user_id: str) -> SSHConnection:
        """Open a new SSH connection using stored credentials."""
        connect_kwargs: dict = {
            "host": config.host,
            "port": config.port,
            "username": config.username,
            "known_hosts": None,           # TODO: implement known_hosts checking
        }

        if config.auth_type == AuthType.KEY:
            if config.key_path:
                connect_kwargs["client_keys"] = [config.key_path]
            # else: let asyncssh use default ~/.ssh/id_* keys

        elif config.auth_type == AuthType.PASSWORD:
            password = self._vault.retrieve_password(discord_user_id, config.server_id)
            if not password:
                raise ValueError(
                    f"未找到服务器 '{config.server_id}' 的密码，请重新注册"
                )
            connect_kwargs["password"] = password
            connect_kwargs["preferred_auth"] = "password"

        logger.info(f"Connecting to {config.display_name}")
        raw_conn = await asyncssh.connect(**connect_kwargs)
        conn = SSHConnection(config, raw_conn)

        # Probe conda path once at connect time, cache on the connection object.
        # asyncssh exec channel is non-interactive — .bashrc/.bash_profile not sourced.
        # We run a login shell once to discover the real conda binary path.
        conn.conda_bin = await _probe_conda(raw_conn)
        logger.info(f"  conda_bin={conn.conda_bin or '(not found)'}")
        return conn

    async def gather_server_info(self, conn: SSHConnection) -> ServerInfo:
        """Collect hardware/OS info from a connected server."""
        info = ServerInfo()

        cmds = {
            "cpu": "nproc",
            "mem": "free -g | awk 'NR==2{print $2}'",
            "disk": "df -BG / | awk 'NR==2{print $3, $2}'",
            "os": "cat /etc/os-release | grep PRETTY_NAME | cut -d'\"' -f2",
            "host": "hostname",
            "conda": "which conda 2>/dev/null && echo yes || echo no",
            "mamba": "which mamba 2>/dev/null && echo yes || echo no",
        }

        for key, cmd in cmds.items():
            try:
                r = await conn.run(cmd, timeout=10)
                out = r.stdout.strip()
                if key == "cpu":
                    info.cpu_count = int(out) if out.isdigit() else 0
                elif key == "mem":
                    info.memory_gb = float(out) if out else 0
                elif key == "disk":
                    parts = out.split()
                    if len(parts) == 2:
                        info.disk_used_gb = float(parts[0].replace("G", ""))
                        info.disk_total_gb = float(parts[1].replace("G", ""))
                elif key == "os":
                    info.os_version = out
                elif key == "host":
                    info.hostname = out
                elif key == "conda":
                    info.conda_available = "yes" in out
                elif key == "mamba":
                    info.mamba_available = "yes" in out
            except Exception as e:
                logger.warning(f"Failed to gather {key}: {e}")

        return info


async def _probe_conda(raw_conn: asyncssh.SSHClientConnection) -> str:
    """
    Probe the real conda binary path using a login shell.
    Called once at connect time; result cached on SSHConnection.conda_bin.

    asyncssh exec channels are non-interactive and don't source .bashrc,
    so `which conda` fails in normal exec. A login shell (`bash --login`)
    does source /etc/profile + ~/.bash_profile, which is where conda init
    writes itself.
    """
    probe_cmd = "bash --login -c 'which conda 2>/dev/null || which mamba 2>/dev/null'"
    try:
        result = await asyncio.wait_for(
            raw_conn.run(probe_cmd, check=False), timeout=10
        )
        path = (result.stdout or "").strip()
        if path:
            return path
    except Exception:
        pass

    # Fallback: scan common install paths directly (no shell init needed)
    scan_cmd = (
        "for p in "
        "~/miniconda3/bin/conda ~/anaconda3/bin/conda "
        "~/miniforge3/bin/conda ~/mambaforge/bin/conda "
        "/opt/conda/bin/conda /opt/miniconda3/bin/conda; do "
        "[ -x \"$p\" ] && echo \"$p\" && break; done"
    )
    try:
        result = await asyncio.wait_for(
            raw_conn.run(scan_cmd, check=False), timeout=10
        )
        path = (result.stdout or "").strip()
        if path:
            return path
    except Exception:
        pass

    return ""
