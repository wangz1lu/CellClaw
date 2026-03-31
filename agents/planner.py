"""
PlannerAgent - Task Planning and Decomposition
============================================

Analyzes user tasks, breaks them into steps, determines skill requirements.
"""

from __future__ import annotations
import os
import logging
from typing import Optional
from dataclasses import dataclass

from agents.base import BaseAgent
from agents.models import AgentConfig, AgentType, TaskStep, ExecutionPlan, Intent


logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    PlannerAgent understands user tasks and creates execution plans.
    
    Responsibilities:
    - Understand user intent from natural language
    - Determine if task is simple or complex
    - Identify required skills
    - Create step-by-step execution plan
    """
    
    # Conversational intents - should NOT trigger tasks
    CONVERSATIONAL_PATTERNS = [
        "你好", "hi", "hello", "嗨", "在吗", "在不在",
        "谢谢", "thanks", "谢了", "多谢",
        "help", "怎么", "如何", "怎样", "问一下",
        "再见", "拜拜", "晚安", "早安",
        "你是谁", "what can you do", "有什么用"
    ]
    
    def __init__(self, config: AgentConfig = None, shared_memory=None, ssh_manager=None):
        self.config = config or AgentConfig.default_for(AgentType.PLANNER)
        self.name = self.config.name
        self.base = BaseAgent(ssh_manager=ssh_manager)
        
        # Shared memory for cross-agent knowledge
        self.shared_memory = shared_memory
        
        # API config
        self._api_key = self.config.api_key or os.getenv("PLANNER_API_KEY") or os.getenv("OMICS_LLM_API_KEY")
        self._base_url = self.config.base_url or os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        self._model = self.config.model or os.getenv("PLANNER_MODEL") or os.getenv("OMICS_LLM_MODEL", "deepseek-chat")
        
        # Keyword mappings
        self._skill_triggers = {
            # DEG Analysis
            "deg": "deg_analysis",
            "差异分析": "deg_analysis",
            "差异基因": "deg_analysis",
            "differential": "deg_analysis",
            "findmarkers": "deg_analysis",
            
            # Visualization
            "umap": "visualization_R",
            "tsne": "visualization_R",
            "热图": "visualization_R",
            "heatmap": "visualization_R",
            "violin": "visualization_R",
            "dotplot": "visualization_R",
            "featureplot": "visualization_R",
            "ridgeplot": "visualization_R",
            "画图": "visualization_R",
            "可视化": "visualization_R",
            
            # CellChat
            "cellchat": "ccc_cellchat",
            "通信": "ccc_cellchat",
            "interaction": "ccc_cellchat",
            
            # Batch Correction
            "harmony": "batch_harmony",
            "batch": "batch_harmony",
            "批次": "batch_harmony",
            "整合": "batch_harmony",
            "integration": "batch_harmony",
            
            # Cell Annotation
            "annotation": "annotation_sctype",
            "细胞类型": "annotation_sctype",
            "celltype": "annotation_sctype",
            "marker": "annotation_sctype",
            "marker基因": "annotation_sctype",
            
            # scRNA
            "scrna": "scRNA_seurat",
            "seurat": "scRNA_seurat",
            
            # snRNA
            "snrna": "snRNA_scanpy",
            "nuclei": "snRNA_scanpy",
        }
        
        self._intent_keywords = {
            "analysis": ["分析", "分析一下", "跑一下", "计算", "做分析"],
            "visualization": ["画图", "可视化", "展示", "显示", "绘图"],
            "query": ["查看", "看看", "查一下", "有什么", "多少"],
            "management": ["添加", "删除", "切换", "设置", "配置"],
        }
    
    # ───────────────────────────────────────────────────────────────
    # Intent Understanding
    # ───────────────────────────────────────────────────────────────
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM API."""
        import aiohttp
        import os
        
        api_key = os.getenv("OMICS_LLM_API_KEY")
        base_url = os.getenv("OMICS_LLM_BASE_URL", "https://api.deepseek.com/v1")
        model = os.getenv("OMICS_LLM_MODEL", "deepseek-chat")
        
        if not api_key:
            logger.warning("No LLM API key configured")
            return None
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return None
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    async def understand(self, message: str, user_id: str) -> Intent:
        """
        Understand user intent from message.
        
        Args:
            message: User's message
            user_id: User ID for context
            
        Returns:
            Intent with parsed intent
        """
        message_lower = message.lower()
        
        # Determine intent type
        intent_type = "query"  # default
        for itype, keywords in self._intent_keywords.items():
            if any(kw in message_lower for kw in keywords):
                intent_type = itype
                break
        
        # Check for skill needs
        skill_needed = None
        for kw, skill_id in self._skill_triggers.items():
            if kw in message_lower:
                skill_needed = skill_id
                break
        
        # Determine if simple or complex
        is_simple = self._is_simple_task(message, intent_type)
        
        # Generate suggested steps
        suggested_steps = self._generate_steps(message, intent_type, skill_needed)
        
        confidence = 0.9 if skill_needed else (0.7 if intent_type != "query" else 0.5)
        
        result = Intent(
            original=message,
            intent_type=intent_type,
            is_simple_task=is_simple,
            confidence=confidence,
            skill_needed=skill_needed,
            suggested_steps=suggested_steps
        )
        logger.info(f"Understood intent: {intent_type}, simple={is_simple}, skill={skill_needed}")
        return result
    
    def _is_conversational(self, message: str) -> bool:
        """Check if message is pure conversation, not a task"""
        msg_lower = message.lower().strip()
        
        # Exact match or contains conversational pattern
        for pattern in self.CONVERSATIONAL_PATTERNS:
            if pattern.lower() in msg_lower:
                return True
        
        # Very short messages (< 5 chars) that aren't clearly tasks
        if len(msg_lower) < 5 and not any(c in msg_lower for c in ["分析", "做", "生成", "跑"]):
            return True
        
        return False
    
    def _is_simple_task(self, message: str, intent_type: str) -> bool:
        """Determine if task is simple (single step)"""
        # Conversational messages are NOT tasks
        if self._is_conversational(message):
            return False
        
        simple_indicators = [
            "查看状态", "list", "ls", "status",
            "查看列表", "有什么", "状态"
        ]
        complex_indicators = [
            "分析", "比较", "整合", "计算",
            "做", "跑", "生成", "执行"
        ]
        
        # If contains complex indicators, not simple
        if any(ind in message.lower() for ind in complex_indicators):
            return False
        
        # If contains simple indicators, simple
        if any(ind in message.lower() for ind in simple_indicators):
            return True
        
        # Default: complex for analysis/visualization, simple for query
        return intent_type in ["query", "management"]
    
    def _generate_steps(self, message: str, intent_type: str, skill_needed: str = None) -> list[str]:
        """Generate suggested execution steps"""
        steps = []
        
        if intent_type == "query":
            steps.append("执行查询命令")
            steps.append("返回结果给用户")
        
        elif intent_type == "analysis":
            if skill_needed == "deg_analysis":
                steps.append("加载数据")
                steps.append("数据预处理")
                steps.append("执行差异分析")
                steps.append("生成结果报告")
            elif skill_needed == "visualization_R":
                steps.append("加载数据")
                steps.append("数据预处理")
                steps.append("生成可视化图表")
                steps.append("保存图片")
            else:
                steps.append("理解任务需求")
                steps.append("生成分析代码")
                steps.append("执行代码")
                steps.append("收集结果")
        
        elif intent_type == "visualization":
            steps.append("加载数据")
            steps.append("选择可视化类型")
            steps.append("生成图表")
            steps.append("保存并展示")
        
        elif intent_type == "management":
            steps.append("验证操作权限")
            steps.append("执行管理操作")
            steps.append("确认结果")
        
        return steps
    
    # ───────────────────────────────────────────────────────────────
    # Plan Creation
    # ───────────────────────────────────────────────────────────────
    
    def create_plan(self, message: str, intent, user_id: str) -> ExecutionPlan:
        """
        Create an execution plan based on intent.
        
        Args:
            message: User's message
            user_id: User ID
            intent: Pre-computed intent (optional)
            
        Returns:
            ExecutionPlan with steps
        """
        import secrets
        
        if intent is None:
            # Run synchronously for simplicity
            import asyncio
            intent = asyncio.get_event_loop().run_until_complete(
                self.understand(message, user_id)
            )
        
        plan_id = secrets.token_hex(4)
        plan = ExecutionPlan(
            plan_id=plan_id,
            user_id=user_id,
            original_task=message,
        )
        
        if intent.is_simple_task:
            # Simple task: single step
            plan.add_step(TaskStep(
                id=f"{plan_id}_1",
                description=intent.suggested_steps[0] if intent.suggested_steps else "执行任务",
                skill_id=intent.skill_needed,
            ))
        
        else:
            # Complex task: multiple steps
            for i, desc in enumerate(intent.suggested_steps, 1):
                step = TaskStep(
                    id=f"{plan_id}_{i}",
                    description=desc,
                    skill_id=intent.skill_needed if i == 2 else None,  # Code gen step needs skill
                )
                plan.add_step(step)
        
        logger.info(f"Created plan {plan_id} with {len(plan.steps)} steps")
        
        return plan
    
    # ───────────────────────────────────────────────────────────────
    # Skill Detection
    # ───────────────────────────────────────────────────────────────
    
    def detect_skill(self, message: str) -> Optional[str]:
        """
        Detect if a skill is needed based on message keywords.
        
        Args:
            message: User's message
            
        Returns:
            Skill ID if detected, None otherwise
        """
        message_lower = message.lower()
        
        for keyword, skill_id in self._skill_triggers.items():
            if keyword in message_lower:
                logger.info(f"Detected skill: {skill_id} (keyword: {keyword})")
                return skill_id
        
        return None
    
    def get_available_skills(self) -> list[str]:
        """Get list of available skill IDs"""
        return list(set(self._skill_triggers.values()))
    
    # ───────────────────────────────────────────────────────────────
    # LLM Integration (Optional)
    # ───────────────────────────────────────────────────────────────
    
    async def understand_with_llm(self, message: str, user_id: str) -> Intent:
        """
        Use LLM for more sophisticated intent understanding.
        Falls back to keyword-based if LLM unavailable.
        """
        try:
            # Build context
            context = self.base.build_context_for_llm(user_id)
            
            prompt = f"""分析用户消息，确定:
1. 任务类型 (analysis/visualization/query/management)
2. 是否简单任务
3. 需要哪个 Skill (如果有)
4. 执行步骤

用户消息: {message}

上下文:
{context}

请以JSON格式返回:
{{
  "intent_type": "...",
  "is_simple": true/false,
  "confidence": 0.0-1.0,
  "skill_needed": "skill_id" 或 null,
  "suggested_steps": ["步骤1", "步骤2", ...]
}}"""
            
            # TODO: Call LLM here when integration is ready
            # For now, fall back to keyword-based
            
        except Exception as e:
            logger.warning(f"LLM understanding failed, using keyword fallback: {e}")
        
        # Fallback to keyword-based
        return await self.understand(message, user_id)
    
    def __repr__(self) -> str:
        return f"<PlannerAgent: {self.name}>"
