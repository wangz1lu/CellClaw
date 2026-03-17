#!/usr/bin/env Rscript
# ==============================================================================
# scRNA-seq Analysis using Seurat
# ==============================================================================

suppressPackageStartupMessages({
  library(Seurat)
  library(dplyr)
  library(patchwork)
  library(ggplot2)
})

# === Parse arguments ===
args <- commandArgs(trailingOnly = TRUE)

input_path <- args[1]
project_name <- ifelse(is.na(args[2]), "scRNA", args[2])
min_cells <- as.integer(ifelse(is.na(args[3]), "3", args[3]))
min_features <- as.integer(ifelse(is.na(args[4]), "200", args[4]))
percent_mt <- as.numeric(ifelse(is.na(args[5]), "5", args[5]))
normalization <- ifelse(is.na(args[6]), "LogNormalize", args[6])
nfeatures <- as.integer(ifelse(is.na(args[7]), "2000", args[7]))
dims <- as.integer(ifelse(is.na(args[8]), "30", args[8]))
resolution <- as.numeric(ifelse(is.na(args[9]), "0.8", args[9]))
reduction <- ifelse(is.na(args[10]), "umap", args[10])
output_rds <- ifelse(is.na(args[11]), "result_seurat.rds", args[11])

cat("========================================\n")
cat("  scRNA-seq Seurat Analysis\n")
cat("========================================\n")
cat("Input:", input_path, "\n")
cat("Project:", project_name, "\n")
cat("Normalization:", normalization, "\n")
cat("PCA dims:", dims, "\n")
cat("Resolution:", resolution, "\n")
cat("========================================\n\n")

# === 1. Load Data ===
cat("[1/8] Loading data...\n")

# Detect file type
if (grepl("\\.h5$", input_path)) {
  data <- Read10X_h5(filename = input_path)
  seurat_obj <- CreateSeuratObject(counts = data, project = project_name, 
                                    min.cells = min_cells, min.features = min_features)
} else {
  # Assume 10X directory
  data <- Read10X(data.dir = input_path)
  seurat_obj <- CreateSeuratObject(counts = data, project = project_name,
                                    min.cells = min_cells, min.features = min_features)
}

cat("  Cells:", ncol(seurat_obj), "\n")
cat("  Genes:", nrow(seurat_obj), "\n\n")

# === 2. QC ===
cat("[2/8] Quality control...\n")
seurat_obj[["percent.mt"]] <- PercentageFeatureSet(seurat_obj, pattern = "^MT-")

# Filter
seurat_obj <- subset(seurat_obj, 
                     nFeature_RNA > min_features & 
                     percent.mt < percent_mt)

cat("  After QC - Cells:", ncol(seurat_obj), "\n\n")

# === 3. Normalization ===
cat("[3/8] Normalization:", normalization, "\n")

if (normalization == "sctransform") {
  seurat_obj <- SCTransform(seurat_obj, vars.to.regress = "percent.mt", verbose = FALSE)
  cat("  Using SCTransform\n\n")
} else {
  seurat_obj <- NormalizeData(seurat_obj, normalization.method = "LogNormalize", scale.factor = 10000)
  cat("  Using LogNormalize\n\n")
}

# === 4. Feature Selection ===
cat("[4/8] Finding variable features...\n")
seurat_obj <- FindVariableFeatures(seurat_obj, selection.method = "vst", nfeatures = nfeatures)
cat("  Top 10 variable genes:\n")
print(head(VariableFeatures(seurat_obj), 10))
cat("\n")

# === 5. Scaling ===
cat("[5/8] Scaling data...\n")
all.genes <- rownames(seurat_obj)
seurat_obj <- ScaleData(seurat_obj, features = all.genes)

# === 6. Dimensional Reduction ===
cat("[6/8] Running PCA...\n")
seurat_obj <- RunPCA(seurat_obj, features = VariableFeatures(object = seurat_obj))
cat("  Elbow plot saved to result_pca_elbow.png\n")
pdf("result_pca_elbow.pdf")
ElbowPlot(seurat_obj, ndims = 50)
dev.off()

# === 7. Clustering & Visualization ===
cat("[7/8] Clustering (dims=", dims, ", resolution=", resolution, ")...\n", sep="")
seurat_obj <- FindNeighbors(seurat_obj, dims = 1:dims)
seurat_obj <- FindClusters(seurat_obj, resolution = resolution)

# UMAP or t-SNE
if (reduction == "umap") {
  cat("  Running UMAP...\n")
  seurat_obj <- RunUMAP(seurat_obj, dims = 1:dims)
} else {
  cat("  Running t-SNE...\n")
  seurat_obj <- RunTSNE(seurat_obj, dims = 1:dims)
}

# === 8. Find Markers ===
cat("[8/8] Finding marker genes...\n")
markers <- FindAllMarkers(seurat_obj, only.pos = TRUE, min.pct = 0.25, thresh.use = 0.25)
markers <- markers %>% group_by(cluster) %>% top_n(n = 10, wt = avg_log2FC)

# Save markers
write.csv(markers, "result_cluster_markers.csv", row.names = FALSE)

# === Save Outputs ===
cat("\n[Saving outputs]\n")
saveRDS(seurat_obj, output_rds)

# Plots
pdf("result_umap.pdf", width = 10, height = 8)
p1 <- DimPlot(seurat_obj, reduction = "umap", label = TRUE)
print(p1)
p2 <- DimPlot(seurat_obj, reduction = "umap", group.by = "seurat_clusters")
print(p2)
dev.off()

# Cluster distribution
cluster_dist <- table(seurat_obj@meta.data$seurat_clusters)
write.csv(cluster_dist, "result_cluster_distribution.csv")

# Summary
cat("\n========================================\n")
cat("  Analysis Complete!\n")
cat("========================================\n")
cat("Outputs:\n")
cat("  -", output_rds, "\n")
cat("  - result_cluster_markers.csv\n")
cat("  - result_umap.pdf\n")
cat("  - result_pca_elbow.pdf\n")
cat("  - result_cluster_distribution.csv\n")
cat("\nCluster summary:\n")
print(cluster_dist)
cat("\n")
