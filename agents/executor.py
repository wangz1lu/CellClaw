"""
ExecutorAgent - Execution Monitoring
===================================

Handles job submission, status polling, result collection, and Dashboard sync.
"""

from __future__ import annotations
import os
import asyncio
import logging
from typing import Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from agents.base import BaseAgent
from agents.models import AgentConfig, AgentType, TaskStep, TaskStatus, ExecutionPlan

logger = logging.getLogger(__name__)


@dataclass
class JobStatus:
    """Status of a running job"""
    job_id: str
    status: str  # "pending", "running", "done", "failed"
    progress: float = 0.0  # 0.0 - 1.0
    result_files: list[str] = None
    error_message: Optional[str] = None
    log_path: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.result_files is None:
            self.result_files = []


class ExecutorAgent:
    """
    ExecutorAgent handles job execution and monitoring.
    
    Responsibilities:
    - Submit jobs to background execution
    - Poll job status
    - Collect results
    - Sync with Dashboard
    - Notify users
    """
    
    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig.default_for(AgentType.EXECUTOR)
        self.name = self.config.name
        self.base = BaseAgent()
        
        # API config
        self._api_key = self.config.api_key or os.getenv("EXECUTOR_API_KEY") or os.getenv("OMICS_LLM_API_KEY")
        
        # Active jobs tracking
        self._active_jobs: dict[str, JobStatus] = {}
        
        # Dashboard sync callback
        self._dashboard_sync: Optional[Callable] = None
        
        # Notification callback
        self._notify_callback: Optional[Callable] = None
    
    # ───────────────────────────────────────────────────────────────
    # Job Submission
    # ───────────────────────────────────────────────────────────────
    
    async def submit(self, code: str, user_id: str, 
                   script_path: str = None,
                   language: str = "R") -> str:
        """
        Submit a job for background execution.
        
        Args:
            code: Code to execute
            user_id: User who submitted the job
            script_path: Path to script file (if pre-saved)
            language: "R" or "Python"
            
        Returns:
            job_id: Unique job identifier
        """
        import secrets
        
        job_id = secrets.token_hex(4)
        
        # Create job status
        job_status = JobStatus(
            job_id=job_id,
            status="pending",
            started_at=datetime.now(),
        )
        
        self._active_jobs[job_id] = job_status
        
        logger.info(f"Submitting job {job_id} for user {user_id}")
        
        # TODO: Integrate with SSHManager.submit_background()
        # For now, just track
        
        return job_id
    
    async def submit_script(self, script_path: str, user_id: str,
                          description: str = "分析任务") -> str:
        """
        Submit an existing script file for execution.
        
        Args:
            script_path: Path to the script
            user_id: User ID
            description: Job description
            
        Returns:
            job_id
        """
        import secrets
        
        job_id = secrets.token_hex(4)
        
        job_status = JobStatus(
            job_id=job_id,
            status="running",
            started_at=datetime.now(),
            log_path=f"/tmp/cell_job_{job_id}.log",
        )
        
        self._active_jobs[job_id] = job_status
        
        # TODO: Call SSHManager.submit_background()
        
        logger.info(f"Submitted script {script_path} as job {job_id}")
        
        return job_id
    
    # ───────────────────────────────────────────────────────────────
    # Status Polling
    # ───────────────────────────────────────────────────────────────
    
    async def poll_status(self, job_id: str) -> JobStatus:
        """
        Poll the status of a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            JobStatus with current status
        """
        job_status = self._active_jobs.get(job_id)
        
        if not job_status:
            logger.warning(f"Job {job_id} not found in active jobs")
            return None
        
        # TODO: Actually poll via SSHManager.poll_job()
        
        return job_status
    
    async def wait_for_completion(self, job_id: str, 
                                 interval: int = 30,
                                 max_wait: int = 3600) -> JobStatus:
        """
        Wait for a job to complete.
        
        Args:
            job_id: Job identifier
            interval: Seconds between polls
            max_wait: Maximum seconds to wait
            
        Returns:
            Final JobStatus
        """
        elapsed = 0
        
        while elapsed < max_wait:
            status = await self.poll_status(job_id)
            
            if status and status.status in ["done", "failed"]:
                return status
            
            await asyncio.sleep(interval)
            elapsed += interval
            
            # Update progress
            if status:
                status.progress = min(elapsed / max_wait, 0.99)
        
        # Timeout
        if status:
            status.status = "failed"
            status.error_message = "Job timed out"
        
        return status
    
    # ───────────────────────────────────────────────────────────────
    # Result Collection
    # ───────────────────────────────────────────────────────────────
    
    async def collect_results(self, job_id: str) -> list[str]:
        """
        Collect result files from a completed job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            List of result file paths
        """
        job_status = self._active_jobs.get(job_id)
        
        if not job_status:
            return []
        
        # TODO: Call SSHManager.collect_job_results()
        
        return job_status.result_files or []
    
    async def sync_dashboard(self, job_id: str, plan: ExecutionPlan = None):
        """
        Sync job status to Dashboard.
        
        Args:
            job_id: Job identifier
            plan: Associated execution plan (optional)
        """
        if not self._dashboard_sync:
            logger.debug("No dashboard sync callback configured")
            return
        
        job_status = self._active_jobs.get(job_id)
        
        try:
            await self._dashboard_sync({
                "job_id": job_id,
                "status": job_status.status if job_status else "unknown",
                "progress": job_status.progress if job_status else 0,
                "result_files": job_status.result_files if job_status else [],
                "error": job_status.error_message if job_status else None,
                "plan": plan.to_dict() if plan else None,
            })
        except Exception as e:
            logger.error(f"Dashboard sync failed: {e}")
    
    # ───────────────────────────────────────────────────────────────
    # Notifications
    # ───────────────────────────────────────────────────────────────
    
    def set_notify_callback(self, callback: Callable):
        """Set callback for job completion notifications"""
        self._notify_callback = callback
    
    async def notify_complete(self, job_id: str, user_id: str):
        """
        Send notification when job completes.
        """
        if not self._notify_callback:
            logger.debug("No notification callback configured")
            return
        
        job_status = self._active_jobs.get(job_id)
        
        try:
            await self._notify_callback({
                "job_id": job_id,
                "user_id": user_id,
                "status": job_status.status if job_status else "unknown",
                "result_files": job_status.result_files if job_status else [],
                "error": job_status.error_message if job_status else None,
            })
        except Exception as e:
            logger.error(f"Notification failed: {e}")
    
    # ───────────────────────────────────────────────────────────────
    # Job Management
    # ───────────────────────────────────────────────────────────────
    
    def get_active_jobs(self, user_id: str = None) -> list[JobStatus]:
        """Get all active jobs for a user"""
        if user_id:
            # TODO: Filter by user_id
            return list(self._active_jobs.values())
        return list(self._active_jobs.values())
    
    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Get status of a specific job"""
        return self._active_jobs.get(job_id)
    
    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.
        
        Returns:
            True if cancelled, False if not found or already done
        """
        job_status = self._active_jobs.get(job_id)
        
        if not job_status:
            return False
        
        if job_status.status in ["done", "failed"]:
            return False
        
        # TODO: Call SSHManager.cancel_job()
        
        job_status.status = "cancelled"
        job_status.finished_at = datetime.now()
        
        return True
    
    def cleanup_completed(self, max_age_hours: int = 24):
        """
        Clean up old completed jobs from memory.
        
        Args:
            max_age_hours: Remove jobs older than this
        """
        now = datetime.now()
        to_remove = []
        
        for job_id, status in self._active_jobs.items():
            if status.finished_at:
                age = (now - status.finished_at).total_seconds() / 3600
                if age > max_age_hours:
                    to_remove.append(job_id)
        
        for job_id in to_remove:
            del self._active_jobs[job_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old jobs")
    
    def __repr__(self) -> str:
        return f"<ExecutorAgent: {self.name}>"
