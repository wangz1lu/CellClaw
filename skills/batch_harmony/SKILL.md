---
name: Batch — 批次校正
version: 1.1.0
scope: 多批次单细胞数据整合与批次效应校正
languages: [R, Python]
triggers: [harmony, batch, integration, 批次, 校正, bbknn, scvi, scanpy harmony, seurat harmony]
---

# Skill: Batch — 批次校正

## 1. 概述

批次校正是将多个批次/样本的单细胞数据整合在一起，消除技术变异（批次效应），保留生物异质性。

### 常用方法

| 方法 | 语言 | 特点 |
|------|------|------|
| **Harmony** | R/Python | 基于 RNN，速度快，效果好 |
| **BBKNN** | Python | 快速，适合大数据 |
| **SCVI** | Python | 深度学习，基于 VAE |
| **ingest** | Python | 标签映射，快速 |

---

## 2. Part A: Harmony (R - Seurat)

### 2.1 原理

Harmony 使用迭代的柔和聚类方法，通过最大似然估计来校正批次效应。

### 2.2 安装

```r
# 安装 Harmony
remotes::install_github("immunogenomics/harmony")
```

### 2.3 使用方法

#### 方法1：标准 Harmony 校正

```r
library(Seurat)
library(harmony)

# 读取并合并数据（假设已有 Seurat 对象）
# 或者分别读取后合并
seu <- readRDS("merged.rds")

# 添加批次标签（如果没有）
seu$batch <- seu$orig.ident  # 或者其他批次列

# Run Harmony
seu <- RunPCA(seu, npcs = 30)
seu <- RunHarmony(seu, group.by.vars = "batch")

# 使用 Harmony 的 PCA 进行后续分析
seu <- RunUMAP(seu, reduction = "harmony", dims = 1:30)
seu <- FindNeighbors(seu, reduction = "harmony", dims = 1:30)
seu <- FindClusters(seu, resolution = 0.8)

# 可视化
DimPlot(seu, reduction = "umap", group.by = "batch")
DimPlot(seu, reduction = "umap", group.by = "seurat_clusters")
```

#### 方法2：多个对象合并后校正

```r
library(Seurat)
library(harmony)

# 读取多个样本
obj1 <- readRDS("sample1.rds")
obj2 <- readRDS("sample2.rds")
obj3 <- readRDS("sample3.rds")

# 添加批次标签
obj1$batch <- "batch1"
obj2$batch <- "batch2"
obj3$batch <- "batch3"

# 合并
seu <- merge(obj1, c(obj2, obj3))

# 标准化
seu <- NormalizeData(seu)
seu <- FindVariableFeatures(seu)
seu <- ScaleData(seu)

# Harmony 校正
seu <- RunPCA(seu, npcs = 30)
seu <- RunHarmony(seu, group.by.vars = "batch")

# 后续分析
seu <- RunUMAP(seu, reduction = "harmony", dims = 1:30)
```

#### 方法3：分层校正（可选）

```r
# 对特定变量进行分层 Harmony
seu <- RunHarmony(seu, group.by.vars = "batch", theta = 2, lambda = 0.1)

# 参数说明：
# theta: 值越大，分割越严格（默认值 2）
# lambda: 正则化参数（默认值 0.1）
# max.iter: 最大迭代次数（默认值 10）
```

### 2.4 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `group.by.vars` | 必需 | 批次变量列名 |
| `theta` | 2 | 柔软聚类阈值 |
| `lambda` | 0.1 | 正则化参数 |
| `max.iter` | 10 | 最大迭代次数 |
| `sigma` | 0.1 | 高斯核宽度 |

---

## 3. Part B: Harmony (Python - Scanpy)

### 3.1 安装

```python
pip install scanpy harmonypy
# 或者
pip install harmony
```

### 3.2 使用方法

#### 方法1：标准 Harmony 校正

