---
name: DimReduc — 标准降维聚类
version: 1.0.0
scope: 单细胞标准分析流程（归一化 → PCA → UMAP/tSNE → Clustering）
languages: [R]
triggers: [umap, tsne, pca, clustering, 降维, 聚类, findclusters, louvain, leiden, seurat workflow]
---
# Skill: DimReduc — 标准降维聚类
# OmicsClaw Skill Knowledge Base
# Version: 1.0.0
# Author: CellClaw
# Scope: 单细胞标准降维聚类流程
# Based on: Seurat v5

---

## 1. Skill 概述

**标准降维聚类流程** 是单细胞数据分析的第一步，包括数据归一化、特征选择、降维（PCA/UMAP/tSNE）和聚类（Louvain/Leiden）。

### 适用场景
| 场景 | 说明 |
|------|------|
| 原始数据分析 | 从头开始的标准流程 |
| 重新聚类 | 已有数据，调整 resolution |
| 多批次整合 | 批次校正后的聚类 |

### 工具要求
- **R** ≥ 4.1.0
- **Seurat** ≥ 5.0.0
- **ggplot2**（可视化）
- **patchwork**（拼图）

---

## 2. 输入数据要求

### 必需输入
```
表达矩阵：基因 × 细胞，raw count 或归一化后
```

### 支持的输入格式
| 格式 | 读取方式 |
|------|---------|
| 10X 目录 | `Read10X()` |
| Seurat 对象 | `readRDS()` |
| CSV/TSV | `ReadMtx()` / `read.table()` |
| AnnData | `anndata::read_h5ad()` → 转换 |

### ⚠️ 重要注意事项
- **Raw count 用 `NormalizeData()` 归一化**，不要直接用 TPM/CPM
- **特征选择**：`FindVariableFeatures()` 默认 top 2000
- **ScaleData`**：PCA 前必须做，用于消除细胞间技术变异
- **聚类 resolution**：0.2-0.8 适合一般数据，太高会过度细分

---

## 3. 标准分析流程

### Step 1: 创建 Seurat 对象
```r
library(Seurat)
library(dplyr)

# 方式 1: 从矩阵创建
raw <- ReadMtx("matrix.mtx", features = "features.tsv", cells = "barcodes.tsv")
seu <- CreateSeuratObject(counts = raw, project = "scRNA", min.cells = 3, min.features = 200)

# 方式 2: 从 10X 创建
seu <- Read10X("10x_dir/")
seu <- CreateSeuratObject(counts = seu, project = "scRNA")

# 方式 3: 从 RDS 加载
seu <- readRDS("input.rds")
```

### Step 2: 质控（QC）
```r
# 线粒体基因比例
seu[["percent.mt"]] <- PercentageFeatureSet(seu, pattern = "^MT-")

# Ribosomal 基因
seu[["percent.rb"]] <- PercentageFeatureSet(seu, pattern = "^RP[SL]")

# QC 阈值（根据数据调整）
seu <- subset(seu, 
    nFeature_RNA > 200 & nFeature_RNA < 5000 &
    nCount_RNA > 500 & nCount_RNA < 50000 &
    percent.mt < 20
)
```

### Step 3: 归一化
```r
seu <- NormalizeData(
    seu,
    normalization.method = "LogNormalize",
    scale.factor = 10000
)
```

### Step 4: 特征选择
```r
seu <- FindVariableFeatures(
    seu,
    selection.method = "vst",
    nfeatures = 2000,
    verbose = FALSE
)

# 查看 top 10
top10 <- head(VariableFeatures(seu), 10)
plot1 <- VariableFeaturePlot(seu)
plot2 <- LabelPoints(plot = plot1, points = top10, repel = TRUE)
```

### Step 5: 标准化（线性变换）
```r
all.genes <- rownames(seu)
seu <- ScaleData(seu, features = all.genes, vars.to.regress = c("percent.mt", "nCount_RNA"))
```

### Step 6: PCA 降维
```r
seu <- RunPCA(
    seu,
    features = VariableFeatures(seu),
    npcs = 50,
    verbose = FALSE
)

# PCA 可视化
DimPlot(seu, reduction = "pca")
ElbowPlot(seu, ndims = 50)  # 找拐点
```

### Step 7: UMAP / tSNE
```r
# UMAP（更快，推荐）
seu <- RunUMAP(
    seu,
    dims = 1:30,              # 使用前 30 个 PC
    reduction = "pca",
    n.neighbors = 30,
    min.dist = 0.3,
    metric = "cosine"
)

