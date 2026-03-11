---
name: CCC — CellChat v2
version: 1.0.0
scope: 单数据集细胞通讯 / 多数据集比较 / 空间转录组 CCC
languages: [R]
triggers: [cellchat, ccc, 细胞通讯, cell communication, cell-cell communication, 配受体, ligand, receptor, 通讯网络]
---
# Skill: CCC — CellChat v2
# OmicsClaw Skill Knowledge Base
# Version: 1.0.0
# Author: CellClaw
# Source: CellChat official tutorials (Suoqin Jin, jinworks/CellChat)
# Scope: Single dataset CCC / Multi-dataset comparison / Spatial CCC

---

## 1. Skill 概述

**细胞通讯分析（Cell-Cell Communication, CCC）** 使用 **CellChat v2** 工具包，
基于配受体（Ligand-Receptor）数据库推断单细胞数据中细胞群体间的通讯网络。

### 适用场景
| 场景 | 说明 |
|------|------|
| 单数据集 CCC | 单个样本/条件，推断全量通讯网络 |
| 多数据集比较 | 两个/多个条件（如正常 vs 疾病）的差异通讯 |
| 空间转录组 CCC | 整合空间坐标的近邻约束通讯分析 |

### 工具要求
- **R** ≥ 4.1.0
- **CellChat** ≥ 2.0.0（`install.packages("CellChat")`）
- 依赖：`NMF`, `ggalluvial`, `patchwork`, `circlize`

---

## 2. 输入数据要求

### 必需输入
```
数据矩阵：基因 × 细胞，已归一化（library-size norm + log1p），稀疏矩阵格式
细胞注释：data.frame，rownames = 细胞名，含细胞类型列
物种：human / mouse（影响数据库选择）
```

### 支持的输入格式
| 格式 | 处理方式 |
|------|---------|
| 归一化矩阵 + meta.data | 直接使用 |
| Seurat 对象 | `seurat_object[["RNA"]]@data` 提取 |
| Anndata (.h5ad) | anndata R 包读取后转换 |
| SingleCellExperiment | `logcounts()` 提取 |

### ⚠️ 重要注意事项
- 输入数据必须是**归一化后**的数据，不是原始 count
- 如果是原始 count，使用 `normalizeData()` 函数处理
- 对于 Anndata：`counts → library-size norm → log1p(x * 10000)`

---

## 3. 标准分析流程（单数据集）

### Step 1：创建 CellChat 对象
```r
library(CellChat)
library(patchwork)

# 从归一化矩阵创建
cellchat <- createCellChat(object = data.input, meta = meta, group.by = "cell_type")

# 从 Seurat 对象创建
cellchat <- createCellChat(object = seurat_obj, group.by = "ident", assay = "RNA")

# 从 Anndata 创建（需先转换）
library(anndata)
ad <- read_h5ad("adata.h5ad")
counts <- t(as.matrix(ad$X))
library.size <- Matrix::colSums(counts)
data.input <- as(log1p(Matrix::t(Matrix::t(counts)/library.size) * 10000), "dgCMatrix")
meta <- ad$obs
meta$labels <- meta[["leiden"]]  # 替换为实际的聚类列名
cellchat <- createCellChat(object = data.input, meta = meta, group.by = "labels")
```

### Step 2：设置配受体数据库
```r
# 人类数据使用 human；小鼠数据使用 mouse
CellChatDB <- CellChatDB.human

# 推荐：仅使用分泌信号（最常用，减少计算量）
CellChatDB.use <- subsetDB(CellChatDB, search = "Secreted Signaling", key = "annotation")

# 或：使用全部数据库（除 Non-protein Signaling）
# CellChatDB.use <- subsetDB(CellChatDB)

cellchat@DB <- CellChatDB.use
```

