---
name: DEG — 差异基因分析
version: 1.1.0
scope: 单细胞差异表达分析
languages: [R, Python]
triggers: [deg, dge, differential expression, 差异基因, findmarkers, findallmarkers, rank_genes_groups, wilcox, mast, t test]
---

# Skill: DEG — 差异基因分析

## 1. 概述

差异基因分析（Differential Gene Expression, DEG）用于识别不同细胞类型、cluster 或条件之间表达显著差异的基因。

### 工具
| 语言 | 函数 |
|------|------|
| R | `FindMarkers()`, `FindAllMarkers()` (Seurat) |
| Python | `scanpy.tl.rank_genes_groups()` |

---

## 2. Part A: R — Seurat

### 2.1 FindAllMarkers

找所有 identity class 的 marker 基因。

```r
FindAllMarkers(
  object,
  assay = NULL,
  features = NULL,
  group.by = NULL,
  logfc.threshold = 0.1,
  test.use = "wilcox",
  slot = "data",
  min.pct = 0.01,
  min.diff.pct = -Inf,
  node = NULL,
  verbose = TRUE,
  only.pos = FALSE,
  max.cells.per.ident = Inf,
  random.seed = 1,
  latent.vars = NULL,
  min.cells.feature = 3,
  min.cells.group = 3,
  mean.fxn = NULL,
  fc.name = NULL,
  base = 2,
  return.thresh = 0.01,
  densify = FALSE
)
```

**参数说明：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `object` | 必需 | Seurat 对象 |
| `group.by` | NULL | 分组列名（默认用 ident） |
| `logfc.threshold` | 0.1 | log fold change 阈值 |
| `test.use` | "wilcox" | 统计检验方法 |
| `slot` | "data" | 数据槽：data / counts / scale.data |
| `min.pct` | 0.01 | 基因在两组中表达的最小比例 |
| `min.diff.pct` | -Inf | 两组检测率最小差异 |
| `only.pos` | FALSE | 只返回上调基因 |
| `max.cells.per.ident` | Inf | 每个 identity 类的最大细胞数（下采样） |
| `return.thresh` | 0.01 | p 值阈值 |

**test.use 选项：**

| 方法 | 说明 |
|------|------|
| `"wilcox"` | Wilcoxon Rank Sum test（默认，最常用） |
| `"wilcox_limma"` | limma 实现的 Wilcoxon |
| `"bimod"` | Likelihood-ratio test |
| `"roc"` | ROC 分析，返回 AUC |
| `"t"` | Student's t-test |
| `"negbinom"` | 负二项分布（UMI 数据） |
| `"poisson"` | Poisson 分布 |
| `"LR"` | Logistic Regression |
| `"MAST"` | Hurdle model（考虑表达率） |
| `"DESeq2"` | DESeq2（需安装） |

**示例：**

```r
# 找所有 cluster 的 marker
all_markers <- FindAllMarkers(
  seu,
  only.pos = TRUE,
  min.pct = 0.1,
  logfc.threshold = 0.25
)

# 筛选显著基因
sig_markers <- all_markers[all_markers$p_val_adj < 0.05, ]

# Top 10 marker per cluster
top10 <- sig_markers %>%
  group_by(cluster) %>%
  top_n(n = 10, wt = avg_log2FC)
```

---

### 2.2 FindMarkers

比较两个 group 的差异基因。

```r
FindMarkers(
  object,
  ident.1 = NULL,
  ident.2 = NULL,
  latent.vars = NULL,
  group.by = NULL,
  subset.ident = NULL,
  assay = NULL,
  reduction = NULL,
  ...
)
```

**参数说明：**

| 参数 | 说明 |
|------|------|
| `ident.1` | 比较组 1 |
| `ident.2` | 比较组 2（NULL = 与其他所有组比较） |
| `group.by` | 分组列 |
| `subset.ident` | 筛选特定 identity |

**示例：**

```r
# Cluster 1 vs Cluster 2
deg <- FindMarkers(
  seu,
  ident.1 = "1",
  ident.2 = "0",
  test.use = "wilcox",
  min.pct = 0.1,
  logfc.threshold = 0.25
)

# 使用 MAST（更严格）
deg_mast <- FindMarkers(
  seu,
  ident.1 = "1",
  ident.2 = "0",
  test.use = "MAST",
  min.pct = 0.1
)

# 使用 ROC（找 marker）
deg_roc <- FindMarkers(
  seu,
  ident.1 = "1",
  ident.2 = "0",
  test.use = "roc"
)
```

---

