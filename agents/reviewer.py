"""
ReviewerAgent - Code Review
===========================

Reviews generated code for errors, path issues, and best practices.
"""

from __future__ import annotations
import os
import re
import logging
from typing import Optional
from dataclasses import dataclass

from agents.base import BaseAgent
from agents.models import AgentConfig, AgentType

logger = logging.getLogger(__name__)


@dataclass
class ReviewIssue:
    """A single issue found during review"""
    severity: str  # "error", "warning", "info"
    category: str  # "syntax", "path", "logic", "security"
    message: str
    line: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class ReviewResult:
    """Result of code review"""
    is_valid: bool
    issues: list
    can_execute: bool  # True if code is safe to run
    
    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")
    
    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


class ReviewerAgent:
    """
    ReviewerAgent checks generated code for problems.
    
    Checks:
    - Syntax errors
    - Path validity
    - Security issues
    - Best practices
    """
    
    # Common path patterns that need validation
    REQUIRED_PATH_VARS = ["input_file", "output_file", "workdir", "data_dir"]
    
    def __init__(self, config: AgentConfig = None, shared_memory=None, ssh_manager=None):
        self.config = config or AgentConfig.default_for(AgentType.REVIEWER)
        self.name = self.config.name
        self.base = BaseAgent(ssh_manager=ssh_manager)
        
        # Shared memory for cross-agent knowledge
        self.shared_memory = shared_memory
        
        # API config
        self._api_key = self.config.api_key or os.getenv("REVIEWER_API_KEY") or os.getenv("OMICS_LLM_API_KEY")
    
    # ───────────────────────────────────────────────────────────────
    # Main Review
    # ───────────────────────────────────────────────────────────────
    
    async def check(self, code: str, language: str = "R") -> ReviewResult:
        """
        Review generated code.
        
        Args:
            code: Code to review
            language: "R" or "Python"
            
        Returns:
            ReviewResult with issues found
        """
        issues = []
        
        # 1. Syntax check
        syntax_issues = self._check_syntax(code, language)
        issues.extend(syntax_issues)
        
        # 2. Path check
        path_issues = self._check_paths(code, language)
        issues.extend(path_issues)
        
        # 3. Security check
        security_issues = self._check_security(code, language)
        issues.extend(security_issues)
        
        # 4. Best practice check
        practice_issues = self._check_best_practices(code, language)
        issues.extend(practice_issues)
        
        # Determine if can execute
        can_execute = not any(i.severity == "error" for i in issues)
        
        result = ReviewResult(
            is_valid=can_execute,
            issues=issues,
            can_execute=can_execute,
        )
        
        logger.info(f"Review complete: {result.error_count} errors, {result.warning_count} warnings")
        
        # Learn from review - save patterns/issues to shared memory
        if self.shared_memory:
            for issue in issues:
                self.shared_memory.add_review_note(
                    agent="reviewer",
                    skill_id=None,  # Could extract from code context
                    note=issue.message,
                    issue_type=issue.category
                )
        
        return result
    
    # ───────────────────────────────────────────────────────────────
    # Syntax Check
    # ───────────────────────────────────────────────────────────────
    
    def _check_syntax(self, code: str, language: str) -> list:
        """Check for syntax errors"""
        issues = []
        
        if language == "R":
            # Common R syntax issues
            if re.search(r'[^\\]"\s*$', code, re.MULTILINE):
                issues.append(ReviewIssue(
                    severity="error",
                    category="syntax",
                    message="Unclosed string literal",
                    suggestion="Ensure all strings are closed with matching quotes"
                ))
            
            # Check for unmatched parentheses
            open_parens = code.count("(")
            close_parens = code.count(")")
            if open_parens != close_parens:
                issues.append(ReviewIssue(
                    severity="error",
                    category="syntax",
                    message=f"Unmatched parentheses: {open_parens} ( vs {close_parens} )",
                ))
        
        elif language == "Python":
            # Basic Python syntax checks
            if "import " not in code and "from " not in code:
                issues.append(ReviewIssue(
                    severity="info",
                    category="syntax",
                    message="No imports found - code may be incomplete",
                ))
        
        return issues
    
    # ───────────────────────────────────────────────────────────────
    # Path Check
    # ───────────────────────────────────────────────────────────────
    
    def _check_paths(self, code: str, language: str) -> list:
        """Check for path issues"""
        issues = []
        
        # Check for hardcoded paths
        hardcoded_paths = re.findall(r'["\'](/[a-zA-Z0-9_/.-]+)["\']', code)
        for path in hardcoded_paths:
            # Skip system paths that are commonly used
            if any(skip in path for skip in ["/usr/", "/bin/", "/opt/", "/etc/"]):
                continue
            
            # Check for Windows paths
            if re.match(r'^[A-Z]:\\', path):
                issues.append(ReviewIssue(
                    severity="warning",
                    category="path",
                    message=f"Windows absolute path detected: {path}",
                    suggestion="Use relative paths or environment variables for portability"
                ))
            
            # Check for unset variables in path
            if "{" in path or "}" in path:
                issues.append(ReviewIssue(
                    severity="warning",
                    category="path",
                    message=f"Path contains variable placeholders: {path}",
                    suggestion="Ensure variables are defined before use"
                ))
        
        # Check for read.csv without check.names
        if "read.csv" in code or "readRDS" in code:
            issues.append(ReviewIssue(
                severity="info",
                category="path",
                message="Data loading detected",
                suggestion="Ensure input file exists and path is correct"
            ))
        
        return issues
    
    # ───────────────────────────────────────────────────────────────
    # Security Check
    # ───────────────────────────────────────────────────────────────
    
    def _check_security(self, code: str, language: str) -> list:
        """Check for security issues"""
        issues = []
        
        # Check for system commands
        if language == "R":
            if "system(" in code or "shell.exec" in code:
                issues.append(ReviewIssue(
                    severity="warning",
                    category="security",
                    message="System command execution detected",
                    suggestion="Avoid shell commands in production code"
                ))
        
        elif language == "Python":
            if "os.system" in code or "subprocess.call" in code or "eval(" in code:
                issues.append(ReviewIssue(
                    severity="warning",
                    category="security",
                    message="Potentially unsafe command execution",
                    suggestion="Use safer alternatives like subprocess.run with shell=False"
                ))
        
        # Check for passwords/keys in code
        password_patterns = [
            r'password\s*=', r'api_key\s*=', r'secret\s*=',
            r'token\s*=', r'auth\s*='
        ]
        for pattern in password_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(ReviewIssue(
                    severity="error",
                    category="security",
                    message=f"Potential credential in code: {pattern}",
                    suggestion="Use environment variables or config files instead"
                ))
        
        return issues
    
    # ───────────────────────────────────────────────────────────────
    # Best Practice Check
    # ───────────────────────────────────────────────────────────────
    
    def _check_best_practices(self, code: str, language: str) -> list:
        """Check for best practice violations"""
        issues = []
        
        if language == "R":
            # Check for library() vs require()
            if "require(" in code and "library(" not in code:
                issues.append(ReviewIssue(
                    severity="info",
                    category="logic",
                    message="Using require() instead of library()",
                    suggestion="Use library() for package loading as it gives better error messages"
                ))
            
            # Check for paste0 vs paste
            if "paste0(" not in code and "paste(" in code and "+" not in code:
                issues.append(ReviewIssue(
                    severity="info",
                    category="logic",
                    message="Using paste() instead of paste0()",
                    suggestion="Use paste0() for concatenation without separator"
                ))
        
        elif language == "Python":
            # Check for print vs logging
            if "print(" in code and "logging" not in code:
                issues.append(ReviewIssue(
                    severity="info",
                    category="logic",
                    message="Using print() instead of logging",
                    suggestion="Consider using logging module for production code"
                ))
            
            # Check for // vs / in Python 3
            if "/\d" in code or "/\w" in code:
                issues.append(ReviewIssue(
                    severity="warning",
                    category="syntax",
                    message="Potential integer division issue",
                    suggestion="Use // for integer division in Python 3"
                ))
        
        return issues
    
    # ───────────────────────────────────────────────────────────────
    # LLM-Assisted Review (Optional)
    # ───────────────────────────────────────────────────────────────
    
    async def check_with_llm(self, code: str, language: str) -> ReviewResult:
        """
        Use LLM for more sophisticated code review.
        """
        # TODO: Implement LLM-based review
        # For now, fall back to static analysis
        
        return await self.check(code, language)
    
    async def fix(self, code: str, issues: list) -> str:
        """
        Attempt to fix code issues.
        
        Args:
            code: The code with issues
            issues: List of issues to fix
            
        Returns:
            Fixed code (or original if cannot fix)
        """
        logger.info(f"Reviewer: Attempting to fix {len(issues)} issues")
        
        # Simple fix logic - in a real system this would use LLM
        fixed_code = code
        
        for issue in issues:
            # Try to fix common issues
            if issue.category == "syntax":
                pass
            elif issue.category == "path":
                pass
        
        return fixed_code

    async def check_from_ssh(self, remote_path: str, language: str) -> ReviewResult:
        """
        Read script from SSH and check it.
        Used in the full pipeline after Coder writes to SSH.
        """
        import subprocess
        
        # Read from SSH
        if hasattr(self.base, '_ssh_manager') and self.base._ssh_manager:
            try:
                # Use scp or sftp to read
                result = await self.base._ssh_manager.run(
                    self.base._ssh_manager._registry._user_id or "user",
                    f"cat {remote_path}"
                )
                if result and result.success:
                    return await self.check(result.stdout, language)
            except:
                pass
        
        # Fallback - read locally if exists
        if os.path.exists(remote_path):
            with open(remote_path, 'r') as f:
                code = f.read()
            return await self.check(code, language)
        
        # Return failed result if can't read
        return ReviewResult(
            is_valid=False,
            issues=[ReviewIssue(category="file", severity="error", message=f"Cannot read {remote_path}")],
            can_execute=False
        )

    async def fix_from_ssh(self, remote_path: str, issues: list) -> str:
        """
        Fix script issues and rewrite to SSH.
        """
        # Read current code
        if hasattr(self.base, '_ssh_manager') and self.base._ssh_manager:
            try:
                result = await self.base._ssh_manager.run(
                    self.base._ssh_manager._registry._user_id or "user",
                    f"cat {remote_path}"
                )
                if result and result.success:
                    code = result.stdout
                    fixed_code = await self.fix(code, issues)
                    # Rewrite to SSH
                    escaped_code = fixed_code.replace("'", "'\''").replace("\n", "\\n")
                    cmd = f"cat > {remote_path} << 'SCRIPT_EOF'\n{fixed_code}\nSCRIPT_EOF"
                    await self.base._ssh_manager.run(
                        self.base._ssh_manager._registry._user_id or "user",
                        cmd
                    )
                    return fixed_code
            except:
                pass
        
        return ""

    def __repr__(self) -> str:
        return f"<ReviewerAgent: {self.name}>"