**数据库选择指南：**
| 数据库子集 | 适用场景 |
|-----------|---------|
| `Secreted Signaling` | 默认推荐，细胞因子/生长因子类 |
| `ECM-Receptor` | 关注细胞外基质互作时 |
| `Cell-Cell Contact` | 关注直接接触信号时 |
| 全库（含 Non-protein）| 代谢/突触信号研究 |

### Step 3：数据预处理
```r
cellchat <- subsetData(cellchat)  # 必须执行，即使使用全库

# 并行加速（推荐）
future::plan("multisession", workers = 4)  # 根据服务器 CPU 核数调整

cellchat <- identifyOverExpressedGenes(cellchat)
cellchat <- identifyOverExpressedInteractions(cellchat)

# 可选：PPI 平滑（适用于测序深度浅的数据，可减少 dropout 影响）
# cellchat <- projectData(cellchat, PPI.human)
# 注意：使用 projectData 后，computeCommunProb 中需设 raw.use = FALSE
```

### Step 4：推断通讯概率
```r
# 标准方法（triMean，严格，预测较强的互作）
cellchat <- computeCommunProb(cellchat, type = "triMean")

# 如果发现已知通路未被预测，改用 truncatedMean（更宽松）
# cellchat <- computeCommunProb(cellchat, type = "truncatedMean", trim = 0.1)

# 过滤：细胞数 < 10 的群体的通讯被移除
cellchat <- filterCommunication(cellchat, min.cells = 10)

# 推断 pathway 级别通讯概率
cellchat <- computeCommunProbPathway(cellchat)

# 计算聚合网络
cellchat <- aggregateNet(cellchat)
```

**参数选择原则：**
| 参数 | 说明 |
|------|------|
| `type = "triMean"` | 默认，近似25%截断均值，交互少但可靠 |
| `type = "truncatedMean", trim=0.1` | 10%截断均值，捕获更多互作 |
| `population.size = TRUE` | 未分选数据推荐，考虑细胞比例效应 |
| `min.cells = 10` | 过滤阈值，细胞数过少的群体不可靠 |

### Step 5：网络可视化

#### 5.1 总体通讯概览
```r
groupSize <- as.numeric(table(cellchat@idents))
par(mfrow = c(1,2), xpd=TRUE)
# 互作数量
netVisual_circle(cellchat@net$count, vertex.weight = groupSize,
                 weight.scale = TRUE, label.edge = FALSE,
                 title.name = "Number of interactions")
# 互作强度
netVisual_circle(cellchat@net$weight, vertex.weight = groupSize,
                 weight.scale = TRUE, label.edge = FALSE,
                 title.name = "Interaction weights/strength")
```

#### 5.2 单个通路可视化（4 种图形）
```r
pathways.show <- c("CXCL")  # 替换为目标通路
vertex.receiver <- seq(1, 4)  # 定义接收方细胞群（层级图左侧）

# 层级图（推荐：清晰展示 sender/receiver 关系）
netVisual_aggregate(cellchat, signaling = pathways.show,
                    vertex.receiver = vertex.receiver)
# 圆圈图
netVisual_aggregate(cellchat, signaling = pathways.show, layout = "circle")
# 弦图（Chord diagram）
netVisual_aggregate(cellchat, signaling = pathways.show, layout = "chord")
# 热图
netVisual_heatmap(cellchat, signaling = pathways.show, color.heatmap = "Reds")
```

#### 5.3 配受体对贡献分析
```r
# 查看某通路内各 L-R pair 的贡献
netAnalysis_contribution(cellchat, signaling = pathways.show)

# 提取富集的 L-R pairs
pairLR <- extractEnrichedLR(cellchat, signaling = pathways.show, geneLR.return = FALSE)
```

#### 5.4 气泡图（多通路多细胞群）
```r
# 展示从特定 source 到特定 target 的所有显著互作
netVisual_bubble(cellchat,
                 sources.use = 4,
                 targets.use = c(5:11),
                 remove.isolate = FALSE)
```

