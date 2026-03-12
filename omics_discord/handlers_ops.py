"""
/env, /project, /job, /status command handlers
"""

from __future__ import annotations
import logging
from typing import Optional

from ssh.manager import SSHManager
from ssh.models import JobStatus
from .parser import ParsedCommand
from .result import CommandResult

logger = logging.getLogger(__name__)


# ======================================================================
# /env handlers
# ======================================================================

class EnvCommandHandler:
    """
    /env list              — list all conda envs on active server
    /env use  <name>       — set active conda env for this session
    /env scan <name>       — deep-scan env for bioinformatics packages
    """

    def __init__(self, ssh_manager: SSHManager):
        self._mgr = ssh_manager

    async def handle(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        action = cmd.action
        if action == "list":
            return await self._list(discord_user_id)
        elif action == "use":
            return await self._use(cmd, discord_user_id)
        elif action == "scan":
            return await self._scan(cmd, discord_user_id)
        else:
            return CommandResult.info(self._help())

    async def _list(self, discord_user_id: str) -> CommandResult:
        try:
            envs = await self._mgr.list_envs(discord_user_id)
        except ValueError as e:
            return CommandResult.err(str(e))

        if not envs:
            return CommandResult.info("🐍 未检测到任何 conda 环境。")

        lines = ["🐍 **conda 环境列表：**"]
        for env in envs:
            lines.append(f"  - `{env.name}`  ({env.path})")
        lines.append(
            "\n💡 使用 `/env use <name>` 激活，`/env scan <name>` 查看安装的生信包"
        )
        return CommandResult.info("\n".join(lines))

    async def _use(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        name = cmd.first_arg() or cmd.flag("name")
        if not name:
            return CommandResult.err("请指定环境名称。\n用法：`/env use <name>`")
        msg = await self._mgr.set_active_env(discord_user_id, name)
        return CommandResult.ok(msg)

    async def _scan(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        name = cmd.first_arg() or cmd.flag("name")
        if not name:
            return CommandResult.err("请指定环境名称。\n用法：`/env scan <name>`")
        try:
            env = await self._mgr.scan_env(discord_user_id, name)
        except Exception as e:
            return CommandResult.err(f"扫描失败：{e}")

        if not env.key_packages:
            return CommandResult.info(
                f"🐍 `{name}` — 未检测到生信相关包\n"
                f"框架分类：**{env.framework.value}**"
            )

        lines = [f"🐍 **`{name}` 环境包扫描结果：**"]
        lines.append(f"分析框架：**{env.framework.value}**")
        lines.append("已安装的关键包：")
        for pkg, ver in env.key_packages.items():
            lines.append(f"  - `{pkg}` v{ver}")
        return CommandResult.info("\n".join(lines))

    def _help(self) -> str:
        return (
            "🐍 **`/env` 命令帮助**\n"
            "```\n"
            "/env list           # 列出服务器上所有 conda 环境\n"
            "/env use  <name>    # 设置当前分析使用的 conda 环境\n"
            "/env scan <name>    # 扫描环境内的生信包（scanpy/seurat等）\n"
            "```"
        )


# ======================================================================
# /project handlers
# ======================================================================

class ProjectCommandHandler:
    """
    /project set  <path>    — set active project directory
    /project ls   [path]    — list directory contents
    /project find [path]    — find data files (.h5ad, .h5, .rds, ...)
    /project info <file>    — inspect h5ad metadata
    """

    def __init__(self, ssh_manager: SSHManager):
        self._mgr = ssh_manager

    async def handle(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        action = cmd.action
        if action == "set":
            return await self._set(cmd, discord_user_id)
        elif action in ("ls", "list"):
            return await self._ls(cmd, discord_user_id)
        elif action == "find":
            return await self._find(cmd, discord_user_id)
        elif action == "info":
            return await self._info(cmd, discord_user_id)
        else:
            return CommandResult.info(self._help())

    async def _set(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        path = cmd.first_arg() or cmd.flag("path")
        if not path:
            return CommandResult.err("请指定路径。\n用法：`/project set <path>`")
        try:
            msg = await self._mgr.set_project(discord_user_id, path)
            return CommandResult.ok(msg) if "✅" in msg else CommandResult.err(msg)
        except ValueError as e:
            return CommandResult.err(str(e))

    async def _ls(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        path = cmd.first_arg() or cmd.flag("path")
        try:
            text = await self._mgr.list_project_files(discord_user_id, path)
            return CommandResult.info(text)
        except ValueError as e:
            return CommandResult.err(str(e))

    async def _find(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        path = cmd.first_arg() or cmd.flag("path")
        try:
            files = await self._mgr.find_data_files(discord_user_id, path)
        except ValueError as e:
            return CommandResult.err(str(e))

        if not files:
            return CommandResult.info(
                f"🔍 在 `{path or '项目目录'}` 下未找到单细胞数据文件\n"
                f"（支持格式：.h5ad, .h5, .loom, .rds）"
            )

        lines = [f"🔍 **找到 {len(files)} 个数据文件：**"]
        for f in files:
            lines.append(f"  📄 `{f}`")
        lines.append("\n💡 使用 `/project info <file>` 查看文件详情")
        return CommandResult.info("\n".join(lines))

    async def _info(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        filepath = cmd.first_arg() or cmd.flag("file") or cmd.flag("path")
        if not filepath:
            return CommandResult.err(
                "请指定文件路径。\n用法：`/project info <file.h5ad>`"
            )
        try:
            info = await self._mgr.inspect_h5ad(discord_user_id, filepath)
        except ValueError as e:
            return CommandResult.err(str(e))

        if "error" in info:
            return CommandResult.err(f"读取文件失败：{info['error']}")

        obs_cols = info.get("obs_columns", [])
        obsm = info.get("obsm_keys", [])
        uns = info.get("uns_keys", [])
        var_sample = info.get("var_names_sample", [])

        # Infer what analyses have been done
        done = []
        if any("leiden" in c or "louvain" in c for c in obs_cols):
            done.append("✅ 聚类（leiden/louvain）")
        if "X_umap" in obsm:
            done.append("✅ UMAP")
        if "X_pca" in obsm:
            done.append("✅ PCA")
        if "rank_genes_groups" in uns:
            done.append("✅ 差异表达（rank_genes_groups）")

        lines = [
            f"📊 **`{filepath}` 数据概览**",
            f"  - 细胞数：**{info.get('n_obs', '?'):,}**",
            f"  - 基因数：**{info.get('n_vars', '?'):,}**",
            f"  - 注释列（obs）：{', '.join(obs_cols[:8]) or '无'}",
            f"  - 嵌入（obsm）：{', '.join(obsm) or '无'}",
            f"  - 基因示例：{', '.join(var_sample)}",
        ]
        if done:
            lines.append(f"\n**已完成的分析步骤：**\n" + "\n".join(done))
        else:
            lines.append("\n⚠️ 暂未检测到聚类/降维结果，建议从 QC 开始分析")

        return CommandResult.info("\n".join(lines))

    def _help(self) -> str:
        return (
            "📁 **`/project` 命令帮助**\n"
            "```\n"
            "/project set  <path>   # 设置当前项目目录\n"
            "/project ls   [path]   # 查看目录内容\n"
            "/project find [path]   # 搜索单细胞数据文件\n"
            "/project info <file>   # 查看 .h5ad 文件详情\n"
            "```"
        )


# ======================================================================
# /job handlers
# ======================================================================

class JobCommandHandler:
    """
    /job list              — list recent jobs for this user
    /job status <job_id>   — check job status
    /job log    <job_id>   — tail job log
    /job cancel <job_id>   — cancel a running job
    """

    def __init__(self, ssh_manager: SSHManager):
        self._mgr = ssh_manager

    async def handle(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        action = cmd.action
        if action == "list":
            return self._list(discord_user_id)
        elif action == "status":
            return await self._status(cmd, discord_user_id)
        elif action == "log":
            return await self._log(cmd, discord_user_id)
        elif action == "cancel":
            return await self._cancel(cmd, discord_user_id)
        else:
            return CommandResult.info(self._help())

    def _list(self, discord_user_id: str) -> CommandResult:
        jobs = {
            jid: job for jid, job in self._mgr._jobs.items()
            if job.discord_user_id == discord_user_id
        }
        if not jobs:
            return CommandResult.info("⚙️ 你当前没有任何任务记录。")

        lines = [f"⚙️ **任务列表（{len(jobs)} 个）：**"]
        status_emoji = {
            JobStatus.RUNNING: "🔄",
            JobStatus.DONE: "✅",
            JobStatus.FAILED: "❌",
            JobStatus.CANCELLED: "⛔",
            JobStatus.PENDING: "⏳",
        }
        for jid, job in sorted(jobs.items(), key=lambda x: x[1].started_at, reverse=True):
            emoji = status_emoji.get(job.status, "❓")
            elapsed = job.elapsed()
            lines.append(
                f"  {emoji} `{jid}` — {job.status.value} | "
                f"耗时 {elapsed} | 服务器: {job.server_id}"
            )
        lines.append("\n💡 使用 `/job log <job_id>` 查看运行日志")
        return CommandResult.info("\n".join(lines))

    async def _status(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        job_id = cmd.first_arg() or cmd.flag("id")
        if not job_id:
            return CommandResult.err("请指定任务ID。\n用法：`/job status <job_id>`")
        try:
            job = await self._mgr.poll_job(job_id, discord_user_id)
        except KeyError:
            return CommandResult.err(f"未找到任务 `{job_id}`")

        status_map = {
            JobStatus.RUNNING: "🔄 运行中",
            JobStatus.DONE: "✅ 已完成",
            JobStatus.FAILED: "❌ 失败",
            JobStatus.CANCELLED: "⛔ 已取消",
            JobStatus.PENDING: "⏳ 等待中",
        }
        status_text = status_map.get(job.status, job.status.value)
        lines = [
            f"⚙️ **任务 `{job_id}` 状态**",
            f"  状态：{status_text}",
            f"  服务器：`{job.server_id}`",
            f"  环境：`{job.conda_env or '默认'}`",
            f"  目录：`{job.workdir}`",
            f"  已耗时：{job.elapsed()}",
        ]
        if job.error_summary:
            lines.append(f"\n**错误摘要：**\n```\n{job.error_summary}\n```")
        if job.result_paths and job.status == JobStatus.DONE:
            lines.append(f"\n**结果文件：**")
            for p in job.result_paths:
                lines.append(f"  📄 `{p}`")

        return CommandResult.info("\n".join(lines))

    async def _log(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        job_id = cmd.first_arg() or cmd.flag("id")
        if not job_id:
            return CommandResult.err("请指定任务ID。\n用法：`/job log <job_id>`")
        tail = int(cmd.flag("n") or cmd.flag("tail") or "50")
        try:
            log = await self._mgr.get_job_log(job_id, discord_user_id, tail)
        except KeyError:
            return CommandResult.err(f"未找到任务 `{job_id}`")

        if not log:
            return CommandResult.info(f"⚙️ 任务 `{job_id}` 暂无日志输出。")

        # Truncate to fit Discord's 2000-char limit
        if len(log) > 1800:
            log = "...(截断，显示最后部分)...\n" + log[-1600:]

        return CommandResult.info(
            f"📋 **任务 `{job_id}` 日志（最后 {tail} 行）：**\n"
            f"```\n{log}\n```"
        )

    async def _cancel(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        job_id = cmd.first_arg() or cmd.flag("id")
        if not job_id:
            return CommandResult.err("请指定任务ID。\n用法：`/job cancel <job_id>`")

        job = self._mgr._jobs.get(job_id)
        if not job:
            return CommandResult.err(f"未找到任务 `{job_id}`")
        if job.discord_user_id != discord_user_id:
            return CommandResult.err("你无权取消他人的任务")
        if job.status != JobStatus.RUNNING:
            return CommandResult.err(f"任务 `{job_id}` 当前状态为 `{job.status.value}`，无法取消")

        try:
            conn = await self._mgr._get_conn(discord_user_id, job.server_id)
            ok = await self._mgr._executor.cancel_job(conn, job)
            if ok:
                return CommandResult.ok(f"⛔ 任务 `{job_id}` 已取消")
            return CommandResult.err(f"取消任务失败，请手动检查 tmux session `{job.tmux_session}`")
        except Exception as e:
            return CommandResult.err(str(e))

    def _help(self) -> str:
        return (
            "⚙️ **`/job` 命令帮助**\n"
            "```\n"
            "/job list                # 列出所有任务\n"
            "/job status <job_id>     # 查看任务状态\n"
            "/job log    <job_id>     # 查看运行日志\n"
            "/job log    <job_id> -n 100  # 查看最后100行\n"
            "/job cancel <job_id>     # 取消运行中的任务\n"
            "```"
        )


# ======================================================================
# /status handler
# ======================================================================

class StatusCommandHandler:
    """
    /status — show current session overview
    """

    def __init__(self, ssh_manager: SSHManager):
        self._mgr = ssh_manager

    async def handle(self, cmd: ParsedCommand, discord_user_id: str) -> CommandResult:
        text = self._mgr.get_session_summary(discord_user_id)
        return CommandResult.info(text)
