"""
CellClaw Memory System
========================
Per-user memory with three tiers (inspired by OpenClaw):

1. Short-term: In-memory conversation history (last N turns, per-user)
2. Mid-term:   Daily markdown logs — memory/YYYY-MM-DD.md (per-user)
3. Long-term:  Curated MEMORY.md per user — distilled facts, project knowledge

Directory structure under data_dir:
    data/
    └── users/
        └── <discord_user_id>/
            ├── MEMORY.md          ← long-term curated memory
            ├── preferences.json   ← user preferences (species, paths, envs)
            └── memory/
                ├── 2026-03-11.md  ← daily log
                └── 2026-03-12.md
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Shanghai timezone
_TZ_SHANGHAI = timezone(timedelta(hours=8))

# Max conversation turns kept in memory per user
_MAX_HISTORY = 20


class UserMemory:
    """
    Manages all memory for a single Discord user.
    Thread-safe for single async event loop use.
    """

    def __init__(self, user_dir: Path):
        self.user_dir = user_dir
        self.memory_dir = user_dir / "memory"
        self.memory_md  = user_dir / "MEMORY.md"
        self.prefs_file = user_dir / "preferences.json"

        user_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(exist_ok=True)

        # In-memory conversation history: deque of {"role": ..., "content": ...}
        self._history: deque[dict] = deque(maxlen=_MAX_HISTORY)

        # Cached preferences
        self._prefs: dict = self._load_prefs()

    # ── Conversation History ────────────────────────────────────────────

    def add_turn(self, role: str, content: str):
        """Add a conversation turn (role = 'user' or 'assistant')."""
        self._history.append({"role": role, "content": content})

    def get_history(self, max_turns: int = 10) -> list[dict]:
        """Get recent conversation history as list of message dicts."""
        turns = list(self._history)
        return turns[-max_turns * 2:]  # Each turn = user + assistant

    def clear_history(self):
        """Clear conversation history (e.g., /clear command)."""
        self._history.clear()

    # ── Daily Log ──────────────────────────────────────────────────────

    def _today_file(self) -> Path:
        today = datetime.now(_TZ_SHANGHAI).strftime("%Y-%m-%d")
        return self.memory_dir / f"{today}.md"

    def log(self, content: str, section: Optional[str] = None):
        """
        Append an entry to today's daily log.
        Called automatically by the agent for significant events.
        """
        now  = datetime.now(_TZ_SHANGHAI).strftime("%H:%M")
        path = self._today_file()

        # Create file with header if new
        if not path.exists():
            date = datetime.now(_TZ_SHANGHAI).strftime("%Y-%m-%d")
            path.write_text(f"# CellClaw Memory — {date}\n\n", encoding="utf-8")

        entry = f"\n## [{now}]"
        if section:
            entry += f" {section}"
        entry += f"\n{content}\n"

        with path.open("a", encoding="utf-8") as f:
            f.write(entry)

        logger.debug(f"Memory log written to {path.name}")

    def read_today(self) -> str:
        """Read today's daily log."""
        p = self._today_file()
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def read_yesterday(self) -> str:
        """Read yesterday's daily log."""
        yesterday = (datetime.now(_TZ_SHANGHAI) - timedelta(days=1)).strftime("%Y-%m-%d")
        p = self.memory_dir / f"{yesterday}.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # ── Long-term MEMORY.md ────────────────────────────────────────────

    def read_memory(self) -> str:
        """Read the long-term MEMORY.md."""
        return self.memory_md.read_text(encoding="utf-8") if self.memory_md.exists() else ""

    def write_memory(self, content: str):
        """Overwrite MEMORY.md (called after LLM distillation)."""
        self.memory_md.write_text(content, encoding="utf-8")
        logger.info(f"MEMORY.md updated for {self.user_dir.name}")

    def append_memory(self, content: str):
        """Append to MEMORY.md."""
        with self.memory_md.open("a", encoding="utf-8") as f:
            f.write("\n" + content + "\n")

    # ── User Preferences ───────────────────────────────────────────────

    def _load_prefs(self) -> dict:
        if self.prefs_file.exists():
            try:
                return json.loads(self.prefs_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def get_pref(self, key: str, default=None):
        return self._prefs.get(key, default)

    def set_pref(self, key: str, value):
        self._prefs[key] = value
        self.prefs_file.write_text(
            json.dumps(self._prefs, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def get_all_prefs(self) -> dict:
        return dict(self._prefs)

    # ── Context Summary for LLM ────────────────────────────────────────

    def build_context_for_llm(
        self,
        include_memory: bool = True,
        include_today:  bool = True,
        max_memory_chars: int = 2000,
        max_today_chars:  int = 1000,
    ) -> str:
        """
        Build a context string to inject into LLM system prompt.
        Includes long-term memory + today's log snippets + preferences.
        """
        parts = []

        # Long-term memory
        if include_memory:
            mem = self.read_memory()
            if mem:
                if len(mem) > max_memory_chars:
                    mem = mem[-max_memory_chars:] + "\n...(earlier entries omitted)"
                parts.append(f"## 长期记忆（MEMORY.md）\n{mem}")

        # Today's log
        if include_today:
            today = self.read_today()
            if today:
                if len(today) > max_today_chars:
                    today = today[-max_today_chars:] + "\n...(earlier entries omitted)"
                parts.append(f"## 今日日志\n{today}")

        # Preferences
        prefs = self.get_all_prefs()
        if prefs:
            pref_str = "\n".join(f"- {k}: {v}" for k, v in prefs.items())
            parts.append(f"## 用户偏好\n{pref_str}")

        return "\n\n".join(parts) if parts else ""


class MemoryManager:
    """
    Global memory manager — one UserMemory per Discord user.
    """

    def __init__(self, data_dir: str):
        self._base = Path(data_dir) / "users"
        self._base.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, UserMemory] = {}

    def get(self, discord_user_id: str) -> UserMemory:
        """Get or create UserMemory for a user."""
        if discord_user_id not in self._cache:
            user_dir = self._base / discord_user_id
            self._cache[discord_user_id] = UserMemory(user_dir)
        return self._cache[discord_user_id]

    def __getitem__(self, discord_user_id: str) -> UserMemory:
        return self.get(discord_user_id)