#### 5.5 批量保存所有通路图（生产用）
```r
pathways.show.all <- cellchat@netP$pathways
vertex.receiver <- seq(1, 4)
for (i in seq_along(pathways.show.all)) {
  netVisual(cellchat, signaling = pathways.show.all[i],
            vertex.receiver = vertex.receiver, layout = "hierarchy")
  gg <- netAnalysis_contribution(cellchat, signaling = pathways.show.all[i])
  ggsave(paste0(pathways.show.all[i], "_LR_contribution.pdf"),
         plot = gg, width = 3, height = 2, dpi = 300)
}
```

### Step 6：系统分析

#### 6.1 信号角色分析（Sender/Receiver/Mediator/Influencer）
```r
cellchat <- netAnalysis_computeCentrality(cellchat, slot.name = "netP")

# 热图：各细胞群在各通路中的信号角色
netAnalysis_signalingRole_network(cellchat, signaling = pathways.show,
                                  width = 8, height = 2.5, font.size = 10)
# 散点图：总 outgoing vs incoming 强度
gg1 <- netAnalysis_signalingRole_scatter(cellchat)
# 热图：outgoing/incoming 模式全局视图
ht1 <- netAnalysis_signalingRole_heatmap(cellchat, pattern = "outgoing")
ht2 <- netAnalysis_signalingRole_heatmap(cellchat, pattern = "incoming")
ht1 + ht2
```

#### 6.2 通讯模式识别（Pattern Recognition）
```r
library(NMF)
library(ggalluvial)

# 确定最佳 pattern 数
selectK(cellchat, pattern = "outgoing")
selectK(cellchat, pattern = "incoming")
# 选择 Cophenetic 和 Silhouette 开始下降的拐点处的 K 值

nPatterns_out <- 6   # 根据 selectK 结果调整
nPatterns_in  <- 3

cellchat <- identifyCommunicationPatterns(cellchat, pattern = "outgoing", k = nPatterns_out)
netAnalysis_river(cellchat, pattern = "outgoing")   # 河流图
netAnalysis_dot(cellchat, pattern = "outgoing")     # 点图

cellchat <- identifyCommunicationPatterns(cellchat, pattern = "incoming", k = nPatterns_in)
netAnalysis_river(cellchat, pattern = "incoming")
netAnalysis_dot(cellchat, pattern = "incoming")
```

#### 6.3 通路相似性聚类（Manifold Learning）
```r
# 功能相似性（要求多组数据细胞组成相同）
cellchat <- computeNetSimilarity(cellchat, type = "functional")
cellchat <- netEmbedding(cellchat, type = "functional")
cellchat <- netClustering(cellchat, type = "functional")
netVisual_embedding(cellchat, type = "functional", label.size = 3.5)

# 结构相似性（无细胞组成限制）
cellchat <- computeNetSimilarity(cellchat, type = "structural")
cellchat <- netEmbedding(cellchat, type = "structural")
cellchat <- netClustering(cellchat, type = "structural")
netVisual_embedding(cellchat, type = "structural", label.size = 3.5)
netVisual_embeddingZoomIn(cellchat, type = "structural", nCol = 2)
```

### Step 7：保存结果
```r
saveRDS(cellchat, file = "cellchat_result.rds")
```

---

## 4. 多数据集比较分析流程

### 前提
- 需要先对每个数据集分别完成 Part I～V 的单数据集分析
- 若两组数据集**细胞组成相同**（联合聚类后），使用本节流程
- 若细胞组成**不同**，参见 `Comparison_different_compositions` 教程

### Step 1：合并 CellChat 对象
```r
cellchat.A <- readRDS("cellchat_conditionA.rds")
cellchat.B <- readRDS("cellchat_conditionB.rds")
object.list <- list(CondA = cellchat.A, CondB = cellchat.B)
cellchat.merged <- mergeCellChat(object.list, add.names = names(object.list))
```

