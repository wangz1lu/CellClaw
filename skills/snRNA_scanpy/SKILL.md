# snRNA_scanpy Skill

> Single-cell RNA-seq analysis using Scanpy (Python)

## Trigger Keywords

```
scanpy, python, anndata, scrnaseq, single cell, python分析,
降维, 聚类, python单细胞, 标准化
```

## Description

Comprehensive scRNA-seq analysis pipeline using Scanpy Python package. This skill covers:
- Data loading (10X, h5, h5ad)
- Quality control (QC) - mitochondrial, ribosomal, hemoglobin genes
- Doublet detection (Scrublet)
- Normalization (total counts, log-transform)
- Feature selection (highly variable genes)
- Dimensionality reduction (PCA, UMAP, t-SNE)
- Clustering (Leiden, Louvain)
- Data integration (ingest, BBKNN, Harmony)
- Visualization (UMAP, violin plots, dot plots, heatmaps)
- Marker gene identification

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_path` | str | required | Path to input data (10X, h5, h5ad) |
| `project_name` | str | "snRNA" | Project name |
| `min_genes` | int | 100 | Min genes per cell |
| `min_cells` | int | 3 | Min cells per gene |
| `mt_percent` | float | 20 | Max mitochondrial percent |
| `n_neighbors` | int | 15 | Number of neighbors for graph |
| `npcs` | int | 50 | Number of PCs |
| `resolution` | float | 0.8 | Clustering resolution |
| `cluster_method` | str | "leiden" | Clustering method: "leiden" or "louvain" |
| `integration` | str | "none" | Integration: "none", "ingest", "bbknn", "harmony" |
| `output_h5ad` | str | "result_scanpy.h5ad" | Output file |

## Data Loading

### Method 1: From 10X h5 file

```python
import scanpy as sc
import anndata as ad

# Load 10X h5 format
adata = sc.read_10x_h5("/path/to/filtered_feature_bc_matrix.h5")
adata.var_names_make_unique()
```

### Method 2: From 10X directory

```python
# Load from 10X matrix directory
adata = sc.read_10x_mtx("/path/to/filtered_gene_bc_matrix/")
adata.var_names_make_unique()
```

### Method 3: From h5ad file

```python
# Load existing AnnData object
adata = sc.read_h5ad("/path/to/data.h5ad")
```

### Method 4: From multiple samples

```python
# Load multiple samples and concatenate
adatas = {}
for sample_id in ["s1d1", "s1d3"]:
    adatas[sample_id] = sc.read_10x_h5(f"/path/to/{sample_id}_filtered_feature_bc_matrix.h5")

adata = ad.concat(adatas, label="sample")
adata.obs_names_make_unique()
```

## Quality Control

### Calculate QC metrics

```python
# Define gene populations
adata.var["mt"] = adata.var_names.str.startswith("MT-")  # mitochondrial
adata.var["ribo"] = adata.var_names.str.startswith(("RPS", "RPL"))  # ribosomal
adata.var["hb"] = adata.var_names.str.contains("^HB[^(P)]")  # hemoglobin

# Calculate QC metrics
sc.pp.calculate_qc_metrics(adata, qc_vars=["mt", "ribo", "hb"], inplace=True)
```

### Filter cells and genes

```python
# Filter cells
sc.pp.filter_cells(adata, min_genes=100)
sc.pp.filter_genes(adata, min_cells=3)

# Filter by mitochondrial percentage
adata = adata[adata.obs.pct_counts_mt < 20, :]
```

### Doublet Detection (Scrublet)

```python
# Run Scrublet for doublet detection
sc.pp.scrublet(adata, batch_key="sample")

# Filter doublets
adata = adata[~adata.obs["predicted_doublet"], :]
```

## Normalization

```python
# Total counts normalization
sc.pp.normalize_total(target_sum=1e4)

# Log transformation
sc.pp.log1p(adata)
```

## Feature Selection

```python
# Find highly variable genes
sc.pp.highly_variable_genes(adata, n_top_genes=2000)
print(f"Variable genes: {sum(adata.var.highly_variable)}")

# Filter to highly variable genes for downstream analysis
adata.raw = adata.copy()
adata = adata[:, adata.var.highly_variable]
```

## Scaling

```python
# Scale data (zero mean, unit variance)
sc.pp.scale(adata, max_value=10)
```

## Dimensionality Reduction

```python
# PCA
sc.tl.pca(adata, n_comps=50)

# UMAP
sc.tl.umap(adata)

# or t-SNE
sc.tl.tsne(adata)
```

## Clustering

```python
# Build neighbor graph
sc.pp.neighbors(adata, n_neighbors=15, n_pcs=50)

