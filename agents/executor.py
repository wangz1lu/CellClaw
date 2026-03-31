"""
ExecutorAgent - Execution Monitoring
===================================

Handles job submission, status polling, result collection, and Dashboard sync.
Reports to user INDEPENDENTLY via callbacks.
"""

from __future__ import annotations
import os
import asyncio
import logging
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class JobStatus:
    """Status of a running job"""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class JobInfo:
    """Information about a tracked job"""
    job_id: str
    user_id: str
    channel_id: Optional[str]
    description: str
    skill_used: Optional[str]
    status: str = JobStatus.PENDING
    progress: float = 0.0
    result_files: list = field(default_factory=list)
    error_message: Optional[str] = None
    log_path: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ExecutorAgent:
    """
    ExecutorAgent - The ONLY agent that reports back to user independently.
    
    Responsibilities:
    - Submit jobs to background execution
    - Report progress/status to user via callbacks (independent communication)
    - Collect results
    - Sync with Dashboard
    
    Key difference from other agents:
    - Does NOT wait to be asked - reports proactively
    - Uses callbacks to notify Orchestrator → User
    """

    def __init__(self, config=None):
        self.config = config
        self.name = "executor"

        # SSH Manager (will be set by integration)
        self._ssh = None

        # User notification callback (set by Orchestrator)
        self._user_notify_callback: Optional[Callable] = None

        # Active jobs tracking
        self._active_jobs: Dict[str, JobInfo] = {}

        # Dashboard sync callback
        self._dashboard_sync: Optional[Callable] = None
        
        # HTTP client for Dashboard sync
        self._dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:7860")

        logger.info("ExecutorAgent initialized")

    def set_notify_callback(self, callback: Callable):
        """Set callback for Orchestrator to receive executor events"""
        # Legacy - kept for compatibility
        pass

    def set_user_notify_callback(self, callback: Callable):
        """Set callback for direct user notifications"""
        self._user_notify_callback = callback

    def set_dashboard_sync(self, callback: Callable):
        """Set callback for dashboard sync"""
        self._dashboard_sync = callback

    # ───────────────────────────────────────────────────────────────
    # Job Submission
    # ───────────────────────────────────────────────────────────────

    async def submit(self, script_path: str, user_id: str,
                     channel_id: str = None,
                     description: str = "分析任务",
                     skill_used: str = None,
                     script_content: str = None) -> str:
        """
        Submit a job for background execution.
        Executor reports to user INDEPENDENTLY when job starts/updates/completes.
        
        Args:
            script_path: Path to the script to execute
            user_id: User who submitted the job
            channel_id: Discord channel for notifications
            description: Job description
            skill_used: Skill used for this job
            
        Returns:
            job_id: Unique job identifier
        """
        import secrets

        job_id = secrets.token_hex(4)

        # Create job info
        job_info = JobInfo(
            job_id=job_id,
            user_id=user_id,
            channel_id=channel_id,
            description=description,
            skill_used=skill_used,
            status=JobStatus.RUNNING,
            started_at=datetime.now()
        )

        self._active_jobs[job_id] = job_info

        logger.info(f"Executor: Submitting job {job_id} for user {user_id}")

        try:
            # Submit to SSH - use submit_analysis to handle script upload
            if self._ssh:
                # Read script content
                if script_path and os.path.exists(script_path):
                    with open(script_path, 'r') as f:
                        script_content = f.read()
                    # Determine language
                    if script_path.endswith(".R"):
                        script_ext = "R"
                    elif script_path.endswith(".py"):
                        script_ext = "py"
                    else:
                        script_ext = "sh"
                    
                    # Use submit_analysis which handles upload
                    job = await self._ssh.submit_analysis(
                        discord_user_id=user_id,
                        script=script_content,
                        script_ext=script_ext,
                        description=description
                    )
                    job_info.log_path = job.log_path
                    actual_job_id = job.job_id
                else:
                    # No script file, run command directly
                    job = await self._ssh.submit_background(
                        discord_user_id=user_id,
                        run_cmd=script_path or "echo 'No script'",
                        description=description
                    )
                    actual_job_id = job.job_id
            else:
                actual_job_id = job_id

            # INDEPENDENT NOTIFICATION: Job started
            await self._notify_user({
                "type": "task_started",
                "job_id": actual_job_id,
                "user_id": user_id,
                "channel_id": channel_id,
                "skill_used": skill_used,
                "message": (
                    f"✅ 任务已开始执行\n"
                    f"任务 PID: `{actual_job_id}`\n"
                    f"描述: {description}"
                )
            })

            # Start monitoring in background
            asyncio.create_task(self._monitor_job(actual_job_id, user_id, channel_id))

            return actual_job_id

        except Exception as e:
            logger.error(f"Executor: Job submission failed: {e}")
            job_info.status = JobStatus.FAILED
            job_info.error_message = str(e)

            await self._notify_user({
                "type": "failed",
                "job_id": job_id,
                "user_id": user_id,
                "channel_id": channel_id,
                "error": str(e),
                "message": f"❌ 任务提交失败: {e}"
            })

            raise

    async def _monitor_job(self, job_id: str, user_id: str, channel_id: str):
        """Monitor job and report status independently"""
        max_polls = 120  # 1 hour max
        poll_interval = 30  # 30 seconds

        for i in range(max_polls):
            await asyncio.sleep(poll_interval)

            job_info = self._active_jobs.get(job_id)
            if not job_info:
                break

            try:
                # Poll status
                if self._ssh:
                    job = await self._ssh.poll_job(job_id, user_id)

                    if job.is_done:
                        if job.is_success:
                            job_info.status = JobStatus.DONE
                            job_info.finished_at = datetime.now()

                            # INDEPENDENT NOTIFICATION: Completed
                            await self._notify_user({
                                "type": "completed",
                                "job_id": job_id,
                                "user_id": user_id,
                                "channel_id": channel_id,
                                "result_files": getattr(job, 'result_files', []),
                                "message": (
                                    f"✅ 任务 `{job_id}` 成功完成！\n"
                                    f"描述: {job_info.description}"
                                )
                            })

                        else:
                            job_info.status = JobStatus.FAILED
                            job_info.error_message = getattr(job, 'error_summary', 'Unknown error')
                            job_info.finished_at = datetime.now()

                            # INDEPENDENT NOTIFICATION: Failed
                            await self._notify_user({
                                "type": "failed",
                                "job_id": job_id,
                                "user_id": user_id,
                                "channel_id": channel_id,
                                "error": job_info.error_message,
                                "message": (
                                    f"❌ 任务 `{job_id}` 失败！\n"
                                    f"错误: {job_info.error_message}"
                                )
                            })

                        # Sync to dashboard
                        await self._sync_dashboard(job_info)
                        break

                    else:
                        # INDEPENDENT NOTIFICATION: Progress
                        progress = (i + 1) / max_polls
                        job_info.progress = progress

                        # Only notify every few polls to avoid spam
                        if i % 3 == 0:
                            await self._notify_user({
                                "type": "progress",
                                "job_id": job_id,
                                "user_id": user_id,
                                "channel_id": channel_id,
                                "progress": progress,
                                "message": (
                                    f"⏳ 任务 `{job_id}` 执行中... "
                                    f"{int(progress * 100)}%\n"
                                    f"描述: {job_info.description}"
                                )
                            })

            except Exception as e:
                logger.error(f"Executor: Monitor error for job {job_id}: {e}")
                break

    # ───────────────────────────────────────────────────────────────
    # Notifications
    # ───────────────────────────────────────────────────────────────

    async def _notify_user(self, event: dict):
        """
        Send notification to user INDEPENDENTLY.
        This is the core of ExecutorAgent's proactive communication.
        """
        if self._user_notify_callback:
            try:
                self._user_notify_callback(event)
            except Exception as e:
                logger.error(f"Executor: Notify callback failed: {e}")
        else:
            # Just log if no callback
            logger.info(f"Executor event (no callback): {event.get('type')} - {event.get('message', '')[:50]}")

    # ───────────────────────────────────────────────────────────────
    # Dashboard Sync
    # ───────────────────────────────────────────────────────────────

    async def _sync_dashboard(self, job_info: JobInfo):
        """Sync job status to Dashboard via HTTP"""
        try:
            import aiohttp
            
            payload = {
                "job_id": job_info.job_id,
                "user_id": job_info.user_id,
                "status": job_info.status,
                "progress": job_info.progress,
                "result_files": job_info.result_files,
                "error": job_info.error_message,
                "description": job_info.description,
                "log_path": job_info.log_path,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._dashboard_url}/api/jobs/update",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        logger.debug(f"Dashboard synced: {job_info.job_id}")
                    else:
                        logger.warning(f"Dashboard sync failed: {resp.status}")
        except Exception as e:
            logger.debug(f"Dashboard sync error: {e}")

    # ───────────────────────────────────────────────────────────────
    # Job Management
    # ───────────────────────────────────────────────────────────────

    def get_active_jobs(self, user_id: str = None) -> List[JobInfo]:
        """Get all active jobs for a user"""
        if user_id:
            return [j for j in self._active_jobs.values() if j.user_id == user_id]
        return list(self._active_jobs.values())

    def get_job_status(self, job_id: str) -> Optional[JobInfo]:
        """Get status of a specific job"""
        return self._active_jobs.get(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        job_info = self._active_jobs.get(job_id)

        if not job_info or job_info.status != JobStatus.RUNNING:
            return False

        # TODO: Call SSH cancel
        job_info.status = JobStatus.FAILED
        job_info.error_message = "Cancelled by user"
        job_info.finished_at = datetime.now()

        return True

    def cleanup_completed(self, max_age_hours: int = 24):
        """Clean up old completed jobs"""
        now = datetime.now()
        to_remove = []

        for job_id, job in self._active_jobs.items():
            if job.finished_at:
                age = (now - job.finished_at).total_seconds() / 3600
                if age > max_age_hours:
                    to_remove.append(job_id)

        for job_id in to_remove:
            del self._active_jobs[job_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old jobs")

    def __repr__(self) -> str:
        return f"<ExecutorAgent: {self.name}, active_jobs={len(self._active_jobs)}>"
