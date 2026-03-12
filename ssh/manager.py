"""
SSH Manager — High-level Facade
=================================
The single entry point used by OmicsClawAgent for all SSH operations.
Combines Registry, ConnectionManager, Executor, Detector, and Transfer
into a clean, intent-oriented API.

Usage:
    mgr = SSHManager()

    # Register a server
    await mgr.add_server(discord_user_id, "mylab", "10.0.0.5", "ubuntu",
                         auth_type="key", key_path="~/.ssh/id_rsa")

    # Run analysis
    conn = await mgr.connect(discord_user_id)
    result = await mgr.run(discord_user_id, "cat /data/pbmc.h5ad | head")
    job = await mgr.submit_analysis(discord_user_id, script, conda_env="scanpy_env")
"""

from __future__ import annotations
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

from .models import (
    AuthType, CondaEnvInfo, ExecuteResult, RemoteJob,
    ServerConfig, ServerInfo, UserSession,
)
from .vault import CredentialVault
from .registry import ServerRegistry
from .connection import SSHConnection, SSHConnectionManager
from .executor import RemoteExecutor
from .detector import EnvironmentDetector
from .transfer import FileTransfer

logger = logging.getLogger(__name__)

_LOCAL_TMP = Path(tempfile.gettempdir()) / "omicsclaw_results"
_LOCAL_TMP.mkdir(exist_ok=True)


