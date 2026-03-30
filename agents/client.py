"""
Multi-Agent Client - Integration with Core Agent
================================================

This module provides the client interface for the Multi-Agent system
that can be used by core/agent.py when MULTI_AGENT_ENABLED=true.
"""

import os
import asyncio
import logging
from typing import Optional

from agents import (
    MultiAgentSystem,
    PlannerAgent,
    CoderAgent,
    ReviewerAgent,
    ExecutorAgent,
    ExecutionPlan,
    TaskStatus
)

logger = logging.getLogger(__name__)


class MultiAgentClient:
    """
    Client for the Multi-Agent system.
    
    Integrates with core/agent.py to provide:
    - Task planning and decomposition
    - Code generation with skill templates
    - Code review before execution
    - Job execution and monitoring
    
    Usage:
        client = MultiAgentClient(ssh_manager=existing_ssh_manager)
        
        # Process a task
        response = await client.process(
            message="帮我做个DEG分析",
            user_id="12345",
            channel_id="67890"
        )
    """
    
    def __init__(self, ssh_manager=None):
        """
        Initialize Multi-Agent Client.
        
        Args:
            ssh_manager: Existing SSHManager instance for job submission
        """
        self._enabled = os.getenv("MULTI_AGENT_ENABLED", "false").lower() == "true"
        self._ssh = ssh_manager
        
        if self._enabled:
            self._init_agents()
        else:
            logger.info("Multi-Agent client disabled")
    
    def _init_agents(self):
        """Initialize all agent components"""
        try:
            # Initialize agents
            self.planner = PlannerAgent()
            self.coder = CoderAgent()
            self.reviewer = ReviewerAgent()
            self.executor = ExecutorAgent()
            
            # Connect to SSH manager
            if self._ssh:
                self.executor._ssh = self._ssh
            
            # Set notification callback
            self.executor._notify_callback = self._notify_callback
            
            logger.info("Multi-Agent client initialized with agents")
            logger.info(f"  Planner: {self.planner}")
            logger.info(f"  Coder: {self.coder}")
            logger.info(f"  Reviewer: {self.reviewer}")
            logger.info(f"  Executor: {self.executor}")
            
        except Exception as e:
            logger.error(f"Failed to initialize agents: {e}")
            self._enabled = False
    
    async def _notify_callback(self, data: dict):
        """Callback for job notifications"""
        logger.info(f"Job notification: {data}")
    
    @property
    def enabled(self) -> bool:
        """Check if multi-agent is enabled"""
        return self._enabled
    
    async def process(self, message: str, user_id: str, channel_id: str = None) -> dict:
        """
        Process a task through the multi-agent system.
        
        Args:
            message: User's message/task description
            user_id: Discord user ID
            channel_id: Discord channel ID
            
        Returns:
            dict with:
                - text: Response text
                - job_id: If a job was submitted
                - skill_used: Which skill was used
                - plan_id: Execution plan ID
                - status: "submitted", "error", "disabled"
        """
        if not self._enabled:
            return {
                "text": "Multi-Agent system is disabled",
                "status": "disabled"
            }
        
        try:
            # Step 1: Understand intent
            logger.info(f"[MultiAgent] Processing: {message[:50]}...")
            intent = await self.planner.understand(message, user_id)
            
            logger.info(f"[MultiAgent] Intent: {intent.intent_type}, skill={intent.skill_needed}, simple={intent.is_simple}")
            
            # Step 2: For simple tasks, generate and submit directly
            if intent.is_simple:
                code_result = await self.coder.generate(
                    task_description=message,
                    skill_id=intent.skill_needed,
                    language="R"
                )
                
                # Review
                review_result = await self.reviewer.check(code_result.code, code_result.language)
                
                if not review_result.can_execute:
                    issues = "\n".join([f"- {i.category}: {i.message}" for i in review_result.issues])
                    return {
                        "text": f"❌ 代码审查未通过:\n{issues}",
                        "status": "error"
                    }
                
                # Save script
                script_path = await self.coder.save_script(
                    code_result.code,
                    code_result.language
                )
                
                # Submit job
                if self._ssh:
                    job = await self._ssh.submit_background(
                        discord_user_id=user_id,
                        run_cmd=f"Rscript {script_path}" if code_result.language == "R" else f"python {script_path}",
                        description=message
                    )
                    
                    return {
                        "text": self._format_submit_response(job.job_id, message, intent.skill_needed),
                        "job_id": job.job_id,
                        "skill_used": intent.skill_needed,
                        "status": "submitted"
                    }
                else:
                    return {
                        "text": f"✅ 代码已生成:\n```r\n{code_result.code[:500]}...\n```",
                        "skill_used": intent.skill_needed,
                        "status": "generated"
                    }
            
            # Step 3: For complex tasks, create plan and execute
            plan = self.planner.create_plan(message, user_id, intent)
            
            return {
                "text": f"📋 任务计划已创建 ({len(plan.steps)} 步骤)\n" +
                       f"描述: {message}\n" +
                       f"技能: {intent.skill_needed or '通用'}",
                "plan_id": plan.plan_id,
                "skill_used": intent.skill_needed,
                "status": "planned"
            }
            
        except Exception as e:
            logger.error(f"[MultiAgent] Error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "text": f"❌ Multi-Agent 处理失败:\n{e}",
                "status": "error"
            }
    
    def _format_submit_response(self, job_id: str, description: str, skill_used: str = None) -> str:
        """Format job submission response"""
        skill_info = f"📌 已调用 Skill: {skill_used}\n" if skill_used else "📌 未调用 Skill\n"
        
        return (
            f"✅ 任务已提交后台运行\n"
            f"{skill_info}"
            f"任务 PID: `{job_id}`\n"
            f"描述: {description}\n"
            f"查看进度: /job status {job_id}\n"
            f"查看日志: /job log {job_id}\n"
            f"⏳ 任务完成后会通知你"
        )
    
    def get_status(self) -> dict:
        """Get multi-agent system status"""
        if not self._enabled:
            return {"enabled": False}
        
        return {
            "enabled": True,
            "planner": str(self.planner) if hasattr(self, 'planner') else None,
            "coder": str(self.coder) if hasattr(self, 'coder') else None,
            "reviewer": str(self.reviewer) if hasattr(self, 'reviewer') else None,
            "executor": str(self.executor) if hasattr(self, 'executor') else None,
            "ssh_connected": self._ssh is not None,
            "active_jobs": len(self.executor._active_jobs) if hasattr(self, 'executor') else 0
        }
