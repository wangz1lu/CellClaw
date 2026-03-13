---
name: DEG — 差异基因分析
version: 1.0.0
scope: 单细胞差异表达分析（两组比较 / 多组比较）
languages: [R, Python]
triggers: [deg, dge, differential expression, 差异基因, findmarkers, mast, wilcox, t test, 比较基因]
---
# Skill: DEG — 差异基因分析
# OmicsClaw Skill Knowledge Base
# Version: 1.0.0
# Author: CellClaw
# Scope: 单细胞差异表达分析（两组比较 / 多组比较）
# Based on: Seurat, MAST, presto, limma-voom

---

## 1. Skill 概述

**差异基因分析（Differential Gene Expression, DEG）** 是单细胞数据分析的核心步骤，用于识别不同细胞类型、cluster 或条件之间表达显著差异的基因。

### 适用场景
| 场景 | 说明 |
|------|------|
| Cluster vs Cluster | 识别特定 cluster 的 marker 基因 |
| 细胞类型比较 | 疾病组 vs 对照组的差异表达 |
| 条件刺激响应 | 处理前后差异基因 |
| 时间序列 | 不同时间点的差异基因 |

### 工具要求
- **R** ≥ 4.1.0
- **Seurat** ≥ 5.0.0（`remotes::install_github('satijalab/seurat')`）
- 可选方法：`MAST`（`BiocManager::install("MAST")`）、`presto`（快）、`edgeR`、`DESeq2`（bulk 也可用）

---

## 2. 输入数据要求

### 必需输入
```
数据矩阵：基因 × 细胞，归一化后（log1p）
细胞注释：metadata 必须有用于分组的列（ident / group / cluster）
```

### 支持的输入格式
| 格式 | 处理方式 |
|------|---------|
| Seurat 对象 (.rds) | 直接 `FindMarkers()` |
| 归一化矩阵 + meta.data | 构建 Seurat 对象 |
| AnnData (.h5ad) | anndata + Seurat 转换 |
| SingleCellExperiment | as.Seurat() 转换 |

### ⚠️ 重要注意事项
- **输入数据必须是 log1p 归一化后的数据**，不是原始 count
- `FindMarkers` 默认使用 `ident` 列作为分组，可通过 `group.by` 指定其他列
- 对于 cluster marker，建议用 `only.pos = TRUE` 筛选上调基因
- **pseudobulk 方法**（聚合后用 DESeq2/edgeR）比 single-cell 方法更稳定，适合细胞数较少的情况

---

## 3. 标准分析流程

### Step 1: 数据准备
```r
library(Seurat)
library(dplyr)

# 加载数据
seu <- readRDS("input.rds")

# 查看分组信息
table(seu$seurat_clusters)  # cluster 分组
table(seu$group)            # 条件分组（如果有用 group）

# 设置要比较的组别
Idents(seu) <- "seurat_clusters"  # 或 "group"
```

### Step 2: 两组比较（Cluster Marker / Condition vs Control）

#### 方法 1: Wilcoxon Rank Sum Test（默认，最常用）
```r
# Cluster 1 vs 所有其他 Cluster
deg <- FindMarkers(
    seu,
    ident.1 = "1",                    # 要比较的组
    ident.2 = NULL,                   # NULL = 与所有其他组比较
    test.use = "wilcox",              # 默认
    min.pct = 0.1,                    # 基因在两组中至少 10% 的细胞表达
    logfc.threshold = 0.25,           # log fold change 阈值
    only.pos = FALSE,                 # 是否只保留上调基因
    densify = FALSE                   # 对于大型数据用 TRUE
)
```

#### 方法 2: MAST（考虑表达率，更严格）
```r
# 需要额外安装：BiocManager::install("MAST")
deg <- FindMarkers(
    seu,
    ident.1 = "1",
    ident.2 = "0",
    test.use = "mast",
    min.pct = 0.1,
    logfc.threshold = 0
)
```

#### 方法 3: presto（快，适合大规模）
```r
# 需要安装：remotes::install_github("immunogenomics/presto")
deg <- FindMarkers(
    seu,
    ident.1 = "1",
    ident.2 = "0",
    test.use = "presto",
    only.pos = FALSE
)
```

### Step 3: 多组比较（ANOVA-style）
```r
# 多个 cluster 的差异分析（逐一比较）
clusters <- unique(seu$seurat_clusters)
all_deg <- list()

for (i in clusters) {
    for (j in clusters) {
        if (i < j) {
            deg <- FindMarkers(seu, ident.1 = i, ident.2 = j)
            deg$cluster1 <- i
            deg$cluster2 <- j
            deg$gene <- rownames(deg)
            all_deg <- rbind(all_deg, deg)
        }
    }
}
```

