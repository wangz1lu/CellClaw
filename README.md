# CellClaw - Personal HPC AI Agent

> **AI Bioinformatics Engineer on Discord — Remote HPC control via natural language**

⚠️ **Note:** This project is under active development. Some bugs may exist and will be fixed as quickly as possible.

CellClaw is a Discord bot that lets you control remote Linux servers, HPC clusters, and workstations through natural language. Built for bioinformatics researchers who want to run scRNA-seq, CellChat, DEG analysis, Visualization and more — without leaving Discord.

**Key Features:**
- **OpenClaw Integration** — Can work as an agent within OpenClaw's Discord group chats
- **SSH-based Remote Execution** — Execute bioinformatics analyses directly on remote HPC clusters via SSH
- **Built-in Analysis Skills** — CellChat, DEG, Batch Correction, Visualization, and more
- **Web Dashboard** — Monitor tasks, servers, and skills in real-time at http://127.0.0.1:7860

```
You:       Run CellChat analysis on my Seurat object at ~/data/pbmc.rds
CellClaw: 🧬 Reading skill knowledge base for cell-cell communication...
           📝 Writing analysis script to ~/jobs/cellchat_20260312.R
           🚀 Submitting job on A100 server...
           ✅ Done! Found 847 interactions across 12 cell types.
```

---

## ✨ Features

- **Natural language control** — Describe your analysis in plain Chinese or English
- **Multi-server management** — Connect multiple HPC clusters or workstations via SSH
- **Skill Knowledge Base** — Built-in expertise for CellChat, DEG, GSEA, Batch Correction, and more
- **Persistent memory** — Bot remembers your projects, preferences, and past analyses
- **Conda environment management** — Auto-detect and switch environments
- **Session continuity** — Conversation history survives bot restarts
- **Dashboard** — Web UI for monitoring tasks, servers, and skills
- **Secure credential storage** — SSH keys and passwords encrypted with AES-256-GCM

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- A Discord bot token ([create one here](https://discord.com/developers/applications))
- An LLM API key (DeepSeek recommended)
- SSH access to a Linux server

### Install

```bash
git clone https://github.com/wangz1lu/CellClaw
cd cellclaw
bash install.sh
```

### Start

```bash
bash start.sh
```

This will start:
- Discord Bot
- Dashboard

### Add your first server

In Discord:

```
/server add --name a100 --host 10.0.0.1 --user ubuntu --key ~/.ssh/id_rsa
/server use a100
/env list
```

---

## 📊 Dashboard

Access at: http://127.0.0.1:7860

Features:
- **Tasks** — Monitor running and completed jobs
- **Servers** — View server status and connections
- **Skills** — Browse installed analysis skills

---

## 📋 Commands Reference

**Server Management**
```
/server add --name <id> --host <IP> --user <user> --port <port> [--key <path>] [--password true]
/server list
/server use <name>
/server test [name]
/server info [name]
/server remove <name>
```

**Project**
```
/project set <path>
/project ls [path]
/project info <file.h5ad>
```

**Job Management**
```
/job list
/job set <description> — Submit background job
/job status <job_id>
/job log <job_id>
/job cancel <job_id>
```

**Skills**
```
/skill list — List all installed skills
/skill use <skill_id> <task> — Force activate skill
```

**Memory**
```
/memory show — View long-term memory
/memory today — View today's logs
/memory clear — Clear chat history
/memory note <content> — Write to memory
```

**Session**
```
/status
```

---

## 🛠️ Skills

Built-in skills:

| Skill | Description |
|-------|-------------|
| `ccc_cellchat` | CellChat cell-cell communication |
| `deg_analysis` | Differential gene expression |
| `gsea_enrichment` | GO/KEGG enrichment |
| `dimreduc_standard` | Standard clustering (PCA/UMAP) |
| `annotation_sctype` | Cell type annotation |
| `batch_harmony` | Batch correction with Harmony |

---

## 📁 Project Structure

```
CellClaw/
├── bot.py                 # Discord bot entry
├── core/                  # Agent, LLM, skills
├── ssh/                   # SSH execution layer
├── dashboard/             # Web dashboard
├── data/                  # Sessions, users, logs
├── skills/               # Analysis skill templates
├── install.sh           # Install script
├── start.sh              # Start bot + dashboard
├── stop.sh              # Stop bot
└── requirements.txt     # Python dependencies
```

---

## ⚙️ Configuration

Edit `.env` file:

```
DISCORD_TOKEN=your_bot_token
OMICS_LLM_API_KEY=your_api_key
OMICS_LLM_MODEL=deepseek-chat
SSH_PROXY=http://127.0.0.1:7890  # optional
```

---

## 🔧 Troubleshooting

**Bot won't start:**
```bash
bash install.sh  # Reinstall dependencies
```

**Dashboard not loading:**
- Check if bot started successfully
- Dashboard runs on http://127.0.0.1:7860

**SSH connection issues:**
```bash
/server test <server_name>
```

---

License: MIT
