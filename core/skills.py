"""
OmicsClaw Skill System
=======================
Skills are KNOWLEDGE BASES, not scripts to copy-paste.

Each skill provides:
  - SKILL.md : Full knowledge doc — protocols, parameters, code snippets, gotchas
                The LLM reads this to UNDERSTAND the analysis, then writes
                context-aware code tailored to the user's actual data.
  - templates/: Reference examples (optional). LLM may read these for inspiration,
                but MUST adapt them — paths, object names, params — to the real task.

Workflow:
  1. User asks for an analysis
  2. LLM calls `read_skill` to load the SKILL.md knowledge base
  3. LLM understands the protocol, parameters, common pitfalls
  4. LLM writes custom code based on the user's actual data/paths/env
  5. LLM uploads and executes the custom code via SSH

SKILL.md YAML front matter (optional):
    ---
    name: CCC — CellChat v2
    version: 1.0.0
    scope: Single dataset CCC / Multi-dataset comparison / Spatial CCC
    languages: [R]
    triggers: [cellchat, ccc, 细胞通讯, cell communication]
    ---
"""

from __future__ import annotations

import logging
import re
import yaml
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SkillInfo:
    """
    Represents a single installed skill.
    """

    def __init__(self, skill_id: str, skill_dir: Path):
        self.skill_id  = skill_id
        self.skill_dir = skill_dir
        self.md_path   = skill_dir / "SKILL.md"

        # Parsed metadata (from YAML front matter or header comments)
        self.name      = skill_id
        self.version   = "1.0.0"
        self.scope     = ""
        self.languages: list[str] = []
        self.triggers:  list[str] = []

        # Cached full content
        self._full_content: Optional[str] = None

        self._parse_metadata()

    def _parse_metadata(self):
        """Parse YAML front matter or # comment headers from SKILL.md."""
        if not self.md_path.exists():
            return
        text = self.md_path.read_text(encoding="utf-8")

        # Try YAML front matter first (--- ... ---)
        m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if m:
            try:
                meta = yaml.safe_load(m.group(1))
                if isinstance(meta, dict):
                    self.name      = meta.get("name", self.skill_id)
                    self.version   = str(meta.get("version", "1.0.0"))
                    self.scope     = meta.get("scope", "")
                    self.languages = meta.get("languages", [])
                    self.triggers  = meta.get("triggers", [])
                    return
            except Exception:
                pass

        # Fallback: parse # comment headers
        for line in text.splitlines()[:15]:
            m2 = re.match(r"^#\s+Skill:\s+(.+)$", line)
            if m2:
                self.name = m2.group(1).strip(); continue
            m2 = re.match(r"^#\s+Version:\s+(.+)$", line)
            if m2:
                self.version = m2.group(1).strip(); continue
            m2 = re.match(r"^#\s+Scope:\s+(.+)$", line)
            if m2:
                self.scope = m2.group(1).strip(); continue

    def load_skill_md(self) -> str:
        """Load and cache SKILL.md content."""
        if self._full_content is None:
            if self.md_path.exists():
                self._full_content = self.md_path.read_text(encoding="utf-8")
            else:
                self._full_content = f"(SKILL.md not found for {self.skill_id})"
        return self._full_content

    def list_templates(self) -> list[str]:
        """List reference templates (for inspiration, not direct copy)."""
        templates_dir = self.skill_dir / "templates"
        if templates_dir.exists():
            return sorted(p.name for p in templates_dir.iterdir() if p.is_file())
        return []

    def read_template(self, name: str) -> Optional[str]:
        """Read a reference template file."""
        p = self.skill_dir / "templates" / name
        return p.read_text(encoding="utf-8") if p.exists() else None

    def matches_trigger(self, text: str) -> bool:
        """Check if this skill is relevant for a given user message."""
        text_lower = text.lower()
        return any(t.lower() in text_lower for t in self.triggers)

    def to_one_liner(self) -> str:
        lang_str = f" [{'/'.join(self.languages)}]" if self.languages else ""
        return f"**{self.skill_id}**{lang_str} — {self.name}: {self.scope}"


