---
name: Batch — 批次校正
version: 1.0.0
scope: 多批次单细胞数据整合与批次效应校正（Harmony / CCA / scVI / Seurat integration）
languages: [R, Python]
triggers: [harmony, batch, integration, 批次, 校正, harmony integration, seurat integration, mnn, combat, scvi]
---
# Skill: Batch — 批次校正
# CellClaw Skill Knowledge Base
# Version: 1.0.0
# Author: CellClaw
# Scope: 多批次单细胞数据整合与批次校正
# Based on: Harmony, Seurat CCA/RC/RPCA, scVI (Python)

---

## 1. Skill 概述

**批次校正（Batch Correction）** 用于消除不同样本/测序批次之间的技术变异，使多批次数据能够整合分析。

### 适用场景
| 场景 | 说明 |
|------|------|
| 多个样本整合 | 10X 多样本、多个lane |
| 跨平台整合 | Smart-seq2 + 10X |
| 跨物种整合 | 需要小心处理 |
| 时间序列 | 不同时间点的样本 |

### 工具要求
- **R** ≥ 4.1.0
- **Harmony**（`remotes::install_github('immunogenomics/harmony')`）
- **Seurat** ≥ 5.0.0
- **scVI**（Python，需要 GPU 推荐）

---

## 2. 输入数据要求

### 必需输入
```
多个样本的 Seurat 对象（或列表）
批次标签：metadata 中的 batch 列
```

### 支持的输入格式
| 格式 | 处理方式 |
|------|---------|
| 多个 .rds 文件 | 分别读取后合并 |
| 10X 目录列表 | 分别读取后合并 |
| 已合并的 Seurat | 直接校正 |

### ⚠️ 重要注意事项
- **批次校正是有风险的** — 过度校正可能丢失生物信号
- **先聚类再校正** 确认批次效应不是生物差异
- **保留原始数据** 校正后也要保留一份未校正的

---

## 3. 方法对比

| 方法 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| Harmony | 快，准，默认首选 | 保守 | 大多数场景 |
| CCA | 可跨平台 | 慢，可能丢失信息 | Smart-seq + 10X |
| RPCA | 比 CCA 快 | 效果略差 | 大数据 |
| scVI | 深度学习，精度高 | 需要 GPU | 追求最佳效果 |

---

## 4. 标准流程：Harmony（推荐）

### Step 1: 合并数据
```r
library(Seurat)
library(harmony)

# 方式 1: 多个 Seurat 合并
seu.list <- lapply(sample_files, readRDS)
seu.combined <- merge(seu.list[[1]], seu.list[-1], add.cell.ids = samples)

# 方式 2: 直接读取 10X
samples <- c("SampleA", "SampleB", "SampleC")
seu.list <- lapply(samples, function(s) {
    tmp <- Read10X(paste0("data/", s))
    CreateSeuratObject(tmp, project = s)
})
seu.combined <- merge(seu.list[[1]], seu.list[-1])
```

### Step 2: 添加批次标签
```r
# 假设样本名作为批次
seu.combined$batch <- seu.combined$orig.ident

# 或手动设置
seu.combined$batch <- c(rep("batch1", 3000), rep("batch2", 2500), rep("batch3", 2800))
```

### Step 3: 标准预处理
```r
seu.combined <- NormalizeData(seu.combined)
seu.combined <- FindVariableFeatures(seu.combined)
seu.combined <- ScaleData(seu.combined)
seu.combined <- RunPCA(seu.combined, npcs = 50)
```

### Step 4: Harmony 校正
```r
seu.combined <- RunHarmony(
    seu.combined,
    group.by.vars = "batch",      # 批次列
    dims.use = 1:30,             # 用哪些 PC
    theta = 2,                   # 校正强度，越大越激进
    lambda = 1,                  # 正则化参数
    sigma = 0.1,                # 邻居半径
    nclust = 50,                 # 初始聚类数
    tau = 0,                     # 0 = 硬分配
    max.iter.cluster = 20,      # 最大迭代
    max.iter.emb = 10,
    method = "equal"             # equal / flexible
)

# 查看 Harmony 嵌入
seu.combined <- RunUMAP(seu.combined, reduction = "harmony", dims = 1:30)
```

