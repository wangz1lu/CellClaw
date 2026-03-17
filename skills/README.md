# CellClaw Skill 开发指南

## 目录结构

```
skills/
├── _template/              # ← 模板，复制这个目录来创建新 Skill
│   ├── SKILL.md            #    Skill 知识库（LLM 读取的核心文件）
│   └── templates/          #    参考脚本模板
│       └── 01_basic_workflow.R
│
├── ccc_cellchat/           # 示例：CellChat 细胞通讯
│   ├── SKILL.md
│   └── templates/
│       ├── 01_single_dataset_CCC.R
│       ├── 02_comparison_CCC.R
│       ├── 03_spatial_CCC.R
│       └── 04_from_anndata.R
│
└── <your_new_skill>/       # ← 你的新 Skill
    ├── SKILL.md
    └── templates/
```

## 创建新 Skill 的步骤

### 1. 复制模板
```bash
cp -r skills/_template skills/my_new_skill
```

### 2. 编辑 SKILL.md

**YAML 头部（必填）：**
```yaml
---
name: 显示名称（如：Trajectory — Monocle3）
version: 1.0.0
scope: 适用场景简述
languages: [R]           # 或 [Python] 或 [R, Python]
triggers: [monocle, monocle3, 轨迹, trajectory, pseudotime, 拟时序]
---
```

**关键字段说明：**
| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 显示在 `/skill list` 中 |
| `triggers` | ✅ | 自然语言触发词，用户消息包含任一词 → 自动激活 |
| `scope` | 推荐 | 显示在 `/skill list` 中 |
| `languages` | 推荐 | R / Python / Shell |
| `version` | 可选 | 版本号 |

### 3. 填写知识库内容

SKILL.md 是给 LLM 看的**知识库**，不是给人看的教程。写法要点：

- **精确**：参数名、默认值、函数签名要准确
- **结构化**：用表格列出参数，用代码块展示关键步骤
- **完整**：覆盖从输入到输出的全流程
- **关注 edge case**：常见错误、数据格式要求、版本兼容性
- **输出规则**：提醒所有输出文件以 `result_` 开头

### 4. 添加模板脚本（可选但推荐）

模板放在 `templates/` 目录下，LLM 可以通过 `read_skill` 工具读取：
```
templates/
├── 01_basic_workflow.R      # 基础流程
├── 02_advanced_usage.R      # 高级用法
└── 03_from_anndata.R        # 特殊输入格式
```

命名规范：`序号_描述.R`（或 `.py`）

### 5. 测试

```
# 在 Discord 中测试：
/skill list                          # 确认新 Skill 出现
/skill info my_new_skill             # 确认内容正确
/skill use my_new_skill 帮我分析数据  # 测试 Agent 调用
```

自然语言测试：直接说包含触发词的话，看 Agent 是否自动激活。

## 触发词设计建议

- 包含**英文工具名**：`monocle3`, `cellchat`, `harmony`
- 包含**中文描述**：`轨迹推断`, `细胞通讯`, `批次校正`
- 包含**缩写**：`ccc`, `deg`, `gsea`
- 包含**同义词**：`pseudotime` + `拟时序` + `时间轨迹`
- **不要太宽泛**：`分析` 这种会误触发所有 Skill

## Agent 调用 Skill 的完整链路

```
用户: "帮我做轨迹分析"
  │
  ├─ 自动触发: 检测触发词 → 注入 SKILL.md 前 3000 字到 session context
  │   └─ LLM 看到知识库 → 调用 read_skill 获取完整内容 → 写脚本 → submit_job
  │
  └─ 显式触发: /skill use trajectory_monocle3 帮我做轨迹分析
      └─ 注入完整 SKILL.md（不截断）→ LLM 直接写脚本 → submit_job
```

## 建议扩展的 Skill 列表

| Skill ID | 名称 | 触发词 | 复杂度 |
|----------|------|--------|--------|
| `deg_analysis` | 差异基因分析 | deg, 差异基因, differential expression | ⭐ |
| `gsea_enrichment` | 富集分析 | gsea, go, kegg, 富集, enrichment | ⭐ |
| `trajectory_monocle3` | 轨迹推断 | monocle, trajectory, 轨迹, pseudotime | ⭐⭐ |
| `annotation_sctype` | 细胞注释 | sctype, 注释, annotation, cell type | ⭐ |
| `batch_harmony` | 批次校正 | harmony, 批次, batch correction, integration | ⭐⭐ |
| `velocity_scvelo` | RNA velocity | scvelo, velocity, RNA速度 | ⭐⭐⭐ |
| `spatial_squidpy` | 空间分析 | squidpy, spatial, 空间转录组 | ⭐⭐ |
| `dimreduc_standard` | 标准降维聚类 | umap, tsne, 降维, 聚类, clustering | ⭐ |
| `cnv_infercnv` | CNV 推断 | infercnv, cnv, 拷贝数 | ⭐⭐ |
| `multiome_wnn` | 多组学整合 | multiome, wnn, atac, 多组学 | ⭐⭐⭐ |
