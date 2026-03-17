# scRNA-seq-Seurat Skill

> Single-cell RNA-seq analysis using Seurat (R)

## Trigger Keywords

```
scRNA, scrnaseq, single cell, seurat, 10x, pbmc, clustering, 
降维, 聚类, 单细胞, Seurat分析
```

## Description

Comprehensive scRNA-seq analysis pipeline using Seurat R package. This skill is specifically designed for:
- **Reading existing Seurat RDS objects** (created by previous Seurat workflows)
- **Standard 10X Cell Ranger output** (matrix, h5 files)
- Complete analysis pipeline from raw data or existing objects

**Supported analyses:**
- Data loading (10X, RDS, h5)
- Quality control (QC)
- Normalization (Standard LogNormalize or sctransform)
- Feature selection
- Dimensional reduction (PCA, UMAP, t-SNE)
- Clustering
- Marker gene identification
- Data integration (multiple datasets/batches)
- Visualization

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_path` | str | required | Path to 10X matrix, h5 file, or RDS object |
| `input_type` | str | "auto" | "10x", "rds", "h5" (auto-detect if not specified) |
| `project_name` | str | "scRNA" | Project name for Seurat object |
| `min_cells` | int | 3 | Min cells per gene (for 10X input) |
| `min_features` | int | 200 | Min genes per cell (for 10X input) |
| `percent_mt` | float | 5 | Max mitochondrial percentage |
| `normalization` | str | "LogNormalize" | Method: "LogNormalize" or "sctransform" |
| `nfeatures` | int | 2000 | Number of variable features |
| `dims` | int | 30 | Number of PCA dimensions |
| `resolution` | float | 0.8 | Clustering resolution |
| `reduction` | str | "umap" | Visualization: "umap" or "tsne" |
| `integration` | str | "none" | Integration: "none", "harmony", "anchors" |
| `output_rds` | str | "result_seurat.rds" | Path to save final RDS file |

## Data Loading Methods

### Method 1: From Seurat RDS (Most Common)

If you already have a Seurat object saved from a previous analysis:

```r
# Load existing Seurat object
seurat_obj <- readRDS("/path/to/your_data.rds")

# Check the object
seurat_obj
# An object of class Seurat 
# 3652 features across 12461 samples within 'RNA'
```

**Important**: When loading from RDS, skip QC and normalization steps - the data is already processed!

### Method 2: From 10X Cell Ranger Output

```r
# From 10X directory (filtered matrix)
pbmc <- Read10X(data.dir = "/path/to/filtered_gene_bc_matrix/")
seurat_obj <- CreateSeuratObject(counts = pbmc, project = "pbmc", min.cells = 3, min.features = 200)

# From multiple directories (for integration)
data1 <- Read10X(data.dir = "/path/to/batch1/")
data2 <- Read10X(data.dir = "/path/to/batch2/")
obj1 <- CreateSeuratObject(counts = data1, project = "batch1")
obj2 <- CreateSeuratObject(counts = data2, project = "batch2")
```

### Method 3: From h5 File

```r
# 10X h5 format
data <- Read10X_h5(filename = "/path/to/filtered_feature_bc_matrix.h5")
seurat_obj <- CreateSeuratObject(counts = data, project = "project")
```

## Analysis Steps

### For Existing RDS Object (Recommended)

```r
# 1. Load existing object
seurat_obj <- readRDS("your_data.rds")

# 2. Re-run clustering with new parameters
seurat_obj <- FindVariableFeatures(seurat_obj, nfeatures = 2000)
seurat_obj <- ScaleData(seurat_obj)
seurat_obj <- RunPCA(seurat_obj, dims = 1:30)
seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30)
seurat_obj <- FindClusters(seurat_obj, resolution = 0.8)
seurat_obj <- RunUMAP(seurat_obj, dims = 1:30)

