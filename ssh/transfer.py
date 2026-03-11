"""
File Transfer
=============
Download result files from remote servers and upload scripts.
Uses asyncssh's built-in SFTP client.
"""

from __future__ import annotations
import logging
from pathlib import Path, PurePosixPath
from typing import Optional

from .connection import SSHConnection
from .executor import RemoteExecutor

logger = logging.getLogger(__name__)

# Max size for inline text reads (bytes)
_MAX_INLINE_READ = 512 * 1024  # 512 KB


class FileTransfer:

    def __init__(self, executor: Optional[RemoteExecutor] = None):
        self._exec = executor or RemoteExecutor()

    async def download(
        self,
        conn: SSHConnection,
        remote_path: str,
        local_path: str,
    ) -> str:
        """
        Download a single file from the remote server.
        Returns local_path on success.
        """
        sftp = await conn.sftp()
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        await sftp.get(remote_path, local_path)
        logger.info(f"Downloaded {remote_path} → {local_path}")
        return local_path

    async def download_many(
        self,
        conn: SSHConnection,
        remote_paths: list[str],
        local_dir: str,
    ) -> list[str]:
        """
        Download multiple files into local_dir.
        Returns list of successfully downloaded local paths.
        """
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        sftp = await conn.sftp()
        local_paths = []
        for remote_path in remote_paths:
            filename = PurePosixPath(remote_path).name
            local_path = str(Path(local_dir) / filename)
            try:
                await sftp.get(remote_path, local_path)
                local_paths.append(local_path)
            except Exception as e:
                logger.warning(f"Failed to download {remote_path}: {e}")
        return local_paths

    async def upload(
        self,
        conn: SSHConnection,
        local_path: str,
        remote_path: str,
    ) -> bool:
        """
        Upload a local file to the remote server.
        Creates parent directories if needed.
        """
        # Ensure remote parent directory exists
        remote_dir = str(PurePosixPath(remote_path).parent)
        await self._exec.run(conn, f"mkdir -p {remote_dir}", timeout=10)

        sftp = await conn.sftp()
        try:
            await sftp.put(local_path, remote_path)
            logger.info(f"Uploaded {local_path} → {remote_path}")
            return True
        except Exception as e:
            logger.error(f"Upload failed {local_path} → {remote_path}: {e}")
            return False

    async def read_text(
        self,
        conn: SSHConnection,
        remote_path: str,
        max_lines: int = 200,
        encoding: str = "utf-8",
    ) -> str:
        """
        Read a remote text file inline (no temp file).
        Truncates at max_lines.
        """
        result = await self._exec.run(
            conn,
            f"head -n {max_lines} {remote_path} 2>/dev/null "
            f"|| echo '(file not found: {remote_path})'",
            timeout=15,
        )
        return result.stdout

    async def list_dir(
        self,
        conn: SSHConnection,
        remote_path: str,
        show_hidden: bool = False,
    ) -> list[dict]:
        """
        List directory contents with metadata.
        Returns list of dicts: {name, type, size, modified}.
        """
        flag = "-la" if show_hidden else "-l"
        result = await self._exec.run(
            conn,
            f"ls {flag} --time-style=long-iso {remote_path} 2>/dev/null",
            timeout=15,
        )
        return self._parse_ls(result.stdout)

    async def file_exists(self, conn: SSHConnection, remote_path: str) -> bool:
        result = await self._exec.run(
            conn,
            f"test -e {remote_path} && echo yes || echo no",
            timeout=10,
        )
        return "yes" in result.stdout

    async def file_size_mb(self, conn: SSHConnection, remote_path: str) -> float:
        result = await self._exec.run(
            conn,
            f"du -sm {remote_path} 2>/dev/null | cut -f1",
            timeout=10,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 0.0

    def _parse_ls(self, ls_output: str) -> list[dict]:
        """Parse `ls -l --time-style=long-iso` output into dicts."""
        entries = []
        for line in ls_output.splitlines():
            parts = line.split()
            if len(parts) < 8 or line.startswith("total"):
                continue
            perms = parts[0]
            size = parts[4]
            date = parts[5]
            time = parts[6]
            name = " ".join(parts[7:])
            entries.append({
                "name": name,
                "type": "dir" if perms.startswith("d") else "file",
                "size": int(size) if size.isdigit() else 0,
                "modified": f"{date} {time}",
                "perms": perms,
            })
        return entries
