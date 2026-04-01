"""
Reviewer Bot - Code Review Agent
================================

Reviews generated code for syntax errors, logic issues, and best practices.
"""

from __future__ import annotations
import asyncio
import logging
import os
import re
from typing import Optional, List

from bots.base import BaseBot, BotConfig
from shared.protocol import MessageType, Message, AgentRole, SubTaskStatus
from shared.state_manager import StateManager


class ReviewerBot(BaseBot):
    """
    Reviewer Bot - reviews code using LLM.
    
    Responsibilities:
    - Receive code from orchestrator
    - Review for syntax, logic, best practices
    - Request revisions if needed
    - Approve if code is good
    """
    
    def __init__(self, config: BotConfig):
        super().__init__(config)
        self.config.role = AgentRole.REVIEWER
        self.logger.info("ReviewerBot initialized")
    
    def _register_default_handlers(self):
        """Register message handlers."""
        self._handlers[MessageType.SUBTASK_REQUEST] = self.handle_review_request
        self._handlers[MessageType.CODE_REVIEW_REQUEST] = self.handle_review_request
        self._handlers[MessageType.PING] = self.handle_ping
    
    async def handle_review_request(self, msg: Message) -> str:
        """Handle code review request."""
        self.logger.info(f"Received review request: {msg.content[:50]}...")
        
        task_id = msg.task_id or self._extract_task_id(msg.content)
        if not task_id:
            return "❌ No task ID found."
        
        task = self.state.get_task(task_id)
        if not task:
            return f"❌ Task `{task_id}` not found."
        
        self.state.update_subtask(task_id, "reviewer", status=SubTaskStatus.IN_PROGRESS)
        
        await self.notify_progress(task.channel_id, task_id, "Reviewing", "Checking code...")
        
        try:
            # Get code from payload or state
            code = None
            if msg.payload and msg.payload.get("code"):
                code = msg.payload["code"]
            elif task.code:
                code = task.code
            
            if not code:
                return "❌ No code found to review."
            
            language = msg.payload.get("language", "R") if msg.payload else (task.language or "R")
            
            # Review code
            issues = await self._review_code(code, language)
            
            if not issues:
                # Code is good!
                self.state.update_subtask(
                    task_id, "reviewer",
                    status=SubTaskStatus.DONE,
                    output="Code approved"
                )
                
                response = (
                    f"✅ **Code Review Passed**\n"
                    f"Task ID: `{task_id}`\n"
                    f"Language: `{language}`\n\n"
                    f"@orchestrator Code approved. Ready for execution."
                )
                
                await self.send_message(task.channel_id, response)
                return None
            
            else:
                # Code has issues
                issues_text = "\n".join([f"- [{i['severity']}] {i['message']}" for i in issues])
                
                self.state.update_task(task_id, review_issues=[i['message'] for i in issues])
                
                response = (
                    f"🔍 **Code Review - Issues Found**\n"
                    f"Task ID: `{task_id}`\n\n"
                    f"**Issues**:\n{issues_text}\n\n"
                    f"@orchestrator Please send back to coder for fixes."
                )
                
                await self.send_message(task.channel_id, response)
                return None
                
        except Exception as e:
            self.logger.error(f"Review failed: {e}")
            
            self.state.update_subtask(
                task_id, "reviewer",
                status=SubTaskStatus.FAILED,
                error=str(e)
            )
            
            return f"❌ Review failed: {str(e)}"
    
    async def handle_ping(self, msg: Message) -> str:
        """Handle ping."""
        return f"pong | reviewer | {self.config.user_id}"
    
    async def _review_code(self, code: str, language: str) -> List[dict]:
        """Review code using LLM."""
        
        prompt = f"""Review the following {language} code for:

1. Syntax errors
2. Logic errors
3. Best practices
4. Potential bugs
5. Security issues

Code:
```{language}
{code[:3000]}
```

Return issues as JSON array:
[
    {{
        "category": "syntax|logic|best_practice|bug|security",
        "severity": "error|warning|info",
        "message": "Issue description",
        "line_estimate": "Line number if visible"
    }}
]

If code is good, return empty array [].
Only return JSON.
"""
        
        response = await self.call_llm(prompt)
        
        if not response:
            return []
        
        # Parse JSON
        try:
            import json
            # Try to find JSON array in response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                issues = json.loads(json_match.group(0))
                return issues if isinstance(issues, list) else []
        except Exception as e:
            self.logger.warning(f"Failed to parse issues JSON: {e}")
        
        return []
    
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


def create_reviewer_bot() -> ReviewerBot:
    """Create reviewer bot from config."""
    config = BotConfig(
        name="CellClaw-Reviewer",
        role=AgentRole.REVIEWER,
        token=os.getenv("CELLCRAW_REVIEWER_TOKEN", "")
    )
    return ReviewerBot(config)
