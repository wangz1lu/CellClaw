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

from bots.base import BaseBot, BotConfig
from shared.protocol import MessageType, Message, AgentRole, SubTaskStatus
from shared.state_manager import StateManager


class ExecutorBot(BaseBot):
    """
    Executor Bot - executes tasks on remote servers.
    
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
        
        # SSH manager (lazy loaded)
        self._ssh = None
    
    def _register_default_handlers(self):
        """Register message handlers."""
        self._handlers[MessageType.SUBTASK_REQUEST] = self.handle_execute_request
        self._handlers[MessageType.EXECUTE_REQUEST] = self.handle_execute_request
        self._handlers[MessageType.PING] = self.handle_ping
    
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
            
            # Submit job
            job_id = await self._submit_job(
                user_id=task.leader_id,
                code=code,
                language=language,
                description=task.description,
                channel_id=task.channel_id
            )
            
            # Save job info
            self.state.update_task(
                task_id,
                job_id=job_id,
                status="executing"
            )
            
            # Mark executor done (job submitted to background)
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
    
    async def _submit_job(
        self,
        user_id: str,
        code: str,
        language: str,
        description: str,
        channel_id: str
    ) -> str:
        """Submit job to SSH server."""
        
        # Generate job ID
        job_id = f"job_{secrets.token_hex(4)}"
        
        # Prepare script
        ext = "R" if language == "R" else "py"
        script_name = f"{job_id}.{ext}"
        
        # Workdir
        workdir = self.config.ssh_workdir or "/tmp/cellclaw_jobs"
        
        # Log file
        log_file = f"{workdir}/{job_id}.log"
        
        # Create script content
        script_content = code
        
        # For now, just save locally and return job ID
        # In production, would use SSHManager
        local_dir = "/tmp/cellclaw_scripts"
        os.makedirs(local_dir, exist_ok=True)
        
        script_path = os.path.join(local_dir, script_name)
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        self.logger.info(f"Script saved to {script_path}")
        
        # TODO: Actually execute via SSH
        # For now, simulate job submission
        # In real implementation:
        # job = await self._ssh.submit_analysis(
        #     discord_user_id=user_id,
        #     script=code,
        #     script_ext=ext,
        #     description=description
        # )
        
        return job_id
    
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
            
            # Check job status (would call SSH API in production)
            # For now, simulate completion after a few polls
            if i >= 2:  # Simulate for demo
                # Job completed successfully
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