# 3. Find markers
markers <- FindAllMarkers(seurat_obj, only.pos = TRUE)
```

### For New 10X Data

```r
# 1. Load data
pbmc <- Read10X(data.dir = "/path/to/matrix/")
seurat_obj <- CreateSeuratObject(counts = pbmc, project = "pbmc")

# 2. QC
seurat_obj[["percent.mt"]] <- PercentageFeatureSet(seurat_obj, pattern = "^MT-")
seurat_obj <- subset(seurat_obj, 
                     nFeature_RNA > 200 & 
                     nFeature_RNA < 2500 & 
                     percent.mt < 5)

# 3. Normalization
seurat_obj <- NormalizeData(seurat_obj)
# OR use sctransform (recommended):
seurat_obj <- SCTransform(seurat_obj, vars.to.regress = "percent.mt")

# 4. Feature Selection
seurat_obj <- FindVariableFeatures(seurat_obj, nfeatures = 2000)

# 5. Scaling
seurat_obj <- ScaleData(seurat_obj)

# 6. PCA
seurat_obj <- RunPCA(seurat_obj, features = VariableFeatures(seurat_obj))

# 7. Clustering
seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30)
seurat_obj <- FindClusters(seurat_obj, resolution = 0.8)

# 8. Visualization
seurat_obj <- RunUMAP(seurat_obj, dims = 1:30)

# 9. Marker genes
markers <- FindAllMarkers(seurat_obj, only.pos = TRUE, min.pct = 0.25)
```

## Integration (Multiple Datasets)

### Harmony Integration

```r
# Load multiple datasets and add batch label
obj1 <- readRDS("batch1.rds")
obj2 <- readRDS("batch2.rds")
obj1$batch <- "batch1"
obj2$batch <- "batch2"

# Merge
seurat_obj <- merge(obj1, obj2)

# Run Harmony
seurat_obj <- RunPCA(seurat_obj, npcs = 30)
seurat_obj <- RunHarmony(seurat_obj, group.by.vars = "batch")
seurat_obj <- RunUMAP(seurat_obj, reduction = "harmony", dims = 1:30)
```

### Anchor-based Integration

```r
# Prepare list of objects
object.list <- list(batch1 = obj1, batch2 = obj2)

# Find integration anchors
anchors <- FindIntegrationAnchors(object.list = object.list, dims = 1:30)

# Integrate
seurat_obj <- IntegrateData(anchorset = anchors)

# Continue with integrated data
seurat_obj <- ScaleData(seurat_obj)
seurat_obj <- RunPCA(seurat_obj)
seurat_obj <- RunUMAP(seurat_obj, dims = 1:30)
```

## Output Files

| File | Description |
|------|-------------|
| `result_seurat.rds` | Final Seurat object |
| `result_cluster_markers.csv` | Marker genes per cluster |
| `result_umap.pdf` | UMAP visualization |
| `result_pca_elbow.pdf` | PCA elbow plot |
| `result_cluster_distribution.csv` | Cell counts per cluster |

## Example Usage

```
# 分析已有的RDS文件
帮我分析 ~/data/pbmc.rds 做聚类和marker分析

# 从头分析10X数据
帮我分析 ~/data/10x_pbmc 做标准Seurat流程

# 用sctransform
用sctransform标准化，resolution设0.6

# 重新聚类
帮我把seurat对象重新聚类，resolution改成0.6

# 批次整合
帮我用harmony整合batch1.rds和batch2.rds
```

## Dependencies

- R >= 4.1
- Seurat >= 5.0
- dplyr
- patchwork
- ggplot2
- sctransform
- harmony (optional, for integration)

## References

1. Hao Y, et al. (2024). Dictionary learning for integrative, multimodal and scalable single-cell analysis. *Nature Biotechnology*.
2. Stuart T, et al. (2019). Comprehensive integration of single-cell data. *Cell*.
3. Satija R, et al. (2015). Spatial reconstruction of single-cell gene expression data. *Nature Biotechnology*.
4. 10X Genomics: https://www.10xgenomics.com/