# tSNE（可选）
seu <- RunTSNE(
    seu,
    dims = 1:30,
    reduction = "pca",
    perplexity = 30
)
```

### Step 8: 聚类
```r
# 构建邻居图
seu <- FindNeighbors(seu, dims = 1:30, reduction = "pca")

# Louvain 聚类
seu <- FindClusters(
    seu,
    resolution = 0.5,          # 0.2-0.8 常用
    algorithm = 1,            # 1 = Louvain, 2 = Leiden, 3 = SLM
    verbose = FALSE
)

# Leiden 聚类（更准确）
seu <- FindClusters(
    seu,
    resolution = 0.5,
    algorithm = 4,            # 4 = Leiden
    method = "igraph"
)
```

### Step 9: 可视化
```r
# UMAP + Cluster
DimPlot(seu, reduction = "umap", label = TRUE)

# 按基因表达着色
FeaturePlot(seu, features = c("CD3D", "MS4A1", "CD14"))

# 小提琴图
VlnPlot(seu, features = c("nFeature_RNA", "nCount_RNA", "percent.mt"))
```

---

## 4. 参数详解

### NormalizeData
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `normalization.method` | "LogNormalize" | LogNormalize / CLR / RC |
| `scale.factor` | 10000 | 缩放因子 |

### FindVariableFeatures
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `selection.method` | "vst" | vst / mean.var.plot / dispersion |
| `nfeatures` | 2000 | 选多少个高变基因 |

### RunPCA
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `npcs` | 50 | 计算多少个 PC |
| `features` | VariableFeatures() | 用哪些特征 |

### RunUMAP
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `dims` | 1:30 | 用哪些 PC |
| `n.neighbors` | 30 | 邻居数，越大越关注全局结构 |
| `min.dist` | 0.3 | 最小距离，越小越紧凑 |
| `metric` | "euclidean" | cosine / euclidean / manhattan |

### FindClusters
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `resolution` | 0.5 | 聚类分辨率，越高 cluster 越多 |
| `algorithm` | 1 | 1=Louvain, 2=SLM, 3=Leiden(旧版), 4=Leiden(新版) |

---

## 5. 输出文件规范

**⚠️ 所有输出文件名必须以 `result_` 开头！**

```r
# RDS 对象
saveRDS(seu, "result_seurat_object.rds")

# Cluster 分配表
cluster_df <- data.frame(
    cell_id = colnames(seu),
    cluster = Idents(seu),
    UMAP_1 = seu@reductions$umap@cell.embeddings[,1],
    UMAP_2 = seu@reductions$umap@cell.embeddings[,2]
)
write.csv(cluster_df, "result_cluster_assignments.csv", row.names = FALSE)

# 可视化
png("result_umap_clusters.png", width = 10, height = 8, units = "in", res = 300)
DimPlot(seu, reduction = "umap", label = TRUE)
dev.off()

png("result_qc_violin.png", width = 12, height = 6, units = "in", res = 300)
VlnPlot(seu, features = c("nFeature_RNA", "nCount_RNA", "percent.mt"), ncol = 3)
dev.off()
```

---

## 6. 常见问题

### Q1: Cluster 太少或太多
**解决**: 调整 `FindClusters()` 的 `resolution` 参数
```r
# 尝试不同 resolution
for (res in c(0.2, 0.4, 0.6, 0.8)) {
    seu <- FindClusters(seu, resolution = res)
    print(table(Idents(seu)))
}
```

### Q2: PCA 贡献太分散
**原因**: 数据噪音大，可能需要更多 QC

**解决**: 
- 检查 `percent.mt` 是否太高
- 调整 `FindVariableFeatures` 的 `nfeatures`
- 尝试回归 `percent.mt`

### Q3: UMAP 成像不连续
**原因**: 数据有批次效应或技术噪音

**解决**:
- 先做批次校正（Harmony / CCA）
- 调整 `n.neighbors` 和 `min.dist`

---

## 7. 完整示例

```r
# 完整流程（从原始数据）
seu <- Read10X("data/") %>% CreateSeuratObject()
seu <- NormalizeData() %>% FindVariableFeatures() %>% ScaleData()
seu <- RunPCA() %>% RunUMAP(dims = 1:30) %>% FindNeighbors() %>% FindClusters()
DimPlot(seu, reduction = "umap", label = TRUE)
saveRDS(seu, "result_final.rds")
```

---

## 8. 参考资料

- Seurat 基础流程: https://satijalab.org/seurat/articles/pbmc3k_tutorial.html
- 聚类算法对比: https://www.nature.com/articles/s41592-019-0569-6
