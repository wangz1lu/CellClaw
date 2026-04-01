"""
Executor Bot - Task Execution Agent
===================================

Executes approved code on remote servers and notifies results.
"""

from __future__ import annotations
import asyncio
import logging
import os
import re
import secrets
from typing import Optional

import asyncssh

from bots.base import BaseBot, BotConfig
from shared.protocol import MessageType, Message, AgentRole, SubTaskStatus
from shared.state_manager import StateManager


class ExecutorBot(BaseBot):
    """
    Executor Bot - executes tasks on remote servers via SSH.
    
    Responsibilities:
    - Receive approved code from orchestrator
    - Upload script to SSH workdir
    - Execute with nohup
    - Monitor job status
    - Notify leader on completion/failure
    """
    
    def __init__(self, config: BotConfig):
        super().__init__(config)
        self.config.role = AgentRole.EXECUTOR
        self.logger.info("ExecutorBot initialized")
        
        # SSH connection pool
        self._ssh_conn = None
    
    def _register_default_handlers(self):
        """Register message handlers."""
        self._handlers[MessageType.SUBTASK_REQUEST] = self.handle_execute_request
        self._handlers[MessageType.EXECUTE_REQUEST] = self.handle_execute_request
        self._handlers[MessageType.PING] = self.handle_ping
    
    async def _get_ssh_connection(self):
        """Get or create SSH connection."""
        if self._ssh_conn is None or self._ssh_conn.is_closed():
            self._ssh_conn = await asyncssh.connect(
                host=self.config.ssh_host,
                port=self.config.ssh_port,
                username=self.config.ssh_user,
            )
        return self._ssh_conn
    
    async def handle_execute_request(self, msg: Message) -> str:
        """Handle execution request."""
        self.logger.info(f"Received execution request")
        
        task_id = msg.task_id or self._extract_task_id(msg.content)
        if not task_id:
            return "❌ No task ID found."
        
        task = self.state.get_task(task_id)
        if not task:
            return f"❌ Task `{task_id}` not found."
        
        self.state.update_subtask(task_id, "executor", status=SubTaskStatus.IN_PROGRESS)
        
        await self.notify_progress(task.channel_id, task_id, "Executor", "Preparing execution...")
        
        try:
            # Get code
            code = None
            if msg.payload and msg.payload.get("code"):
                code = msg.payload["code"]
            elif task.code:
                code = task.code
            
            if not code:
                return "❌ No code found to execute."
            
            language = msg.payload.get("language", "R") if msg.payload else (task.language or "R")
            
            # Submit job via SSH
            job_id = await self._submit_job_via_ssh(
                code=code,
                language=language,
                description=task.description,
            )
            
            # Save job info
            self.state.update_task(
                task_id,
                job_id=job_id,
                status="executing"
            )
            
            # Mark executor subtask done
            self.state.update_subtask(
                task_id, "executor",
                status=SubTaskStatus.DONE,
                output=f"Job submitted: {job_id}"
            )
            
            response = (
                f"🚀 **Job Submitted**\n"
                f"Task ID: `{task_id}`\n"
                f"Job ID: `{job_id}`\n\n"
                f"Job is running in background. I'll notify you when it's done."
            )
            
            await self.send_message(task.channel_id, response)
            
            # Start monitoring in background
            asyncio.create_task(self._monitor_job(task_id, job_id, task.leader_id, task.channel_id))
            
            return None
            
        except Exception as e:
            self.logger.error(f"Execution failed: {e}")
            
            self.state.update_subtask(
                task_id, "executor",
                status=SubTaskStatus.FAILED,
                error=str(e)
            )
            
            return f"❌ Execution failed: {str(e)}"
    
    async def handle_ping(self, msg: Message) -> str:
        """Handle ping."""
        return f"pong | executor | {self.config.user_id}"
    
    async def _submit_job_via_ssh(
        self,
        code: str,
        language: str,
        description: str
    ) -> str:
        """Submit job to remote server via SSH."""
        
        # Generate job ID
        job_id = f"job_{secrets.token_hex(4)}"
        
        # Prepare script
        ext = "R" if language == "R" else "py"
        script_name = f"{job_id}.{ext}"
        
        # Workdir
        workdir = self.config.ssh_workdir or "/tmp/cellclaw_jobs"
        
        # Log file
        log_file = f"{workdir}/{job_id}.log"
        pid_file = f"{workdir}/{job_id}.pid"
        
        # Get SSH connection
        conn = await self._get_ssh_connection()
        
        # Create workdir if needed
        await conn.run(f"mkdir -p {workdir}", check=True)
        
        # Write script to remote
        async with conn.open_sftp() as sftp:
            script_path = f"{workdir}/{script_name}"
            await sftp.write_file(script_path, code)
        
        # Submit with nohup, save PID
        run_cmd = f"cd {workdir} && nohup bash {script_name} > {log_file} 2>&1 & echo $! > {pid_file} && cat {pid_file}"
        
        result = await conn.run(run_cmd, check=True)
        pid = result.stdout.strip()
        
        self.logger.info(f"Job {job_id} submitted with PID {pid}")
        
        return job_id
    
    async def _check_job_status(self, job_id: str) -> dict:
        """Check job status on remote server."""
        try:
            conn = await self._get_ssh_connection()
            workdir = self.config.ssh_workdir or "/tmp/cellclaw_jobs"
            log_file = f"{workdir}/{job_id}.log"
            pid_file = f"{workdir}/{job_id}.pid"
            
            # Check if process is still running
            check_cmd = f"ps -p $(cat {pid_file} 2>/dev/null) > /dev/null 2>&1 && echo 'running' || echo 'done'"
            result = await conn.run(check_cmd, check=False)
            
            is_running = "running" in result.stdout
            is_done = not is_running
            
            # Read last lines of log for status
            tail_cmd = f"tail -10 {log_file} 2>/dev/null || echo 'No log yet'"
            log_result = await conn.run(tail_cmd, check=False)
            last_log = log_result.stdout
            
            return {
                "is_running": is_running,
                "is_done": is_done,
                "is_success": "error" not in last_log.lower() and "failed" not in last_log.lower(),
                "log_tail": last_log
            }
            
        except Exception as e:
            self.logger.error(f"Failed to check job status: {e}")
            return {"is_done": True, "is_success": False, "error": str(e)}
    
    async def _monitor_job(
        self,
        task_id: str,
        job_id: str,
        leader_id: str,
        channel_id: str
    ):
        """Monitor job status and notify on completion."""
        
        max_polls = 120  # 1 hour max
        poll_interval = 30  # 30 seconds
        
        for i in range(max_polls):
            await asyncio.sleep(poll_interval)
            
            # Check job status
            status = await self._check_job_status(job_id)
            
            if status.get("is_done"):
                if status.get("is_success"):
                    self.state.update_task(
                        task_id,
                        status="done",
                        completed_at=self._get_timestamp()
                    )
                    
                    await self.send_message(
                        channel_id,
                        f"✅ **Task Completed!**\n"
                        f"Task ID: `{task_id}`\n"
                        f"Job ID: `{job_id}`\n\n"
                        f"Results saved to workdir."
                    )
                else:
                    self.state.update_task(
                        task_id,
                        status="failed",
                        error_message=status.get("error", "Job failed")
                    )
                    
                    await self.send_message(
                        channel_id,
                        f"❌ **Task Failed**\n"
                        f"Task ID: `{task_id}`\n"
                        f"Job ID: `{job_id}`\n\n"
                        f"Check logs for details."
                    )
                return
            
            # Log progress
            self.logger.info(f"Job {job_id} poll {i+1}/{max_polls}")
        
        # Timeout
        self.state.update_task(task_id, status="failed", error_message="Job timeout")
        await self.send_message(
            channel_id,
            f"❌ **Task Timeout**\n"
            f"Task ID: `{task_id}`\n"
            f"Job ID: `{job_id}`\n\n"
            f"Job exceeded maximum runtime."
        )
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        import time
        return time.strftime("%Y-%m-%d %H:%M:%S")
    
    def _extract_task_id(self, content: str) -> Optional[str]:
        """Extract task ID from content."""
        patterns = [
            r'task[_\s]?id:?\s*`?([a-zA-Z0-9]+)`?',
            r'\[task:([^\]]+)\]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    async def close(self):
        """Close SSH connection."""
        if self._ssh_conn and not self._ssh_conn.is_closed():
            self._ssh_conn.close()


def create_executor_bot() -> ExecutorBot:
    """Create executor bot from config."""
    config = BotConfig(
        name="CellClaw-Executor",
        role=AgentRole.EXECUTOR,
        token=os.getenv("CELLCRAW_EXECUTOR_TOKEN", ""),
        ssh_host=os.getenv("CELLCRAW_EXECUTOR_SSH_HOST", ""),
        ssh_port=int(os.getenv("CELLCRAW_EXECUTOR_SSH_PORT", "50000")),
        ssh_user=os.getenv("CELLCRAW_EXECUTOR_SSH_USER", ""),
        ssh_workdir=os.getenv("CELLCRAW_EXECUTOR_SSH_WORKDIR", "/tmp/cellclaw_jobs")
    )
    return ExecutorBot(config)
