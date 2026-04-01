"""
Orchestrator Bot - Main Task Coordinator
==========================================

Receives tasks from leader, dispatches to sub-agents, monitors progress.
"""

from __future__ import annotations
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

from bots.base import BaseBot, BotConfig
from shared.protocol import (
    MessageType, Message, AgentRole,
    format_task_request, format_subtask_request,
    SubTask, SubTaskStatus
)
from shared.state_manager import StateManager, TaskState, TaskStatus


class OrchestratorBot(BaseBot):
    """
    Orchestrator Bot - coordinates the multi-agent workflow.
    
    Responsibilities:
    - Receive tasks from leader (@orchestrator)
    - Create task state
    - Dispatch subtasks to planner, coder, reviewer, executor
    - Monitor progress
    - Report completion/failure to leader
    """
    
    def __init__(self, config: BotConfig):
        super().__init__(config)
        
        # Role is always orchestrator
        self.config.role = AgentRole.ORCHESTRATOR
        
        self.logger.info("OrchestratorBot initialized")
    
    def _register_default_handlers(self):
        """Register message handlers."""
        self._handlers[MessageType.TASK_REQUEST] = self.handle_task_request
        self._handlers[MessageType.SUBTASK_RESPONSE] = self.handle_subtask_response
        self._handlers[MessageType.CODE_REVIEW_RESPONSE] = self.handle_review_response
        self._handlers[MessageType.EXECUTE_RESPONSE] = self.handle_execute_response
        self._handlers[MessageType.NOTIFY_COMPLETED] = self.handle_completed
        self._handlers[MessageType.NOTIFY_FAILED] = self.handle_failed
        self._handlers[MessageType.NOTIFY_PROGRESS] = self.handle_progress
        self._handlers[MessageType.PING] = self.handle_ping
    
    # ─────────────────────────────────────────────────────────────
    # Message Handlers
    # ─────────────────────────────────────────────────────────────
    
    async def handle_task_request(self, msg: Message) -> str:
        """Handle new task from leader."""
        self.logger.info(f"New task request: {msg.content[:50]}...")
        
        # Check if this is a direct task or confirmation
        if "确认" in msg.content or "继续" in msg.content:
            # User confirmed a pending task
            return await self.handle_confirmation(msg)
        
        # Create new task
        task = self.state.create_task(
            leader_id=msg.sender,
            channel_id=msg.channel_id,
            description=msg.content
        )
        
        # Save task_id to message for context
        task_id = task.task_id
        
        # Notify leader task received
        response = (
            f"✅ Task received!\n"
            f"Task ID: `{task_id}`\n"
            f"Description: {msg.content}\n\n"
            f"Starting workflow..."
        )
        
        # Start workflow: dispatch to planner
        await self.dispatch_to_planner(task)
        
        return response
    
    async def handle_confirmation(self, msg: Message) -> str:
        """Handle user confirmation for pending task."""
        # Find pending task for this user
        tasks = self.state.list_tasks(leader_id=msg.sender)
        pending = [t for t in tasks if t.status == TaskStatus.PENDING]
        
        if not pending:
            return "No pending task to confirm."
        
        task = pending[-1]  # Most recent
        await self.dispatch_to_planner(task)
        return f"Confirmed! Starting task `{task.task_id}` workflow..."
    
    async def handle_subtask_response(self, msg: Message) -> str:
        """Handle responses from sub-agents."""
        self.logger.info(f"Subtask response from {msg.sender_name}: {msg.content[:50]}...")
        
        # Find task
        task_id = msg.task_id or self._extract_task_id_from_content(msg.content)
        if not task_id:
            return "No task ID found in response."
        
        task = self.state.get_task(task_id)
        if not task:
            return f"Task `{task_id}` not found."
        
        # Update the appropriate subtask based on sender
        # This is simplified - in production would track which bot responded
        return "Acknowledged."
    
    async def handle_review_response(self, msg: Message) -> str:
        """Handle code review response."""
        task_id = msg.task_id or self._extract_task_id_from_content(msg.content)
        if not task_id:
            return "No task ID found."
        
        if "通过" in msg.content or "✓" in msg.content:
            # Code approved - proceed to executor
            task = self.state.get_task(task_id)
            if task:
                await self.dispatch_to_executor(task)
                return f"Code approved! Task `{task_id}` sent to executor."
        
        if "需要修改" in msg.content or "修改" in msg.content:
            # Need revision - send back to coder
            task = self.state.get_task(task_id)
            if task:
                await self.dispatch_to_coder(task, needs_revision=True)
                return f"Code needs revision. Task `{task_id}` sent back to coder."
        
        return "Review response noted."
    
    async def handle_execute_response(self, msg: Message) -> str:
        """Handle execution response."""
        task_id = msg.task_id or self._extract_task_id_from_content(msg.content)
        
        if "完成" in msg.content or "completed" in msg.content.lower():
            self.logger.info(f"Task {task_id} execution completed")
        
        return "Execution response noted."
    
    async def handle_completed(self, msg: Message) -> str:
        """Handle task completion notification."""
        task_id = msg.task_id or self._extract_task_id_from_content(msg.content)
        self.logger.info(f"Task {task_id} completed")
        
        # Update state
        if task_id:
            self.state.update_task(task_id, status=TaskStatus.DONE)
        
        return f"✅ Task `{task_id}` completed successfully!"
    
    async def handle_failed(self, msg: Message) -> str:
        """Handle task failure notification."""
        task_id = msg.task_id or self._extract_task_id_from_content(msg.content)
        self.logger.error(f"Task {task_id} failed")
        
        # Update state
        if task_id:
            error = self._extract_error_from_content(msg.content)
            self.state.update_task(task_id, status=TaskStatus.FAILED, error_message=error)
        
        return f"❌ Task `{task_id}` failed. Check logs for details."
    
    async def handle_progress(self, msg: Message) -> str:
        """Handle progress update."""
        # Just log it
        self.logger.info(f"Progress: {msg.content[:100]}...")
        return None  # Don't respond to progress updates
    
    async def handle_ping(self, msg: Message) -> str:
        """Handle ping."""
        return f"pong | orchestrator | {self.config.user_id}"
    
    # ─────────────────────────────────────────────────────────────
    # Workflow Dispatch
    # ─────────────────────────────────────────────────────────────
    
    async def dispatch_to_planner(self, task: TaskState):
        """Start workflow by dispatching to planner."""
        self.logger.info(f"Dispatching task {task.task_id} to planner")
        
        # Update task status
        self.state.update_task(task.task_id, status=TaskStatus.PLANNING)
        self.state.update_subtask(task.task_id, "planner", status=SubTaskStatus.IN_PROGRESS)
        
        # Dispatch to planner
        await self.notify_agent(
            channel_id=task.channel_id,
            agent_role=AgentRole.PLANNER,
            task_id=task.task_id,
            instruction=f"Create an execution plan for the following task:\n\n{task.description}",
            payload={
                "skill_needed": task.skill_needed or "none",
                "leader_id": task.leader_id
            }
        )
    
    async def dispatch_to_coder(self, task: TaskState, needs_revision: bool = False):
        """Dispatch to coder."""
        self.logger.info(f"Dispatching task {task.task_id} to coder (revision={needs_revision})")
        
        # Update subtask status
        self.state.update_subtask(task.task_id, "coder", status=SubTaskStatus.IN_PROGRESS)
        if needs_revision:
            self.state.update_task(task.task_id, status=TaskStatus.REVISING)
        else:
            self.state.update_task(task.task_id, status=TaskStatus.CODING)
        
        # Build instruction
        instruction = f"Generate code for task:\n\n{task.description}\n\n"
        
        if task.plan_text:
            instruction += f"Plan:\n{task.plan_text}\n\n"
        
        if task.skill_needed:
            instruction += f"Use skill: {task.skill_needed}\n"
        
        if needs_revision:
            instruction += f"\nIMPORTANT: Previous code had issues. Please fix and regenerate.\n"
            if task.review_issues:
                instruction += f"\nReview issues:\n" + "\n".join([f"- {i}" for i in task.review_issues])
        
        await self.notify_agent(
            channel_id=task.channel_id,
            agent_role=AgentRole.CODER,
            task_id=task.task_id,
            instruction=instruction,
            payload={
                "skill_needed": task.skill_needed or "none",
                "language": "R"  # Default, can be auto-detected
            }
        )
    
    async def dispatch_to_reviewer(self, task: TaskState):
        """Dispatch to reviewer."""
        self.logger.info(f"Dispatching task {task.task_id} to reviewer")
        
        self.state.update_subtask(task.task_id, "reviewer", status=SubTaskStatus.IN_PROGRESS)
        self.state.update_task(task.task_id, status=TaskStatus.REVIEWING)
        
        await self.notify_agent(
            channel_id=task.channel_id,
            agent_role=AgentRole.REVIEWER,
            task_id=task.task_id,
            instruction=f"Review the generated code for task:\n\n{task.description}",
            payload={
                "code": task.code or "",
                "language": task.language or "R"
            }
        )
    
    async def dispatch_to_executor(self, task: TaskState):
        """Dispatch to executor."""
        self.logger.info(f"Dispatching task {task.task_id} to executor")
        
        self.state.update_subtask(task.task_id, "executor", status=SubTaskStatus.IN_PROGRESS)
        self.state.update_task(task.task_id, status=TaskStatus.EXECUTING)
        
        await self.notify_agent(
            channel_id=task.channel_id,
            agent_role=AgentRole.EXECUTOR,
            task_id=task.task_id,
            instruction=f"Execute the approved code for task:\n\n{task.description}",
            payload={
                "script_path": task.script_path or "",
                "code": task.code or "",
                "language": task.language or "R"
            }
        )
    
    # ─────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────
    
    def _extract_task_id_from_content(self, content: str) -> Optional[str]:
        """Extract task ID from message content."""
        patterns = [
            r'task[_\s]?id:?\s*`?([a-zA-Z0-9]+)`?',
            r'\[task:([^\]]+)\]',
            r'#([a-zA-Z0-9]{8,})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_error_from_content(self, content: str) -> str:
        """Extract error message from content."""
        # Look for common error patterns
        patterns = [
            r'error[:\s]+(.+)',
            r'failed[:\s]+(.+)',
            r'exception[:\s]+(.+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return "Unknown error"


def create_orchestrator_bot() -> OrchestratorBot:
    """Create orchestrator bot from config."""
    config = BotConfig(
        name="CellClaw-Orchestrator",
        role=AgentRole.ORCHESTRATOR,
        token=os.getenv("CELLCRAW_ORCHESTRATOR_TOKEN") or os.getenv("DISCORD_TOKEN", "")
    )
    return OrchestratorBot(config)


# Import os for env vars
import os
