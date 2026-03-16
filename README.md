# OmicsClaw 🧬

> **AI Bioinformatics Engineer on Discord — Remote HPC control via natural language**

OmicsClaw is a Discord bot that lets you control remote Linux servers, HPC clusters, and workstations through natural language.

---

## ✨ Features

- Natural language control — Describe your analysis in plain Chinese or English
- Multi-server management — Connect multiple HPC clusters via SSH
- Skill Knowledge Base — Built-in expertise for CellChat, DEG, GSEA, Batch Correction, and more
- Persistent memory — Bot remembers your projects and preferences
- Conda environment management — Auto-detect and switch environments
- Dashboard — Web UI for monitoring tasks, servers, and skills

---

## 🚀 Quick Start

### Install

```bash
git clone https://github.com/wangz1lu/omicsclaw
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
/job set    <description>     # Submit background task
/job status <job_id>
/job log    <job_id>
/job cancel <job_id>
```

**Tip:** You can also say "挂后台" or "提交任务" to run tasks in background.

### Skills
```
/skill list
/skill info <skill_id>
/skill use  <skill_id> <your request>
/skill run  <skill_id> <your request>
```

**Tip:** Just say "帮我跑细胞通讯" and the bot will auto-activate the relevant skill.

### Memory
```
/memory show              # View long-term memory
/memory today             # View today's operation logs
/memory clear            # Clear conversation history
/memory note <content>   # Manually write to memory
```

### Other
```
/status    # Show current server and environment
/help      # Show this help
```

---

## 🛠️ Skills

| Skill | Description |
|-------|-------------|
| `ccc_cellchat` | CellChat cell-cell communication |
| `deg_analysis` | Differential gene expression |
| `gsea_enrichment` | GO/KEGG enrichment |
| `dimreduc_standard` | Standard clustering |
| `annotation_sctype` | Cell type annotation |
| `batch_harmony` | Batch correction |

---

## 📊 Dashboard

Access: http://127.0.0.1:7860

- **Tasks** — Monitor running jobs
- **Servers** — Server status
- **Skills** — Installed skills
- **Config** — Quick commands

---

## 💬 Natural Language Examples

```
帮我分析 ~/data/pbmc.h5ad 做 UMAP 聚类
你會哪些分析？
cluster 3 裡有多少個細胞？
幫我從頭做完整的單細胞分析流程
記住：我們的數據在 /data/project_A/
```

---

License: MIT
