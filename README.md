# CellClaw 🧬

> **AI Bioinformatics Engineer on Discord — Remote HPC control via natural language**

CellClaw is a Discord bot that lets you control remote Linux servers, HPC clusters, and workstations through natural language. Built for bioinformatics researchers who want to run scRNA-seq, CellChat, trajectory analysis and more — without leaving Discord.

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
cd omicsclaw
bash install.sh
```

### Start

```bash
bash start.sh
```

This will start:
- Discord Bot
- Dashboard (http://127.0.0.1:7860)

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
- **Config** — Quick commands and configuration

---

## 📋 Commands Reference

### Server Management
```
/server add   --name <id> --host <IP> --user <user> [--key <path>] [--port <port>] [--password true]
/server list
/server use   <name>
/server test  [name]
/server info  [name>
/server remove <name>
```

### Environment
```
/env list
/env use    <name>
/env scan   <name>
```

### Project
```
/project set  <path>
/project ls   [path]
/project find [path]
/project info <file.h5ad>
```

### Jobs
```
/job list
/job set    <description>      # Submit background task
/job status <job_id>
/job log    <job_id>
/job cancel <job_id>
```
💡 You can also say "挂后台" or "提交任务" to run tasks in background.

### Skills
```
/skill list
/skill info <skill_id>
/skill use  <skill_id> <your request>
/skill run  <skill_id> <your request>
```
💡 Just say "帮我跑细胞通讯" and bot will auto-activate the relevant skill.

### Memory
```
/memory show              # View long-term memory
/memory today             # View today's logs
/memory clear            # Clear conversation history
/memory note <content>   # Write to memory
```

### Other
```
/status   # Show current server and environment
/help     # Show this help
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
