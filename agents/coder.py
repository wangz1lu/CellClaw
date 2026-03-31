"""
CoderAgent - Code Generation with LLM
===================================

Uses LLM to:
1. Generate complete, executable code
2. Use Skills as templates when available
3. Save code to SSH workdir
"""

from __future__ import annotations
import os
import re
import logging
import asyncio
from typing import Optional

from agents.base import BaseAgent
from agents.models import AgentConfig, AgentType, CodeResult

logger = logging.getLogger(__name__)


class CoderAgent:
    """
    CoderAgent - Generates executable code using LLM.

    Uses LLM to:
    - Write complete code from task description
    - Use Skills as reference templates
    - Save code to SSH workdir
    """

    def __init__(self, config: AgentConfig = None, shared_memory=None, ssh_manager=None):
        self.config = config or AgentConfig.default_for(AgentType.CODER)
        self.name = self.config.name
        self.base = BaseAgent(ssh_manager=ssh_manager)
        self.shared_memory = shared_memory
        
        # LLM config
        self._api_key = os.getenv("OMICS_LLM_API_KEY")
        self._base_url = os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        self._model = os.getenv("OMICS_LLM_MODEL", "deepseek-chat")
        
        # Skills
        self._skills = self._load_skills()

    def _load_skills(self) -> dict:
        """Load available skills from skills directory."""
        skills = {}
        skills_dir = os.path.join(os.path.dirname(__file__), '..', 'skills')
        
        if os.path.exists(skills_dir):
            for skill_id in os.listdir(skills_dir):
                skill_path = os.path.join(skills_dir, skill_id)
                if os.path.isdir(skill_path):
                    # Try to read skill metadata
                    meta_path = os.path.join(skill_path, 'SKILL.md')
                    description = skill_id
                    template = ""
                    
                    if os.path.exists(meta_path):
                        with open(meta_path, 'r') as f:
                            content = f.read()
                            # Extract description from first heading
                            match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                            if match:
                                description = match.group(1)
                    
                    skills[skill_id] = {
                        'id': skill_id,
                        'description': description,
                        'path': skill_path
                    }
        
        logger.info(f"Coder: Loaded {len(skills)} skills: {list(skills.keys())}")
        return skills

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM API."""
        import aiohttp
        
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        logger.error(f"LLM API error: {resp.status} - {error}")
                        return None
                    
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return None

    async def generate(self, task_description: str, skill_id: str = None, language: str = "R") -> CodeResult:
        """
        Generate executable code for the task.
        
        Args:
            task_description: What the code should do
            skill_id: Optional skill to use as template
            language: "R" or "Python"
            
        Returns:
            CodeResult with generated code
        """
        logger.info(f"Coder: Generating {language} code for: {task_description[:50]}...")
        
        # Get context
        workdir = self.base.get_workdir("user") or "~/cellclaw_jobs"
        
        # Build prompt for LLM
        prompt = self._build_code_prompt(task_description, skill_id, language, workdir)
        
        # Call LLM
        response = await self._call_llm(prompt)
        
        if not response:
            logger.error("Coder: LLM returned empty response")
            return CodeResult(
                code=f"# ERROR: Failed to generate code for: {task_description}",
                language=language,
                skill_used=skill_id
            )
        
        # Extract code
        code = self._extract_code(response, language)
        
        if not code or len(code) < 50:
            logger.error(f"Coder: Generated code too short: {code[:100] if code else 'None'}")
            return CodeResult(
                code=f"# ERROR: Failed to generate valid code for: {task_description}",
                language=language,
                skill_used=skill_id
            )
        
        # Save to shared memory
        if self.shared_memory and skill_id:
            self.shared_memory.add_code_template(
                agent="coder",
                skill_id=skill_id,
                code=code,
                language=language
            )
        
        logger.info(f"Coder: Generated {len(code)} chars of {language} code")
        
        return CodeResult(
            code=code,
            language=language,
            skill_used=skill_id
        )

    def _build_code_prompt(self, task: str, skill_id: str, language: str, workdir: str) -> str:
        """Build prompt for code generation."""
        
        prompt = f"""生成完整的{language}代码来完成以下生物信息学任务：

任务: {task}
工作目录: {workdir}
语言: {language}

"""
        
        # Add skill context if available
        if skill_id and skill_id in self._skills:
            skill = self._skills[skill_id]
            prompt += f"\n参考技能: {skill['id']} - {skill['description']}\n"
        
        prompt += """
要求：
1. 代码要完整可运行，不要省略任何部分
2. 使用真实可用的函数和包
3. 添加适当的注释
4. 设置合理的工作目录
5. 输出结果要有清晰的命名和路径

只返回代码，不要其他解释。
"""
        
        return prompt

    def _extract_code(self, response: str, language: str) -> str:
        """Extract code from LLM response."""
        
        # Try markdown code blocks
        patterns = [
            rf'```(?:{language})?\n(.*?)```',
            rf'```\n(.*?)```',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            if matches:
                return matches[0].strip()
        
        # If no markdown, try to find code-like content
        lines = response.split('\n')
        code_lines = []
        in_code = False
        
        for line in lines:
            if line.strip().startswith(('library(', 'require(', 'import ', 'def ', 'function(', '#', '//')):
                in_code = True
            if in_code:
                code_lines.append(line)
        
        if code_lines:
            return '\n'.join(code_lines)
        
        # Return as-is if nothing else worked
        return response.strip()

    async def save_script(self, code: str, language: str, filename: str = None, user_id: str = None) -> str:
        """Save code to file."""
        import time
        import secrets
        
        if not filename:
            prefix = secrets.token_hex(4)
            ext = ".R" if language == "R" else ".py"
            filename = f"cellclaw_{prefix}{ext}"
        
        # Save locally
        local_dir = "/tmp/cellclaw_scripts"
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, filename)
        
        with open(local_path, 'w') as f:
            f.write(code)
        
        logger.info(f"Coder: Script saved to {local_path}")
        
        return local_path

    def __repr__(self) -> str:
        return f"<CoderAgent: {self.name}, skills={len(self._skills)}>"