## 3. Part B: Python — Scanpy

### 3.1 rank_genes_groups

```python
sc.tl.rank_genes_groups(
    adata,
    groupby,
    mask_var=None,
    use_raw=None,
    groups='all',
    reference='rest',
    n_genes=None,
    rankby_abs=False,
    pts=False,
    key_added=None,
    copy=False,
    method=None,
    corr_method='benjamini-hochberg',
    tie_correct=False,
    layer=None,
    **kwds
)
```

**参数说明：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `adata` | AnnData | 必需 |
| `groupby` | str | 分组列名（obs 中的列） |
| `groups` | str/list | 要比较的组，'all' 或 ['g1', 'g2'] |
| `reference` | str | 参考组，'rest' 或特定组名 |
| `n_genes` | int | 返回的基因数，默认全部 |
| `rankby_abs` | bool | 按绝对值排序 |
| `pts` | bool | 计算表达比例 |
| `method` | str | 统计方法 |
| `corr_method` | str | p 值校正方法 |

**method 选项：**

| 方法 | 说明 |
|------|------|
| `"logreg"` | Logistic Regression |
| `"t-test"` | t-test |
| `"wilcoxon"` | Wilcoxon rank-sum test |
| `"t-test_overestim_var"` | t-test（过度估计方差） |

**corr_method 选项：**

| 方法 | 说明 |
|------|------|
| `"benjamini-hochberg"` | FDR 校正（默认） |
| `"bonferroni"` | Bonferroni 校正 |

**示例：**

```python
import scanpy as sc

# 加载数据
adata = sc.read_h5ad('input.h5ad')

# 找所有 cluster 的 marker
sc.tl.rank_genes_groups(
    adata, 
    groupby='leiden',
    method='wilcoxon',
    corr_method='benjamini-hochberg'
)

# 查看结果
adata.uns['rank_genes_groups']['names'].dtype()

# 提取结果为 DataFrame
result = sc.get.rank_genes_groups_df(adata, group='1')
result.to_csv('result_cluster1_markers.csv', index=False)
```

**获取结果：**

```python
# 获取某个 group 的 marker
markers = sc.get.rank_genes_groups_df(adata, group='1')
print(markers.head(20))

# 获取所有 group 的 marker
for group in adata.obs[groupby].unique():
    markers = sc.get.rank_genes_groups_df(adata, group=group)
    markers.to_csv(f'result_{group}_markers.csv', index=False)
```

**可视化：**

```python
# 热图
sc.pl.rank_genes_groups_heatmap(adata, n_genes=10)

# Dotplot
sc.pl.rank_genes_groups_dotplot(adata, n_genes=10)

# 堆叠 violin
sc.pl.rank_genes_groups_stacked_violin(adata, n_genes=10)
```

---

## 4. 输出文件规范

**⚠️ 所有输出文件名必须以 `result_` 开头！**

### R 输出
```r
# 所有 marker
write.csv(all_markers, "result_all_markers.csv", row.names = FALSE)

# 显著 marker（padj < 0.05, |log2FC| > 0.5）
sig_markers <- all_markers[all_markers$p_val_adj < 0.05 & abs(all_markers$avg_log2FC) > 0.5, ]
write.csv(sig_markers, "result_significant_markers.csv")

# Top 10 per cluster
top10 <- sig_markers %>% group_by(cluster) %>% top_n(10, wt = avg_log2FC)
write.csv(top10, "result_top10_per_cluster.csv")
```

### Python 输出
```python
# 所有结果
sc.get.rank_genes_groups_df(adata).to_csv('result_all_markers.csv', index=False)

# 显著 marker
sig = adata.uns['rank_genes_groups']
# 筛选...

# 可视化
sc.pl.rank_genes_groups_heatmap(adata, n_genes=10, save='result_heatmap.png')
sc.pl.rank_genes_groups_dotplot(adata, n_genes=10, save='result_dotplot.png')
```

---

## 5. 示例命令

```
# R - FindAllMarkers
帮我找所有cluster的marker基因

# R - FindMarkers
比较cluster 1和cluster 2的差异基因

# Python - rank_genes_groups
用scanpy找每个cluster的marker

# Python - 指定方法
用wilcoxon方法跑差异分析
```

---

## 6. 参考资料

- **Seurat FindAllMarkers**: https://satijalab.org/seurat/reference/findallmarkers
- **Seurat FindMarkers**: https://satijalab.org/seurat/reference/findmarkers
- **Scanpy rank_genes_groups**: https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html
- **MAST**: https://www.nature.com/articles/nmeth.3969
