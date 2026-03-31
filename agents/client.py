"""
Multi-Agent Client - Integration with Core Agent
================================================

This module provides the client interface for the Multi-Agent system
that can be used by core/agent.py when MULTI_AGENT_ENABLED=true.
"""

import os
import asyncio
import logging
from typing import Optional, Callable

from agents import OrchestratorAgent

logger = logging.getLogger(__name__)


class MultiAgentClient:
    """
    Client for the Multi-Agent system.
    
    Integrates with core/agent.py to provide:
    - Task planning and decomposition (via Orchestrator)
    - Code generation with skill templates
    - Code review before execution
    - Job execution and monitoring (via Executor)
    - INDEPENDENT notifications to user (via Executor)
    
    Usage:
        client = MultiAgentClient(ssh_manager=existing_ssh_manager)
        
        # Set notification callback (for Discord)
        client.set_notify_callback(discord_send_function)
        
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
        """Initialize Orchestrator Agent"""
        try:
            # Initialize Orchestrator (which includes all agents internally)
            self.orchestrator = OrchestratorAgent()

            # Connect SSH to executor
            if self._ssh and hasattr(self.orchestrator.executor, '_ssh'):
                self.orchestrator.executor._ssh = self._ssh
            
            # Also give orchestrator access to SSH manager for context
            self.orchestrator.set_ssh_manager(self._ssh)

            logger.info("Multi-Agent client initialized")
            logger.info(f"  Orchestrator: {self.orchestrator}")

        except Exception as e:
            logger.error(f"Failed to initialize agents: {e}")
            self._enabled = False

    def set_notify_callback(self, callback: Callable):
        """
        Set callback for user notifications.
        Executor will call this to send notifications to user.
        
        Args:
            callback: Function(event_dict) that sends to Discord/user
        """
        if hasattr(self, 'orchestrator'):
            self.orchestrator.set_notify_callback(callback)

    @property
    def enabled(self) -> bool:
        """Check if multi-agent is enabled"""
        return self._enabled

    async def process(self, message: str, user_id: str, channel_id: str = None) -> dict:
        """
        Process a task through the Multi-Agent system.
        User talks to Orchestrator, Executor notifies independently.
        
        Args:
            message: User's message/task description
            user_id: Discord user ID
            channel_id: Discord channel ID
            
        Returns:
            dict with:
                - text: Response text
                - job_id: If a job was submitted
                - skill_used: Which skill was used
                - status: "submitted", "planned", "error", "disabled"
        """
        if not self._enabled:
            return {
                "text": "Multi-Agent system is disabled",
                "status": "disabled"
            }

        try:
            # Orchestrator handles everything
            # Executor notifies user INDEPENDENTLY via callback
            response_text = await self.orchestrator.process(
                message=message,
                user_id=user_id,
                channel_id=channel_id
            )

            return {
                "text": response_text,
                "status": "processed"
            }

        except Exception as e:
            logger.error(f"[MultiAgent] Error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "text": f"❌ Multi-Agent 处理失败:\n{e}",
                "status": "error"
            }

    def get_status(self) -> dict:
        """Get multi-agent system status"""
        if not self._enabled or not hasattr(self, 'orchestrator'):
            return {"enabled": False}

        return {
            "enabled": True,
            "orchestrator": str(self.orchestrator),
            "ssh_connected": self._ssh is not None,
            "active_jobs": len(self.orchestrator.executor._active_jobs)
        }
