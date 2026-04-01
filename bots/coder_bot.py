"""
Coder Bot - Code Generation Agent
==================================

Generates executable code using LLM based on task description and plan.
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


class CoderBot(BaseBot):
    """
    Coder Bot - generates code using LLM.
    
    Responsibilities:
    - Receive task from orchestrator
    - Generate code based on task description and plan
    - Use skills as reference when available
    - Save code to state
    - Report back to orchestrator
    """
    
    def __init__(self, config: BotConfig):
        super().__init__(config)
        self.config.role = AgentRole.CODER
        self.logger.info("CoderBot initialized")
    
    def _register_default_handlers(self):
        """Register message handlers."""
        self._handlers[MessageType.SUBTASK_REQUEST] = self.handle_subtask_request
        self._handlers[MessageType.CODE_REVISION_REQUEST] = self.handle_revision_request
        self._handlers[MessageType.PING] = self.handle_ping
    
    async def handle_subtask_request(self, msg: Message) -> str:
        """Handle coding task from orchestrator."""
        self.logger.info(f"Received coding task: {msg.content[:50]}...")
        
        task_id = msg.task_id or self._extract_task_id(msg.content)
        if not task_id:
            return "❌ No task ID found."
        
        task = self.state.get_task(task_id)
        if not task:
            return f"❌ Task `{task_id}` not found."
        
        # Mark as in progress
        self.state.update_subtask(task_id, "coder", status=SubTaskStatus.IN_PROGRESS)
        
        language = msg.payload.get("language", "R") if msg.payload else "R"
        
        await self.notify_progress(task.channel_id, task_id, "Coding", "Generating code...")
        
        try:
            # Generate code
            code = await self._generate_code(
                task_description=task.description,
                plan=task.plan_text,
                skill_needed=task.skill_needed,
                language=language
            )
            
            # Save to state
            self.state.update_task(
                task_id,
                code=code,
                language=language
            )
            
            # Mark coder subtask done
            self.state.update_subtask(
                task_id, "coder",
                status=SubTaskStatus.DONE,
                output=f"Code generated ({len(code)} chars)"
            )
            
            # Notify orchestrator with code
            response = (
                f"✅ **Code Generated**\n"
                f"Task ID: `{task_id}`\n"
                f"Language: `{language}`\n"
                f"Size: {len(code)} chars\n\n"
                f"@orchestrator Code ready for review."
            )
            
            # Send code as separate message (larger content)
            await self.send_message(task.channel_id, response)
            await self.send_message(
                task.channel_id,
                f"```{'R' if language == 'R' else language}\n{code[:4000]}```"
            )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Coding failed: {e}")
            
            self.state.update_subtask(
                task_id, "coder",
                status=SubTaskStatus.FAILED,
                error=str(e)
            )
            
            return (
                f"❌ **Coding Failed**\n"
                f"Task ID: `{task_id}`\n"
                f"Error: {str(e)}\n\n"
                f"@orchestrator Please retry or cancel task."
            )
    
    async def handle_revision_request(self, msg: Message) -> str:
        """Handle code revision request (reviewer found issues)."""
        self.logger.info(f"Received revision request: {msg.content[:50]}...")
        
        task_id = msg.task_id or self._extract_task_id(msg.content)
        if not task_id:
            return "❌ No task ID found."
        
        task = self.state.get_task(task_id)
        if not task:
            return f"❌ Task `{task_id}` not found."
        
        self.state.update_subtask(task_id, "coder", status=SubTaskStatus.IN_PROGRESS)
        
        await self.notify_progress(task.channel_id, task_id, "Coding", "Fixing code issues...")
        
        try:
            # Extract issues from message
            issues = self._extract_issues(msg.content)
            
            # Generate fixed code
            code = await self._generate_code(
                task_description=task.description,
                plan=task.plan_text,
                skill_needed=task.skill_needed,
                language=task.language or "R",
                previous_code=task.code,
                issues=issues
            )
            
            # Save to state
            self.state.update_task(task_id, code=code, review_issues=[])
            
            self.state.update_subtask(
                task_id, "coder",
                status=SubTaskStatus.DONE,
                output=f"Code fixed ({len(code)} chars)"
            )
            
            response = (
                f"✅ **Code Fixed**\n"
                f"Task ID: `{task_id}`\n\n"
                f"@orchestrator Code revised, ready for re-review."
            )
            
            await self.send_message(task.channel_id, response)
            await self.send_message(
                task.channel_id,
                f"```{'R' if task.language == 'R' else task.language}\n{code[:4000]}```"
            )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Code revision failed: {e}")
            
            self.state.update_subtask(
                task_id, "coder",
                status=SubTaskStatus.FAILED,
                error=str(e)
            )
            
            return f"❌ Revision failed: {str(e)}"
    
    async def handle_ping(self, msg: Message) -> str:
        """Handle ping."""
        return f"pong | coder | {self.config.user_id}"
    
    async def _generate_code(
        self,
        task_description: str,
        plan: str = None,
        skill_needed: str = None,
        language: str = "R",
        previous_code: str = None,
        issues: list = None
    ) -> str:
        """Generate code using LLM."""
        
        prompt_parts = [f"Generate {language} code for this bioinformatics task:\n\n{task_description}\n"]
        
        if plan:
            prompt_parts.append(f"\nExecution Plan:\n{plan}")
        
        if skill_needed and skill_needed != "none":
            prompt_parts.append(f"\nUse skill: {skill_needed}")
        
        if previous_code:
            prompt_parts.append(f"\n\nPrevious code had issues:\n{previous_code}")
            if issues:
                prompt_parts.append("\nIssues to fix:")
                for issue in issues:
                    prompt_parts.append(f"- {issue}")
        
        prompt_parts.append(f"\n\nRequirements:\n")
        prompt_parts.append("1. Complete, runnable code\n")
        prompt_parts.append("2. Include comments\n")
        prompt_parts.append("3. Handle errors gracefully\n")
        prompt_parts.append("4. Output results to files\n")
        
        prompt = "".join(prompt_parts)
        
        response = await self.call_llm(prompt)
        
        if not response:
            raise Exception("LLM returned empty response")
        
        # Extract code from response
        code = self.extract_first_code_block(response)
        
        if not code or len(code) < 50:
            raise Exception("Generated code too short or invalid")
        
        return code
    
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
    
    def _extract_issues(self, content: str) -> list:
        """Extract review issues from message."""
        issues = []
        
        # Look for bullet points
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('*'):
                issues.append(line[1:].strip())
            elif '[error]' in line.lower() or '[warning]' in line.lower():
                issues.append(line)
        
        return issues


def create_coder_bot() -> CoderBot:
    """Create coder bot from config."""
    config = BotConfig(
        name="CellClaw-Coder",
        role=AgentRole.CODER,
        token=os.getenv("CELLCRAW_CODER_TOKEN", "")
    )
    return CoderBot(config)
