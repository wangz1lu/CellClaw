"""
Planner Bot - Task Planning Agent
==================================

Creates execution plans for tasks using LLM.
"""

from __future__ import annotations
import asyncio
import logging
import os
import re
from typing import Optional

from bots.base import BaseBot, BotConfig
from shared.protocol import MessageType, Message, AgentRole, SubTaskStatus
from shared.state_manager import StateManager


class PlannerBot(BaseBot):
    """
    Planner Bot - generates execution plans.
    
    Responsibilities:
    - Receive task from orchestrator
    - Analyze task requirements
    - Generate step-by-step plan
    - Use LLM for intelligent planning
    - Save plan to workdir
    - Report back to orchestrator
    """
    
    def __init__(self, config: BotConfig):
        super().__init__(config)
        self.config.role = AgentRole.PLANNER
        self.logger.info("PlannerBot initialized")
    
    def _register_default_handlers(self):
        """Register message handlers."""
        self._handlers[MessageType.SUBTASK_REQUEST] = self.handle_subtask_request
        self._handlers[MessageType.PING] = self.handle_ping
    
    async def handle_subtask_request(self, msg: Message) -> str:
        """Handle planning task from orchestrator."""
        self.logger.info(f"Received planning task: {msg.content[:50]}...")
        
        # Extract task info
        task_id = msg.task_id or self._extract_task_id(msg.content)
        if not task_id:
            return "❌ No task ID found."
        
        task = self.state.get_task(task_id)
        if not task:
            return f"❌ Task `{task_id}` not found."
        
        # Mark as in progress
        self.state.update_subtask(task_id, "planner", status=SubTaskStatus.IN_PROGRESS)
        
        # Notify progress
        await self.notify_progress(task.channel_id, task_id, "Planning", "Analyzing task...")
        
        try:
            # Generate plan using LLM
            plan_text = await self._generate_plan(task.description, task.skill_needed)
            
            # Save plan to state
            self.state.update_task(
                task_id,
                plan_text=plan_text,
                status="planning_done"  # Custom status
            )
            
            # Mark planner subtask done
            self.state.update_subtask(
                task_id, "planner",
                status=SubTaskStatus.DONE,
                output=plan_text
            )
            
            # Notify orchestrator
            response = (
                f"✅ **Plan Completed**\n"
                f"Task ID: `{task_id}`\n\n"
                f"**Plan**:\n{plan_text}\n\n"
                f"@orchestrator Plan ready. Please dispatch to coder."
            )
            
            await self.send_message(task.channel_id, response)
            return None
            
        except Exception as e:
            self.logger.error(f"Planning failed: {e}")
            
            self.state.update_subtask(
                task_id, "planner",
                status=SubTaskStatus.FAILED,
                error=str(e)
            )
            
            return (
                f"❌ **Planning Failed**\n"
                f"Task ID: `{task_id}`\n"
                f"Error: {str(e)}\n\n"
                f"@orchestrator Please retry or cancel task."
            )
    
    async def handle_ping(self, msg: Message) -> str:
        """Handle ping."""
        return f"pong | planner | {self.config.user_id}"
    
    async def _generate_plan(self, task_description: str, skill_needed: str = None) -> str:
        """Generate execution plan using LLM."""
        
        # Available skills for reference
        skills_info = ""
        if skill_needed:
            skills_info = f"Required skill: {skill_needed}\n"
        
        prompt = f"""Create a detailed execution plan for this bioinformatics task.

Task: {task_description}

{skills_info}

Generate a step-by-step plan with:
1. Each step numbered
2. Brief description of what to do
3. Estimated time for each step

Format:
```
1. [Step name] - [Description] (Est: X min)
2. ...
```

Keep the plan practical and actionable.
"""
        
        response = await self.call_llm(prompt)
        
        if not response:
            # Fallback simple plan
            return (
                "1. Load data - Load input data files (Est: 1 min)\n"
                "2. Process data - Run analysis (Est: 5 min)\n"
                "3. Output results - Save results (Est: 1 min)"
            )
        
        # Clean up response - extract just the plan
        lines = response.strip().split('\n')
        plan_lines = []
        for line in lines:
            if line.strip() and (line[0].isdigit() or line.startswith('-') or line.startswith('•')):
                plan_lines.append(line.strip())
        
        if plan_lines:
            return '\n'.join(plan_lines)
        
        return response
    
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


def create_planner_bot() -> PlannerBot:
    """Create planner bot from config."""
    config = BotConfig(
        name="CellClaw-Planner",
        role=AgentRole.PLANNER,
        token=os.getenv("CELLCRAW_PLANNER_TOKEN", "")
    )
    return PlannerBot(config)
