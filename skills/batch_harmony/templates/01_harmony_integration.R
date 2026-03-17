#!/usr/bin/env Rscript
# ==============================================================================
# Harmony Integration (R - Seurat)
# ==============================================================================

suppressPackageStartupMessages({
  library(Seurat)
  library(harmony)
  library(dplyr)
})

# === Parse arguments ===
args <- commandArgs(trailingOnly = TRUE)

input_rds <- args[1] %||% "merged.rds"
output_rds <- args[2] %||% "result_harmony.rds"
batch_col <- args[3] %||% "batch"
dims <- as.integer(args[4]) %||% 30
resolution <- as.numeric(args[5]) %||% 0.8

cat("========================================\n")
cat("  Harmony Integration (Seurat)\n")
cat("========================================\n")
cat("Input:", input_rds, "\n")
cat("Batch column:", batch_col, "\n")
cat("PCA dims:", dims, "\n")
cat("========================================\n\n")

`%||%` <- function(x, y) if (is.null(x)) y else x

# === 1. Load Data ===
cat("[1/5] Loading data...\n")
seu <- readRDS(input_rds)
cat("  Cells:", ncol(seu), "\n")
cat("  Clusters:", length(unique(Idents(seu))), "\n\n")

# === 2. Check batch column ===
if (!batch_col %in% colnames(seu@meta.data)) {
  stop("Batch column '", batch_col, "' not found in metadata")
}

# === 3. Run PCA ===
cat("[2/5] Running PCA...\n")
seu <- RunPCA(seu, npcs = dims)

# === 4. Run Harmony ===
cat("[3/5] Running Harmony...\n")
seu <- RunHarmony(seu, group.by.vars = batch_col)

# === 5. Clustering and Visualization ===
cat("[4/5] Clustering...\n")
seu <- FindNeighbors(seu, reduction = "harmony", dims = 1:dims)
seu <- FindClusters(seu, resolution = resolution)

# Run UMAP
seu <- RunUMAP(seu, reduction = "harmony", dims = 1:dims)

# === 6. Save Outputs ===
cat("[5/5] Saving outputs...\n")
saveRDS(seu, output_rds)

# Save coordinates
umap_df <- data.frame(
  cell_id = colnames(seu),
  UMAP_1 = seu@reductions$umap@cell.embeddings[, 1],
  UMAP_2 = seu@reductions$umap@cell.embeddings[, 2],
  batch = seu[[batch_col]][, 1],
  cluster = Idents(seu),
  stringsAsFactors = FALSE
)
write.csv(umap_df, "result_umap_coordinates.csv", row.names = FALSE)

cat("\n========================================\n")
cat("  Analysis Complete!\n")
cat("========================================\n")
cat("Outputs:\n")
cat("  -", output_rds, "\n")
cat("  - result_umap_coordinates.csv\n")
cat("\n")
