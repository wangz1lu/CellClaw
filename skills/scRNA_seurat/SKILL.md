# scRNA-seq-Seurat Skill

> Single-cell RNA-seq analysis using Seurat (R)

## Trigger Keywords

```
scRNA, scrnaseq, single cell, seurat, 10x, pbmc, clustering, 
降维, 聚类, 单细胞, Seurat分析
```

## Description

Comprehensive scRNA-seq analysis pipeline using Seurat R package. Covers:
- Data loading (10X Cell Ranger output)
- Quality control (QC)
- Normalization (Standard or sctransform)
- Feature selection
- Dimensional reduction (PCA, UMAP, t-SNE)
- Clustering
- Marker gene identification
- Data integration (multiple datasets/batches)
- Visualization

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_path` | str | required | Path to 10X matrix or h5 file |
| `project_name` | str | "scRNA" | Project name for Seurat object |
| `min_cells` | int | 3 | Min cells per gene |
| `min_features` | int | 200 | Min genes per cell |
| `percent_mt` | float | 5 | Max mitochondrial percentage |
| `normalization` | str | "LogNormalize" | Method: "LogNormalize" or "sctransform" |
| `nfeatures` | int | 2000 | Number of variable features |
| `dims` | int | 30 | Number of PCA dimensions |
| `resolution` | float | 0.8 | Clustering resolution |
| `reduction` | str | "umap" | Visualization: umap or tsne |
| `integration` | str | "none" | Integration method: "none", "harmony", "scvi", "anchors" |
| `output_rds` | str | NULL | Path to save final RDS file |

## Analysis Steps

### 1. Data Loading

```r
# From 10X directory
pbmc <- Read10X(data.dir = "/path/to/filtered_gene_bc_matrix/")
seurat_obj <- CreateSeuratObject(counts = pbmc, project = "pbmc", min.cells = 3, min.features = 200)

# From h5 file
seurat_obj <- Read10X_h5(filename = "/path/to/filtered_feature_bc_matrix.h5")
seurat_obj <- CreateSeuratObject(counts = data, project = "project")
```

### 2. Quality Control

```r
# Mitochondrial genes
seurat_obj[["percent.mt"]] <- PercentageFeatureSet(seurat_obj, pattern = "^MT-")

# Filter cells
seurat_obj <- subset(seurat_obj, 
                     nFeature_RNA > 200 & 
                     nFeature_RNA < 2500 & 
                     percent.mt < 5)
```

### 3. Normalization

**Standard (LogNormalize):**
```r
seurat_obj <- NormalizeData(seurat_obj, normalization.method = "LogNormalize", scale.factor = 10000)
```

**SCTransform (recommended):**
```r
seurat_obj <- SCTransform(seurat_obj, vars.to.regress = "percent.mt", verbose = FALSE)
```

### 4. Feature Selection

```r
seurat_obj <- FindVariableFeatures(seurat_obj, selection.method = "vst", nfeatures = 2000)
```

### 5. Scaling

```r
all.genes <- rownames(seurat_obj)
seurat_obj <- ScaleData(seurat_obj, features = all.genes)
```

### 6. Dimensional Reduction

```r
seurat_obj <- RunPCA(seurat_obj, features = VariableFeatures(object = seurat_obj))
seurat_obj <- RunUMAP(seurat_obj, dims = 1:30)
# or
seurat_obj <- RunTSNE(seurat_obj, dims = 1:30)
```

### 7. Clustering

```r
seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30)
seurat_obj <- FindClusters(seurat_obj, resolution = 0.8)
```

### 8. Marker Genes

```r
# Find markers for all clusters
cluster.markers <- FindAllMarkers(seurat_obj, only.pos = TRUE, min.pct = 0.25, thresh.use = 0.25)

# Top markers per cluster
top10 <- cluster.markers %>% group_by(cluster) %>% top_n(n = 10, wt = avg_log2FC)
```

### 9. Integration (Optional)

**Harmony:**
```r
seurat_obj <- RunHarmony(seurat_obj, group.by.vars = "batch")
seurat_obj <- RunUMAP(seurat_obj, reduction = "harmony", dims = 1:30)
```

**Anchor-based:**
```r
# Split object by dataset
immune.anchors <- FindIntegrationAnchors(object.list = object.list, dims = 1:30)
immune.combined <- IntegrateData(anchorset = immune.anchors)
```

## Output Files

| File | Description |
|------|-------------|
| `result_seurat.rds` | Final Seurat object |
| `result_cluster_markers.csv` | Marker genes per cluster |
| `result_umap.png` | UMAP plot |
| `result_cluster_distribution.csv` | Cell counts per cluster |

## Example Usage

```
帮我分析 ~/data/pbmc10x 做Seurat标准流程
用sctransform标准化，resolution设0.6
帮我找出每个cluster的marker基因
```

## Dependencies

- R >= 4.1
- Seurat >= 5.0
- dplyr
- patchwork
- ggplot2
- sctransform
- harmony (optional)

## References

1. Hao Y, et al. (2024). Dictionary learning for integrative, multimodal and scalable single-cell analysis. *Nature Biotechnology*.
2. Stuart T, et al. (2019). Comprehensive integration of single-cell data. *Cell*.
3. Satija R, et al. (2015). Spatial reconstruction of single-cell gene expression data. *Nature Biotechnology*.
4. 10X Genomics: https://www.10xgenomics.com/
