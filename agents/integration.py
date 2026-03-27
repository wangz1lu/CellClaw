"""
Integration Layer - Connect Multi-Agent with Existing System
========================================================

Bridges the new multi-agent system with existing:
- SSHManager
- Discord bot
- Dashboard
"""

from __future__ import annotations
import os
import logging
from typing import Optional, Callable
from dataclasses import dataclass

from agents import (
    BaseAgent, OrchestratorAgent, PlannerAgent,
    CoderAgent, ReviewerAgent, ExecutorAgent,
    ExecutionPlan, TaskStep, TaskStatus, PlanStatus
)
from agents.models import ServerInfo

logger = logging.getLogger(__name__)


@dataclass
class IntegrationConfig:
    """Configuration for integration layer"""
    ssh_manager = None  # Will be set from existing system
    discord_channel = None
    dashboard_sync_url = "http://127.0.0.1:19766"
    notify_callback = None


class MultiAgentSystem:
    """
    Complete multi-agent system integrated with existing infrastructure.
    
    This class wires together:
    - OrchestratorAgent (coordination)
    - BaseAgent (context management)
    - PlannerAgent (task planning)
    - CoderAgent (code generation)
    - ReviewerAgent (code review)
    - ExecutorAgent (execution monitoring)
    
    With:
    - SSHManager (job submission)
    - Discord (notifications)
    - Dashboard (status sync)
    """
    
    def __init__(self, config: IntegrationConfig = None):
        self.config = config or IntegrationConfig()
        
        # Initialize all agents
        self.base = BaseAgent()
        self.planner = PlannerAgent()
        self.coder = CoderAgent()
        self.reviewer = ReviewerAgent()
        self.executor = ExecutorAgent()
        self.orchestrator = OrchestratorAgent()
        
        # Wire up executor callbacks
        self.executor._dashboard_sync = self._sync_dashboard
        self.executor._notify_callback = self._notify_user
        
        # Connect to existing SSHManager
        self._ssh = None
        
        logger.info("MultiAgentSystem initialized")
    
    # ───────────────────────────────────────────────────────────────
    # SSHManager Connection
    # ───────────────────────────────────────────────────────────────
    
    def set_ssh_manager(self, ssh_manager):
        """Connect to existing SSHManager"""
        self._ssh = ssh_manager
        logger.info("Connected to SSHManager")
    
    # ───────────────────────────────────────────────────────────────
    # Main Processing
    # ───────────────────────────────────────────────────────────────
    
    async def process(self, message: str, user_id: str) -> str:
        """
        Process a user message through the multi-agent system.
        
        Returns:
            str: Response to send to user
        """
        logger.info(f"Processing message for user {user_id}: {message[:50]}...")
        
        # Step 1: Understand intent
        intent = await self.planner.understand(message, user_id)
        
        if intent.is_simple:
            return await self._process_simple(message, user_id, intent)
        else:
            return await self._process_complex(message, user_id, intent)
    
    async def _process_simple(self, message: str, user_id: str, intent) -> str:
        """Handle simple tasks (queries, etc.)"""
        # For simple tasks, use existing dispatcher
        # TODO: Wire up to existing command dispatcher
        
        return f"简单任务: {intent.intent_type}\n请使用 /{intent.intent_type} 命令"
    
    async def _process_complex(self, message: str, user_id: str, intent) -> str:
        """Handle complex tasks (analysis, visualization)"""
        # Step 1: Create plan
        plan = self.planner.create_plan(message, user_id, intent)
        
        # Step 2: Generate code
        task_step = plan.steps[1] if len(plan.steps) > 1 else plan.steps[0]  # Code gen step
        code_result = await self.coder.generate(
            task_description=task_step.description,
            skill_id=intent.skill_needed,
            language="R"
        )
        
        # Step 3: Review code
        review_result = await self.reviewer.check(code_result.code, code_result.language)
        
        if not review_result.can_execute:
            issues = [f"- {i.category}: {i.message}" for i in review_result.issues]
            return f"❌ 代码审查未通过:\n" + "\n".join(issues)
        
        # Step 4: Save script
        script_path = await self.coder.save_script(
            code=code_result.code,
            language=code_result.language
        )
        
        # Step 5: Submit job
        job_id = await self._submit_job(script_path, user_id, plan.original_task)
        
        # Step 6: Return submission confirmation
        skill_info = f"📌 使用 Skill: {intent.skill_needed}\n" if intent.skill_needed else ""
        
        return (
            f"✅ 任务已提交后台运行\n"
            f"{skill_info}"
            f"任务 PID: {job_id}\n"
            f"描述: {plan.original_task}\n"
            f"代码审查: ✅ 通过\n"
            f"查看进度: /job status {job_id}\n"
            f"查看日志: /job log {job_id}\n"
        )
    
    # ───────────────────────────────────────────────────────────────
    # Job Management
    # ───────────────────────────────────────────────────────────────
    
    async def _submit_job(self, script_path: str, user_id: str, description: str) -> str:
        """Submit job via SSHManager"""
        if not self._ssh:
            return "no_ssh_manager"
        
        try:
            # Determine run command
            if script_path.endswith(".R"):
                run_cmd = f"Rscript {script_path}"
            elif script_path.endswith(".py"):
                run_cmd = f"python {script_path}"
            else:
                run_cmd = f"bash {script_path}"
            
            # Get workdir from base agent
            workdir = self.base.get_workdir(user_id)
            
            # Submit via SSHManager
            job = await self._ssh.submit_background(
                discord_user_id=user_id,
                run_cmd=run_cmd,
                description=description,
                workdir=workdir
            )
            
            # Start polling
            channel_id = self._get_channel_id(user_id)
            if channel_id:
                self.executor._start_polling = self._create_polling_wrapper(job.job_id, user_id, channel_id)
            
            return job.job_id
            
        except Exception as e:
            logger.error(f"Job submission failed: {e}")
            return f"error: {e}"
    
    def _create_polling_wrapper(self, job_id: str, user_id: str, channel_id: str):
        """Create a polling wrapper for the executor"""
        # TODO: Implement proper polling
        async def poll_wrapper():
            pass
        return poll_wrapper
    
    # ───────────────────────────────────────────────────────────────
    # Dashboard Sync
    # ───────────────────────────────────────────────────────────────
    
    async def _sync_dashboard(self, data: dict):
        """Sync status to Dashboard"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.config.dashboard_sync_url}/api/jobs",
                    json=data
                )
        except Exception as e:
            logger.warning(f"Dashboard sync failed: {e}")
    
    # ───────────────────────────────────────────────────────────────
    # Notifications
    # ───────────────────────────────────────────────────────────────
    
    async def _notify_user(self, data: dict):
        """Send notification to user via Discord"""
        # TODO: Wire up to Discord channel
        logger.info(f"Notifying user {data.get('user_id')}: {data}")
    
    def _get_channel_id(self, user_id: str) -> Optional[str]:
        """Get Discord channel ID for user"""
        # TODO: Look up from session/channel registry
        return None
    
    # ───────────────────────────────────────────────────────────────
    # Status
    # ───────────────────────────────────────────────────────────────
    
    def get_status(self) -> dict:
        """Get system status"""
        return {
            "agents": {
                "base": str(self.base),
                "planner": str(self.planner),
                "coder": str(self.coder),
                "reviewer": str(self.reviewer),
                "executor": str(self.executor),
                "orchestrator": str(self.orchestrator),
            },
            "ssh_connected": self._ssh is not None,
            "active_jobs": len(self.executor._active_jobs),
        }


# ─────────────────────────────────────────────────────────────────
# Backward Compatibility
# ─────────────────────────────────────────────────────────────────

def create_multi_agent_system() -> MultiAgentSystem:
    """Factory function to create multi-agent system"""
    return MultiAgentSystem()