```python
import scanpy as sc
import harmonypy as hm

# 加载数据
adata = sc.read_h5ad('merged.h5ad')

# 添加批次标签
# adata.obs['batch'] = ...

# PCA
sc.pp.pca(adata, n_comps=50)

# Harmony 校正
hm.run_harmony(adata, 'batch', max_iter=10)

# 使用 Harmony 结果
sc.pp.neighbors(adata, use_rep='X_pca_harmony')
sc.tl.umap(adata)

# 可视化
sc.pl.umap(adata, color=['batch'])
sc.pl.umap(adata, color=['leiden'])
```

#### 方法2：使用 scanpy 的 harmony wrapper

```python
import scanpy as sc
from scanpy.external.pp import harmony

# 数据
adata = sc.read_h5ad('merged.h5ad')
sc.pp.pca(adata, n_comps=50)

# Harmony
harmony(adata, key='batch')

# 后续分析
sc.pp.neighbors(adata, use_rep='X_pca_harmony')
sc.tl.umap(adata)
```

---

## 4. Part C: BBKNN (Python)

### 4.1 原理

BBKNN (Batch-Balanced kNN) 通过修改 kNN 图的构建方式来实现批次校正，比 Harmony 更快。

### 4.2 安装

```python
pip install bbknn
```

### 4.3 使用方法

#### 方法1：标准 BBKNN

```python
import scanpy as sc
import bbknn

# 加载数据
adata = sc.read_h5ad('merged.h5ad')

# PCA
sc.pp.pca(adata, n_comps=50)

# BBKNN 校正
bbknn.bbknn(adata, batch_key='batch', n_pcs=50)

# UMAP
sc.tl.umap(adata)

# 可视化
sc.pl.umap(adata, color=['batch'])
sc.pl.umap(adata, color=['leiden'])
```

#### 方法2：分层 BBKNN（按细胞类型）

```python
# 先聚类，再对每个 cluster 分别 BBKNN
sc.pp.neighbors(adata, n_pcs=50)
sc.tl.leiden(adata, resolution=0.3)

# 对每个 cluster 分别 BBKNN
bbknn.bbknn(adata, batch_key='batch', n_pcs=50, 
            neighbors_within_batch=3, cluster_key='leiden')

# 合并 cluster 后的邻居图
sc.tl.umap(adata, spread=1., min_dist=0.3)
```

#### 方法3：使用 trim (去除批次特异连接)

```python
# trim 参数：每个细胞去除批次特异性最强的 k 个邻居
bbknn.bbknn(adata, batch_key='batch', n_pcs=50, trim=15)
```

### 4.4 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `batch_key` | 'batch' | 批次变量 |
| `n_pcs` | 50 | PCA 维度 |
| `neighbors_within_batch` | 3 | 每个批次保留的邻居数 |
| `trim` | None | 去除批次特异连接数 |
| `cluster_key` | None | 分层 BBKNN |

---

## 5. Part D: SCVI (Python)

### 5.1 原理

SCVI (Single-cell Variational Inference) 使用变分自编码器 (VAE) 进行数据整合，可以建模批次效应和生物变异。

### 5.2 安装

```python
# 推荐使用 conda
conda install scvi-tools -c conda-forge

# 或者 pip
pip install scvi-tools
```

### 5.3 使用方法

#### 方法1：标准 SCVI

```python
import scanpy as sc
import scvi

# 设置 SCVI 背景
scvi.settings.seed = 42

# 加载数据
adata = sc.read_h5ad('merged.h5ad')

# 准备 SCVI 数据
scvi.model.SCVI.setup_anndata(adata, batch_key='batch')

# 训练模型
model = scvi.model.SCVI(adata, n_layers=2, n_latent=30)
model.train()

# 获取整合后的 latent space
adata.obsm["X_scVI"] = model.get_latent_representation()

# 使用 SCVI 结果
sc.pp.neighbors(adata, use_rep='X_scVI', n_neighbors=15)
sc.tl.umap(adata)

# 可视化
sc.pl.umap(adata, color=['batch'])
sc.pl.umap(adata, color=['leiden'])
```

