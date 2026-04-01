"""
Base Bot Class for Multi-Bot System
====================================

Provides common functionality for all CellClaw bots:
- Discord connection
- Message parsing
- State management
- Logging
"""

from __future__ import annotations
import asyncio
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Awaitable

import discord
from discord import Message as DiscordMessage

from shared.protocol import (
    MessageType, Message, AgentRole, 
    parse_message, format_task_request,
    format_subtask_request, format_progress_message,
    format_completion_message, format_error_message,
    SubTask
)
from shared.state_manager import StateManager, TaskState, TaskStatus, SubTaskStatus


@dataclass
class BotConfig:
    """Configuration for a bot."""
    name: str
    role: AgentRole
    token: str
    
    # Bot's Discord user ID (set after login)
    user_id: str = ""
    
    # Channel to operate in (can be overridden by messages)
    default_channel_id: Optional[str] = None
    
    # State manager
    state_dir: str = "/tmp/cellclaw_state"
    
    # Rate limiting
    message_delay: float = 1.0  # seconds between messages
    
    # LLM settings
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    
    # SSH settings (for executor)
    ssh_host: str = ""
    ssh_port: int = 50000
    ssh_user: str = ""
    ssh_workdir: str = ""


class BaseBot(discord.Client):
    """
    Base class for all CellClaw bots.
    
    Handles:
    - Discord connection and events
    - Message parsing and routing
    - State management
    - Inter-bot communication via mentions
    """
    
    def __init__(self, config: BotConfig):
        super().__init__(intents=discord.Intents.default())
        
        self.config = config
        self.logger = self._setup_logger()
        
        # State management
        self.state = StateManager(state_dir=config.state_dir)
        
        # Message handlers (override in subclasses)
        self._handlers: dict[MessageType, Callable[[Message], Awaitable[str]]] = {}
        
        # Rate limiting
        self._last_message_time = 0
        self._message_lock = asyncio.Lock()
        
        # SSH manager (lazy init)
        self._ssh_manager = None
        
        # Register default handlers
        self._register_default_handlers()
        
        self.logger.info(f"{config.name} ({config.role.value}) initialized")
    
    def _setup_logger(self) -> logging.Logger:
        """Setup logger for this bot."""
        logger = logging.getLogger(f"cellclaw.{self.config.role.value}")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter(
                f'%(asctime)s | {self.config.role.value.upper()} | %(message)s',
                datefmt='%H:%M:%S'
            ))
            logger.addHandler(handler)
        
        return logger
    
    def _register_default_handlers(self):
        """Register default message handlers."""
        # Override in subclasses to add custom handlers
        pass
    
    # ─────────────────────────────────────────────────────────────
    # Discord Events
    # ─────────────────────────────────────────────────────────────
    
    async def on_ready(self):
        """Called when bot is ready."""
        self.config.user_id = str(self.user.id)
        self.logger.info(f"Logged in as {self.user.name} ({self.user.id})")
        
        # Set status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"@{self.config.name}"
            )
        )
    
    async def on_message(self, message: DiscordMessage):
        """Called when a message is received."""
        # Ignore bots (including self)
        if message.author.bot:
            return
        
        # Check if this bot is mentioned
        mentioned = False
        for mention in message.mentions:
            if str(mention.id) == self.config.user_id:
                mentioned = True
                break
        
        # Also respond if bot name is in content (for when mentions are disabled)
        if not mentioned:
            if f"@{self.config.name}" in message.content:
                mentioned = True
        
        if not mentioned:
            return
        
        # Parse message
        parsed = parse_message(
            content=message.content,
            sender_id=str(message.author.id),
            sender_name=message.author.name,
            channel_id=str(message.channel_id),
            guild_id=str(message.guild.id) if message.guild else None
        )
        
        # Route to handler
        handler = self._handlers.get(parsed.type)
        if handler:
            response = await handler(parsed)
            if response:
                await self.send_message(message.channel, response)
        else:
            # Default: echo understanding
            await self.send_message(
                message.channel,
                f"📝 Received: {parsed.type.value}"
            )
    
    async def on_mention(self, message: DiscordMessage):
        """Called when bot is mentioned (alternative to on_message)."""
        await self.on_message(message)
    
    # ─────────────────────────────────────────────────────────────
    # Message Sending
    # ─────────────────────────────────────────────────────────────
    
    async def send_message(self, channel, content: str, **kwargs):
        """Send a message with rate limiting."""
        async with self._message_lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_message_time
            
            if elapsed < self.config.message_delay:
                await asyncio.sleep(self.config.message_delay - elapsed)
            
            if isinstance(channel, str):
                channel = self.get_channel(int(channel))
            
            if channel:
                await channel.send(content, **kwargs)
                self._last_message_time = asyncio.get_event_loop().time()
    
    async def reply_to(self, original_message: DiscordMessage, content: str):
        """Reply to a message with rate limiting."""
        async with self._message_lock:
            await asyncio.sleep(self.config.message_delay)
            await original_message.reply(content)
            self._last_message_time = asyncio.get_event_loop().time()
    
    async def send_dm(self, user_id: str, content: str):
        """Send a DM to a user."""
        user = self.get_user(int(user_id))
        if user:
            async with self._message_lock:
                await asyncio.sleep(self.config.message_delay)
                await user.send(content)
                self._last_message_time = asyncio.get_event_loop().time()
    
    # ─────────────────────────────────────────────────────────────
    # Inter-Bot Communication
    # ─────────────────────────────────────────────────────────────
    
    async def notify_agent(
        self,
        channel_id: str,
        agent_role: AgentRole,
        task_id: str,
        instruction: str,
        payload: dict = None
    ) -> str:
        """
        Send a subtask to another agent.
        
        Returns the message sent.
        """
        subtask_id = f"{task_id}_{agent_role.value}"
        
        message = f"@{'planner' if agent_role == AgentRole.PLANNER else agent_role.value}\n\n"
        message += f"**New Subtask**\n"
        message += f"Task ID: `{task_id}`\n"
        message += f"Subtask ID: `{subtask_id}`\n\n"
        message += f"**Instruction**:\n{instruction}\n"
        
        if payload:
            message += f"\n**Payload**:\n"
            for k, v in payload.items():
                message += f"- {k}: `{v}`\n"
        
        await self.send_message(channel_id, message)
        return message
    
    async def notify_progress(
        self,
        channel_id: str,
        task_id: str,
        step: str,
        detail: str
    ):
        """Notify progress on a task."""
        message = format_progress_message(task_id, step, detail)
        await self.send_message(channel_id, message)
    
    async def notify_completion(
        self,
        channel_id: str,
        task_id: str,
        result_files: List[str],
        job_id: str = None
    ):
        """Notify task completion."""
        message = format_completion_message(task_id, result_files, job_id)
        await self.send_message(channel_id, message)
    
    async def notify_error(
        self,
        channel_id: str,
        task_id: str,
        error: str
    ):
        """Notify task failure."""
        message = format_error_message(task_id, error)
        await self.send_message(channel_id, message)
    
    # ─────────────────────────────────────────────────────────────
    # State Management Helpers
    # ─────────────────────────────────────────────────────────────
    
    def get_task(self, task_id: str) -> Optional[TaskState]:
        """Get task state."""
        return self.state.get_task(task_id)
    
    def update_task(self, task_id: str, **updates) -> Optional[TaskState]:
        """Update task fields."""
        return self.state.update_task(task_id, **updates)
    
    def update_subtask(
        self,
        task_id: str,
        subtask_key: str,
        status: SubTaskStatus = None,
        output: str = None,
        error: str = None
    ) -> Optional[TaskState]:
        """Update subtask state."""
        return self.state.update_subtask(task_id, subtask_key, status, output, error)
    
    # ─────────────────────────────────────────────────────────────
    # LLM Integration
    # ─────────────────────────────────────────────────────────────
    
    async def call_llm(self, prompt: str, system: str = None) -> Optional[str]:
        """Call LLM API."""
        import aiohttp
        
        api_key = self.config.llm_api_key or os.getenv("OMICS_LLM_API_KEY")
        base_url = self.config.llm_base_url or os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        model = self.config.llm_model or os.getenv("OMICS_LLM_MODEL", "deepseek-chat")
        
        if not api_key:
            self.logger.warning("No LLM API key configured")
            return None
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        self.logger.error(f"LLM API error: {resp.status} - {error}")
                        return None
                    
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            self.logger.error(f"LLM API error: {e}")
            return None
    
    # ─────────────────────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────────────────────
    
    def extract_code_blocks(self, content: str) -> List[str]:
        """Extract code blocks from markdown content."""
        pattern = r'```(?:\w+)?\n?(.*?)```'
        return re.findall(pattern, content, re.DOTALL)
    
    def extract_first_code_block(self, content: str) -> Optional[str]:
        """Extract first code block from content."""
        blocks = self.extract_code_blocks(content)
        return blocks[0] if blocks else None
    
    async def run(self):
        """Run the bot."""
        self.logger.info(f"Starting {self.config.name}...")
        await self.start(self.config.token)


# Helper to create a bot config from environment
def config_from_env(role: AgentRole) -> BotConfig:
    """Create BotConfig from environment variables."""
    env_prefix = f"CELLCRAW_{role.value.upper()}_"
    
    return BotConfig(
        name=os.getenv(f"{env_prefix}NAME", role.value.capitalize()),
        role=role,
        token=os.getenv(f"{env_prefix}TOKEN", os.getenv("DISCORD_TOKEN", "")),
        default_channel_id=os.getenv(f"{env_prefix}CHANNEL"),
        ssh_host=os.getenv(f"{env_prefix}SSH_HOST"),
        ssh_port=int(os.getenv(f"{env_prefix}SSH_PORT", "50000")),
        ssh_user=os.getenv(f"{env_prefix}SSH_USER"),
        ssh_workdir=os.getenv(f"{env_prefix}SSH_WORKDIR"),
    )
