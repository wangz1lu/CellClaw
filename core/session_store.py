"""
OmicsClaw Session Store
=======================
Persistent conversation history per user, stored as JSONL transcripts.
Mirrors OpenClaw's session model:
  - Each user has a transcript file: sessions/<user_id>.jsonl
  - Each entry is a JSON object on one line (role, content, tool_calls, etc.)
  - On load: replay last N messages for context window
  - Compaction: when token estimate exceeds threshold, summarize old messages

Directory layout:
    data/
    └── sessions/
        └── <discord_user_id>.jsonl
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TZ_SHANGHAI = timezone(timedelta(hours=8))

# Approx chars per token (rough estimate for compaction trigger)
_CHARS_PER_TOKEN = 4
# Trigger compaction when history exceeds this many estimated tokens
_COMPACTION_TOKEN_THRESHOLD = 6000
# How many recent messages to always keep after compaction
_COMPACTION_KEEP_RECENT = 10


def _estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        c = m.get("content") or ""
        if isinstance(c, list):
            c = " ".join(str(x) for x in c)
        total += len(str(c)) // _CHARS_PER_TOKEN
        for tc in m.get("tool_calls", []):
            total += len(json.dumps(tc)) // _CHARS_PER_TOKEN
    return total


class SessionStore:
    """
    Per-user persistent session store.
    Thread-safe for single async event loop.
    """

    def __init__(self, user_id: str, sessions_dir: Path):
        self.user_id      = user_id
        self.path         = sessions_dir / f"{user_id}.jsonl"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        self._messages: list[dict] = []
        self._load()

    def _load(self):
        """Load existing transcript from disk."""
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._messages.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            logger.debug(f"Session loaded: {self.user_id} ({len(self._messages)} messages)")
        except Exception as e:
            logger.warning(f"Failed to load session {self.user_id}: {e}")
            self._messages = []

    def _append_to_disk(self, message: dict):
        """Append a single message to the JSONL file."""
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Failed to append to session {self.user_id}: {e}")

    def _rewrite_disk(self):
        """Rewrite the full transcript (after compaction)."""
        try:
            with self.path.open("w", encoding="utf-8") as f:
                for m in self._messages:
                    f.write(json.dumps(m, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Failed to rewrite session {self.user_id}: {e}")

    def add(self, message: dict):
        """Add a message to history and persist."""
        # Add timestamp if missing
        if "_ts" not in message:
            message["_ts"] = datetime.now(_TZ_SHANGHAI).isoformat()
        self._messages.append(message)
        self._append_to_disk(message)

    def get_history(self, max_messages: int = 20) -> list[dict]:
        """
        Get recent messages for LLM context.
        Strips internal metadata (_ts, etc.) before returning.
        """
        recent = self._messages[-max_messages:]
        clean  = []
        for m in recent:
            msg = {k: v for k, v in m.items() if not k.startswith("_")}
            # Skip system messages — will be rebuilt fresh each call
            if msg.get("role") == "system":
                continue
            clean.append(msg)
        return clean

    def needs_compaction(self) -> bool:
        """Check if history is getting too long."""
        return _estimate_tokens(self._messages) > _COMPACTION_TOKEN_THRESHOLD

    def compact(self, summary: str):
        """
        Replace old messages with a compaction summary.
        Keeps the most recent N messages intact.
        """
        ts  = datetime.now(_TZ_SHANGHAI).isoformat()
        recent = self._messages[-_COMPACTION_KEEP_RECENT:]

        compaction_entry = {
            "role":    "system",
            "content": f"[对话历史摘要 — {ts}]\n{summary}",
            "_ts":     ts,
            "_type":   "compaction",
        }

        self._messages = [compaction_entry] + recent
        self._rewrite_disk()
        logger.info(f"Session compacted for {self.user_id}: {len(recent)} recent messages kept")

    def clear(self):
        """Clear all history."""
        self._messages = []
        if self.path.exists():
            self.path.unlink()
        logger.info(f"Session cleared for {self.user_id}")

    def __len__(self):
        return len(self._messages)


class SessionManager:
    """
    Global session manager — one SessionStore per Discord user.
    """

    def __init__(self, data_dir: str):
        self._sessions_dir = Path(data_dir) / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, SessionStore] = {}

    def get(self, user_id: str) -> SessionStore:
        if user_id not in self._cache:
            self._cache[user_id] = SessionStore(user_id, self._sessions_dir)
        return self._cache[user_id]

    def __getitem__(self, user_id: str) -> SessionStore:
        return self.get(user_id)
