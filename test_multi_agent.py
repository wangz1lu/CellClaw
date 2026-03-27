#!/usr/bin/env python3
"""
Test Script for Multi-Agent System
=================================
"""

import sys
import asyncio
sys.path.insert(0, '/Users/wzlmac/.openclaw/workspace-developer/bioinfo_analysis/CellClaw')

from agents import (
    BaseAgent, OrchestratorAgent, PlannerAgent,
    CoderAgent, ReviewerAgent, ExecutorAgent,
    ExecutionPlan, TaskStep
)


def test_base_agent():
    """Test BaseAgent"""
    print("Testing BaseAgent...")
    agent = BaseAgent()
    
    # Test user context
    ctx = agent.get_user_context("test_user")
    print(f"  Created context: {ctx.user_id}")
    
    # Test context building
    ctx_str = agent.build_context_for_llm("test_user")
    print(f"  Context: {ctx_str[:50]}...")
    
    print("  ✓ BaseAgent OK\n")


def test_planner_agent():
    """Test PlannerAgent"""
    print("Testing PlannerAgent...")
    agent = PlannerAgent()
    
    # Test intent understanding
    test_messages = [
        "帮我做个DEG分析",
        "画个UMAP图",
        "查看当前服务器状态",
    ]
    
    for msg in test_messages:
        intent = asyncio.get_event_loop().run_until_complete(
            agent.understand(msg, "test_user")
        )
        print(f"  '{msg}'")
        print(f"    Intent: {intent.intent_type}, Simple: {intent.is_simple}, Skill: {intent.skill_needed}")
    
    # Test skill detection
    skill = agent.detect_skill("帮我做个差异分析")
    print(f"  Detected skill: {skill}")
    
    print("  ✓ PlannerAgent OK\n")


def test_coder_agent():
    """Test CoderAgent"""
    print("Testing CoderAgent...")
    agent = CoderAgent()
    
    # Test code generation with skill
    code = asyncio.get_event_loop().run_until_complete(
        agent.generate(
            task_description="Find DEG markers",
            skill_id="deg_analysis",
            language="R"
        )
    )
    print(f"  Generated {len(code.code)} chars of {code.language} code")
    print(f"  Skill used: {code.skill_used}")
    print(f"  Code preview:\n{code.code[:200]}...")
    
    print("  ✓ CoderAgent OK\n")


def test_reviewer_agent():
    """Test ReviewerAgent"""
    print("Testing ReviewerAgent...")
    agent = ReviewerAgent()
    
    # Test code review
    test_code = '''
library(Seurat)
data <- ReadRDS("/path/to/data.rds")
markers <- FindAllMarkers(data)
write.csv(markers, "/path/to/output.csv")
'''
    
    result = asyncio.get_event_loop().run_until_complete(
        agent.check(test_code, "R")
    )
    
    print(f"  Valid: {result.is_valid}")
    print(f"  Errors: {result.error_count}, Warnings: {result.warning_count}")
    
    for issue in result.issues[:3]:
        print(f"    [{issue.severity}] {issue.category}: {issue.message}")
    
    print("  ✓ ReviewerAgent OK\n")


def test_executor_agent():
    """Test ExecutorAgent"""
    print("Testing ExecutorAgent...")
    agent = ExecutorAgent()
    
    # Test job tracking
    job_id = asyncio.get_event_loop().run_until_complete(
        agent.submit("print('test')", "test_user", language="Python")
    )
    print(f"  Submitted job: {job_id}")
    
    status = agent.get_job_status(job_id)
    print(f"  Job status: {status.status}")
    
    print("  ✓ ExecutorAgent OK\n")


def test_orchestrator_agent():
    """Test OrchestratorAgent"""
    print("Testing OrchestratorAgent...")
    agent = OrchestratorAgent()
    
    # Test processing
    response = asyncio.get_event_loop().run_until_complete(
        agent.process("帮我做个DEG分析", "test_user")
    )
    print(f"  Response: {response[:100]}...")
    
    print("  ✓ OrchestratorAgent OK\n")


def test_models():
    """Test data models"""
    print("Testing Models...")
    
    # Test ExecutionPlan
    plan = ExecutionPlan(
        plan_id="test123",
        user_id="user1",
        original_task="Test task"
    )
    plan.add_step(TaskStep(id="s1", description="Step 1"))
    plan.add_step(TaskStep(id="s2", description="Step 2"))
    
    print(f"  Plan: {plan.plan_id}, Steps: {len(plan.steps)}")
    print(f"  Current step: {plan.get_current_step()}")
    
    plan.advance_step()
    print(f"  After advance: {plan.get_current_step()}")
    
    print("  ✓ Models OK\n")


def main():
    print("=" * 60)
    print("CellClaw Multi-Agent System Tests")
    print("=" * 60)
    print()
    
    try:
        test_base_agent()
        test_planner_agent()
        test_coder_agent()
        test_reviewer_agent()
        test_executor_agent()
        test_orchestrator_agent()
        test_models()
        
        print("=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
