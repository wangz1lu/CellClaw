# CellClaw 设计文档

> 版本：v1.0-beta | 最后更新：2026-03-11

---

## 核心理念

**让研究人员通过 Discord 对话，驱动远程 HPC / 工作站完成专业的单细胞多组学分析。**

无需开 SSH 终端，无需记命令，结果直接推送回 Discord。

---

## 系统架构

```
Discord 用户消息
        │
        ▼
┌───────────────────────────────────────────────────────┐
│                    bot.py (Gateway层)                  │
│  discord.py Client ← proxy:7890 → Discord Gateway     │
│  on_message → CellClawAgent.process()                │
│  通知轮询：每5秒 pop_notification() → 推送完成结果      │
└───────────────────┬───────────────────────────────────┘
                    │
        ┌───────────▼───────────┐
        │   CommandDispatcher   │  ← /slash 指令路由
        │   (omics_discord/)    │
        └───────────┬───────────┘
                    │ 非slash消息
        ┌───────────▼───────────┐
        │      NLRouter         │  ← 关键词/正则意图解析
        │   (core/nl_router.py) │     中英文双语支持
        └───────────┬───────────┘
                    │ 无法匹配 → fallback
        ┌───────────▼───────────┐
        │      LLMClient        │  ← DeepSeek / OpenAI兼容
        │    (core/llm.py)      │     自由对话 / 错误诊断 / 结果摘要
        └───────────────────────┘
                    │ 分析类意图
        ┌───────────▼───────────┐
        │    CodeGenerator      │  ← 动态生成分析脚本
        │ (core/code_generator) │     7种分析类型模板
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │      SSHManager       │  ← 高层 SSH 操作接口
        │    (ssh/manager.py)   │
        └──┬────────┬───────────┘
           │        │
    ┌──────▼──┐  ┌──▼──────────┐
    │Executor │  │  Transfer   │  ← 同步命令 / tmux后台任务 / SFTP传输
    │tmux job │  │  SFTP up/dl │
    └─────────┘  └─────────────┘
           │
    ┌──────▼──────────────┐
    │   远程 Linux 服务器  │  ← HPC集群 / 工作站
    │   conda env         │
    │   python/R 脚本执行  │
    └─────────────────────┘
```

---

## 模块详情

### 1. Gateway 层 — `bot.py`
| 文件 | 说明 |
|------|------|
| `bot.py` | Discord Bot 入口，`CellClawBot(discord.Client)` |

- 代理支持：`proxy=http://127.0.0.1:7890`（本地网络必需）
- 文件上传：自动检测附件 → 下载 → 交给 Agent 处理
- DM 密码收集：引导用户私信发送服务器密码（不在群里明文）
- 通知轮询：每 5 秒检查后台任务是否完成，主动推送结果

---

### 2. Discord 交互层 — `omics_discord/`
| 文件 | 说明 |
|------|------|
| `dispatcher.py` | 指令分发器，全局 `/help` |
| `handlers_server.py` | `/server add/list/use/test/remove/info` |
| `handlers_ops.py` | `/env` `/project` `/job` `/status` |
| `parser.py` | slash 命令解析器，支持 `--flag value` + 位置参数 + 别名 |
| `result.py` | `CommandResult`（success/error/info/pending/prompt）|

**支持的 slash 指令：**
```
/server add  <host> <user>      # 添加远程服务器（引导DM输入密码）
/server list                    # 查看已配置服务器列表
/server use  <id>               # 切换当前活跃服务器
/server test                    # 测试当前服务器连通性
/server info                    # 查看服务器硬件信息（CPU/内存/GPU）

/env list                       # 列出远程 conda 环境
/env use     <name>             # 切换当前使用的 conda 环境

/project set <path>             # 设置当前工作目录
/project ls  [path]             # 列出远程目录文件

/job list                       # 查看后台任务列表
/job status  <id>               # 查看指定任务状态
/job log     <id>               # 获取任务日志

/status                         # 查看当前会话状态
/help                           # 显示所有指令
```

---

