"""
Wrapper to use Multi-Agent System in existing CellClaw
=====================================================

This module provides a drop-in replacement for the existing agent
that uses the multi-agent system while maintaining backward compatibility.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MultiAgentWrapper:
    """
    Wrapper that integrates multi-agent system with existing CellClaw.
    
    Usage:
        from agents.wrapper import MultiAgentWrapper
        
        wrapper = MultiAgentWrapper(ssh_manager=existing_ssh_manager)
        
        # Use instead of existing handle_message
        response = await wrapper.process(
            message="帮我做个DEG分析",
            user_id="12345",
            channel_id="67890"
        )
    """
    
    def __init__(self, ssh_manager=None, enable_multi_agent: bool = None):
        """
        Initialize the wrapper.
        
        Args:
            ssh_manager: Existing SSHManager instance
            enable_multi_agent: Force enable/disable multi-agent mode.
                               If None, uses MULTI_AGENT_ENABLED env var.
        """
        # Check if multi-agent is enabled
        if enable_multi_agent is None:
            enable_multi_agent = os.getenv("MULTI_AGENT_ENABLED", "false").lower() == "true"
        
        self._enabled = enable_multi_agent
        self._ssh = ssh_manager
        
        if self._enabled:
            self._init_multi_agent()
        else:
            logger.info("Multi-agent system disabled, using legacy mode")
    
    def _init_multi_agent(self):
        """Initialize the multi-agent system"""
        try:
            from agents import MultiAgentSystem
            self._system = MultiAgentSystem()
            
            if self._ssh:
                self._system.set_ssh_manager(self._ssh)
            
            logger.info("Multi-agent system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize multi-agent system: {e}")
            self._enabled = False
            self._system = None
    
    @property
    def enabled(self) -> bool:
        """Check if multi-agent mode is enabled"""
        return self._enabled
    
    async def process(self, message: str, user_id: str, channel_id: str = None) -> dict:
        """
        Process a message using multi-agent system.
        
        Args:
            message: User's message
            user_id: Discord user ID
            channel_id: Discord channel ID
            
        Returns:
            dict with 'text', 'figures', etc.
        """
        if not self._enabled:
            return {
                "text": "Multi-agent system is not enabled",
                "enabled": False
            }
        
        try:
            # Use multi-agent system
            response_text = await self._system.process(message, user_id)
            
            return {
                "text": response_text,
                "enabled": True,
                "system": self._system.get_status()
            }
        except Exception as e:
            logger.error(f"Multi-agent processing failed: {e}")
            return {
                "text": f"Multi-agent system error: {e}",
                "enabled": True,
                "error": str(e)
            }
    
    def get_system_status(self) -> dict:
        """Get multi-agent system status"""
        if not self._enabled or not self._system:
            return {"enabled": False}
        
        return {
            "enabled": True,
            **self._system.get_status()
        }


# ─────────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────────

def create_multi_agent_wrapper(ssh_manager=None) -> MultiAgentWrapper:
    """Factory function to create a configured wrapper"""
    return MultiAgentWrapper(ssh_manager=ssh_manager)


def is_multi_agent_enabled() -> bool:
    """Check if multi-agent mode is enabled"""
    return os.getenv("MULTI_AGENT_ENABLED", "false").lower() == "true"


def enable_multi_agent():
    """Enable multi-agent mode for this process"""
    os.environ["MULTI_AGENT_ENABLED"] = "true"


def disable_multi_agent():
    """Disable multi-agent mode for this process"""
    os.environ["MULTI_AGENT_ENABLED"] = "false"
