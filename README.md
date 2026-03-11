# OmicsClaw 🧬

> **AI Bioinformatics Engineer on Discord — Remote HPC control via natural language**

OmicsClaw is a Discord bot that lets you control remote Linux servers, HPC clusters, and workstations through natural language. Built for bioinformatics researchers who want to run scRNA-seq, CellChat, trajectory analysis and more — without leaving Discord.

```
You:       Run CellChat analysis on my Seurat object at ~/data/pbmc.rds
OmicsClaw: 🧬 Reading skill knowledge base for cell-cell communication...
           📝 Writing analysis script to ~/jobs/cellchat_20260312.R
           🚀 Submitting job on A100 server...
           ✅ Done! Found 847 interactions across 12 cell types.
           Top pathway: MHC-II signaling (L-R pairs: 23)
```

---

## ✨ Features

- **Natural language control** — Describe your analysis in plain Chinese or English
- **Multi-server management** — Connect multiple HPC clusters or workstations via SSH
- **Skill Knowledge Base** — Built-in expertise for CellChat, Scanpy, Seurat, and more
- **Persistent memory** — Bot remembers your projects, preferences, and past analyses
- **Conda environment management** — Auto-detect and switch environments
- **Session continuity** — Conversation history survives bot restarts
- **Secure credential storage** — SSH keys and passwords encrypted with AES-256-GCM

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- A Discord bot token ([create one here](https://discord.com/developers/applications))
- An LLM API key (DeepSeek recommended — cheap and powerful)
- SSH access to a Linux server

### Install

```bash
git clone https://github.com/yourorg/omicsclaw
cd omicsclaw
bash install.sh
```

The installer will guide you through:
1. Creating a Python virtual environment
2. Installing dependencies
3. Configuring your Discord token, LLM API key, and proxy settings

### Start

```bash
bash start.sh
```

### Add your first server

In Discord, DM the bot or use it in a channel:

```
/server add --name a100 --host 10.0.0.1 --user ubuntu --key ~/.ssh/id_rsa
/server use a100
/env list
```

Then just talk to it:

```
帮我看看 ~/data 目录下有什么数据文件
列出所有 conda 环境，然后用 scanpy 环境跑一个质控
```

---

## 📋 Commands Reference

### Server Management
```
/server add --name <name> --host <ip> --user <user> --key <path>
/server add --name <name> --host <ip> --user <user> --password true
/server list
/server use <name>
/server test
/server info
/server remove <name>
```

### Environment
```
/env list              # List all conda environments
/env use <name>        # Set active conda environment
/env scan <name>       # Scan env for bioinformatics packages
```

### Project
```
/project set <path>    # Set working directory
/project ls            # List files in project directory
/project files         # Find data files (h5ad, rds, etc.)
```

### Jobs
```
/job list              # List running/recent jobs
/job status <id>       # Check job status
/job log <id>          # View job output
/job kill <id>         # Cancel a job
```

### Skills
```
/skill list            # List installed analysis skills
/skill info <id>       # View skill knowledge base
```

### Memory
```
/memory show           # View your long-term memory
/memory today          # View today's activity log
/memory clear          # Clear conversation history
```

---

## 🔬 Skills (Knowledge Base)

Skills are domain-specific knowledge bases that teach OmicsClaw how to run analyses correctly. When you mention a relevant topic, the bot automatically loads the appropriate skill.

| Skill ID | Domain | Triggers |
|---|---|---|
| `ccc_cellchat` | Cell-Cell Communication | cellchat, CCC, 细胞通讯, ligand, receptor |

### Adding Custom Skills

Create a directory under `skills/`:

```
skills/
└── my_skill/
    ├── SKILL.md          # Knowledge base (YAML front matter + markdown)
    └── templates/        # Reference scripts (R, Python)
        └── 01_example.R
```

SKILL.md format:
```yaml
---
id: my_skill
name: My Analysis
scope: R
triggers: [keyword1, keyword2, 关键词]
---

# Knowledge base content here...
```

---

## ⚙️ Configuration

All configuration is in `.env` (copy from `.env.example`):

| Variable | Description | Default |
|---|---|---|
| `DISCORD_BOT_TOKEN` | Discord bot token | required |
| `OMICS_LLM_BASE_URL` | LLM API base URL | `https://api.deepseek.com/v1` |
| `OMICS_LLM_API_KEY` | LLM API key | required |
| `OMICS_LLM_MODEL` | Model name | `deepseek-chat` |
| `OMICS_LLM_PROXY` | HTTP proxy | optional |
| `OMICS_BOT_NAME` | Bot display name | `OmicsClaw` |

### Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create New Application → Bot → Reset Token
3. Enable **Privileged Gateway Intents**:
   - ✅ MESSAGE CONTENT INTENT
4. Invite bot to your server with `bot` + `applications.commands` scopes

### Supported LLM Providers

Any OpenAI-compatible API works:

```env
# DeepSeek (recommended — best price/performance)
OMICS_LLM_BASE_URL=https://api.deepseek.com/v1
OMICS_LLM_MODEL=deepseek-chat

# OpenAI
OMICS_LLM_BASE_URL=https://api.openai.com/v1
OMICS_LLM_MODEL=gpt-4o

# Kimi
OMICS_LLM_BASE_URL=https://api.moonshot.cn/v1
OMICS_LLM_MODEL=moonshot-v1-8k
```

---

## 🏗️ Architecture

```
Discord Message
    │
    ▼
OmicsClawAgent.handle_message()
    ├── [/command]   → CommandDispatcher → SSH layer
    └── [NL text]    → LLM Agent (native function calling)
                            │
                ┌──────────┴──────────┐
                ▼                     ▼
          Tool Executor          Session Store
          (SSH commands)         (JSONL transcript)
                │
         Remote Server
         (Linux/HPC/GPU)
```

**Core modules:**
- `core/agent.py` — Main agent orchestrator
- `core/llm.py` — LLM client with native OpenAI function calling
- `core/session_store.py` — Persistent JSONL conversation history
- `core/memory.py` — Long-term memory (MEMORY.md + daily logs)
- `core/skills.py` — Skill knowledge base loader
- `ssh/` — SSH connection pool, executor, credential vault
- `omics_discord/` — Discord event handling, command parsing

---

## 📁 Project Structure

```
omicsclaw/
├── bot.py                  # Entry point
├── install.sh              # Setup wizard
├── start.sh / stop.sh / restart.sh
├── requirements.txt
├── .env.example
├── SOUL.md                 # Bot personality
├── core/                   # Agent logic
│   ├── agent.py
│   ├── llm.py
│   ├── session_store.py
│   ├── memory.py
│   └── skills.py
├── ssh/                    # SSH layer
│   ├── manager.py
│   ├── connection.py
│   ├── executor.py
│   ├── detector.py
│   ├── vault.py
│   └── models.py
├── omics_discord/          # Discord layer
│   ├── dispatcher.py
│   ├── parser.py
│   ├── handlers_server.py
│   ├── handlers_ops.py
│   └── result.py
├── skills/                 # Knowledge bases
│   └── ccc_cellchat/
│       ├── SKILL.md
│       └── templates/
└── data/                   # Runtime data (gitignored)
    ├── sessions/           # Per-user conversation JSONL
    └── users/              # Per-user memory files
```

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/new-skill`
3. Add your skill under `skills/`
4. Submit a PR

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

## Acknowledgements

- Inspired by [BioClaw](https://github.com/Runchuan-BU/BioClaw) and [OpenClaw](https://github.com/openclaw/openclaw)
- Built with [discord.py](https://github.com/Rapptz/discord.py) and [asyncssh](https://github.com/ronf/asyncssh)
- LLM: [DeepSeek](https://platform.deepseek.com) (recommended)