### 3. Agent 核心层 — `core/`
| 文件 | 行数 | 说明 |
|------|------|------|
| `agent.py` | ~620 | CellClawAgent 主控，意图路由 + 任务管理 |
| `llm.py` | ~210 | LLM 客户端，OpenAI兼容，支持代理 |
| `nl_router.py` | ~160 | 自然语言意图解析（关键词/正则，中英双语）|
| `code_generator.py` | ~460 | 动态生成 Python 分析脚本 |
| `router.py` | ~96 | 辅助路由 |
| `session.py` | ~79 | 会话状态管理 |

**NLRouter 支持的意图：**
- `query` — 快速数据查询（同步，<60s）
- `analyze` — 分析类型识别（qc / cluster / annotate / deg / trajectory / spatial / batch_integration）
- `full_pipeline` — 全流程一键分析
- `read_script` — 读取/解释/修改远程脚本
- `setup_env` — 创建 conda 环境
- `status` / `help`
- `llm_chat` — fallback 转 LLM 自由对话

**LLM 三大能力：**
- `chat_with_context()` — 注入 session 上下文的专家对话
- `summarize_result()` — 分析完成后自动生成 AI 摘要
- `explain_error()` — 任务报错自动诊断原因 + 修复建议

---

### 4. SSH 执行层 — `ssh/`
| 文件 | 行数 | 说明 |
|------|------|------|
| `manager.py` | 369 | SSHManager 高层接口 |
| `executor.py` | 326 | 同步命令执行 + tmux 后台任务 |
| `connection.py` | 182 | asyncssh 连接池 + 硬件信息采集 |
| `registry.py` | 194 | 多用户服务器注册表，JSON持久化 |
| `vault.py` | 124 | AES-256-GCM 密码加密存储 |
| `detector.py` | 201 | conda 环境探测 + h5ad 元数据检查 |
| `transfer.py` | 164 | SFTP 上传/下载/目录列表 |
| `models.py` | 140 | 数据模型（ServerConfig/UserSession/RemoteJob等）|

**后台任务机制：**
- tmux session 命名：`omics_<hex6>`
- 完成标识：脚本末尾写入 `OMICS_JOB_DONE` / `OMICS_JOB_ERROR`
- 轮询：Bot 每 5 秒检查 tmux 日志中的标识字符串
- 完成后：自动 SFTP 下载结果文件 → Discord 推送

**安全机制：**
- 密码 AES-256-GCM 加密存储于 `data/vault.json`
- master key 来自 `OMICSCLAW_VAULT_KEY` 环境变量，或自动生成存于 `data/.vault_key`
- SSH 密钥支持文件路径存储

---

### 5. 分析流程层 — `pipelines/`
| 模块 | 文件 | 说明 |
|------|------|------|
| scRNA | `scrna/qc.py` | QC 过滤、doublet检测 |
| scRNA | `scrna/clustering.py` | PCA + UMAP + Leiden聚类 |
| scRNA | `scrna/deg.py` | 差异表达分析 |
| scRNA | `scrna/annotation.py` | 细胞类型注释 |
| 空间 | `spatial/visium.py` | Visium 数据处理 |
| 空间 | `spatial/visualization.py` | 空间可视化 |

---

### 6. 知识库技能 — `skills/`
| 技能 | 文件数 | 说明 |
|------|--------|------|
| `ccc_cellchat/` | 5 | CellChat 细胞通讯分析完整知识库 |

**CellChat Skill v1.0 覆盖：**
- 单数据集 CCC 分析（7步标准流程）
- 多数据集比较（相同/不同细胞组成）
- 空间转录组 CCC（spatially proximal）
- 从 AnnData/h5ad 输入（Scanpy兼容）
- 完整 R 脚本模板 × 4

---

## 数据持久化

```
data/                       # 默认: CellClaw/data/
├── registry.json           # 服务器注册表（多用户）
├── sessions.json           # 用户会话状态
├── vault.json              # 加密凭证
└── .vault_key              # 主密钥（自动生成）
```

---

## 环境配置 — `.env`

