"""
Natural Language Router
========================
Parses free-form user messages into structured intents.
Works alongside the slash command parser: NLRouter handles everything
that isn't a /command.

Intent schema:
  {
    "action":  str,       # "query" | "analyze" | "read_script" | "setup_env" | ...
    "params":  dict,      # action-specific parameters
    "raw":     str        # original message
  }

NLRouter uses regex + keyword heuristics for speed and reliability.
For ambiguous cases, it returns a "clarify" intent.
"""

from __future__ import annotations
import re
import logging
from typing import Optional

from ssh.manager import SSHManager
from .llm import get_llm_client

logger = logging.getLogger(__name__)

# Common file path pattern
_PATH_RE = re.compile(r'[~/.][\w/.\-]+\.(?:h5ad|h5|rds|robj|loom|py|r|sh|csv|tsv)')
_GENE_RE = re.compile(r'\b([A-Z][A-Z0-9]{1,10})\b')


class NLRouter:

    def __init__(self, ssh_manager: SSHManager):
        self._ssh = ssh_manager

    async def parse(self, message: str, discord_user_id: str) -> dict:
        """
        Parse a natural language message into a structured intent.
        Returns intent dict.
        """
        msg = message.strip()
        msg_lower = msg.lower()
        session = self._ssh._registry.get_session(discord_user_id)

        # Extract file path if present in message
        path_match = _PATH_RE.search(msg)
        filepath = path_match.group(0) if path_match else None

        # ── Status / session queries ───────────────────────────────────
        if any(kw in msg_lower for kw in ["我的状态", "当前状态", "/status", "session"]):
            return {"action": "status", "params": {}, "raw": msg}

        # ── Help ──────────────────────────────────────────────────────
        if any(kw in msg_lower for kw in ["怎么用", "help", "帮助", "有什么功能"]):
            return {"action": "help", "params": {}, "raw": msg}

        # ── Script read/explain ───────────────────────────────────────
        if any(kw in msg_lower for kw in ["读一下", "看一下", "解释", "读懂", "查看脚本", "看看这个脚本"]):
            script_path = filepath or session.active_project_path
            action_type = "explain" if any(k in msg_lower for k in ["解释", "读懂"]) else "read"
            return {
                "action": "read_script",
                "params": {"path": script_path, "action": action_type},
                "raw": msg
            }

        # ── Script modify ─────────────────────────────────────────────
        if any(kw in msg_lower for kw in ["修改", "优化", "加上", "加一个", "添加", "改成"]):
            return {
                "action": "read_script",
                "params": {"path": filepath, "action": "modify", "instruction": msg},
                "raw": msg
            }

        # ── Environment setup ──────────────────────────────────────────
        if any(kw in msg_lower for kw in ["建环境", "创建环境", "装包", "安装环境", "setup env", "create env"]):
            framework = "seurat" if "seurat" in msg_lower else "scanpy"
            env_name_match = re.search(r'(?:叫|名字|name)[：: ]?(\w+)', msg_lower)
            env_name = env_name_match.group(1) if env_name_match else f"{framework}_env"
            return {
                "action": "setup_env",
                "params": {"env_name": env_name, "framework": framework},
                "raw": msg
            }

        # ── Quick queries (synchronous) ────────────────────────────────
        if any(kw in msg_lower for kw in [
            "多少", "几个", "有没有", "是什么", "平均", "最多", "最少",
            "看看", "告诉我", "查一下", "how many", "what is", "show me"
        ]):
            return {
                "action": "query",
                "params": {
                    "question": msg,
                    "filepath": filepath or self._infer_filepath(session),
                    "conda_env": session.active_conda_env,
                },
                "raw": msg
            }

        # ── Full pipeline ──────────────────────────────────────────────
        if any(kw in msg_lower for kw in [
            "完整", "全流程", "从头", "全套", "full pipeline", "完整分析",
            "从0开始", "从零开始"
        ]):
            return {
                "action": "full_pipeline",
                "params": {
                    "filepath": filepath or self._infer_filepath(session),
                    "analysis_type": "full",
                    "conda_env": session.active_conda_env,
                    "workdir": session.active_project_path,
                },
                "raw": msg
            }

        # ── Specific analysis types ────────────────────────────────────
        analysis_type = self._detect_analysis_type(msg_lower)
        if analysis_type:
            return {
                "action": "analyze",
                "params": {
                    "filepath": filepath or self._infer_filepath(session),
                    "analysis_type": analysis_type,
                    "conda_env": session.active_conda_env,
                    "workdir": session.active_project_path,
                },
                "raw": msg
            }

        # ── Fallback: LLM if available, else unknown ──────────────────
        llm = get_llm_client()
        if llm.enabled:
            return {"action": "llm_chat", "params": {"message": msg, "filepath": filepath}, "raw": msg}
        return {"action": "unknown", "params": {"message": msg}, "raw": msg}

    def _detect_analysis_type(self, msg_lower: str) -> Optional[str]:
        """Detect the type of analysis requested."""
        if any(k in msg_lower for k in ["qc", "质控", "过滤", "quality"]):
            return "qc"
        if any(k in msg_lower for k in ["cluster", "聚类", "umap", "tsne", "降维"]):
            return "cluster"
        if any(k in msg_lower for k in ["注释", "annotate", "cell type", "细胞类型"]):
            return "annotate"
        if any(k in msg_lower for k in ["差异", "deg", "differential", "marker gene"]):
            return "deg"
        if any(k in msg_lower for k in ["轨迹", "trajectory", "pseudotime", "rna velocity"]):
            return "trajectory"
        if any(k in msg_lower for k in ["空间", "spatial", "visium", "stereo"]):
            return "spatial"
        if any(k in msg_lower for k in ["批次", "batch", "integration", "整合"]):
            return "batch_integration"
        return None

    def _infer_filepath(self, session) -> Optional[str]:
        """Try to infer the data file from session context."""
        if session.active_project_path:
            return session.active_project_path
        return None
