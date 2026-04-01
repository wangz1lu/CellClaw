"""
State Manager for Multi-Bot Architecture
==========================================

Manages shared task state across all bots using Redis-like interface
with file-based fallback.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
import json
import os
import threading
import time
import uuid
import fcntl


class TaskStatus(str, Enum):
    """Task status states."""
    PENDING = "pending"
    PLANNING = "planning"
    CODING = "coding"
    REVIEWING = "reviewing"
    REVISING = "revising"      # Coder is fixing issues
    EXECUTING = "executing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubTaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SubTaskState:
    """State of a sub-task assigned to an agent."""
    subtask_id: str
    assigned_to: str           # Agent role
    instruction: str
    status: SubTaskStatus = SubTaskStatus.PENDING
    output: Optional[str] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    completed_at: Optional[str] = None


@dataclass
class TaskState:
    """
    Full task state tracked across all agents.
    
    This is the canonical state for a task being processed by the multi-bot system.
    """
    task_id: str
    leader_id: str
    channel_id: str
    
    description: str
    skill_needed: Optional[str] = None
    
    status: TaskStatus = TaskStatus.PENDING
    
    # Sub-tasks for each agent
    subtasks: Dict[str, SubTaskState] = field(default_factory=dict)
    
    # Code artifacts
    code: Optional[str] = None
    language: Optional[str] = None
    script_path: Optional[str] = None
    review_issues: List[str] = field(default_factory=list)
    
    # Execution
    job_id: Optional[str] = None
    log_path: Optional[str] = None
    result_files: List[str] = field(default_factory=list)
    
    # Plan
    plan_text: Optional[str] = None
    plan_path: Optional[str] = None
    
    # Timestamps
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%M"))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        d = asdict(self)
        # Convert enums to strings
        d['status'] = self.status.value if isinstance(self.status, TaskStatus) else self.status
        for k, v in d.get('subtasks', {}).items():
            if isinstance(v, SubTaskState):
                d['subtasks'][k] = {
                    'subtask_id': v.subtask_id,
                    'assigned_to': v.assigned_to,
                    'instruction': v.instruction,
                    'status': v.status.value if isinstance(v.status, SubTaskStatus) else v.status,
                    'output': v.output,
                    'error': v.error,
                    'created_at': v.created_at,
                    'updated_at': v.updated_at,
                    'completed_at': v.completed_at
                }
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> 'TaskState':
        """Create from dictionary."""
        if 'status' in d:
            d['status'] = TaskStatus(d['status'])
        for k, v in d.get('subtasks', {}).items():
            if isinstance(v, dict) and 'status' in v:
                v['status'] = SubTaskStatus(v['status'])
        return cls(**d)


class StateManager:
    """
    Shared state manager for multi-bot tasks.
    
    Uses file-based storage with locking for safety.
    Thread-safe and process-safe via fcntl.
    
    Usage:
        sm = StateManager()
        
        # Create task
        task = sm.create_task(leader_id="123", description="Do analysis")
        
        # Update task
        sm.update_subtask(task.task_id, "planner", status=SubTaskStatus.DONE, output="Plan created")
        
        # Get task
        task = sm.get_task(task.task_id)
    """
    
    def __init__(self, state_dir: str = "/tmp/cellclaw_state"):
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self._lock_file = os.path.join(state_dir, ".lock")
        self._tasks_file = os.path.join(state_dir, "tasks.json")
        
        # Ensure tasks file exists
        if not os.path.exists(self._tasks_file):
            self._save_all({})
    
    def _acquire_lock(self):
        """Acquire exclusive lock."""
        self._lock_fd = open(self._lock_file, 'w')
        fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX)
    
    def _release_lock(self):
        """Release lock."""
        if hasattr(self, '_lock_fd'):
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
            self._lock_fd.close()
    
    def _load_all(self) -> Dict[str, dict]:
        """Load all tasks from disk."""
        try:
            with open(self._tasks_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_all(self, tasks: Dict[str, dict]):
        """Save all tasks to disk."""
        with open(self._tasks_file, 'w') as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
    
    def create_task(
        self,
        leader_id: str,
        channel_id: str,
        description: str,
        skill_needed: Optional[str] = None
    ) -> TaskState:
        """Create a new task."""
        task_id = uuid.uuid4().hex[:12]
        
        task = TaskState(
            task_id=task_id,
            leader_id=leader_id,
            channel_id=channel_id,
            description=description,
            skill_needed=skill_needed,
            status=TaskStatus.PENDING,
            subtasks={
                "planner": SubTaskState(
                    subtask_id=f"{task_id}_planner",
                    assigned_to="planner",
                    instruction="Create execution plan"
                ),
                "coder": SubTaskState(
                    subtask_id=f"{task_id}_coder",
                    assigned_to="coder",
                    instruction="Generate code"
                ),
                "reviewer": SubTaskState(
                    subtask_id=f"{task_id}_reviewer",
                    assigned_to="reviewer",
                    instruction="Review code"
                ),
                "executor": SubTaskState(
                    subtask_id=f"{task_id}_executor",
                    assigned_to="executor",
                    instruction="Execute and notify"
                )
            }
        )
        
        self._acquire_lock()
        try:
            tasks = self._load_all()
            tasks[task_id] = task.to_dict()
            self._save_all(tasks)
        finally:
            self._release_lock()
        
        return task
    
    def get_task(self, task_id: str) -> Optional[TaskState]:
        """Get a task by ID."""
        self._acquire_lock()
        try:
            tasks = self._load_all()
            if task_id in tasks:
                return TaskState.from_dict(tasks[task_id])
            return None
        finally:
            self._release_lock()
    
    def update_task(self, task_id: str, **updates) -> Optional[TaskState]:
        """Update task fields."""
        self._acquire_lock()
        try:
            tasks = self._load_all()
            if task_id not in tasks:
                return None
            
            task_dict = tasks[task_id]
            task_dict['updated_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            for key, value in updates.items():
                if key in task_dict:
                    task_dict[key] = value
            
            tasks[task_id] = task_dict
            self._save_all(tasks)
            
            return TaskState.from_dict(task_dict)
        finally:
            self._release_lock()
    
    def update_subtask(
        self,
        task_id: str,
        subtask_key: str,
        status: SubTaskStatus = None,
        output: str = None,
        error: str = None
    ) -> Optional[TaskState]:
        """Update a sub-task state."""
        self._acquire_lock()
        try:
            tasks = self._load_all()
            if task_id not in tasks:
                return None
            
            task_dict = tasks[task_id]
            if subtask_key not in task_dict.get('subtasks', {}):
                return None
            
            subtask = task_dict['subtasks'][subtask_key]
            subtask['updated_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            if status:
                subtask['status'] = status.value if isinstance(status, SubTaskStatus) else status
                if status in (SubTaskStatus.DONE, SubTaskStatus.FAILED):
                    subtask['completed_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            if output is not None:
                subtask['output'] = output
            
            if error is not None:
                subtask['error'] = error
            
            tasks[task_id] = task_dict
            self._save_all(tasks)
            
            return TaskState.from_dict(task_dict)
        finally:
            self._release_lock()
    
    def advance_workflow(self, task_id: str) -> Optional[TaskState]:
        """
        Advance task to next workflow stage based on completed subtasks.
        
        Returns updated task state.
        """
        self._acquire_lock()
        try:
            tasks = self._load_all()
            if task_id not in tasks:
                return None
            
            task_dict = tasks[task_id]
            subtasks = task_dict.get('subtasks', {})
            
            planner_done = subtasks.get('planner', {}).get('status') == SubTaskStatus.DONE.value
            coder_done = subtasks.get('coder', {}).get('status') == SubTaskStatus.DONE.value
            reviewer_done = subtasks.get('reviewer', {}).get('status') == SubTaskStatus.DONE.value
            executor_done = subtasks.get('executor', {}).get('status') == SubTaskStatus.DONE.value
            
            # Determine next status
            if not planner_done:
                task_dict['status'] = TaskStatus.PLANNING.value
            elif not coder_done:
                task_dict['status'] = TaskStatus.CODING.value
            elif not reviewer_done:
                task_dict['status'] = TaskStatus.REVIEWING.value
            elif not executor_done:
                task_dict['status'] = TaskStatus.EXECUTING.value
            else:
                task_dict['status'] = TaskStatus.DONE.value
                task_dict['completed_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            task_dict['updated_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            tasks[task_id] = task_dict
            self._save_all(tasks)
            
            return TaskState.from_dict(task_dict)
        finally:
            self._release_lock()
    
    def list_tasks(self, leader_id: str = None, status: TaskStatus = None) -> List[TaskState]:
        """List tasks, optionally filtered."""
        self._acquire_lock()
        try:
            tasks = self._load_all()
            result = []
            
            for task_dict in tasks.values():
                if leader_id and task_dict.get('leader_id') != leader_id:
                    continue
                if status and task_dict.get('status') != status.value:
                    continue
                result.append(TaskState.from_dict(task_dict))
            
            return result
        finally:
            self._release_lock()
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        self._acquire_lock()
        try:
            tasks = self._load_all()
            if task_id in tasks:
                del tasks[task_id]
                self._save_all(tasks)
                return True
            return False
        finally:
            self._release_lock()
    
    def cleanup_old_tasks(self, hours: int = 24) -> int:
        """Delete tasks older than specified hours."""
        self._acquire_lock()
        try:
            tasks = self._load_all()
            cutoff = time.time() - (hours * 3600)
            deleted = 0
            
            for task_id, task_dict in list(tasks.items()):
                created = task_dict.get('created_at', '')
                if created:
                    try:
                        struct = time.strptime(created, "%Y-%m-%d %H:%M:%S")
                        if time.mktime(struct) < cutoff:
                            del tasks[task_id]
                            deleted += 1
                    except ValueError:
                        pass
            
            self._save_all(tasks)
            return deleted
        finally:
            self._release_lock()
