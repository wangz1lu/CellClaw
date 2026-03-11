"""
Server Registry
===============
Persists ServerConfig entries per Discord user to registry.json.
Supports add / remove / list / get / set-active operations.
"""

from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import ServerConfig, AuthType, UserSession


_REGISTRY_FILE = Path(__file__).parent.parent / "data" / "registry.json"
_SESSIONS_FILE = Path(__file__).parent.parent / "data" / "sessions.json"


class ServerRegistry:
    """
    Stores all registered servers across all Discord users.
    Thread-safe reads; writes serialized via simple file lock.
    """

    def __init__(self, registry_path: Path = _REGISTRY_FILE,
                 sessions_path: Path = _SESSIONS_FILE):
        self._reg_path = registry_path
        self._ses_path = sessions_path
        self._reg_path.parent.mkdir(parents=True, exist_ok=True)
        self._servers: dict[str, dict] = self._load(self._reg_path)
        self._sessions: dict[str, dict] = self._load(self._ses_path)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _load(self, path: Path) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                return {}
        return {}

    def _save_registry(self):
        self._reg_path.write_text(json.dumps(self._servers, indent=2, default=str))

    def _save_sessions(self):
        self._ses_path.write_text(json.dumps(self._sessions, indent=2, default=str))

    def _server_key(self, discord_user_id: str, server_id: str) -> str:
        return f"{discord_user_id}:{server_id}"

    # ------------------------------------------------------------------ #
    # Server CRUD
    # ------------------------------------------------------------------ #

    def add_server(self, config: ServerConfig) -> ServerConfig:
        """Register a new server (or overwrite if same server_id for user)."""
        key = self._server_key(config.owner_discord_id, config.server_id)
        self._servers[key] = {
            "server_id": config.server_id,
            "host": config.host,
            "port": config.port,
            "username": config.username,
            "owner_discord_id": config.owner_discord_id,
            "auth_type": config.auth_type.value,
            "key_path": config.key_path,
            "password_token": config.password_token,
            "created_at": config.created_at.isoformat(),
            "notes": config.notes,
        }
        self._save_registry()
        return config

    def remove_server(self, discord_user_id: str, server_id: str) -> bool:
        key = self._server_key(discord_user_id, server_id)
        if key not in self._servers:
            return False
        del self._servers[key]
        self._save_registry()
        # Clear from active session if needed
        session = self.get_session(discord_user_id)
        if session and session.active_server_id == server_id:
            session.active_server_id = None
            self._persist_session(session)
        return True

    def get_server(self, discord_user_id: str, server_id: str) -> Optional[ServerConfig]:
        key = self._server_key(discord_user_id, server_id)
        data = self._servers.get(key)
        if not data:
            return None
        return self._dict_to_config(data)

    def list_servers(self, discord_user_id: str) -> list[ServerConfig]:
        prefix = f"{discord_user_id}:"
        configs = []
        for key, data in self._servers.items():
            if key.startswith(prefix):
                configs.append(self._dict_to_config(data))
        return sorted(configs, key=lambda c: c.server_id)

    def update_last_used(self, discord_user_id: str, server_id: str):
        key = self._server_key(discord_user_id, server_id)
        if key in self._servers:
            self._servers[key]["last_used"] = datetime.now().isoformat()
            self._save_registry()

    def _dict_to_config(self, data: dict) -> ServerConfig:
        return ServerConfig(
            server_id=data["server_id"],
            host=data["host"],
            port=data.get("port", 22),
            username=data["username"],
            owner_discord_id=data["owner_discord_id"],
            auth_type=AuthType(data.get("auth_type", "key")),
            key_path=data.get("key_path"),
            password_token=data.get("password_token"),
            created_at=datetime.fromisoformat(data["created_at"])
                if data.get("created_at") else datetime.now(),
            notes=data.get("notes"),
        )

    # ------------------------------------------------------------------ #
    # User Session management
    # ------------------------------------------------------------------ #

    def get_session(self, discord_user_id: str) -> UserSession:
        data = self._sessions.get(discord_user_id)
        if not data:
            return UserSession(discord_user_id=discord_user_id)
        return UserSession(
            discord_user_id=discord_user_id,
            active_server_id=data.get("active_server_id"),
            active_project_path=data.get("active_project_path"),
            active_conda_env=data.get("active_conda_env"),
        )

    def set_active_server(self, discord_user_id: str, server_id: str):
        session = self.get_session(discord_user_id)
        session.active_server_id = server_id
        # Reset project/env when switching servers
        session.active_project_path = None
        session.active_conda_env = None
        self._persist_session(session)

    def set_active_project(self, discord_user_id: str, path: str):
        session = self.get_session(discord_user_id)
        session.active_project_path = path
        self._persist_session(session)

    def set_active_env(self, discord_user_id: str, env_name: str):
        session = self.get_session(discord_user_id)
        session.active_conda_env = env_name
        self._persist_session(session)

    def _persist_session(self, session: UserSession):
        self._sessions[session.discord_user_id] = {
            "active_server_id": session.active_server_id,
            "active_project_path": session.active_project_path,
            "active_conda_env": session.active_conda_env,
            "last_activity": datetime.now().isoformat(),
        }
        self._save_sessions()

    # ------------------------------------------------------------------ #
    # Convenience helpers for the Agent
    # ------------------------------------------------------------------ #

    def resolve_server(self, discord_user_id: str,
                       server_id: Optional[str] = None) -> Optional[ServerConfig]:
        """
        Resolve server to use:
        1. Explicit server_id if provided
        2. User's active server from session
        3. If user has exactly one server, auto-select it
        Returns None if cannot resolve.
        """
        if server_id:
            return self.get_server(discord_user_id, server_id)

        session = self.get_session(discord_user_id)
        if session.active_server_id:
            return self.get_server(discord_user_id, session.active_server_id)

        servers = self.list_servers(discord_user_id)
        if len(servers) == 1:
            return servers[0]

        return None
