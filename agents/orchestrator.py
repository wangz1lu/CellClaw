"""
OrchestratorAgent - Main Coordinator
====================================

Coordinates all agents in the multi-agent system.
Routes requests to appropriate agents and aggregates results.
"""

from __future__ import annotations
import os
import logging
import asyncio
from typing import Optional, Any
from dataclasses import dataclass
import secrets

from agents.base import BaseAgent
from agents.models import (
    AgentConfig, AgentType, UserContext, 
    TaskStep, ExecutionPlan, PlanStatus, TaskStatus
)

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    """User intent parsed from message"""
    original: str
    is_simple_task: bool = False
    intent_type: str = "unknown"  # analysis, visualization, query, etc.
    skill_needed: Optional[str] = None
    confidence: float = 0.0


class OrchestratorAgent:
    """
    Main orchestrator that coordinates the multi-agent workflow.
    
    Workflow:
    1. Receive user message
    2. Understand intent (via Planner)
    3. Create execution plan
    4. Coordinate agents to execute plan
    5. Aggregate results
    6. Notify user
    """
    
    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig.default_for(AgentType.ORCHESTRATOR)
        self.name = self.config.name
        
        # Initialize base agent for context
        self.base = BaseAgent()
        
        # API config
        self._api_key = self.config.api_key or os.getenv("ORCHESTRATOR_API_KEY") or os.getenv("OMICS_LLM_API_KEY")
        self._base_url = self.config.base_url or os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        self._model = self.config.model or os.getenv("ORCHESTRATOR_MODEL") or os.getenv("OMICS_LLM_MODEL", "deepseek-chat")
        
        # Active plans
        self._plans: dict[str, ExecutionPlan] = {}
    
    # ───────────────────────────────────────────────────────────────
    # Main Processing
    # ───────────────────────────────────────────────────────────────
    
    async def process(self, message: str, user_id: str) -> str:
        """
        Main entry point for processing user messages.
        
        Returns:
            str: Response to send to user
        """
        logger.info(f"Orchestrator processing: {message[:100]}... for user {user_id}")
        
        # Add to history
        self.base.add_to_history(user_id, "user", message)
        
        # Step 1: Understand intent
        intent = await self._understand_intent(message, user_id)
        
        # Step 2: Create plan
        plan = await self._create_plan(message, intent, user_id)
        
        # Step 3: Execute plan
        result = await self._execute_plan(plan, user_id)
        
        # Step 4: Format response
        response = self._format_response(plan, result)
        
        # Add to history
        self.base.add_to_history(user_id, "assistant", response)
        
        return response
    
    async def _understand_intent(self, message: str, user_id: str) -> Intent:
        """
        Understand user intent from message.
        """
        intent = Intent(original=message)
        
        # Simple keyword-based detection first
        message_lower = message.lower()
        
        # Check for simple vs complex tasks
        simple_keywords = ["查看", "show", "list", "ls", "状态", "status", "help"]
        complex_keywords = ["分析", "analysis", "画图", "plot", "比较", "compare", "找出", "find"]
        
        if any(kw in message_lower for kw in simple_keywords):
            intent.is_simple_task = True
            intent.intent_type = "query"
        elif any(kw in message_lower for kw in complex_keywords):
            intent.is_simple_task = False
            intent.intent_type = "analysis"
        
        # Check for skill needs
        skill_keywords = {
            "deg": "deg_analysis",
            "差异": "deg_analysis",
            "umap": "visualization_R",
            "heatmap": "visualization_R",
            "cellchat": "ccc_cellchat",
            "annotation": "annotation_sctype",
            "celltype": "annotation_sctype",
            "harmony": "batch_harmony",
            "batch": "batch_harmony",
        }
        
        for kw, skill_id in skill_keywords.items():
            if kw in message_lower:
                intent.skill_needed = skill_id
                break
        
        intent.confidence = 0.8 if intent.skill_needed else 0.5
        
        logger.info(f"Intent: {intent.intent_type}, simple={intent.is_simple_task}, skill={intent.skill_needed}")
        
        return intent
    
    async def _create_plan(self, message: str, intent: Intent, user_id: str) -> ExecutionPlan:
        """
        Create an execution plan based on intent.
        """
        plan_id = secrets.token_hex(4)
        plan = ExecutionPlan(
            plan_id=plan_id,
            user_id=user_id,
            original_task=message,
        )
        
        if intent.is_simple_task:
            # Simple task: single step
            plan.add_step(TaskStep(
                id=f"{plan_id}_step_1",
                description=f"执行简单任务: {message}",
            ))
        else:
            # Complex task: multiple steps
            steps = [
                TaskStep(
                    id=f"{plan_id}_step_1",
                    description="理解任务需求",
                ),
                TaskStep(
                    id=f"{plan_id}_step_2", 
                    description="生成代码",
                    skill_id=intent.skill_needed,
                ),
                TaskStep(
                    id=f"{plan_id}_step_3",
                    description="审查代码",
                ),
                TaskStep(
                    id=f"{plan_id}_step_4",
                    description="执行并监控",
                ),
            ]
            
            for step in steps:
                plan.add_step(step)
        
        self._plans[plan_id] = plan
        logger.info(f"Created plan {plan_id} with {len(plan.steps)} steps")
        
        return plan
    
    async def _execute_plan(self, plan: ExecutionPlan, user_id: str) -> dict:
        """
        Execute the plan using appropriate agents.
        """
        results = {
            "status": "completed",
            "steps_completed": 0,
            "final_result": None,
        }
        
        for i, step in enumerate(plan.steps):
            logger.info(f"Executing step {i+1}/{len(plan.steps)}: {step.description}")
            step.status = TaskStatus.RUNNING
            
            try:
                if "理解" in step.description:
                    step.result = f"理解任务: {plan.original_task}"
                elif "生成" in step.description:
                    # Code generation would happen here
                    step.result = "代码生成完成"
                    step.code = "# Generated code placeholder"
                elif "审查" in step.description:
                    # Code review would happen here
                    step.result = "代码审查通过"
                elif "执行" in step.description:
                    # Execution would happen here
                    step.result = "任务执行完成"
                
                step.status = TaskStatus.DONE
                results["steps_completed"] += 1
                
            except Exception as e:
                logger.error(f"Step {step.id} failed: {e}")
                step.status = TaskStatus.FAILED
                step.error = str(e)
                results["status"] = "failed"
                break
        
        plan.status = PlanStatus.COMPLETED if results["status"] == "completed" else PlanStatus.FAILED
        results["final_result"] = f"完成了 {results['steps_completed']}/{len(plan.steps)} 个步骤"
        
        return results
    
    def _format_response(self, plan: ExecutionPlan, result: dict) -> str:
        """
        Format execution result for user.
        """
        if result["status"] == "completed":
            return f"✅ 任务完成！\n{result['final_result']}"
        else:
            return f"❌ 任务失败\n{result.get('final_result', '请检查日志')}"
    
    # ───────────────────────────────────────────────────────────────
    # Plan Management
    # ───────────────────────────────────────────────────────────────
    
    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get a plan by ID"""
        return self._plans.get(plan_id)
    
    def list_user_plans(self, user_id: str) -> list[ExecutionPlan]:
        """List all plans for a user"""
        return [p for p in self._plans.values() if p.user_id == user_id]
    
    def cancel_plan(self, plan_id: str) -> bool:
        """Cancel a running plan"""
        plan = self._plans.get(plan_id)
        if plan:
            plan.status = PlanStatus.FAILED
            for step in plan.steps:
                if step.status == TaskStatus.RUNNING:
                    step.status = TaskStatus.CANCELLED
            return True
        return False
    
    # ───────────────────────────────────────────────────────────────
    # Context Access
    # ───────────────────────────────────────────────────────────────
    
    def get_user_context(self, user_id: str) -> UserContext:
        """Get user context from base agent"""
        return self.base.get_user_context(user_id)
    
    def build_context(self, user_id: str) -> str:
        """Build context string for LLM"""
        return self.base.build_context_for_llm(user_id)
    
    def __repr__(self) -> str:
        return f"<OrchestratorAgent: {self.name}>"