### Step 2：总体差异比较
```r
# 互作数量和强度的总体对比
gg1 <- compareInteractions(cellchat.merged, show.legend = FALSE, group = c(1,2))
gg2 <- compareInteractions(cellchat.merged, show.legend = FALSE,
                            group = c(1,2), measure = "weight")
gg1 + gg2

# 差异网络圆圈图（红色=增加，蓝色=减少）
par(mfrow = c(1,2), xpd=TRUE)
netVisual_diffInteraction(cellchat.merged, weight.scale = TRUE)
netVisual_diffInteraction(cellchat.merged, weight.scale = TRUE, measure = "weight")

# 差异热图
gg1 <- netVisual_heatmap(cellchat.merged)
gg2 <- netVisual_heatmap(cellchat.merged, measure = "weight")
gg1 + gg2
```

### Step 3：主要 Source/Target 变化
```r
# 各数据集的 outgoing/incoming 信号散点图（统一 dot size 范围）
num.link <- sapply(object.list, function(x) {
  rowSums(x@net$count) + colSums(x@net$count) - diag(x@net$count)
})
weight.MinMax <- c(min(num.link), max(num.link))
gg <- lapply(seq_along(object.list), function(i) {
  netAnalysis_signalingRole_scatter(object.list[[i]],
                                    title = names(object.list)[i],
                                    weight.MinMax = weight.MinMax)
})
patchwork::wrap_plots(plots = gg)

# 特定细胞群的信号变化
gg <- netAnalysis_signalingChanges_scatter(cellchat.merged,
                                            idents.use = "目标细胞类型",
                                            signaling.exclude = "MIF")
```

### Step 4：差异信号通路分析
```r
# 气泡图展示各条件下特定互作的强度变化
netVisual_bubble(cellchat.merged,
                 sources.use = c(1,2),
                 targets.use = c(4,5),
                 comparison = c(1,2),
                 max.dataset = 2,
                 title.name = "Condition B vs Condition A",
                 angle.x = 45,
                 remove.isolate = TRUE)

# 弦图展示增加/减少的互作
par(mfrow=c(1,2), xpd=TRUE)
netVisual_chord_gene(object.list[[2]],
                     sources.use = c(1,2), targets.use = c(4,5),
                     title.name = paste0("Up-regulated signaling in ", names(object.list)[2]),
                     color.use = ...)
```

### Step 5：联合流形学习
```r
# 功能相似性（适用于相同细胞组成）
cellchat.merged <- computeNetSimilarityPairwise(cellchat.merged, type = "functional")
cellchat.merged <- netEmbedding(cellchat.merged, type = "functional")
cellchat.merged <- netClustering(cellchat.merged, type = "functional")
netVisual_embeddingPairwise(cellchat.merged, type = "functional", label.size = 3.5)

# 通路排序（按两条件间差异大小）
rankNet(cellchat.merged, mode = "comparison", stacked = TRUE, do.stat = TRUE)
```

---

## 5. 空间转录组 CCC（Spatial CCC）

### 与普通 CCC 的关键区别
```
普通 CCC：基于配受体表达推断，无空间约束
空间 CCC：在配受体基础上，叠加空间接近性约束（spot 间距离）
```

### 核心参数
```r
# contact.range：定义通讯的最大空间距离（单位同坐标系）
# 推荐：先可视化 spot 间距离分布后确定

cellchat <- computeCommunProb(cellchat,
                               type = "truncatedMean",
                               trim = 0.1,
                               distance.use = TRUE,          # 启用空间约束
                               interaction.range = 250,      # 最大通讯距离（µm）
                               scale.distance = 0.01,        # 距离衰减系数
                               contact.dependent = TRUE,
                               contact.range = 100)          # 直接接触范围
```

### 空间 CCC 可视化
```r
# 空间网络可视化（在组织切片图上展示通讯）
netVisual_aggregate(cellchat, signaling = pathways.show,
                    layout = "spatial",
                    edge.width.max = 2,
                    vertex.size.max = 1,
                    alpha.image = 0.2,
                    vertex.label.size = 3.5)
```

