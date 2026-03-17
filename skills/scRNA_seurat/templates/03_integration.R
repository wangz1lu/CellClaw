#!/usr/bin/env Rscript
# ==============================================================================
# scRNA-seq Integration Analysis using Seurat
# For integrating multiple datasets (batches, conditions, donors)
# ==============================================================================

suppressPackageStartupMessages({
  library(Seurat)
  library(dplyr)
  library(patchwork)
  library(ggplot2)
  library(harmony)
})

# === Parse arguments ===
args <- commandArgs(trailingOnly = TRUE)

input_dirs <- unlist(strsplit(args[1], ","))
project_name <- ifelse(is.na(args[2]), "scRNA_integrated", args[2])
batch_label <- ifelse(is.na(args[3]), "batch", args[3])
integration_method <- ifelse(is.na(args[4]), "harmony", args[4])
dims <- as.integer(ifelse(is.na(args[5]), "30", args[5]))
resolution <- as.numeric(ifelse(is.na(args[6]), "0.8", args[6]))
output_rds <- ifelse(is.na(args[7]), "result_integrated.rds", args[7])

cat("========================================\n")
cat("  scRNA-seq Integration Analysis\n")
cat("========================================\n")
cat("Input directories:", paste(input_dirs, collapse=", "), "\n")
cat("Project:", project_name, "\n")
cat("Batch label:", batch_label, "\n")
cat("Integration:", integration_method, "\n")
cat("========================================\n\n")

# === 1. Load all datasets ===
cat("[1/7] Loading datasets...\n")
object.list <- list()
for (i in seq_along(input_dirs)) {
  data <- Read10X(data.dir = input_dirs[i])
  obj <- CreateSeuratObject(counts = data, project = paste0(project_name, "_", i))
  obj[[batch_label]] <- paste0("batch", i)
  object.list[[i]] <- obj
  cat("  Loaded batch", i, "- Cells:", ncol(obj), "\n")
}

# Merge
seurat_obj <- merge(object.list[[1]], object.list[-1], add.cell.ids = paste0("batch", seq_along(object.list)))
cat("  Total cells:", ncol(seurat_obj), "\n\n")

# === 2. Split and Normalize ===
cat("[2/7] Splitting layers and normalizing...\n")
seurat_obj[["RNA"]] <- split(seurat_obj[["RNA"]], f = seurat_obj[[batch_label]])
seurat_obj <- NormalizeData(seurat_obj)
seurat_obj <- FindVariableFeatures(seurat_obj)
seurat_obj <- ScaleData(seurat_obj)

# === 3. Integration ===
cat("[3/7] Integration using:", integration_method, "\n\n")

if (integration_method == "harmony") {
  cat("  Running Harmony integration...\n")
  seurat_obj <- RunPCA(seurat_obj, npcs = dims)
  seurat_obj <- RunHarmony(seurat_obj, group.by.vars = batch_label)
  reduction_use <- "harmony"
} else if (integration_method == "anchors") {
  cat("  Running anchor-based integration...\n")
  anchors <- FindIntegrationAnchors(object.list = object.list, dims = 1:dims)
  seurat_obj <- IntegrateData(anchorset = anchors)
  seurat_obj <- ScaleData(seurat_obj)
  seurat_obj <- RunPCA(seurat_obj, npcs = dims)
  reduction_use <- "pca"
} else {
  cat("  No integration (just merge)...\n")
  seurat_obj <- RunPCA(seurat_obj, npcs = dims)
  reduction_use <- "pca"
}

# === 4. Clustering ===
cat("[4/7] Clustering...\n")
seurat_obj <- FindNeighbors(seurat_obj, dims = 1:dims, reduction = reduction_use)
seurat_obj <- FindClusters(seurat_obj, resolution = resolution)

# === 5. Visualization ===
cat("[5/7] Running UMAP...\n")
seurat_obj <- RunUMAP(seurat_obj, dims = 1:dims, reduction = reduction_use)

# === 6. Find Markers ===
cat("[6/7] Finding marker genes...\n")
markers <- FindAllMarkers(seurat_obj, only.pos = TRUE, min.pct = 0.25)
markers <- markers %>% group_by(cluster) %>% top_n(n = 10, wt = avg_log2FC)
write.csv(markers, "result_cluster_markers.csv", row.names = FALSE)

# === 7. Save Outputs ===
cat("[7/7] Saving outputs...\n")
saveRDS(seurat_obj, output_rds)

# Plots
pdf("result_integration_umap.pdf", width = 12, height = 5)
p1 <- DimPlot(seurat_obj, reduction = "umap", group.by = batch_label)
p2 <- DimPlot(seurat_obj, reduction = "umap", label = TRUE)
print(p1 | p2)
dev.off()

pdf("result_integration_by_batch.pdf", width = 10, height = 8)
p3 <- DimPlot(seurat_obj, reduction = "umap", split.by = batch_label, ncol = 2)
print(p3)
dev.off()

cluster_dist <- table(seurat_obj@meta.data$seurat_clusters)
write.csv(cluster_dist, "result_cluster_distribution.csv")

cat("\n========================================\n")
cat("  Analysis Complete!\n")
cat("========================================\n")
cat("Outputs:\n")
cat("  -", output_rds, "\n")
cat("  - result_cluster_markers.csv\n")
cat("  - result_integration_umap.pdf\n")
cat("  - result_integration_by_batch.pdf\n")
cat("\nCluster summary:\n")
print(cluster_dist)
cat("\n")
