# OmicsClaw: A Natural Language Interface for Remote Bioinformatics Analysis on Discord

## Abstract

**Background:** Bioinformatics analysis typically requires command-line expertise, limiting accessibility for researchers without programming skills. Running analyses on remote HPC clusters adds additional complexity.

**Results:** We present OmicsClaw, a Discord bot that enables natural language-driven bioinformatics analysis on remote Linux servers and HPC clusters. Users can execute single-cell pipelines (CellChat, DEG, GSEA, etc.) by simply describing their needs in Chinese or English. OmicsClaw provides seamless SSH connectivity, Conda environment management, persistent memory, and a web dashboard for monitoring tasks and servers.

**Availability:** OmicsClaw is open source (MIT License) and freely available at https://github.com/wangz1lu/OmicsClaw

---

## 1. Introduction

Bioinformatics workflows often involve multiple steps executed on remote High-Performance Computing (HPC) clusters. Traditional approaches require:

1. SSH connections to remote servers
2. Command-line interface (CLI) proficiency
3. Manual environment setup and package management
4. Job submission and monitoring

These barriers significantly limit accessibility, especially for biologists without computational backgrounds. While several web-based bioinformatics platforms exist, they typically require account creation, payment, or have limited customization.

We developed **OmicsClaw**, a Discord bot that provides a conversational interface to remote bioinformatics analysis. By leveraging large language models (LLMs), users can describe their analysis needs in natural language, and OmicsClaw translates these into executable code on configured remote servers.

---

## 2. Implementation

### 2.1 System Architecture

OmicsClaw consists of four main components:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Discord       │────►│   OmicsClaw      │────►│   Remote SSH   │
│   (User UI)    │     │   (Bot + LLM)   │     │   (HPC)        │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │   Dashboard     │
                        │   (Monitoring) │
                        └──────────────────┘
```

**Core Technologies:**
- **Discord Bot** (discord.py): User interface and message handling
- **LLM Integration** (OpenAI-compatible APIs): Natural language understanding
- **SSH Management** (asyncssh): Remote server communication
- **FastAPI**: RESTful API for dashboard
- **Gradio** (optional): Web dashboard

### 2.2 Natural Language Processing

OmicsClaw uses LLMs (default: DeepSeek Chat) to:
1. Parse user intent from natural language
2. Generate bioinformatics code (R/Python)
3. Execute scripts on remote servers
4. Interpret results and provide summaries

### 2.3 Skill Knowledge Base

Built-in **Skills** provide domain expertise:

| Skill | Description |
|-------|-------------|
| `ccc_cellchat` | Cell-cell communication analysis |
| `deg_analysis` | Differential gene expression |
| `gsea_enrichment` | GO/KEGG pathway enrichment |
| `dimreduc_standard` | Standard clustering (PCA/UMAP) |
| `annotation_sctype` | Cell type annotation |
| `batch_harmony` | Batch correction with Harmony |

Each skill includes:
- Knowledge base (SKILL.md) with detailed parameters
- Reference templates (R/Python scripts)
- Automatic context injection when relevant keywords detected

### 2.4 SSH and Environment Management

- **Multi-server support**: Configure multiple remote servers
- **Conda integration**: Auto-detect and switch environments
- **Background job execution**: Automatic tmux/nohup submission
- **Real-time monitoring**: Job status polling and logging

### 2.5 Memory System

- **Session persistence**: JSONL-based conversation history
- **Long-term memory**: Persistent notes via `/memory` commands
- **Cross-platform continuity**: Dashboard and Discord share the same session

---

## 3. Application Examples

### Example 1: CellChat Analysis

```
User: 帮我做CellChat分析，数据在~/data/pbmc.rds
OmicsClaw: 🔬 Reading CellChat skill knowledge base...
       📝 Writing analysis script...
       🚀 Submitting job on A100 server...
       ✅ Done! Found 847 interactions across 12 cell types.
```

### Example 2: Differential Expression

```
User: cluster 2和cluster 3的差异基因是什么？
OmicsClaw: 🔬 Running DEG analysis...
       ✅ Found 234 significant genes (padj < 0.05, log2FC > 0.5)
       Top markers: IL7R, CD8A, GZMA, NKG7...
```

### Example 3: Dashboard Monitoring

Users can monitor running jobs via the built-in dashboard (http://localhost:7860):
- Server status (online/offline)
- Task progress and logs
- Installed skills overview

---

## 4. Discussion

OmicsClaw demonstrates the potential of conversational interfaces for bioinformatics, making advanced analyses accessible without CLI expertise.

**Limitations:**
- Dependent on LLM quality for code generation
- Requires internet connectivity for LLM API
- SSH access to remote servers is essential

**Future Work:**
- Support for more bioinformatics tools (Scanpy, Seurat)
- Integration with additional LLM providers
- Mobile-friendly interface
- Collaborative features for team sharing

---

## 5. Conclusion

OmicsClaw provides an accessible, free alternative for running bioinformatics analyses on remote servers. By combining natural language processing with SSH automation, it bridges the gap between user intent and computational execution.

---

## Authors

[Author names and affiliations to be added]

## References

1. Hao D, et al. (2024). CellChat v2: Inference and analysis of cell-cell communication. *Nature Methods*.
2. Stuart T, et al. (2019). Comprehensive integration of single-cell data. *Cell*.
3. Wu Y, et al. (2021). Harmony: fast and accurate integration of single-cell data. *Nature Methods*.
4. Gu Z, et al. (2022). clusterProfiler and enrichment可视化. *Genomics*.
5. SingleR: automatic cell type annotation for single-cell RNA-seq.
6. Wolf FA, et al. (2018). SCANPY: large-scale single-cell gene analysis. *Genome Biology*.
7. https://github.com/wangz1lu/OmicsClaw

---

*Paper generated for Bioinformatics Application Note submission*