---

## 6. 常见问题（FAQ）

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 已知通路未被预测到 | `triMean` 过于严格 | 改用 `truncatedMean, trim=0.1` |
| 通讯数量过少 | min.cells 过高 | 降低 `filterCommunication(min.cells=5)` |
| 内存不足 | 数据量大 | 先 `subsetData()` 再并行；或分批处理 |
| Chord diagram 有孤立 bar | circlize 包已知问题 | 忽略，不影响结果 |
| 基因名不匹配 | 数据库与数据物种不符 | 确认 `CellChatDB.human` vs `CellChatDB.mouse` |
| NMF 报错 | pattern 数过大 | 减小 `k` 值，`selectK()` 辅助确定 |
| Seurat v5 数据提取 | API 变更 | 用 `seurat_object[["RNA"]]$data` 而非 `@data` |

---

## 7. 关键输出解读

### 结果存储位置
```r
cellchat@net$count    # 互作数量矩阵（细胞群 × 细胞群）
cellchat@net$weight   # 互作强度矩阵
cellchat@netP         # pathway 级别通讯概率
cellchat@netP$pathways # 所有显著通讯通路列表
cellchat@idents       # 细胞群标签

# 提取为 data.frame
df.LR  <- subsetCommunication(cellchat)                    # L-R pair 级别
df.path <- subsetCommunication(cellchat, slot.name = "netP")  # pathway 级别
```

### 图形解读要点
- **圆圈图**：边的颜色 = sender 颜色，边的粗细 = 信号强度
- **层级图**：左侧实心圆 = sender，右侧空心圆 = receiver
- **弦图内侧细条**：接收方接收到的信号强度
- **散点图**：x轴=outgoing总强度，y轴=incoming总强度，点大小=连接数
- **差异圆圈图**：红色边=第二组增加，蓝色边=第二组减少
- **河流图（Alluvial）**：展示细胞群-模式-通路三者关联

---

## 8. 推荐分析报告输出结构

```
results/CCC/
├── 01_overview/
│   ├── circle_count.pdf         # 互作数量总览
│   ├── circle_weight.pdf        # 互作强度总览
│   └── per_celltype_circle.pdf  # 每个细胞群发出的信号
├── 02_pathways/
│   ├── {pathway}_hierarchy.pdf  # 每个通路的层级图
│   ├── {pathway}_chord.pdf      # 弦图
│   └── {pathway}_LR_contribution.pdf  # L-R pair 贡献
├── 03_bubble_plots/
│   └── bubble_{source}_{target}.pdf
├── 04_signaling_roles/
│   ├── role_scatter.pdf         # 2D 信号角色散点图
│   ├── outgoing_heatmap.pdf
│   └── incoming_heatmap.pdf
├── 05_patterns/
│   ├── outgoing_river.pdf
│   ├── outgoing_dot.pdf
│   ├── incoming_river.pdf
│   └── incoming_dot.pdf
├── 06_manifold/
│   ├── functional_embedding.pdf
│   └── structural_embedding.pdf
└── cellchat_result.rds          # 保存的 CellChat 对象
```

---

## 9. 完整流程 R 脚本模板

参见同目录下：
- `scripts/01_single_dataset_CCC.R`  — 单数据集完整流程
- `scripts/02_comparison_CCC.R`      — 多数据集比较流程
- `scripts/03_spatial_CCC.R`         — 空间转录组 CCC 流程
- `scripts/04_from_anndata.R`        — 从 Anndata/Scanpy 输入

---

## 10. 参考文献

1. Jin S, et al. **CellChat v2** — Nature Communications, 2024
2. Jin S, et al. **Inference and analysis of CCC using CellChat** — Nature Communications, 2021
3. Luecken MD & Theis FJ. **Current best practices in single‑cell RNA‑seq analysis** — Mol Syst Biol, 2019