class SSHManager:

    def __init__(self):
        self._vault = CredentialVault()
        self._registry = ServerRegistry()
        self._connections = SSHConnectionManager(self._vault)
        self._executor = RemoteExecutor()
        self._detector = EnvironmentDetector(self._executor)
        self._transfer = FileTransfer(self._executor)
        self._jobs: dict[str, RemoteJob] = {}   # job_id → RemoteJob

    # ------------------------------------------------------------------ #
    # Server management
    # ------------------------------------------------------------------ #

    async def add_server(
        self,
        discord_user_id: str,
        server_id: str,
        host: str,
        username: str,
        port: int = 22,
        auth_type: str = "key",
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Register a new server and verify connectivity.
        Returns (success, message).
        """
        atype = AuthType(auth_type)
        password_token = None

        if atype == AuthType.PASSWORD:
            if not password:
                return False, "❌ 密码认证需要提供密码"
            password_token = self._vault.store_password(
                discord_user_id, server_id, password
            )

        config = ServerConfig(
            server_id=server_id,
            host=host,
            port=port,
            username=username,
            owner_discord_id=discord_user_id,
            auth_type=atype,
            key_path=key_path,
            password_token=password_token,
            notes=notes,
        )

        # Test connection before saving
        ok, msg = await self._connections.test_connection(config, discord_user_id)
        if not ok:
            if atype == AuthType.PASSWORD:
                self._vault.delete(discord_user_id, server_id)
            return False, msg

        self._registry.add_server(config)
        self._registry.set_active_server(discord_user_id, server_id)

        # Gather server info
        try:
            conn = await self._connections.get_connection(config, discord_user_id)
            info = await self._connections.gather_server_info(conn)
            envs = await self._detector.list_conda_envs(conn)
            env_names = [e.name for e in envs]

            reply = (
                f"✅ 服务器 `{server_id}` 注册成功！\n"
                f"{info.summary()}\n"
                f"🐍 conda 环境：{', '.join(env_names) if env_names else '未检测到'}"
            )
            return True, reply
        except Exception as e:
            return True, f"✅ 服务器 `{server_id}` 已注册（环境信息获取失败：{e}）"

    def remove_server(self, discord_user_id: str, server_id: str) -> tuple[bool, str]:
        ok = self._registry.remove_server(discord_user_id, server_id)
        if ok:
            self._vault.delete(discord_user_id, server_id)
            return True, f"✅ 服务器 `{server_id}` 已移除"
        return False, f"❌ 未找到服务器 `{server_id}`"

    def list_servers(self, discord_user_id: str) -> str:
        servers = self._registry.list_servers(discord_user_id)
        session = self._registry.get_session(discord_user_id)
        if not servers:
            return "🖥️  你还没有注册任何服务器。\n用 `/server add` 添加第一台服务器。"

        lines = ["🖥️  **已注册服务器：**"]
        for s in servers:
            active_marker = " ◀ 当前" if s.server_id == session.active_server_id else ""
            lines.append(
                f"  - `{s.server_id}` — {s.username}@{s.host}:{s.port}"
                f"{active_marker}"
            )
        return "\n".join(lines)

    async def switch_server(
        self, discord_user_id: str, server_id: str
    ) -> tuple[bool, str]:
        config = self._registry.get_server(discord_user_id, server_id)
        if not config:
            return False, f"❌ 未找到服务器 `{server_id}`"
        self._registry.set_active_server(discord_user_id, server_id)
        return True, f"✅ 已切换到服务器 `{server_id}`"

    async def test_server(
        self, discord_user_id: str, server_id: Optional[str] = None
    ) -> str:
        config = self._registry.resolve_server(discord_user_id, server_id)
        if not config:
            return "❌ 请先指定或切换到一台服务器"
        ok, msg = await self._connections.test_connection(config, discord_user_id)
        return msg

    # ------------------------------------------------------------------ #
    # Connection helpers
    # ------------------------------------------------------------------ #

    async def _get_conn(
        self, discord_user_id: str, server_id: Optional[str] = None
    ) -> SSHConnection:
        config = self._registry.resolve_server(discord_user_id, server_id)
        if not config:
            raise ValueError(
                "没有可用的服务器。请先用 `/server add` 注册服务器，"
                "或用 `/server use <name>` 切换。"
            )
        self._registry.update_last_used(discord_user_id, config.server_id)
        return await self._connections.get_connection(config, discord_user_id)

    # ------------------------------------------------------------------ #
    # Remote execution
    # ------------------------------------------------------------------ #

    async def run(
        self,
        discord_user_id: str,
        command: str,
        conda_env: Optional[str] = None,
        workdir: Optional[str] = None,
        timeout: int = 60,
        server_id: Optional[str] = None,
    ) -> ExecuteResult:
        """Run a short command on the active server."""
        conn = await self._get_conn(discord_user_id, server_id)
        session = self._registry.get_session(discord_user_id)
        env = conda_env or session.active_conda_env
        wd = workdir or session.active_project_path
        return await self._executor.run(conn, command, conda_env=env,
                                        workdir=wd, timeout=timeout)

    async def run_python(
        self,
        discord_user_id: str,
        code: str,
        conda_env: Optional[str] = None,
        workdir: Optional[str] = None,
        timeout: int = 30,
    ) -> ExecuteResult:
        """Run a Python snippet on the active server."""
        conn = await self._get_conn(discord_user_id)
        session = self._registry.get_session(discord_user_id)
        env = conda_env or session.active_conda_env
        wd = workdir or session.active_project_path
        return await self._executor.run_python(conn, code, conda_env=env,
                                               workdir=wd, timeout=timeout)

    async def submit_analysis(
        self,
        discord_user_id: str,
        script: str,
        script_ext: str = "py",
        conda_env: Optional[str] = None,
        workdir: Optional[str] = None,
        result_patterns: Optional[list[str]] = None,
        server_id: Optional[str] = None,
    ) -> RemoteJob:
        """Submit a long-running analysis script as a background job."""
        conn = await self._get_conn(discord_user_id, server_id)
        session = self._registry.get_session(discord_user_id)
        env = conda_env or session.active_conda_env
        wd = workdir or session.active_project_path or "~"

        job = await self._executor.run_background(
            conn=conn,
            discord_user_id=discord_user_id,
            server_id=conn.config.server_id,
            script_content=script,
            script_ext=script_ext,
            conda_env=env,
            workdir=wd,
            result_patterns=result_patterns,
        )
        self._jobs[job.job_id] = job
        return job

    async def poll_job(self, job_id: str, discord_user_id: str) -> RemoteJob:
        """Poll a background job for status updates."""
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Job {job_id} not found")
        conn = await self._get_conn(discord_user_id, job.server_id)
        return await self._executor.poll_job(conn, job)

    async def submit_background(
        self,
        discord_user_id: str,
        run_cmd: str,
        description: str = "分析任务",
        conda_env: Optional[str] = None,
        workdir: Optional[str] = None,
        server_id: Optional[str] = None,
    ) -> "RemoteJob":
        """Submit an already-written script file as a background nohup job.

        Unlike submit_analysis (which takes script content), this takes a
        shell command like 'Rscript /path/to/analyze.R' and runs it via
        nohup in a tmux session so the user can track it with /job commands.
        """
        import secrets
        from ssh.models import RemoteJob, JobStatus

        conn = await self._get_conn(discord_user_id, server_id)
        session = self._registry.get_session(discord_user_id)
        env = conda_env or session.active_conda_env
        wd  = workdir or session.active_project_path or "~"

        job_id   = secrets.token_hex(3)  # 6-char hex
        log_path = f"{wd}/omics_job_{job_id}.log"
        tmux_name = f"omics_{job_id}"

        # Wrap command through executor for env/workdir handling
        wrapped = self._executor._wrap_command(run_cmd, env, wd, conn=conn)
        # Run in a detached tmux window with sentinels
        sentinel_ok  = "OMICS_JOB_DONE"
        sentinel_err = "OMICS_JOB_ERROR"
        full_cmd = (
            f"tmux new-session -d -s {tmux_name} "
            f"'({wrapped}) > {log_path} 2>&1 && "
            f"echo {sentinel_ok} >> {log_path} || "
            f"echo {sentinel_err} >> {log_path}'"
        )
        result = await conn.run(full_cmd, timeout=15)
        if result.exit_status != 0:
            raise RuntimeError(f"tmux launch failed: {result.stderr}")

        job = RemoteJob(
            job_id          = job_id,
            server_id       = conn.config.server_id,
            discord_user_id = discord_user_id,
            script_path     = run_cmd,
            log_path        = log_path,
            tmux_session    = tmux_name,
            command         = run_cmd,
            workdir         = wd,
            conda_env       = env,
            status          = JobStatus.RUNNING,
        )
        self._jobs[job_id] = job
        logger.info(f"submit_background: job={job_id} cmd={run_cmd[:60]}")
        return job

    async def get_job_log(self, job_id: str, discord_user_id: str,
                          tail: int = 50) -> str:
        job = self._jobs.get(job_id)
        if not job:
            return f"Job {job_id} not found"
        conn = await self._get_conn(discord_user_id, job.server_id)
        return await self._executor.get_job_log(conn, job, tail)

    async def collect_job_results(
        self, job_id: str, discord_user_id: str
    ) -> list[str]:
        """Download result files from a completed job."""
        job = self._jobs.get(job_id)
        if not job:
            return []
        conn = await self._get_conn(discord_user_id, job.server_id)
        local_dir = str(_LOCAL_TMP / job.job_id)
        return await self._executor.collect_results(conn, job, local_dir)

    # ------------------------------------------------------------------ #
    # Environment management
    # ------------------------------------------------------------------ #

    async def list_envs(self, discord_user_id: str) -> list[CondaEnvInfo]:
        conn = await self._get_conn(discord_user_id)
        return await self._detector.list_conda_envs(conn)

    async def scan_env(
        self, discord_user_id: str, env_name: str
    ) -> CondaEnvInfo:
        conn = await self._get_conn(discord_user_id)
        env = CondaEnvInfo(name=env_name, path="")
        return await self._detector.scan_env(conn, env)

    async def set_active_env(self, discord_user_id: str, env_name: str) -> str:
        self._registry.set_active_env(discord_user_id, env_name)
        return f"✅ 已切换到 conda 环境 `{env_name}`"

    # ------------------------------------------------------------------ #
    # File & project management
    # ------------------------------------------------------------------ #

    async def set_project(self, discord_user_id: str, path: str) -> str:
        """Set the active project directory."""
        conn = await self._get_conn(discord_user_id)
        result = await self._executor.run(conn, f"ls {path}", timeout=10)
        if not result.success:
            return f"❌ 路径不存在或无权限：`{path}`"
        self._registry.set_active_project(discord_user_id, path)
        return f"✅ 项目目录已设置为 `{path}`"

    async def list_project_files(
        self, discord_user_id: str, path: Optional[str] = None
    ) -> str:
        conn = await self._get_conn(discord_user_id)
        session = self._registry.get_session(discord_user_id)
        target = path or session.active_project_path or "~"
        entries = await self._transfer.list_dir(conn, target)
        if not entries:
            return f"📁 `{target}` 为空或不存在"

        lines = [f"📁 `{target}` 内容："]
        for e in entries[:30]:
            icon = "📂" if e["type"] == "dir" else "📄"
            size = f"{e['size']:,}B" if e["type"] == "file" else ""
            lines.append(f"  {icon} {e['name']}  {size}  {e['modified']}")
        return "\n".join(lines)

    async def read_script(
        self, discord_user_id: str, remote_path: str, max_lines: int = 100
    ) -> str:
        conn = await self._get_conn(discord_user_id)
        return await self._transfer.read_text(conn, remote_path, max_lines)

    async def find_data_files(
        self, discord_user_id: str, search_path: Optional[str] = None
    ) -> list[str]:
        conn = await self._get_conn(discord_user_id)
        session = self._registry.get_session(discord_user_id)
        target = search_path or session.active_project_path or "~"
        return await self._detector.find_data_files(conn, target)

    async def inspect_h5ad(
        self, discord_user_id: str, filepath: str,
        conda_env: Optional[str] = None
    ) -> dict:
        conn = await self._get_conn(discord_user_id)
        session = self._registry.get_session(discord_user_id)
        env = conda_env or session.active_conda_env
        return await self._detector.inspect_h5ad(conn, filepath, env)

    async def download_file(
        self, discord_user_id: str, remote_path: str
    ) -> str:
        """Download a file and return local path (for Discord upload)."""
        conn = await self._get_conn(discord_user_id)
        filename = Path(remote_path).name
        local_path = str(_LOCAL_TMP / filename)
        return await self._transfer.download(conn, remote_path, local_path)

    # ------------------------------------------------------------------ #
    # Session info
    # ------------------------------------------------------------------ #

    def get_session_summary(self, discord_user_id: str) -> str:
        session = self._registry.get_session(discord_user_id)
        servers = self._registry.list_servers(discord_user_id)
        lines = [f"📊 **OmicsClaw 会话状态**"]
        lines.append(f"  🖥️  服务器：`{session.active_server_id or '未选择'}`（共 {len(servers)} 台）")
        lines.append(f"  📁 项目目录：`{session.active_project_path or '未设置'}`")
        lines.append(f"  🐍 conda 环境：`{session.active_conda_env or '未选择'}`")
        running_jobs = [j for j in self._jobs.values()
                        if j.discord_user_id == discord_user_id
                        and j.status.value == "running"]
        lines.append(f"  ⚙️  运行中任务：{len(running_jobs)} 个")
        return "\n".join(lines)