```bash
# Discord Bot Token
DISCORD_TOKEN=...

# LLM（OpenAI兼容，支持 DeepSeek / Kimi / Qwen 等）
OMICS_LLM_BASE_URL=https://api.deepseek.com/v1
OMICS_LLM_API_KEY=sk-...
OMICS_LLM_MODEL=deepseek-chat
OMICS_LLM_MAX_TOKENS=1024

# 可选
OMICSCLAW_DATA=./data
OMICSCLAW_VAULT_KEY=<base64>
HTTPS_PROXY=http://127.0.0.1:7890
```

---

## 开发进度

### ✅ 已完成

**基础架构**
- [x] 项目骨架搭建，模块化设计
- [x] Discord Bot 启动（代理支持，omicsclaw#4633 在线）
- [x] 全局 `/help` + slash 指令路由系统

**SSH 执行层（完整）**
- [x] asyncssh 连接池管理
- [x] 服务器注册表（多用户，JSON持久化）
- [x] AES-256-GCM 密码加密 Vault
- [x] 同步命令执行 + tmux 后台任务
- [x] 任务完成检测（sentinel字符串轮询）
- [x] SFTP 文件上传/下载
- [x] conda 环境探测
- [x] h5ad 文件元数据检查

**Discord 交互层（完整）**
- [x] `/server` 指令全套（add/list/use/test/remove/info）
- [x] `/env` `/project` `/job` `/status` 指令
- [x] DM 密码收集流程
- [x] slash 命令解析器（`--flag`+位置参数+别名）

**Agent 核心层（完整）**
- [x] 自然语言意图解析（中英双语，关键词/正则）
- [x] CodeGenerator（7种分析类型脚本生成）
- [x] LLM 接入（DeepSeek，OpenAI兼容接口）
  - [x] 自由对话（生信专家系统提示）
  - [x] 分析完成自动 AI 摘要
  - [x] 任务报错自动 AI 诊断

**知识库**
- [x] CellChat Skill v1.0（1298行，4个R脚本模板）
  - [x] 单数据集 CCC 分析
  - [x] 多数据集比较
  - [x] 空间转录组 CCC
  - [x] AnnData 输入兼容

**分析流程骨架**
- [x] scRNA：QC / clustering / DEG / annotation 模块
- [x] 空间：Visium / visualization 模块

---

### 🚧 待开发

**核心功能**
- [ ] 端到端测试（接入真实 Linux 服务器跑完整分析）
- [ ] 文件上传触发自动分析（用户发 h5ad → Bot 询问做什么）

**知识库扩展（Skill KB 第二批）**
- [ ] 轨迹分析 Skill：Monocle3 / CellRank（pseudotime / RNA velocity）
- [ ] 细胞注释 Skill：scType / CellTypist（自动化注释）
- [ ] 批次矫正 Skill：Harmony / scVI
- [ ] CCC 顶刊知识蒸馏版（待 leader 确认优先级）

**工程改进**
- [ ] R/Seurat 脚本模板接入 CodeGenerator
- [ ] 富集分析（GO/KEGG）流程
- [ ] 结果报告 HTML 自动生成
- [ ] 多服务器负载均衡（任务自动分配到空闲节点）

---

## 运行方式

```bash
# 启动 Bot
cd bioinfo_analysis/CellClaw
python3 -u bot.py

# 后台运行（推荐）
nohup python3 -u bot.py >> /tmp/omicsclaw_bot.log 2>&1 &

# 查看日志
tail -f /tmp/omicsclaw_bot.log
```

---

## 技术依赖

| 依赖 | 用途 |
|------|------|
| `discord.py>=2.3` | Discord Bot 框架 |
| `asyncssh` | 异步 SSH 连接 |
| `cryptography` | AES-256-GCM 加密 |
| `aiohttp` | 异步 HTTP（LLM API调用）|
| `python-dotenv` | .env 文件加载 |
| `scanpy` | 单细胞分析核心 |
| `anndata` | 数据格式标准 |
| `squidpy` | 空间转录组分析 |
| `harmonypy` | 批次矫正 |