class SkillLoader:
    """
    Global skill registry. Loaded once at startup.
    """

    def __init__(self, skills_dir: str):
        self._skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillInfo] = {}
        self._load_all()

    def _load_all(self):
        if not self._skills_dir.exists():
            logger.warning(f"Skills directory not found: {self._skills_dir}")
            return
        for item in sorted(self._skills_dir.iterdir()):
            if item.is_dir() and (item / "SKILL.md").exists():
                skill = SkillInfo(item.name, item)
                self._skills[item.name] = skill
                logger.info(f"Loaded skill: {item.name} — {skill.name}")
        logger.info(f"SkillLoader: {len(self._skills)} skills loaded")

    def list_skills(self) -> list[SkillInfo]:
        return list(self._skills.values())

    def get(self, skill_id: str) -> Optional[SkillInfo]:
        return self._skills.get(skill_id)

    def skill_ids(self) -> list[str]:
        return list(self._skills.keys())

    def find_relevant(self, user_message: str) -> list[SkillInfo]:
        """Find skills whose triggers match the user message."""
        return [s for s in self._skills.values() if s.matches_trigger(user_message)]

    def build_prompt_section(self) -> str:
        """
        Inject skill awareness into LLM system prompt.
        Tells LLM WHAT skills exist and HOW to use them properly.
        """
        if not self._skills:
            return "（暂无已安装的分析 Skill）"

        lines = [
            "## 已安装的分析 Skill\n",
            "当用户需要分析时，**必须先调用 `read_skill` 读取对应 Skill 的知识库**，",
            "理解标准流程和参数，然后**根据用户的实际数据路径、对象名称、物种等信息**",
            "编写定制化的代码，再上传执行。\n",
            "⚠️ 禁止跳过 `read_skill` 步骤直接生成代码，禁止无脑复制模板。\n",
        ]

        for skill in self._skills.values():
            lines.append(f"### {skill.skill_id}")
            lines.append(f"- 名称: {skill.name}")
            if skill.scope:
                lines.append(f"- 适用: {skill.scope}")
            if skill.languages:
                lines.append(f"- 语言: {', '.join(skill.languages)}")
            if skill.triggers:
                lines.append(f"- 触发词: {', '.join(skill.triggers)}")
            templates = skill.list_templates()
            if templates:
                lines.append(f"- 参考模板（可选读取）: {', '.join(templates)}")
            lines.append("")

        lines += [
            "## read_skill 工具用法\n",
            "**第一步：读取知识库**（必须）",
            "```tool",
            '{"tool": "read_skill", "skill_id": "ccc_cellchat"}',
            "```\n",
            "**第二步（可选）：查看参考模板**",
            "```tool",
            '{"tool": "read_skill", "skill_id": "ccc_cellchat", "template": "01_single_dataset_CCC.R"}',
            "```\n",
            "读取知识库后，结合用户提供的数据路径/对象/物种/条件，编写定制化代码执行。",
        ]
        return "\n".join(lines)

    def build_discord_list(self) -> str:
        """Human-readable list for /skill list command."""
        if not self._skills:
            return "暂无已安装的 Skill。"
        lines = []
        for s in self._skills.values():
            lines.append(f"🔬 **{s.skill_id}** — {s.name}")
            if s.scope:
                lines.append(f"   适用: {s.scope}")
            if s.languages:
                lines.append(f"   语言: {', '.join(s.languages)}")
            templates = s.list_templates()
            if templates:
                lines.append(f"   参考模板: `{'`, `'.join(templates)}`")
            lines.append("")
        return "\n".join(lines)


# ── Soul loader ──────────────────────────────────────────────────────────────

def load_soul(project_root: str) -> str:
    """Load SOUL.md from project root. Returns empty string if not found."""
    soul_path = Path(project_root) / "SOUL.md"
    if soul_path.exists():
        content = soul_path.read_text(encoding="utf-8")
        logger.info(f"SOUL.md loaded ({len(content)} chars)")
        return content
    logger.warning("SOUL.md not found")
    return ""
