---
name: Annotation — 细胞类型注释
version: 1.0.0
scope: 单细胞自动注释（scType / CellTypist / manual）
languages: [R, Python]
triggers: [annotation, 注释, celltype, sctype, celltypist, annotate, manual annotation, marker genes, 细胞类型]
---
# Skill: Annotation — 细胞类型注释
# CellClaw Skill Knowledge Base
# Version: 1.0.0
# Author: CellClaw
# Scope: 单细胞细胞类型自动注释
# Based on: scType, CellTypist, SingleR, manual annotation

---

## 1. Skill 概述

**细胞类型注释** 是单细胞分析的关键步骤，将聚类产生的 cluster 标记为具体的细胞类型（如 T cells, B cells, Macrophages）。

### 适用场景
| 场景 | 说明 |
|------|------|
| 自动注释 | 用已知细胞类型 marker 数据库快速注释 |
| 精细注释 | 细分免疫细胞/肝细胞等特定类型 |
| 交叉验证 | 多种方法对比，提高准确性 |

### 工具要求
- **R**: scType, SingleR
- **Python**: CellTypist（推荐，精度高）

---

## 2. 输入数据要求

### 必需输入
```
已聚类的 Seurat 对象（cluster 已有）
表达矩阵（归一化后）
```

### ⚠️ 重要注意事项
- **注释前确保聚类质量好**，如果 cluster 混杂，注释会不准
- **自动注释只是辅助**，最终需要人工验证
- **marker 基因是核心**，了解常见细胞类型的 marker 很重要

---

## 3. 方法一：scType（R，推荐）

### 安装
```r
remotes::install_github("IanevskiAleksandr/scType", force = TRUE)
```

### 准备 Marker 基因库
```r
# scType 内置的细胞类型 marker（可自定义）
# 免疫细胞
gs_list <- list(
    Immune = c("CD3D", "CD3E", "CD3G", "CD247"),  # T cells
    B = c("CD79A", "CD79B", "MS4A1", "CD19"),    # B cells  
    NK = c("NKG7", "GNLY", "KLRD1", "GZMA"),    # NK cells
    Monocyte = c("CD14", "CD68", "CD163", "MS4A4A"),
    Macrophage = c("CD68", "CD163", "MARCO", "CX3CR1"),
    DC = c("FCER1A", "CD1C", "CST3", "TPSAB1"),
    Mast = c("TPSAB1", "TPSB2", "MS4A2", "HDC")
)
```

### 运行 scType
```r
library(scType)

# 输入数据
expression_matrix <- GetAssayData(seu, layer = "data")

# 注释
results <- scType(
    expression_matrix = expression_matrix,
    gs_list = gs_list,
    species = "Human"
)

# 添加到 Seurat
seu$celltype_sctype <- results$cell_type
```

---

## 4. 方法二：CellTypist（Python，推荐）

### 安装
```python
pip install celltypist
```

### 使用
```python
import celltypist
from celltypist import models

# 下载模型（首次）
model = models.Model.load(model = 'Immune_All_Low.pkl')

# 注释
predictions = model.predict(input_file, gene_symbols = True)

# 合并结果
import scanpy as sc
adata.obs['celltype_celltypist'] = predictions.predicted_labels
```

### 常用模型
| 模型 | 说明 |
|------|------|
| `Immune_All_Low.pkl` | 免疫细胞（低分辨率）|
| `Immune_All_High.pkl` | 免疫细胞（高分辨率）|
| `Cell_Type_Human.pkl` | 全部细胞类型 |

---

## 5. 方法三：SingleR（R）

### 安装
```r
BiocManager::install("SingleR")
BiocManager::install("celldex")
```

### 使用
```r
library(SingleR)
library(celldex)

# 参考数据
ref <- HumanPrimaryCellAtlasData()

# 注释
pred <- SingleR(
    test = seu@assays$RNA@data,
    ref = ref,
    labels = ref$label.main
)

# 添加结果
seu$celltype_singler <- pred$labels
```

---

## 6. 方法四：Manual 注释（基于 Marker）

