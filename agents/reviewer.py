"""
ReviewerAgent - Code Review with LLM
=====================================

Uses LLM to:
1. Check code for syntax errors
2. Review code logic and best practices
3. Suggest improvements
"""

from __future__ import annotations
import os
import re
import logging
from typing import List, Optional

from agents.base import BaseAgent
from agents.models import AgentConfig, AgentType, ReviewResult, ReviewIssue

logger = logging.getLogger(__name__)


class ReviewerAgent:
    """
    ReviewerAgent - Reviews code using LLM.

    Uses LLM to:
    - Check syntax errors
    - Review code logic
    - Suggest improvements
    - Approve or request changes
    """

    def __init__(self, config: AgentConfig = None, shared_memory=None, ssh_manager=None):
        self.config = config or AgentConfig.default_for(AgentType.REVIEWER)
        self.name = self.config.name
        self.base = BaseAgent(ssh_manager=ssh_manager)
        self.shared_memory = shared_memory
        
        # LLM config
        self._api_key = os.getenv("OMICS_LLM_API_KEY")
        self._base_url = os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        self._model = os.getenv("OMICS_LLM_MODEL", "deepseek-chat")

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
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status != 200:
                        return None
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return None

    async def check(self, code: str, language: str) -> ReviewResult:
        """
        Review code and check for issues.
        
        Args:
            code: The code to review
            language: "R" or "Python"
            
        Returns:
            ReviewResult with issues found
        """
        logger.info(f"Reviewer: Checking {len(code)} chars of {language} code")
        
        issues = []
        
        # Basic syntax check
        syntax_issues = self._check_syntax(code, language)
        issues.extend(syntax_issues)
        
        # Use LLM for deeper review
        llm_issues = await self._llm_review(code, language)
        issues.extend(llm_issues)
        
        can_execute = not any(i.severity == "error" for i in issues)
        
        result = ReviewResult(
            is_valid=can_execute,
            issues=issues,
            can_execute=can_execute
        )
        
        logger.info(f"Reviewer: Found {len(issues)} issues, can_execute={can_execute}")
        
        return result

    def _check_syntax(self, code: str, language: str) -> List[ReviewIssue]:
        """Basic syntax checking."""
        issues = []
        
        if language == "R":
            # Check for common R issues
            if "read.csv" in code and "header" not in code.lower():
                issues.append(ReviewIssue(
                    category="syntax",
                    severity="warning",
                    message="Consider adding header=TRUE if file has headers"
                ))
            
            if "library(" in code or "require(" in code:
                # Check for package loading without error handling
                if "!require(" not in code and "!library(" not in code:
                    issues.append(ReviewIssue(
                        category="best_practice",
                        severity="warning",
                        message="Consider adding error handling for package loading"
                    ))
        
        elif language == "Python":
            if "import " in code:
                if "try:" not in code and "except" not in code:
                    issues.append(ReviewIssue(
                        category="best_practice",
                        severity="warning",
                        message="Consider adding try/except for imports"
                    ))
        
        return issues

    async def _llm_review(self, code: str, language: str) -> List[ReviewIssue]:
        """Use LLM to review code."""
        prompt = f"""审查以下{language}代码，检查问题：

```{language}
{code[:3000]}
```

请检查：
1. 语法错误
2. 逻辑问题
3. 最佳实践
4. 潜在的bug

以JSON格式返回发现的问题：
[
    {{
        "category": "syntax/logic/best_practice/bug",
        "severity": "error/warning/info",
        "message": "具体问题描述",
        "line_hint": "可能的行号或代码片段"
    }}
]

如果没有问题，返回空数组 []。
只返回JSON，不要其他内容。"""

        response = await self._call_llm(prompt)
        
        if not response:
            return []
        
        try:
            # Try to parse as JSON
            import json
            data = json.loads(response)
            if isinstance(data, list):
                return [
                    ReviewIssue(
                        category=item.get('category', 'unknown'),
                        severity=item.get('severity', 'warning'),
                        message=item.get('message', '')
                    )
                    for item in data
                ]
        except:
            pass
        
        return []

    async def fix(self, code: str, issues: List[ReviewIssue]) -> str:
        """
        Fix code based on issues.
        
        Args:
            code: Original code
            issues: List of issues to fix
            
        Returns:
            Fixed code
        """
        if not issues:
            return code
        
        logger.info(f"Reviewer: Fixing {len(issues)} issues")
        
        prompt = f"""修复以下代码中的问题：

```{self._detect_language(code)}
{code[:3000]}
```

问题列表：
{chr(10).join([f"- [{i.severity}] {i.message}" for i in issues])}

请修复这些问题，保持代码其他部分不变。
只返回修复后的代码，不要其他解释。"""

        response = await self._call_llm(prompt)
        
        if response:
            # Extract code
            fixed = self._extract_code(response)
            if fixed:
                return fixed
        
        return code

    def _detect_language(self, code: str) -> str:
        """Detect language from code content."""
        if any(kw in code for kw in ['library(', 'require(', '<-', 'ggplot', 'dplyr', 'tidyr']):
            return 'R'
        if any(kw in code for kw in ['import ', 'def ', 'pandas', 'numpy', 'matplotlib']):
            return 'Python'
        return 'text'

    def _extract_code(self, response: str) -> str:
        """Extract code from response."""
        patterns = [
            r'```(?:R|python)?\n(.*?)```',
            r'```\n(.*?)```',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            if matches:
                return matches[0].strip()
        
        return response.strip() if len(response) > 50 else ""

    def __repr__(self) -> str:
        return f"<ReviewerAgent: {self.name}>"
