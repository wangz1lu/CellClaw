"""
Remote Executor
===============
Executes commands on remote Linux servers via SSH.

Two modes:
  run()             — synchronous short commands (timeout enforced)
  run_background()  — long-running jobs via tmux, non-blocking

Background job lifecycle:
  1. Write Python/bash script to /tmp/omics_<job_id>.py (or .sh)
  2. Start tmux session: tmux new-session -d -s omics_<job_id>
  3. Run inside tmux: conda run -n <env> python script.py > log 2>&1
  4. poll_job() checks: tmux has-session + tail log for "OMICS_DONE"/"OMICS_ERROR"
  5. Agent proactively polls and notifies Discord on completion
"""

from __future__ import annotations
import asyncio
import logging
import secrets
import textwrap
from datetime import datetime
from pathlib import PurePosixPath
from typing import Optional

from .models import ExecuteResult, JobStatus, RemoteJob
from .connection import SSHConnection

logger = logging.getLogger(__name__)

# Sentinel strings written to log when a job finishes
_JOB_DONE_SENTINEL = "OMICS_JOB_DONE"
_JOB_ERROR_SENTINEL = "OMICS_JOB_ERROR"


class RemoteExecutor:

    # ------------------------------------------------------------------ #
    # Synchronous execution (short commands)
    # ------------------------------------------------------------------ #

    async def run(
        self,
        conn: SSHConnection,
        command: str,
        conda_env: Optional[str] = None,
        workdir: Optional[str] = None,
        timeout: int = 60,
    ) -> ExecuteResult:
        """
        Run a command synchronously on the remote server.
        Wraps with conda activation and workdir cd if provided.
        """
        full_cmd = self._wrap_command(command, conda_env, workdir)
        try:
            result = await conn.run(full_cmd, timeout=timeout)
            return ExecuteResult(
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                exit_code=result.exit_status or 0,
            )
        except asyncio.TimeoutError:
            return ExecuteResult(
                stdout="",
                stderr=f"命令超时（>{timeout}s）",
                exit_code=-1,
            )

    async def run_python(
        self,
        conn: SSHConnection,
        code: str,
        conda_env: Optional[str] = None,
        workdir: Optional[str] = None,
        timeout: int = 30,
    ) -> ExecuteResult:
        """
        Execute a short Python snippet synchronously via `python3 -c`.
        For multi-line code, writes to /tmp first.
        """
        if "\n" in code or len(code) > 200:
            tmp_path = f"/tmp/omics_snippet_{secrets.token_hex(4)}.py"
            await self._write_remote_file(conn, tmp_path, code)
            cmd = f"python3 {tmp_path}"
        else:
            escaped = code.replace('"', '\\"')
            cmd = f'python3 -c "{escaped}"'

        return await self.run(conn, cmd, conda_env=conda_env,
                              workdir=workdir, timeout=timeout)

    # ------------------------------------------------------------------ #
    # Background execution (long-running jobs via tmux)
    # ------------------------------------------------------------------ #

    async def run_background(
        self,
        conn: SSHConnection,
        discord_user_id: str,
        server_id: str,
        script_content: str,
        script_ext: str = "py",
        conda_env: Optional[str] = None,
        workdir: Optional[str] = None,
        result_patterns: Optional[list[str]] = None,
    ) -> RemoteJob:
        """
        Submit a long-running analysis script as a background tmux job.

        Args:
            script_content: Full Python or shell script content
            script_ext:     "py" | "sh" | "R"
            conda_env:      conda env to activate
            workdir:        working directory on remote
            result_patterns: glob patterns to collect results after completion
        """
        job_id = f"omics_{secrets.token_hex(6)}"
        tmux_name = job_id
        work = workdir or "~"
        log_path = f"/tmp/{job_id}.log"
        script_path = f"/tmp/{job_id}.{script_ext}"

        # Inject sentinels so we can detect completion
        wrapped_script = self._inject_sentinels(script_content, script_ext, log_path)
        await self._write_remote_file(conn, script_path, wrapped_script)

        # Build the execution command
        if script_ext == "py":
            exec_cmd = f"python3 {script_path}"
        elif script_ext == "R":
            exec_cmd = f"Rscript {script_path}"
        else:
            exec_cmd = f"bash {script_path}"

        run_cmd = self._wrap_command(exec_cmd, conda_env, work)
        tmux_cmd = (
            f"tmux new-session -d -s {tmux_name} "
            f"'cd {work} && {run_cmd} >> {log_path} 2>&1'"
        )

        result = await conn.run(tmux_cmd, timeout=15)
        if result.exit_status != 0:
            raise RuntimeError(
                f"Failed to start tmux job: {result.stderr.strip()}"
            )

        logger.info(f"Started background job {job_id} on {conn.config.server_id}")

        return RemoteJob(
            job_id=job_id,
            discord_user_id=discord_user_id,
            server_id=server_id,
            tmux_session=tmux_name,
            command=exec_cmd,
            workdir=work,
            conda_env=conda_env,
            log_path=log_path,
            script_path=script_path,
            status=JobStatus.RUNNING,
            started_at=datetime.now(),
            result_paths=result_patterns or [],
        )

    async def poll_job(self, conn: SSHConnection, job: RemoteJob) -> RemoteJob:
        """
        Check the current status of a background job.
        Updates job.status in-place and returns the job.
        """
        # Check if tmux session still exists
        tmux_check = await conn.run(
            f"tmux has-session -t {job.tmux_session} 2>/dev/null && echo alive || echo dead",
            timeout=10
        )
        tmux_alive = "alive" in tmux_check.stdout

        # Check log for sentinels
        log_tail = await conn.run(f"tail -5 {job.log_path} 2>/dev/null", timeout=10)
        log_text = log_tail.stdout

        if _JOB_DONE_SENTINEL in log_text:
            job.status = JobStatus.DONE
            job.finished_at = datetime.now()
            logger.info(f"Job {job.job_id} completed successfully")
        elif _JOB_ERROR_SENTINEL in log_text:
            job.status = JobStatus.FAILED
            job.finished_at = datetime.now()
            # Extract error summary
            err_check = await conn.run(
                f"grep -A5 'Traceback\|Error\|{_JOB_ERROR_SENTINEL}' {job.log_path} "
                f"| tail -10", timeout=10
            )
            job.error_summary = err_check.stdout.strip()
        elif not tmux_alive:
            # tmux died but no sentinel → unexpected crash
            job.status = JobStatus.FAILED
            job.finished_at = datetime.now()
            job.error_summary = "进程意外退出（无错误信息）"
        else:
            job.status = JobStatus.RUNNING

        return job

    async def get_job_log(
        self,
        conn: SSHConnection,
        job: RemoteJob,
        tail: int = 50,
    ) -> str:
        """Return the last N lines of the job log."""
        result = await conn.run(
            f"tail -n {tail} {job.log_path} 2>/dev/null || echo '(log not found)'",
            timeout=10,
        )
        return result.stdout.strip()

    async def cancel_job(self, conn: SSHConnection, job: RemoteJob) -> bool:
        """Kill the tmux session to cancel a running job."""
        result = await conn.run(
            f"tmux kill-session -t {job.tmux_session} 2>/dev/null",
            timeout=10
        )
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now()
        return result.exit_status == 0

    async def collect_results(
        self,
        conn: SSHConnection,
        job: RemoteJob,
        local_dir: str,
    ) -> list[str]:
        """
        After job completion, collect result files from the server.
        Returns list of local file paths.
        """
        local_paths = []
        if not job.result_paths:
            return local_paths

        sftp = await conn.sftp()
        for pattern in job.result_paths:
            # Expand globs on remote
            find_result = await conn.run(
                f"ls {pattern} 2>/dev/null", timeout=10
            )
            for remote_path in find_result.stdout.strip().splitlines():
                remote_path = remote_path.strip()
                if not remote_path:
                    continue
                filename = PurePosixPath(remote_path).name
                local_path = str(PurePosixPath(local_dir) / filename)
                try:
                    await sftp.get(remote_path, local_path)
                    local_paths.append(local_path)
                    logger.info(f"Downloaded {remote_path} → {local_path}")
                except Exception as e:
                    logger.warning(f"Failed to download {remote_path}: {e}")

        return local_paths

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _wrap_command(
        self,
        command: str,
        conda_env: Optional[str],
        workdir: Optional[str],
    ) -> str:
        parts = []
        if workdir:
            parts.append(f"cd {workdir}")
        if conda_env:
            # conda run is cleaner than source activate in non-interactive shells
            parts.append(f"conda run -n {conda_env} --no-capture-output {command}")
        else:
            parts.append(command)
        return " && ".join(parts) if len(parts) > 1 else parts[0]

    async def _write_remote_file(
        self, conn: SSHConnection, remote_path: str, content: str
    ):
        """Write content to a remote file via echo/heredoc."""
        # Use base64 to safely transfer arbitrary content
        import base64
        encoded = base64.b64encode(content.encode()).decode()
        cmd = f"echo '{encoded}' | base64 -d > {remote_path}"
        result = await conn.run(cmd, timeout=15)
        if result.exit_status != 0:
            raise RuntimeError(f"Failed to write {remote_path}: {result.stderr}")

    def _inject_sentinels(
        self, script: str, ext: str, log_path: str
    ) -> str:
        """Wrap script to emit DONE/ERROR sentinels at the end."""
        if ext == "py":
            return textwrap.dedent(f"""\
                import sys, traceback
                _omics_log = open({log_path!r}, 'a')
                try:
                {textwrap.indent(script, '    ')}
                    print("{_JOB_DONE_SENTINEL}", flush=True)
                    _omics_log.write("{_JOB_DONE_SENTINEL}\\n")
                except Exception as _e:
                    traceback.print_exc()
                    _omics_log.write("{_JOB_ERROR_SENTINEL}\\n")
                    sys.exit(1)
                finally:
                    _omics_log.close()
            """)
        elif ext == "sh":
            return (
                f"{script}\n"
                f'echo "{_JOB_DONE_SENTINEL}" || echo "{_JOB_ERROR_SENTINEL}"\n'
            )
        elif ext == "R":
            return (
                f"tryCatch({{\n{script}\n"
                f'cat("{_JOB_DONE_SENTINEL}\\n", file=stderr())\n'
                f"}}, error = function(e) {{\n"
                f'cat("{_JOB_ERROR_SENTINEL}\\n", file=stderr())\n'
                f"stop(e)\n}})\n"
            )
        return script
