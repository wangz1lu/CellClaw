---
name: Annotation — 细胞类型注释
version: 1.1.0
scope: 单细胞自动注释（ScType R / CellTypist Python）
languages: [R, Python]
triggers: [annotation, 注释, celltype, sctype, celltypist, annotate, marker genes, 细胞类型, 细胞注释]
---

# Skill: Annotation — 细胞类型注释

## 1. 概述

细胞类型注释是将聚类产生的 cluster 标记为具体细胞类型（如 T cells, B cells, Macrophages）。

| 工具 | 语言 | 特点 |
|------|------|------|
| **ScType** | R | 使用 marker gene list，自动匹配 |
| **CellTypist** | Python | 机器学习模型，精度高，支持 built-in 模型 |

---

## 2. Part A: ScType (R)

### 2.1 原理

ScType 通过对比细胞的基因表达与已知的正/负 marker 基因列表，自动判断细胞类型。

### 2.2 安装

```r
# 安装 scType
remotes::install_github("IanevskiAleksandr/sc-type", force = TRUE)
```

### 2.3 使用方法

#### 方法1：使用内置数据库

```r
library(dplyr)
library(Seurat)
library(HGNChelper)
library(openxlsx)

# 加载 scType 函数
source("https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/R/gene_sets_prepare.R")
source("https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/R/sctype_score_.R")

# 准备基因集（从内置数据库）
db_ <- "https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/ScTypeDB_full.xlsx"
tissue <- "Immune system"  # 可选: Liver, Pancreas, Kidney, Brain, Lung 等

gs_list <- gene_sets_prepare(db_, tissue)

# 检查 Seurat 版本
seurat_package_v5 <- isFALSE('counts' %in% names(attributes(pbmc[["RNA"]])))

# 提取表达矩阵
scRNAseqData_scaled <- if (seurat_package_v5) {
  as.matrix(pbmc[["RNA"]]$scale.data)
} else {
  as.matrix(pbmc[["RNA"]]@scale.data)
}

# 运行 ScType
es.max <- sctype_score(
  scRNAseqData = scRNAseqData_scaled, 
  scaled = TRUE, 
  gs = gs_list$gs_positive, 
  gs2 = gs_list$gs_negative
)

# 按 cluster 合并结果
cL_resutls <- do.call("rbind", lapply(unique(pbmc@meta.data$seurat_clusters), function(cl){
  es.max.cl = sort(rowSums(es.max[ ,rownames(pbmc@meta.data[pbmc@meta.data$seurat_clusters==cl, ])]), decreasing = !0)
  head(data.frame(
    cluster = cl, 
    type = names(es.max.cl), 
    scores = es.max.cl, 
    ncells = sum(pbmc@meta.data$seurat_clusters==cl)
  ), 10)
}))

# 获取每个 cluster 的最佳匹配
sctype_scores <- cL_resutls %>% group_by(cluster) %>% top_n(n = 1, wt = scores)

# 设置低置信度为 "Unknown"
sctype_scores$type[as.numeric(as.character(sctype_scores$scores)) < sctype_scores$ncells/4] <- "Unknown"

# 添加注释到 Seurat 对象
pbmc@meta.data$sctype_classification <- ""
for(j in unique(sctype_scores$cluster)){
  cl_type <- sctype_scores[sctype_scores$cluster==j,]
  pbmc@meta.data$sctype_classification[pbmc@meta.data$seurat_clusters == j] <- as.character(cl_type$type[1])
}

# 可视化
DimPlot(pbmc, reduction = "umap", label = TRUE, repel = TRUE, group.by = 'sctype_classification')
```

#### 方法2：使用自定义 Marker

```r
# 自定义 marker 基因列表
gs_list <- list(
  `T cells` = list(
    positive = c("CD3D", "CD3E", "CD3G", "CD247", "CD2", "CD7"),
    negative = c("CD79A", "MS4A1", "CD19")
  ),
  `B cells` = list(
    positive = c("CD79A", "CD79B", "MS4A1", "CD19", "CD20"),
    negative = c("CD3D", "CD3E", "NKG7")
  ),
  `NK cells` = list(
    positive = c("NKG7", "GNLY", "KLRD1", "GZMA", "GZMB"),
    negative = c("CD79A", "MS4A1")
  ),
  `Monocytes/Macrophages` = list(
    positive = c("CD14", "CD68", "CD163", "MS4A4A", "CX3CR1"),
    negative = c("CD3D", "CD79A")
  ),
  `DC` = list(
    positive = c("FCER1A", "CD1C", "CST3", "TPSAB1"),
    negative = c("CD3D", "CD79A")
  ),
  `Mast cells` = list(
    positive = c("TPSAB1", "TPSB2", "MS4A2", "HDC"),
    negative = c("CD3D", "CD79A")
  )
)

# 运行
es.max <- sctype_score(
  scRNAseqData = scRNAseqData_scaled,
  scaled = TRUE,
  gs = gs_list,
  gs2 = NULL  # 如果没有负 marker
)
```

### 2.4 自动检测组织类型

```r
source("https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/R/auto_detect_tissue_type.R")

# 自动检测
tissue_guess <- auto_detect_tissue_type(
  path_to_db_file = db_,
  seuratObject = pbmc,
  scaled = TRUE,
  assay = "RNA"
)
```

---

## 3. Part B: CellTypist (Python)

### 3.1 原理

CellTypist 使用逻辑回归模型进行细胞类型预测，支持：
- Built-in 模型（已训练好的）
- 自定义模型训练
- 多标签分类（概率阈值）

### 3.2 安装

```python
pip install celltypist
```

### 3.3 使用方法

#### 方法1：使用 Built-in 模型