### Step 5: 聚类
```r
seu.combined <- FindNeighbors(seu.combined, reduction = "harmony", dims = 1:30)
seu.combined <- FindClusters(seu.combined, resolution = 0.5)
```

---

## 5. Seurat Integration（备选）

### CCA（慢，跨平台）
```r
# 找 anchor
anchors <- FindIntegrationAnchors(
    object.list = seu.list,
    dims = 1:30,
    anchor.features = 2000,
    k.anchor = 5
)

# 整合
seu.integrated <- IntegrateData(anchors, dims = 1:30)

# 后续
seu.integrated <- ScaleData(seu.integrated)
seu.integrated <- RunPCA(seu.integrated)
seu.integrated <- RunUMAP(seu.integrated, dims = 1:30)
```

### RPCA（更快）
```r
# 快速模式
anchors <- FindIntegrationAnchors(
    object.list = seu.list,
    dims = 1:30,
    reduction = "rpca",
    k.anchor = 5
)
seu.integrated <- IntegrateData(anchors, dims = 1:30)
```

---

## 6. 验证批次校正效果

### 校正前 vs 校正后
```r
# 用原始 PCA
p1 <- DimPlot(seu.combined, reduction = "pca", group.by = "batch")
# 用 Harmony
p2 <- DimPlot(seu.combined, reduction = "harmony", group.by = "batch")

# 拼图
p1 + p2
```

### 批次效应指标
```r
# 1. kBET（批次效应测试）
library(kBET)
pca <- seu.combined@reductions$pca@cell.embeddings[,1:30]
batch <- seu.combined$batch
kbet_result <- kBET(pca, batch)

# 2. PC regression（看批次方差）
# 在 PC space 回归批次，看 R²
```

---

## 7. 输出文件规范

**⚠️ 所有输出文件名必须以 `result_` 开头！**

```r
# 校正后的 Seurat
saveRDS(seu.combined, "result_seurat_harmony.rds")

# Cluster 分配
cluster_df <- data.frame(
    cell_id = colnames(seu.combined),
    batch = seu.combined$batch,
    cluster = Idents(seu.combined),
    UMAP_1 = seu.combined@reductions$umap@cell.embeddings[,1],
    UMAP_2 = seu.combined@reductions$umap@cell.embeddings[,2]
)
write.csv(cluster_df, "result_batch_integration.csv", row.names = FALSE)

# 可视化
png("result_batch_comparison.png", width = 14, height = 6, units = "in", res = 300)
p1 <- DimPlot(seu.combined, reduction = "pca", group.by = "batch")
p2 <- DimPlot(seu.combined, reduction = "harmony", group.by = "batch")
p1 + p2
dev.off()

png("result_harmony_clusters.png", width = 10, height = 8, units = "in", res = 300)
DimPlot(seu.combined, reduction = "umap", group.by = "seurat_clusters", label = TRUE)
dev.off()
```

---

## 8. 常见问题

### Q1: 校正后cluster乱掉了
**原因**: `theta` 太大，校正过度

**解决**:
```r
seu.combined <- RunHarmony(seu.combined, group.by.vars = "batch", theta = 0.5)
```

### Q2: 批次效应仍然存在
**原因**: 批次差异太大，或用了错误的方法

**解决**:
- 检查原始数据质量
- 尝试 CCA（跨平台）
- 检查是否有生物差异被误判为批次

### Q3: 不同方法的对比
**解决**: 
```r
# 试试不同方法
seu <- RunHarmony(...)
seu <- RunUMAP(seu, reduction = "harmony")

seu <- RunUMAP(seu, reduction = "pca")  # 对比
```

---

## 9. 参考资料

- Harmony: https://github.com/immunogenomics/harmony
- Harmony paper: https://www.nature.com/articles/s41592-019-0619-0
- Seurat Integration: https://satijalab.org/seurat/articles/integration_introduction.html
- kBET: https://github.com/theislab/kBET
