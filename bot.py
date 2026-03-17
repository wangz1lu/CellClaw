"""
CellClaw Discord Gateway
=========================
Connects Discord (via discord.py) to CellClawAgent.

Environment variables (or .env file):
    DISCORD_TOKEN   — Bot token
    OMICSCLAW_DATA  — Data directory (default: ./data)

Run:
    python -m cellclaw.gateway
    # or
    python gateway.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
import tempfile
from pathlib import Path
from typing import Optional

import discord
from discord.ext import tasks
from discord import app_commands

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cellclaw.gateway")

# ── Import Agent ───────────────────────────────────────────────────────────
import sys
# Always add the project root to sys.path so imports work regardless of
# how the script is invoked or what the parent directory is named.
_PROJECT_ROOT = str(Path(__file__).parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.agent import CellClawAgent, AgentResponse


# ── Configuration ──────────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
DATA_DIR      = os.environ.get("OMICSCLAW_DATA", str(Path(__file__).parent / "data"))
PROXY         = (
    os.environ.get("HTTPS_PROXY")
    or os.environ.get("https_proxy")
    or os.environ.get("HTTP_PROXY")
    or os.environ.get("http_proxy")
    or "http://127.0.0.1:7890"   # default local proxy
)

# Discord Intents
intents = discord.Intents.default()
intents.message_content = True   # Required to read message text
intents.dm_messages     = True
intents.guild_messages  = True


# ─────────────────────────────────────────────────────────────────────────────
class CellClawBot(discord.Client):
    """
    Discord client that bridges discord.py events → CellClawAgent.
    """

    def __init__(self, proxy: str = ""):
        # discord.py 2.x passes proxy/proxy_auth down to its internal HTTPClient
        kwargs = {"intents": intents}
        if proxy:
            kwargs["proxy"] = proxy
        super().__init__(**kwargs)
        self.agent = CellClawAgent(workspace_dir=DATA_DIR)
        self._download_dir = Path(tempfile.mkdtemp(prefix="cellclaw_attachments_"))
        self._dm_pending_users: set[str] = set()
        # Create command tree manually
        self.tree = app_commands.CommandTree(self)
        logger.info(f"CellClawBot created | data_dir={DATA_DIR} | proxy={proxy or 'none'}")

    async def setup_hook(self):
        # Register slash commands
        @self.tree.command(name="server", description="Server management")
        async def server_slash(interaction: discord.Interaction, action: str = "list"):
            cmd = f"/server {action}"
            result = await self.agent._dispatcher.dispatch(cmd, str(interaction.user.id), is_dm=False)
            if result:
                await interaction.response.send_message(result.text, ephemeral=True)
            else:
                await interaction.response.send_message("Use /server add/list/use/test/info/remove", ephemeral=True)

        @self.tree.command(name="env", description="Environment management")
        async def env_slash(interaction: discord.Interaction, action: str = "list"):
            cmd = f"/env {action}"
            result = await self.agent._dispatcher.dispatch(cmd, str(interaction.user.id), is_dm=False)
            if result:
                await interaction.response.send_message(result.text, ephemeral=True)
            else:
                await interaction.response.send_message("Use /env list/use/scan", ephemeral=True)

        @self.tree.command(name="job", description="Job management")
        async def job_slash(interaction: discord.Interaction, action: str = "list"):
            cmd = f"/job {action}"
            result = await self.agent._dispatcher.dispatch(cmd, str(interaction.user.id), is_dm=False)
            if result:
                await interaction.response.send_message(result.text, ephemeral=True)
            else:
                await interaction.response.send_message("Use /job list/status/log/cancel", ephemeral=True)

        @self.tree.command(name="skill", description="Skill management")
        async def skill_slash(interaction: discord.Interaction, action: str = "list"):
            cmd = f"/skill {action}"
            result = await self.agent._dispatcher.dispatch(cmd, str(interaction.user.id), is_dm=False)
            if result:
                await interaction.response.send_message(result.text, ephemeral=True)
            else:
                await interaction.response.send_message("Use /skill list/info/use/run", ephemeral=True)

        @self.tree.command(name="memory", description="Memory management")
        async def memory_slash(interaction: discord.Interaction, action: str = "show"):
            cmd = f"/memory {action}"
            result = await self.agent._dispatcher.dispatch(cmd, str(interaction.user.id), is_dm=False)
            if result:
                await interaction.response.send_message(result.text, ephemeral=True)
            else:
                await interaction.response.send_message("Use /memory show/today/clear/note", ephemeral=True)

        # Sync commands with Discord
        await self.tree.sync()
        logger.info(f"  setup_hook: bot={self.user}")
        logger.info("  Slash commands synced")

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def on_ready(self):
        logger.info(f"✅ Logged in as {self.user} (id={self.user.id})")
        logger.info(f"   Connected to {len(self.guilds)} guild(s)")
        
        # Start Dashboard API servers
        try:
            from dashboard.start import start_api
            start_api(self.agent._ssh, self.agent)
            logger.info("🚀 Dashboard API started (API: 19766)")
            logger.info("   Dashboard: python dashboard_server.py")
        except Exception as e:
            logger.warning(f"Dashboard API not available: {e}")
        
        self.poll_notifications.start()

    async def on_disconnect(self):
        logger.warning("⚠️  Discord connection lost")

    # ── Message handler ──────────────────────────────────────────────────

    async def on_message(self, message: discord.Message):
        # Ignore own messages
        if message.author == self.user:
            return

        user_id   = str(message.author.id)
        is_dm     = isinstance(message.channel, discord.DMChannel)
        channel_id = str(message.channel.id)
        content   = message.content.strip()

        # Skip empty messages that only have non-file attachments (reactions, etc.)

        # Check if bot was mentioned (for group channels)
        is_mention = self.user in message.mentions or f"<@{self.user.id}>" in content

        # For group channels (not DM), require mention
        if not is_dm and not is_mention:
            return
        if not content and not message.attachments:
            return

        logger.info(
            f"[MSG] user={message.author.name}({user_id}) "
            f"channel={channel_id} dm={is_dm} | {content[:80]!r}"
        )

        # ── Download attachments ─────────────────────────────────────────
        local_attachments: list[str] = []
        image_attachments: list[str] = []   # image files for vision model
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

        for att in message.attachments:
            dest = self._download_dir / att.filename
            try:
                await att.save(dest)
                local_attachments.append(str(dest))
                if Path(att.filename).suffix.lower() in IMAGE_EXTS:
                    image_attachments.append(str(dest))
                logger.info(f"  Downloaded attachment: {att.filename} ({att.size} bytes)")
            except Exception as e:
                logger.warning(f"  Failed to download {att.filename}: {e}")

        # ── Call Agent ───────────────────────────────────────────────────
        try:
            async with message.channel.typing():
                response: AgentResponse = await self.agent.handle_message(
                    message=content,
                    discord_user_id=user_id,
                    attachments=local_attachments if local_attachments else None,
                    images=image_attachments if image_attachments else None,
                    is_dm=is_dm,
                    channel_id=channel_id,
                )
        except Exception as e:
            logger.exception(f"Agent error: {e}")
            response = AgentResponse(text=f"❌ Internal error: {e}")

        # ── Send DM if requested ─────────────────────────────────────────
        if response.dm_user_id and response.dm_text:
            await self._send_dm(response.dm_user_id, response.dm_text)
            self._dm_pending_users.add(response.dm_user_id)

        # ── Send reply ───────────────────────────────────────────────────
        if response.text or response.figures:
            await self._send_response(message.channel, response, message)

        # ── Start job polling if a background job was submitted ──────────
        if response.job_id and response.poll_secs > 0:
            self.agent._start_polling(
                job_id=response.job_id,
                discord_user_id=user_id,
                channel_id=channel_id,
                interval=response.poll_secs,
            )
            logger.info(f"Started polling job {response.job_id} every {response.poll_secs}s → channel {channel_id}")

    # ── Response renderer ────────────────────────────────────────────────

    async def _send_response(
        self,
        channel: discord.abc.Messageable,
        response: AgentResponse,
        original_message: Optional[discord.Message] = None,
    ):
        """Render an AgentResponse to Discord."""
        text = response.text or ""
        files: list[discord.File] = []

        # Attach figures
        for fig_path in response.figures:
            p = Path(fig_path)
            if p.exists():
                files.append(discord.File(str(p), filename=p.name))
            else:
                logger.warning(f"Figure not found: {fig_path}")

        # Discord message limit is 2000 chars; split if needed
        chunks = _split_message(text)

        for i, chunk in enumerate(chunks):
            send_files = files if i == len(chunks) - 1 else []
            try:
                if original_message and i == 0:
                    await original_message.reply(chunk, files=send_files)
                else:
                    await channel.send(chunk, files=send_files)
            except discord.HTTPException as e:
                logger.error(f"Failed to send chunk {i}: {e}")

    async def _send_dm(self, user_id: str, text: str):
        """Send a DM to a user by ID."""
        try:
            user = await self.fetch_user(int(user_id))
            chunks = _split_message(text)
            for chunk in chunks:
                await user.send(chunk)
        except Exception as e:
            logger.warning(f"Failed to send DM to {user_id}: {e}")

    # ── Background job notification polling ──────────────────────────────

    @tasks.loop(seconds=5)
    async def poll_notifications(self):
        """
        Every 5 seconds, check if the agent has queued notifications
        for completed background jobs, and deliver them to the right channel.
        """
        try:
            notifications = self.agent.get_all_pending_notifications()
        except AttributeError:
            # Fallback: agent may not have this method yet
            return

        for channel_id, agent_response in notifications.items():
            try:
                channel = self.get_channel(int(channel_id))
                if channel is None:
                    channel = await self.fetch_channel(int(channel_id))
                if channel:
                    await self._send_response(channel, agent_response)
            except Exception as e:
                logger.warning(f"Failed to deliver notification to channel {channel_id}: {e}")

    @poll_notifications.before_loop
    async def before_poll(self):
        await self.wait_until_ready()


# ── Utilities ──────────────────────────────────────────────────────────────

def _split_message(text: str, limit: int = 1990) -> list[str]:
    """Split a long message into chunks within Discord's 2000-char limit."""
    if len(text) <= limit:
        return [text] if text else []
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to split at newline boundary
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    # Load .env if present
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

    token = os.environ.get("DISCORD_TOKEN", DISCORD_TOKEN)
    if not token:
        raise RuntimeError(
            "Discord bot token not set.\n"
            "Set DISCORD_TOKEN env variable or put it in CellClaw/.env file."
        )

    import ssl as _ssl
    _ssl._create_default_https_context = _ssl._create_unverified_context

    # Start Dashboard servers (API + WebSocket) in background
    try:
        from cell_discord.gateway import CellClawGateway
        # Note: Gateway not yet created, will start after
        logger.info("Dashboard servers will start with gateway")
    except ImportError as e:
        logger.warning(f"Dashboard not available: {e}")

    bot = CellClawBot(proxy=PROXY)
    logger.info("Starting CellClaw Discord Gateway...")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