#### 方法2：SCANVI（带标签的半监督）

```python
import scanpy as sc
import scvi
from scvi.model import SCANVI

# 先用 SCVI
scvi.model.SCVI.setup_anndata(adata, batch_key='batch', labels_key='cell_type')
model = scvi.model.SCVI(adata)
model.train()

# 转为 SCANVI（利用已有标签）
scanvi_model = SCANVI.from_scvi_model(model, adata=adata)
scanvi_model.train()

# 预测
adata.obs['scanvi_prediction'] = scanvi_model.predict()

# 可视化
sc.pl.umap(adata, color=['cell_type', 'scanvi_prediction'])
```

#### 方法3：只使用部分高变基因

```python
# 选择高变基因再训练（更快）
sc.pp.highly_variable_genes(adata, n_top_genes=2000)
adata = adata[:, adata.var.highly_variable]

# 训练 SCVI
scvi.model.SCVI.setup_anndata(adata, batch_key='batch')
model = scvi.model.SCVI(adata)
model.train()
```

### 5.4 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `n_layers` | 2 | 编码器层数 |
| `n_latent` | 30 | latent 维度 |
| `n_epochs` | None | 训练轮数 |
| `early_stopping` | True | 早停 |
| `batch_key` | 'batch' | 批次变量 |

---

## 6. 方法对比与选择

| 方法 | 速度 | 内存 | 适用场景 |
|------|------|------|----------|
| Harmony (R) | 中 | 中 | 标准整合，首选 |
| Harmony (Python) | 快 | 中 | Python 流程 |
| BBKNN | 快 | 低 | 大数据，快速探索 |
| SCVI | 慢 | 高 | 需要深度学习建模 |
| ingest | 快 | 低 | 有参考数据集 |

### 选择建议

- **大多数情况**：Harmony (R 或 Python)
- **快速探索**：BBKNN
- **需要概率模型**：SCVI
- **有参考注释**：ingest

---

## 7. 输出文件规范

**⚠️ 所有输出文件名必须以 `result_` 开头！**

### R 输出
```r
# 保存校正后的对象
saveRDS(seu, "result_harmony.rds")

# 导出 UMAP 坐标
umap_df <- data.frame(
  cell_id = colnames(seu),
  UMAP_1 = seu@reductions$umap@cell.embeddings[,1],
  UMAP_2 = seu@reductions$umap@cell.embeddings[,2],
  batch = seu$batch,
  cluster = Idents(seu)
)
write.csv(umap_df, "result_umap_coordinates.csv", row.names = FALSE)
```

### Python 输出
```python
# 保存校正后的对象
adata.write('result_integrated.h5ad')

# 导出 UMAP 坐标
umap_df = pd.DataFrame({
    'cell_id': adata.obs_names,
    'UMAP_1': adata.obsm['X_umap'][:, 0],
    'UMAP_2': adata.obsm['X_umap'][:, 1],
    'batch': adata.obs['batch'],
    'leiden': adata.obs['leiden']
})
umap_df.to_csv('result_umap_coordinates.csv', index=False)
```

---

## 8. 示例命令

```
# R - Harmony
帮我用Harmony整合batch1.rds, batch2.rds, batch3.rds

# Python - Harmony
用scanpy的harmony整合 ~/data/batch*.h5ad

# Python - BBKNN
用BBKNN整合这几个样本

# Python - SCVI
用SCVI跑一下这个数据
```

---

## 9. 参考资料

- **Harmony**: https://github.com/immunogenomics/harmony
- **Harmony Paper**: https://www.nature.com/articles/s41587-019-0199-9
- **BBKNN**: https://github.com/Teichlab/bbknn
- **SCVI**: https://scvi-tools.org/
- **SCVI Paper**: https://www.nature.com/articles/s41592-021-01256-7
- **Scanpy Integration**: https://scanpy.readthedocs.io/en/stable/tutorials/basics/integrating-data-using-ingest.html
