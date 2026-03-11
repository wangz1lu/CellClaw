"""
Data Models for OmicsClaw SSH Layer
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AuthType(str, Enum):
    KEY = "key"
    PASSWORD = "password"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisFramework(str, Enum):
    SCANPY = "scanpy"       # Python: scanpy + anndata
    SEURAT = "seurat"       # R: Seurat
    BOTH = "both"           # Both available
    UNKNOWN = "unknown"


@dataclass
class ServerConfig:
    """Represents a registered remote server."""
    server_id: str                      # User-defined name, e.g. "mylab"
    host: str                           # IP or hostname
    username: str
    owner_discord_id: str               # Which Discord user owns this entry
    port: int = 22
    auth_type: AuthType = AuthType.KEY
    key_path: Optional[str] = None      # Path to private key on OmicsClaw host
    password_token: Optional[str] = None  # Vault token (never plaintext)
    created_at: datetime = field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    notes: Optional[str] = None         # e.g. "lab GPU server, 8x A100"

    @property
    def display_name(self) -> str:
        return f"{self.server_id} ({self.username}@{self.host}:{self.port})"


@dataclass
class ServerInfo:
    """Runtime info gathered after connecting."""
    cpu_count: int = 0
    memory_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    os_version: str = ""
    hostname: str = ""
    conda_available: bool = False
    mamba_available: bool = False

    def summary(self) -> str:
        disk_pct = (self.disk_used_gb / self.disk_total_gb * 100) if self.disk_total_gb else 0
        return (
            f"🖥️  {self.hostname} | {self.os_version}\n"
            f"⚙️  CPU: {self.cpu_count} 核 | 内存: {self.memory_gb:.0f} GB\n"
            f"💾 存储: {self.disk_used_gb:.0f}/{self.disk_total_gb:.0f} GB "
            f"({disk_pct:.0f}% 已用)"
        )


@dataclass
class UserSession:
    """Per-Discord-user runtime state."""
    discord_user_id: str
    active_server_id: Optional[str] = None
    active_project_path: Optional[str] = None
    active_conda_env: Optional[str] = None
    last_activity: datetime = field(default_factory=datetime.now)

    def touch(self):
        self.last_activity = datetime.now()


@dataclass
class ExecuteResult:
    """Result of a synchronous remote command."""
    stdout: str
    stderr: str
    exit_code: int

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def output(self) -> str:
        """Combined stdout, fallback to stderr if empty."""
        return self.stdout.strip() or self.stderr.strip()


@dataclass
class RemoteJob:
    """Tracks a background (tmux) job on a remote server."""
    job_id: str                         # e.g. "omics_abc123"
    discord_user_id: str
    server_id: str
    tmux_session: str                   # tmux session name
    command: str                        # original command submitted
    workdir: str
    conda_env: Optional[str]
    log_path: str                       # remote path to stdout log
    script_path: str                    # remote path to the generated script
    status: JobStatus = JobStatus.PENDING
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    result_paths: list[str] = field(default_factory=list)   # output files
    error_summary: Optional[str] = None

    def elapsed(self) -> str:
        end = self.finished_at or datetime.now()
        secs = int((end - self.started_at).total_seconds())
        m, s = divmod(secs, 60)
        return f"{m}m{s:02d}s"


@dataclass
class CondaEnvInfo:
    """Information about a conda/mamba environment."""
    name: str
    path: str
    framework: AnalysisFramework = AnalysisFramework.UNKNOWN
    key_packages: dict[str, str] = field(default_factory=dict)  # pkg -> version

    def summary(self) -> str:
        fw = self.framework.value
        pkgs = ", ".join(f"{k}={v}" for k, v in list(self.key_packages.items())[:5])
        return f"🐍 `{self.name}` [{fw}] — {pkgs or '(packages not scanned)'}"