```python
import scanpy as sc
import celltypist
from celltypist import models

# 下载模型（首次）
models.download_models(force_update=True)

# 查看可用模型
models.models_description()

# 加载模型
model = models.Model.load(model='Immune_All_Low.pkl')

# 预测（需要 log1p 归一化到 10000）
# 方法1: 直接预测
predictions = celltypist.annotate(adata, model='Immune_All_Low.pkl')

# 方法2: 使用 majority voting（更准确但更慢）
predictions = celltypist.annotate(adata, model='Immune_All_Low.pkl', majority_voting=True)

# 转换结果到 AnnData
adata = predictions.to_adata()

# 查看结果
print(predictions.predicted_labels)
print(adata.obs[['predicted_labels', 'majority_voting', 'conf_score']])

# 可视化
sc.tl.umap(adata)
sc.pl.umap(adata, color=['cell_type', 'predicted_labels', 'majority_voting'])
```

#### 方法2：训练自定义模型

```python
import scanpy as sc
import celltypist

# 准备训练数据（需要有 cell_type 标签）
adata_train = sc.read_h5ad('reference.h5ad')
# 确保数据是 log1p 归一化的
# adata_train.X = sc.pp.normalize_total(adata_train, target_sum=1e4, exclude_highly_expressed=True)
# adata_train.X = sc.pp.log1p(adata_train)

# 训练模型
# feature_selection=True 自动选择特征
model = celltypist.train(adata_train, labels='cell_type', n_jobs=10, feature_selection=True)

# 保存模型
model.write('my_model.pkl')

# 加载模型并预测
model = models.Model.load('my_model.pkl')
predictions = celltypist.annotate(adata_query, model=model, majority_voting=True)

# 合并结果
adata_result = predictions.to_adata()
```

#### 方法3：多标签分类（概率阈值）

```python
# 使用概率阈值进行多标签分类
# 模式: 'prob match'
predictions = celltypist.annotate(
    adata, 
    model='Immune_All_Low.pkl',
    mode='prob match',  # 启用概率模式
    p_thres=0.5,       # 概率阈值
    majority_voting=True
)

# 获取概率结果
adata = predictions.to_adata(insert_prob=True)

# 可视化
sc.pl.umap(adata, color=['cell_type', 'Macrophages', 'pDC'], vmin=0, vmax=1)
```

### 3.4 常用 Built-in 模型

| 模型 | 说明 | 细胞类型数 |
|------|------|-----------|
| `Immune_All_Low.pkl` | 免疫细胞（低分辨率） | ~90 |
| `Immune_All_High.pkl` | 免疫细胞（高分辨率） | ~100+ |
| `Cell_Type_Human.pkl` | 人类全部细胞类型 | ~100+ |

### 3.5 检查模型的 Marker 基因

```python
# 加载模型
model = models.Model.load('Immune_All_Low.pkl')

# 查看细胞类型
print(model.cell_types)

# 提取某细胞类型的 top marker
top_genes = model.extract_top_markers("Macrophages", top_n=10)
print(top_genes)

# 在数据中可视化
sc.pl.violin(adata_2000, top_genes, groupby='cell_type', rotation=90)
```

---

## 4. 输出文件规范

**⚠️ 所有输出文件名必须以 `result_` 开头！**

### Python 输出
```python
# 保存注释结果
adata.write('result_annotated.h5ad')

# 导出注释表
annotation_df = adata.obs[['predicted_labels', 'majority_voting', 'conf_score']].copy()
annotation_df.to_csv('result_celltype_annotation.csv')

# 保存模型
model.write('result_celltypist_model.pkl')
```

### R 输出
```r
# 保存带注释的 Seurat 对象
saveRDS(pbmc, "result_sctype_annotated.rds")

# 导出注释表
annotation_df <- data.frame(
  cell_id = colnames(pbmc),
  cluster = Idents(pbmc),
  sctype_classification = pbmc$sctype_classification
)
write.csv(annotation_df, "result_celltype_annotation.csv", row.names = FALSE)
```

---

## 5. 常见细胞类型 Marker

| 细胞类型 | Marker 基因 |
|----------|------------|
| CD4+ T | CD3D, CD4, IL7R, CCR7 |
| CD8+ T | CD3D, CD8A, GZMA, GZMB, NKG7 |
| NK | NKG7, GNLY, KLRD1, GZMA |
| B | CD79A, MS4A1, CD19, CD20 |
| Naive B | IGHD, MS4A1 |
| Plasma B | IGJ, XBP1, MZB1 |
| Monocyte | CD14, FCGR3A, LYZ |
| Macrophage | CD163, MS4A4A, CX3CR1, C1QA |
| DC | CD1C, FCER1A, CST3, CLEC9A |
| pDC | LILRA4, GZMB, IRF4 |
| Mast | TPSAB1, TPSB2, MS4A2, HDC |
| Platelet | PPBP, PF4, SELPLG |
| Proliferating | MKI67, TOP2A, PCNA |
| Erythroid | HBA1, HBA2, HBB |
| Megakaryocyte | PPBP, PF4, ITGA2B |

---

## 6. 示例命令

```
# Python - CellTypist
帮我用CellTypist注释 ~/data/pbmc.h5ad
用Immune_All_Low模型跑一下

# R - ScType  
帮我用ScType注释 ~/data/pbmc.rds
用免疫细胞的marker

# 手动调整
cluster 3 改成 Macrophages
```

---

## 7. 参考资料

- **ScType**: https://github.com/IanevskiAleksandr/sc-type
- **ScType Web**: http://sctype.app
- **CellTypist**: https://www.celltypist.org
- **CellTypist GitHub**: https://github.com/Teichlab/celltypist
- **CellTypist 文档**: https://celltypist.readthedocs.io
