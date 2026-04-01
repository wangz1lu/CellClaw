# CellClaw Multi-Bot Deployment Guide

## Overview

CellClaw Multi-Bot is a Discord-based multi-agent system where 5 independent bots work together in a group chat to complete bioinformatics tasks.

## Architecture

```
CellClaw Workspace (Discord Server)
├── 👤 leader (you)
│
├── 🤖 @CellClaw-Orchestrator
│       Receives tasks, coordinates workflow
│
├── 🧠 @CellClaw-Planner
│       Creates execution plans
│
├── 💻 @CellClaw-Coder
│       Generates code
│
├── 🔍 @CellClaw-Reviewer
│       Reviews code
│
└── ⚡ @CellClaw-Executor
        Executes on remote server
```

## Prerequisites

1. Python 3.10+
2. 5 Discord Bot Tokens
3. SSH access to remote server (for Executor)

## Installation

### 1. Clone and Setup

```bash
git clone https://github.com/wangz1lu/CellClaw.git
cd CellClaw
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install additional dependency for SSH
pip install asyncssh
```

### 2. Create Discord Applications

Go to https://discord.com/developers/applications and create 5 applications:

| Bot | Application Name | Purpose |
|-----|-----------------|---------|
| 1 | CellClaw-Orchestrator | Task coordinator |
| 2 | CellClaw-Planner | Execution planner |
| 3 | CellClaw-Coder | Code generator |
| 4 | CellClaw-Reviewer | Code reviewer |
| 5 | CellClaw-Executor | Remote executor |

For each:
1. Click **Bot** in left sidebar
2. Click **Add Bot**
3. Enable **Message Content Intent** (under Privileged Gateway Intents)
4. Copy **Token**

### 3. Configure Tokens

```bash
# Copy example config
cp bots/config.yaml .env.multi

# Edit with your tokens
nano .env.multi
```

```bash
CELLCRAW_ORCHESTRATOR_TOKEN=your_orchestrator_token
CELLCRAW_PLANNER_TOKEN=your_planner_token
CELLCRAW_CODER_TOKEN=your_coder_token
CELLCRAW_REVIEWER_TOKEN=your_reviewer_token
CELLCRAW_EXECUTOR_TOKEN=your_executor_token

OMICS_LLM_API_KEY=your_llm_api_key
CELLCRAW_EXECUTOR_SSH_HOST=your.server.com
CELLCRAW_EXECUTOR_SSH_PORT=22
CELLCRAW_EXECUTOR_SSH_USER=your_username
CELLCRAW_EXECUTOR_SSH_WORKDIR=/path/to/workdir
```

### 4. Create Discord Server

1. Open Discord
2. Click **+** (Create My Own)
3. Name it "CellClaw Workspace"
4. Create a channel called `#tasks`

### 5. Invite Bots

For each bot application:

1. Go to **OAuth2** → **URL Generator**
2. Check scopes: `bot`
3. Bot Permissions:
   - ✅ Send Messages
   - ✅ Read Message History
   - ✅ Mention @everyone
   - ✅ Attach Files
   - ✅ Add Reactions
4. Copy URL and open in browser
5. Select your server

### 6. Start Bots

```bash
# Start all bots
source venv/bin/activate
python main_multi.py all

# Or start individually
python main_multi.py orchestrator
python main_multi.py planner
python main_multi.py coder
python main_multi.py reviewer
python main_multi.py executor
```

## Usage

### Starting a Task

In the `#tasks` channel:

```
@CellClaw-Orchestrator 帮我做差异分析
```

### Workflow

1. **Orchestrator** receives task → creates task ID
2. **Planner** generates execution plan
3. **Coder** writes code
4. **Reviewer** checks code
5. **Executor** runs code on remote server
6. **Leader** receives completion notification

### Example Session

```
leader: @CellClaw-Orchestrator 帮我做差异分析

CellClaw-Orchestrator: ✅ Task received! Task ID: abc123xyz
CellClaw-Orchestrator: @CellClaw-Planner New Subtask - Task ID: abc123xyz

CellClaw-Planner: @CellClaw-Orchestrator Plan completed!
CellClaw-Orchestrator: @CellClaw-Coder New Subtask - Task ID: abc123xyz

CellClaw-Coder: @CellClaw-Orchestrator Code generated! (800 chars)

CellClaw-Orchestrator: @CellClaw-Reviewer New Subtask - Task ID: abc123xyz

CellClaw-Reviewer: @CellClaw-Orchestrator Code review passed! ✓

CellClaw-Orchestrator: @CellClaw-Executor New Subtask - Task ID: abc123xyz

CellClaw-Executor: 🚀 Job Submitted! Job ID: job_abc123

CellClaw-Executor: ✅ Task Completed! Task ID: abc123xyz

@leader ✅ Task abc123xyz completed successfully!
```

## Systemd Service (Production)

### Install Services

```bash
# Copy service files
sudo cp deploy/systemd/*.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable cellclaw-orchestrator
sudo systemctl enable cellclaw-planner
sudo systemctl enable cellclaw-coder
sudo systemctl enable cellclaw-reviewer
sudo systemctl enable cellclaw-executor

# Start services
sudo systemctl start cellclaw-orchestrator
sudo systemctl start cellclaw-planner
sudo systemctl start cellclaw-coder
sudo systemctl start cellclaw-reviewer
sudo systemctl start cellclaw-executor

# Check status
sudo systemctl status cellclaw-orchestrator
```

### View Logs

```bash
# View logs
sudo journalctl -u cellclaw-orchestrator -f
sudo tail -f /var/log/cellclaw/orchestrator.log
```

## Troubleshooting

### Bot Not Responding

1. Check bot is online in Discord (green status)
2. Check bot was invited to the correct server
3. Check message mentions the bot correctly (`@CellClaw-Orchestrator`)

### SSH Connection Failed

1. Verify SSH credentials in `.env.multi`
2. Test SSH manually: `ssh user@host`
3. Check firewall allows SSH

### LLM Not Working

1. Verify API key is correct
2. Check API endpoint is accessible
3. Check LLM quota

## State Management

Tasks are stored in `/tmp/cellclaw_state/tasks.json` by default.

To view current tasks:
```bash
cat /tmp/cellclaw_state/tasks.json | jq
```

To clean old tasks:
```python
from shared.state_manager import StateManager
sm = StateManager()
sm.cleanup_old_tasks(hours=24)
```
