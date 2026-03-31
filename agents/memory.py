"""
SharedMemory - Cross-Agent Knowledge Sharing
=========================================

Provides shared long-term memory for all agents:
- Skill knowledge base
- Server/environment info
- User preferences
- Code snippets
- Learned patterns
"""

from __future__ import annotations
import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeEntry:
    """A single knowledge entry"""
    id: str
    agent: str  # Which agent added this
    category: str  # "skill", "code", "pattern", "preference"
    content: Any  # The knowledge content
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    usage_count: int = 0


@dataclass
class SkillKnowledge:
    """Skill-related knowledge"""
    skill_id: str
    task_patterns: List[str]  # User phrases that triggered this skill
    code_templates: List[str]  # Successful code patterns
    review_notes: List[str]  # Common issues found


class SharedMemory:
    """
    Shared memory accessible by all agents.
    
    Agents can:
    - add_knowledge() - Add new knowledge
    - get_relevant() - Query relevant knowledge
    - update_usage() - Track usage for prioritization
    """

    def __init__(self):
        # Knowledge storage
        self._knowledge: Dict[str, KnowledgeEntry] = {}
        
        # Skill knowledge base
        self._skill_knowledge: Dict[str, SkillKnowledge] = {}
        
        # Server configs per user
        self._server_configs: Dict[str, dict] = {}
        
        # User preferences
        self._user_preferences: Dict[str, dict] = {}
        
        # Code snippets library
        self._code_snippets: List[dict] = []
        
        # Index for fast lookup
        self._tag_index: Dict[str, set] = defaultdict(set)
        
        logger.info("SharedMemory initialized")

    # ───────────────────────────────────────────────────────────────
    # Knowledge Management
    # ───────────────────────────────────────────────────────────────

    def add_knowledge(self, agent: str, category: str, content: Any, 
                     tags: List[str] = None, skill_id: str = None) -> str:
        """
        Add knowledge to shared memory.
        
        Args:
            agent: Name of agent adding knowledge
            category: Type of knowledge (skill, code, pattern, preference)
            content: The knowledge content
            tags: Searchable tags
            skill_id: Associated skill ID (for skill-related knowledge)
            
        Returns:
            knowledge_id
        """
        import secrets
        knowledge_id = secrets.token_hex(4)
        
        entry = KnowledgeEntry(
            id=knowledge_id,
            agent=agent,
            category=category,
            content=content,
            tags=tags or []
        )
        
        self._knowledge[knowledge_id] = entry
        
        # Update tag index
        for tag in entry.tags:
            self._tag_index[tag].add(knowledge_id)
        
        # If skill-related, update skill knowledge
        if skill_id and category == "skill":
            if skill_id not in self._skill_knowledge:
                self._skill_knowledge[skill_id] = SkillKnowledge(
                    skill_id=skill_id,
                    task_patterns=[],
                    code_templates=[],
                    review_notes=[]
                )
            
            sk = self._skill_knowledge[skill_id]
            if category == "pattern":
                sk.task_patterns.append(str(content))
            elif category == "code":
                sk.code_templates.append(str(content))
        
        logger.info(f"SharedMemory: {agent} added {category} knowledge: {knowledge_id}")
        
        return knowledge_id

    def get_relevant(self, query: str, category: str = None, 
                   limit: int = 5) -> List[KnowledgeEntry]:
        """
        Get knowledge relevant to query.
        
        Args:
            query: Search query
            category: Filter by category (optional)
            limit: Max results
            
        Returns:
            List of relevant knowledge entries
        """
        results = []
        query_lower = query.lower()
        
        # Search by tags and content
        for entry in self._knowledge.values():
            if category and entry.category != category:
                continue
            
            # Simple relevance: check if query words in tags or content
            score = 0
            content_str = str(entry.content).lower()
            
            for word in query_lower.split():
                if word in entry.tags:
                    score += 3
                if word in content_str:
                    score += 1
            
            if score > 0:
                entry.usage_count += 1
                results.append((score, entry))
        
        # Sort by score and return top N
        results.sort(key=lambda x: x[0], reverse=True)
        
        return [entry for _, entry in results[:limit]]

    def add_skill_pattern(self, agent: str, skill_id: str, pattern: str):
        """Add a successful task pattern for a skill"""
        self.add_knowledge(
            agent=agent,
            category="pattern",
            content={"skill_id": skill_id, "pattern": pattern},
            tags=[skill_id, "pattern", pattern.lower()],
            skill_id=skill_id
        )

    def add_code_template(self, agent: str, skill_id: str, code: str, language: str = "R"):
        """Add a successful code template for a skill"""
        self.add_knowledge(
            agent=agent,
            category="code",
            content={"skill_id": skill_id, "code": code, "language": language},
            tags=[skill_id, "code", language],
            skill_id=skill_id
        )

    def add_review_note(self, agent: str, skill_id: str, note: str, issue_type: str):
        """Add a review note/lesson learned"""
        self.add_knowledge(
            agent=agent,
            category="review",
            content={"skill_id": skill_id, "note": note, "issue_type": issue_type},
            tags=[skill_id, "review", issue_type],
            skill_id=skill_id
        )

    # ───────────────────────────────────────────────────────────────
    # User Preferences
    # ───────────────────────────────────────────────────────────────

    def set_user_preference(self, user_id: str, key: str, value: Any):
        """Set a user preference"""
        if user_id not in self._user_preferences:
            self._user_preferences[user_id] = {}
        self._user_preferences[user_id][key] = value
        logger.info(f"SharedMemory: Set preference {key}={value} for user {user_id}")

    def get_user_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        """Get a user preference"""
        return self._user_preferences.get(user_id, {}).get(key, default)

    # ───────────────────────────────────────────────────────────────
    # Server Configs
    # ───────────────────────────────────────────────────────────────

    def set_server_config(self, user_id: str, server_id: str, config: dict):
        """Set server configuration for user"""
        if user_id not in self._server_configs:
            self._server_configs[user_id] = {}
        self._server_configs[user_id][server_id] = config
        logger.info(f"SharedMemory: Updated server {server_id} config for user {user_id}")

    def get_server_config(self, user_id: str, server_id: str = None) -> Optional[dict]:
        """Get server configuration"""
        if server_id:
            return self._server_configs.get(user_id, {}).get(server_id)
        # Return all servers for user
        return self._server_configs.get(user_id, {})

    # ───────────────────────────────────────────────────────────────
    # Statistics
    # ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get memory statistics"""
        return {
            "total_knowledge": len(self._knowledge),
            "skill_knowledge": len(self._skill_knowledge),
            "code_snippets": len(self._code_snippets),
            "users": len(self._user_preferences),
            "top_tags": sorted(
                [(tag, len(ids)) for tag, ids in self._tag_index.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }


# ─────────────────────────────────────────────────────────────────
# TaskMemory - Single Task Context
# ─────────────────────────────────────────────────────────────────

class TaskMemory:
    """
    Memory specific to a single task execution.
    Created for each plan, shared among agents during that plan's execution.
    """

    def __init__(self, plan_id: str):
        self.plan_id = plan_id
        self.steps_completed = []
        self.current_step = 0
        self.generated_codes = []  # Code generated for this task
        self.review_history = []  # Review results for this task
        self.errors = []  # Errors encountered
        self.created_at = datetime.now()

    def add_generated_code(self, step: int, code: str, language: str = "R"):
        """Record generated code for a step"""
        self.generated_codes.append({
            "step": step,
            "code": code,
            "language": language,
            "timestamp": datetime.now()
        })

    def add_review(self, step: int, result: dict):
        """Record review result for a step"""
        self.review_history.append({
            "step": step,
            "result": result,
            "timestamp": datetime.now()
        })

    def add_error(self, step: int, error: str):
        """Record an error"""
        self.errors.append({
            "step": step,
            "error": error,
            "timestamp": datetime.now()
        })

    def get_summary(self) -> dict:
        """Get task memory summary"""
        return {
            "plan_id": self.plan_id,
            "steps_completed": len(self.steps_completed),
            "codes_generated": len(self.generated_codes),
            "reviews_done": len(self.review_history),
            "errors": len(self.errors),
            "duration": (datetime.now() - self.created_at).total_seconds()
        }


# ─────────────────────────────────────────────────────────────────
# Global Instance
# ─────────────────────────────────────────────────────────────────

_shared_memory: Optional[SharedMemory] = None


def get_shared_memory() -> SharedMemory:
    """Get or create global shared memory instance"""
    global _shared_memory
    if _shared_memory is None:
        _shared_memory = SharedMemory()
    return _shared_memory