### Step 4: 结果筛选与可视化
```r
# 筛选显著差异基因
sig_deg <- deg[deg$p_val_adj < 0.05 & abs(deg$avg_log2FC) > 0.5, ]
sig_deg <- sig_deg[order(sig_deg$avg_log2FC, decreasing = TRUE), ]

# 热图
top_genes <- head(rownames(sig_deg), 20)
DoHeatmap(seu, features = top_genes, group.by = "seurat_clusters")

# 小提琴图
VlnPlot(seu, features = c("GeneA", "GeneB"), split.by = "group")

# 散点图（FeaturePlot）
FeaturePlot(seu, features = c("GeneA", "GeneB"), reduction = "umap")
```

---

## 4. 参数详解

### FindMarkers 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ident.1` | 必填 | 比较组 1（字符串或数字） |
| `ident.2` | NULL | 比较组 2，NULL = 与所有其他组比较 |
| `test.use` | "wilcox" | 统计方法：wilcox / mast / t / negbinom / poisson /DESeq2 / presto |
| `min.pct` | 0.1 | 基因在两组中表达的细胞比例阈值 |
| `logfc.threshold` | 0.25 | logFC 阈值 |
| `only.pos` | FALSE | 是否只保留上调基因 |
| `return.thresh` | 0.05 | p_val_adj 阈值 |
| `base` | 2 | logFC 计算的底数 |

### 各方法适用场景

| 方法 | 适用场景 | 优缺点 |
|------|---------|--------|
| Wilcoxon | 常规 marker 检测 | 快，不假设分布 |
| MAST | 需要考虑表达率 | 慢，更严格 |
| t-test | 大样本 | 简单，快 |
| presto | 大数据集 | 极快，结果准 |
| DESeq2/edgeR | Pseudobulk / Bulk | 需要聚合 |

---

## 5. 输出文件规范

**⚠️ 所有输出文件名必须以 `result_` 开头！**

```r
# CSV：完整 DEG 结果
write.csv(deg, "result_deg_full.csv", row.names = TRUE)

# CSV：显著 DEG（筛选后）
write.csv(sig_deg, "result_deg_significant.csv")

# CSV：Top DEG（每个方向 top N）
top_up <- head(sig_deg[sig_deg$avg_log2FC > 0, ], 50)
top_down <- head(sig_deg[sig_deg$avg_log2FC < 0, ], 50)
write.csv(rbind(top_up, top_down), "result_deg_top50.csv")

# RDS：完整 Seurat 对象（带 DEG 结果）
deg$gene <- rownames(deg)
seu@misc$deg_results <- deg
saveRDS(seu, "result_deg_seurat_object.rds")
```

---

## 6. 常见问题

### Q1: 没有差异基因
**原因**: 
- `min.pct` 或 `logfc.threshold` 太高
- 两组之间确实没有显著差异
- 数据质量差

**解决**: 
```r
# 降低阈值
FindMarkers(seu, ident.1 = "1", ident.2 = "0", 
            min.pct = 0.05, logfc.threshold = 0.1)
```

### Q2: 某 cluster 的 marker 很少
**原因**: 该 cluster 与其他 cluster 差异不明显

**解决**: 
- 用 `only.pos = FALSE` 查看双向差异
- 检查 cluster 注释是否正确
- 考虑增加 resolution

### Q3: p_val_adj 很高
**原因**: 多重检验校正（Benjamini-Hochberg）

**解决**: 
- 关注 `avg_log2FC` 而不只是 p 值
- 差异基因数量和生物学意义更重要

---

## 7. Pseudobulk 方法（高级）

当单细胞方法不稳定时（细胞数少），用 pseudobulk：

```r
# 1. 聚合每个 cluster 的平均表达
expr <- AverageExpression(seu, group.by = "seurat_clusters")
expr_matrix <- expr$RNA

# 2. 用 DESeq2 / edgeR 做差异分析
library(DESeq2)
coldata <- data.frame(condition = c("ClusterA", "ClusterB", "ClusterC"))
dds <- DESeqDataSetFromMatrix(expr_matrix, coldata, design = ~condition)
dds <- DESeq(dds)
results <- results(dds)
```

---

## 8. 参考资料

- Seurat FindMarkers: https://satijalab.org/seurat/articles/find_markers
- MAST paper: https://www.nature.com/articles/nmeth.3969
- Pseudobulk 最佳实践: https://www.nature.com/articles/s41596-021-00546-x
