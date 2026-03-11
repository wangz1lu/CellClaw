"""
Session Manager - Manages per-channel analysis sessions and state
"""

import json
import pickle
from pathlib import Path
from datetime import datetime
from typing import Optional


class Session:
    """Represents a single analysis session (per Discord channel)."""

    def __init__(self, session_id: str, workspace: Path):
        self.session_id = session_id
        self.workspace = workspace / session_id
        self.workspace.mkdir(exist_ok=True)
        self.adata = None           # Current AnnData object
        self.latest_file = None     # Most recently uploaded file
        self.history = []           # Analysis history
        self.metadata = {
            "created_at": datetime.now().isoformat(),
            "species": "human",     # default
            "analyses_run": 0
        }

    def register_file(self, filepath: str):
        """Register a newly uploaded data file."""
        self.latest_file = Path(filepath)

    def load_adata(self, filepath: str):
        """Load AnnData from file."""
        import scanpy as sc
        self.adata = sc.read_h5ad(filepath)
        self.latest_file = Path(filepath)
        return self.adata

    def save_adata(self):
        """Save current AnnData to workspace."""
        if self.adata is not None:
            save_path = self.workspace / "current.h5ad"
            self.adata.write_h5ad(save_path)
            return save_path
        return None

    def add_history(self, command: str, result: dict):
        """Add an analysis step to history."""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "success": result.get("success", True)
        })
        self.metadata["analyses_run"] += 1

    def get_figure_dir(self) -> Path:
        """Return directory for saving figures."""
        fig_dir = self.workspace / "figures"
        fig_dir.mkdir(exist_ok=True)
        return fig_dir


class SessionManager:
    """Manages multiple analysis sessions."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id, self.workspace)
        return self._sessions[session_id]

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list:
        return list(self._sessions.keys())