### 步骤
1. 找每个 cluster 的 marker 基因
2. 对比已知 marker 库
3. 手动分配细胞类型

```r
# 找 cluster marker
all_markers <- FindAllMarkers(seu, only.pos = TRUE, logfc.threshold = 0.5)

# 常用免疫细胞 marker
marker_genes <- list(
    T_cells = c("CD3D", "CD3E", "CD4", "CD8A", "CD8B"),
    B_cells = c("CD79A", "MS4A1", "CD19"),
    NK_cells = c("NKG7", "GNLY", "KLRD1"),
    Monocytes = c("CD14", "CD68", "FCGR3A"),
    DC = c("CD1C", "FCER1A", "CST3"),
    Mast = c("TPSAB1", "TPSB2"),
    Macrophages = c("CD163", "MS4A4A", "CX3CR1"),
    Prolif = c("MKI67", "TOP2A", "PCNA"),
    Platelet = c("PPBP", "PF4")
)

# 根据 marker 手动注释
cluster_annotations <- c(
    "0" = "CD4+ T cells",
    "1" = "CD8+ T cells", 
    "2" = "B cells",
    "3" = "Monocytes",
    "4" = "NK cells",
    "5" = "DC",
    "6" = "Macrophages",
    "7" = "Proliferating"
)

seu$celltype_manual <- unname(cluster_annotations[as.character(Idents(seu))])
```

---

## 7. 综合注释流程

```r
# 1. 自动注释（scType / CellTypist）
seu <- readRDS("result_seurat_clustered.rds")
seu <- run_sctype_annotation(seu)

# 2. 验证
DimPlot(seu, reduction = "umap", group.by = "celltype")

# 3. 精细调整（基于 marker）
VlnPlot(seu, features = c("CD3D", "CD4", "CD8A", "CD79A"))

# 4. 最终注释
seu$celltype_final <- seu$celltype_sctype  # 或手动调整
```

---

## 8. 输出文件规范

**⚠️ 所有输出文件名必须以 `result_` 开头！**

```r
# 注释结果表
annotation_df <- data.frame(
    cell_id = colnames(seu),
    cluster = Idents(seu),
    celltype_sctype = seu$celltype_sctype,
    celltype_manual = seu$celltype_manual,
    UMAP_1 = seu@reductions$umap@cell.embeddings[,1],
    UMAP_2 = seu@reductions$umap@cell.embeddings[,2]
)
write.csv(annotation_df, "result_celltype_annotation.csv", row.names = FALSE)

# RDS
saveRDS(seu, "result_seurat_annotated.rds")

# 可视化
png("result_celltype_umap.png", width = 12, height = 8, units = "in", res = 300)
DimPlot(seu, reduction = "umap", group.by = "celltype", label = TRUE)
dev.off()

# Marker 热图
png("result_marker_heatmap.png", width = 14, height = 10, units = "in", res = 300)
DoHeatmap(seu, features = c("CD3D", "CD4", "CD8A", "CD79A", "CD14", "NKG7"), group.by = "celltype")
dev.off()
```

---

## 9. 常见细胞类型 Marker

| 细胞类型 | Marker 基因 |
|----------|------------|
| CD4+ T | CD3D, CD4, IL7R |
| CD8+ T | CD3D, CD8A, GZMA |
| NK | NKG7, GNLY, KLRD1 |
| B | CD79A, MS4A1, CD19 |
| Monocyte | CD14, FCGR3A, LYZ |
| Macrophage | CD163, MS4A4A, CX3CR1 |
| DC | CD1C, FCER1A, CST3 |
| Mast | TPSAB1, TPSB2, MS4A2 |
| Plasma | IGJ, XBP1, MZB1 |
| Platelet | PPBP, PF4, SELPLG |
| Proliferating | MKI67, TOP2A, PCNA |
| Erythroid | HBA1, HBA2, HBB |

---

## 10. 参考资料

- scType: https://github.com/IanevskiAleksandr/scType
- CellTypist: https://www.celltypist.py
- SingleR: https://bioconductor.org/packages/release/bioc/html/SingleR.html
- Human Cell Atlas: https://www.cellgeni.com/