# Leiden clustering (recommended)
sc.tl.leiden(adata, resolution=0.8)

# or Louvain clustering
sc.tl.louvain(adata, resolution=0.8)
```

## Marker Gene Identification

```python
# Find markers for all clusters
sc.tl.rank_genes_groups(adata, "leiden", method="t-test")

# Get marker genes as DataFrame
markers = sc.get.rank_genes_groups_df(adata, group=None)
markers.to_csv("result_cluster_markers.csv", index=False)

# Visualization
sc.pl.rank_genes_groups_heatmap(adata, n_genes=10)
sc.pl.rank_genes_groups_dotplot(adata, n_genes=10)
```

## Data Integration

### Method 1: ingest (label transfer)

```python
import scanpy as sc

# Reference and query data
adata_ref = sc.read_h5ad("reference.h5ad")
adata_query = sc.read_h5ad("query.h5ad")

# Use same variable names
var_names = adata_ref.var_names.intersection(adata_query.var_names)
adata_ref = adata_ref[:, var_names].copy()
adata_query = adata_query[:, var_names].copy()

# Run PCA on reference
sc.pp.pca(adata_ref)
sc.pp.neighbors(adata_ref)
sc.tl.umap(adata_ref)

# Ingest query data into reference
sc.tl.ingest(adata_query, adata_ref, obs="cell_type")

# Combine
adata_query.obs["cell_type"] = adata_query.obs["ingest_cell_type"]
```

### Method 2: BBKNN (batch-balanced kNN)

```python
import scanpy as sc
import bbknn

# Concatenate multiple batches
adata = sc.read_h5ad("combined.h5ad")

# Run PCA
sc.pp.pca(adata)

# BBKNN integration
bbknn.bbknn(adata, batch_key="batch")

# UMAP
sc.tl.umap(adata)
```

### Method 3: Harmony (via scanpy)

```python
import scanpy as sc
import harmony

# Run PCA
sc.pp.pca(adata)

# Run Harmony
sc.tl.harmony(adata, group_by="batch")

# Use Harmony reduction for neighbors and UMAP
sc.pp.neighbors(adata, use_rep="X_pca_harmony")
sc.tl.umap(adata)
```

## Visualization

### UMAP

```python
# Basic UMAP
sc.pl.umap(adata, color=["leiden"])

# UMAP with multiple genes
sc.pl.umap(adata, color=["CD3D", "CD4", "CD8A"])
```

### Violin plot

```python
sc.pl.violin(adata, keys=["n_genes_by_counts", "total_counts", "pct_counts_mt"], 
             groupby="leiden", multi_panel=True)
```

### Dot plot

```python
# Dot plot of marker genes
sc.pl.dotplot(adata, var_names=["CD3D", "MS4A1", "NKG7"], groupby="leiden")
```

### Heatmap

```python
sc.pl.heatmap(adata, var_names=top_markers, groupby="leiden", 
              swap_axes=True, dendrogram=True)
```

## Output Files

| File | Description |
|------|-------------|
| `result_scanpy.h5ad` | Final AnnData object |
| `result_cluster_markers.csv` | Marker genes per cluster |
| `result_umap.png` | UMAP visualization |
| `result_pca.png` | PCA plot |
| `result_cluster_distribution.csv` | Cell counts per cluster |

## Example Usage

```
# 分析10X数据
帮我用scanpy分析 ~/data/pbmc10x.h5

# 标准流程
用scanpy标准流程跑一下，leiden resolution设0.6

# 批次整合
用bbknn整合batch1和batch2的数据

# 找marker基因
帮我找出每个cluster的marker基因

# 标签转换
用ingest把reference的标签转过来
```

## Dependencies

- Python >= 3.8
- scanpy >= 1.9
- anndata >= 0.8
- numpy
- pandas
- scipy
- matplotlib
- seaborn
- scikit-learn
- bbknn (optional, for BBKNN integration)
- harmony (optional, for Harmony integration)
- scrublet (optional, for doublet detection)

## References

1. Wolf FA, Angerer P, Theis FJ (2018). SCANPY: large-scale single-cell gene analysis. *Genome Biology*.
2. McCarthy DJ, Campbell K, Lun ATL, Wills QF (2017). Scater: pre-processing, quality control, normalization and visualization of single-cell RNA-seq data in R. *Bioinformatics*.
3. Polanski K, et al. (2019). BBKNN: fast batch-balanced kNN. *Bioinformatics*.
4. Korsunsky I, et al. (2019). Fast, sensitive and accurate integration of single-cell data with Harmony. *Nature Methods*.
