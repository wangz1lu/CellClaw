# CellClaw Multi-Agent System

## Overview

CellClaw v2.0 introduces a **Multi-Agent Architecture** where specialized agents collaborate to handle bioinformatics tasks.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Orchestrator Agent                              │
│  - Intent understanding                                         │
│  - Workflow coordination                                        │
│  - Response aggregation                                         │
└─────────────────────────────────────────────────────────────────┘
         ↓              ↓              ↓              ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Base Agent   │ │ Planner Agent│ │ Coder Agent  │ │Reviewer Agent│
│              │ │              │ │              │ │              │
│ - Server info│ │ - Task       │ │ - Code gen   │ │ - Syntax     │
│ - Workdir    │ │   planning   │ │ - Templates   │ │ - Path       │
│ - Envs       │ │ - Skill det. │ │ - Skill KB   │ │ - Security   │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
                                                                ↓
                                              ┌──────────────────────────┐
                                              │ Executor Agent          │
                                              │                        │
                                              │ - Job submission        │
                                              │ - Status polling       │
                                              │ - Result collection    │
                                              │ - Dashboard sync       │
                                              └──────────────────────────┘
```

## Agents

### 1. BaseAgent
Manages foundational context:
- Server connections
- Working directories
- Conda environments
- User conversation history

### 2. PlannerAgent
Analyzes tasks and creates execution plans:
- Intent classification (analysis/visualization/query/management)
- Task decomposition into steps
- Skill detection

### 3. CoderAgent
Generates executable code:
- R/Python script generation
- Skill template integration
- Code templates for common tasks

### 4. ReviewerAgent
Reviews code before execution:
- Syntax validation
- Path checking
- Security scanning
- Best practice suggestions

### 5. ExecutorAgent
Handles job execution and monitoring:
- Background job submission
- Status polling
- Result collection
- Dashboard synchronization
- User notifications

## Usage

### Enable Multi-Agent Mode

```bash
# In .env file
MULTI_AGENT_ENABLED=true
```

### Python API

```python
from agents import MultiAgentSystem

# Create system
system = MultiAgentSystem()

# Process a task
response = await system.process("帮我做个DEG分析", "user123")

print(response)
# ✅ 任务已提交后台运行
# 📌 使用 Skill: deg_analysis
# 任务 PID: abc123
```

### Direct Agent Usage

```python
from agents import PlannerAgent, CoderAgent, ReviewerAgent

# Plan
planner = PlannerAgent()
intent = await planner.understand("画个UMAP图", user_id)

# Generate
coder = CoderAgent()
code = await coder.generate(intent.skill_needed, language="R")

# Review
reviewer = ReviewerAgent()
result = await reviewer.check(code.code, "R")
```

## Configuration

### Environment Variables

```env
# Default LLM (used by all agents if no agent-specific key set)
OMICS_LLM_API_KEY=sk-xxx
OMICS_LLM_BASE_URL=https://api.deepseek.com/v1
OMICS_LLM_MODEL=deepseek-chat

# Agent-specific overrides (optional)
ORCHESTRATOR_API_KEY=
PLANNER_API_KEY=
CODER_API_KEY=
REVIEWER_API_KEY=
EXECUTOR_API_KEY=

# Multi-agent mode
MULTI_AGENT_ENABLED=false
```

### API Key Priority

1. Agent-specific key (e.g., `CODER_API_KEY`)
2. Default key (`OMICS_LLM_API_KEY`)

## Testing

```bash
python test_multi_agent.py
```

## Files

```
agents/
├── __init__.py      # Exports
├── models.py        # Data models
├── base.py          # BaseAgent
├── orchestrator.py   # OrchestratorAgent
├── planner.py      # PlannerAgent
├── coder.py        # CoderAgent
├── reviewer.py     # ReviewerAgent
├── executor.py    # ExecutorAgent
├── integration.py # System integration
└── wrapper.py     # Wrapper for existing system
```

## Roadmap

- [x] Phase 1: Framework foundation
- [x] Phase 2: Agent implementations
- [x] Phase 3: Integration and testing
- [ ] Phase 4: Full system integration
- [ ] Phase 5: Real-time WebSocket updates
- [ ] Phase 6: Dashboard enhancements
