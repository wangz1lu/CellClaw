"""
Environment Detector
====================
Detects conda/mamba environments and installed bioinformatics packages
on a remote Linux server.
"""

from __future__ import annotations
import json
import logging
from typing import Optional

from .models import AnalysisFramework, CondaEnvInfo
from .connection import SSHConnection
from .executor import RemoteExecutor

logger = logging.getLogger(__name__)

# Key packages to probe for framework detection
_SCANPY_PACKAGES = ["scanpy", "anndata", "squidpy", "scvi"]
_SEURAT_PACKAGES  = ["r-seurat", "seurat"]          # conda package names
_OMICS_PACKAGES   = [                               # broader probe list
    "scanpy", "anndata", "squidpy", "scvi-tools",
    "cellrank", "harmonypy", "leidenalg",
    "r-seurat", "r-monocle3",
    "cell2location", "spatialDE",
]


class EnvironmentDetector:

    def __init__(self, executor: Optional[RemoteExecutor] = None):
        self._exec = executor or RemoteExecutor()

    # ------------------------------------------------------------------ #
    # Env listing
    # ------------------------------------------------------------------ #

    async def _get_conda_cmd(self, conn: SSHConnection) -> str:
        """
        Find the real conda binary path on non-interactive SSH shells.
        conda init writes to .bashrc with an interactive guard (case $- in *i*),
        so source ~/.bashrc won't activate conda. We find the binary directly.
        """
        # Try common install locations first (fastest)
        find_cmd = (
            "for p in "
            "$HOME/miniconda3/bin/conda "
            "$HOME/miniconda/bin/conda "
            "$HOME/anaconda3/bin/conda "
            "$HOME/anaconda/bin/conda "
            "$HOME/miniforge3/bin/conda "
            "$HOME/mambaforge/bin/conda "
            "/opt/conda/bin/conda "
            "/opt/miniconda3/bin/conda "
            "/opt/anaconda3/bin/conda "
            "/usr/local/bin/conda "
            "/usr/bin/conda; "
            "do [ -x \"$p\" ] && echo \"$p\" && break; done"
        )
        r = await self._exec.run(conn, find_cmd, timeout=10)
        if r.success and r.stdout.strip():
            return r.stdout.strip()

        # Try CONDA_EXE env var
        r = await self._exec.run(conn, "echo $CONDA_EXE", timeout=5)
        val = r.stdout.strip()
        if val and val != "$CONDA_EXE" and "/" in val:
            return val

        # Extract path from .bashrc __conda_setup line
        r = await self._exec.run(
            conn,
            r'''python3 -c "
import re, os
try:
    c = open(os.path.expanduser('~/.bashrc')).read()
    m = re.search(r'[\x22\x27]([^\x22\x27]+/bin/conda)[\x22\x27]', c)
    if m: print(m.group(1))
except: pass
" 2>/dev/null''',
            timeout=10,
        )
        if r.success and r.stdout.strip():
            return r.stdout.strip()

        return ""

    async def list_conda_envs(self, conn: SSHConnection) -> list[CondaEnvInfo]:
        """List all conda environments on the remote server."""
        conda = await self._get_conda_cmd(conn)
        if not conda:
            logger.warning("[ENV] conda binary not found on remote server")
            return []

        logger.info(f"[ENV] conda binary: {conda}")
        result = await self._exec.run(conn, f"{conda} env list --json 2>&1", timeout=20)
        logger.info(f"[ENV] list result: exit={result.exit_code} out={result.stdout[:200]!r}")

        if result.success and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                envs = []
                for path in data.get("envs", []):
                    name = path.rstrip("/").split("/")[-1] if "/" in path else path
                    if not name:
                        name = "base"
                    envs.append(CondaEnvInfo(name=name, path=path))
                if envs:
                    return envs
            except json.JSONDecodeError:
                pass

        # Fallback: plain text
        result = await self._exec.run(conn, f"{conda} env list 2>&1", timeout=20)
        return self._parse_env_list_text(result.stdout)

    async def get_env_packages(
        self, conn: SSHConnection, env_name: str
    ) -> dict[str, str]:
        """Return installed packages in an env: {package_name: version}."""
        conda = await self._get_conda_cmd(conn)
        if not conda:
            return {}
        result = await self._exec.run(
            conn,
            f"{conda} run -n {env_name} {conda} list --json 2>/dev/null",
            timeout=30,
        )
        packages: dict[str, str] = {}
        if result.success and result.stdout.strip():
            try:
                pkgs     = json.loads(result.stdout)
                relevant = {p.lower() for p in _OMICS_PACKAGES}
                for pkg in pkgs:
                    name = pkg.get("name", "").lower()
                    if name in relevant:
                        packages[name] = pkg.get("version", "?")
            except json.JSONDecodeError:
                pass
        return packages

    async def scan_env(self, conn: SSHConnection, env: CondaEnvInfo) -> CondaEnvInfo:
        """Full scan: detect packages + classify framework."""
        env.key_packages = await self.get_env_packages(conn, env.name)
        env.framework = self._classify_framework(env.key_packages)
        return env

    async def scan_all_envs(self, conn: SSHConnection) -> list[CondaEnvInfo]:
        """List + scan all envs. May be slow for many large envs."""
        envs = await self.list_conda_envs(conn)
        for env in envs:
            try:
                await self.scan_env(conn, env)
            except Exception as e:
                logger.warning(f"Failed to scan env {env.name}: {e}")
        return envs

    # ------------------------------------------------------------------ #
    # Data file discovery
    # ------------------------------------------------------------------ #

    async def find_data_files(
        self,
        conn: SSHConnection,
        search_path: str,
        extensions: Optional[list[str]] = None,
        max_results: int = 20,
    ) -> list[str]:
        """
        Recursively find single-cell data files under search_path.
        Returns list of remote absolute paths.
        """
        exts = extensions or [".h5ad", ".h5", ".loom", ".rds", ".robj"]
        find_exprs = []
        for ext in exts:
            find_exprs.append(f'-name "*{ext}"')
        find_cmd = (
            f"find {search_path} -maxdepth 5 "
            f"\\( {' -o '.join(find_exprs)} \\) "
            f"-not -path '*/.*' 2>/dev/null | head -{max_results}"
        )
        result = await self._exec.run(conn, find_cmd, timeout=30)
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        return files

    async def inspect_h5ad(
        self, conn: SSHConnection, filepath: str, conda_env: Optional[str] = None
    ) -> dict:
        """
        Read basic metadata from an .h5ad file using Python.
        Returns dict with n_obs, n_vars, obs_columns, obsm_keys, uns_keys.
        """
        code = f"""
import anndata as ad, json, sys
try:
    adata = ad.read_h5ad({filepath!r}, backed='r')
    info = {{
        "n_obs": adata.n_obs,
        "n_vars": adata.n_vars,
        "obs_columns": list(adata.obs.columns),
        "obsm_keys": list(adata.obsm.keys()),
        "uns_keys": list(adata.uns.keys()),
        "var_names_sample": list(adata.var_names[:5]),
    }}
    print(json.dumps(info))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
        result = await self._exec.run_python(
            conn, code, conda_env=conda_env, timeout=30
        )
        try:
            return json.loads(result.output)
        except Exception:
            return {"error": result.output or "无法读取文件"}

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _classify_framework(self, packages: dict[str, str]) -> AnalysisFramework:
        has_scanpy = "scanpy" in packages or "anndata" in packages
        has_seurat = "r-seurat" in packages or "seurat" in packages
        if has_scanpy and has_seurat:
            return AnalysisFramework.BOTH
        elif has_scanpy:
            return AnalysisFramework.SCANPY
        elif has_seurat:
            return AnalysisFramework.SEURAT
        return AnalysisFramework.UNKNOWN

    def _parse_env_list_text(self, text: str) -> list[CondaEnvInfo]:
        envs = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                name, path = parts[0], parts[-1]
                envs.append(CondaEnvInfo(name=name, path=path))
            elif len(parts) == 1 and "/" in parts[0]:
                path = parts[0]
                name = path.split("/")[-1]
                envs.append(CondaEnvInfo(name=name, path=path))
        return envs
