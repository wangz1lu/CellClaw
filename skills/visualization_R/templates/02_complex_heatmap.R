#!/usr/bin/env Rscript
# ==============================================================================
# ComplexHeatmap Visualization Template
# ==============================================================================

suppressPackageStartupMessages({
  library(ComplexHeatmap)
  library(circlize)
})

# === Parse arguments ===
args <- commandArgs(trailingOnly = TRUE)

input_file <- args[1] %||% "data.csv"
output_file <- args[2] %||% "result_heatmap.pdf"
heatmap_name <- args[3] %||% "expression"
cluster_rows <- args[4] %||% "TRUE"
cluster_cols <- args[5] %||% "TRUE"

cat("========================================\n")
cat("  ComplexHeatmap Visualization\n")
cat("========================================\n")
cat("Input:", input_file, "\n")
cat("Output:", output_file, "\n")
cat("Name:", heatmap_name, "\n")
cat("========================================\n\n")

`%||%` <- function(x, y) if (is.null(x)) y else x

# === Load Data ===
cat("[1/2] Loading data...\n")

if (file.exists(input_file)) {
  data <- read.csv(input_file, row.names = 1)
  mat <- as.matrix(data)
} else {
  # Generate demo data
  set.seed(123)
  mat <- matrix(rnorm(100), 10, 10)
  rownames(mat) <- paste0("gene", 1:10)
  colnames(mat) <- paste0("cell", 1:10)
  cat("  Using demo data\n")
}

cat("  Dimensions:", dim(mat)[1], "x", dim(mat)[2], "\n\n")

# === Create Heatmap ===
cat("[2/2] Creating heatmap...\n")

# Color function
col_fun <- colorRamp2(c(-2, 0, 2), c("blue", "white", "red"))

# Cluster settings
cluster_rows_val <- if (cluster_rows == "TRUE") TRUE else FALSE
cluster_cols_val <- if (cluster_cols == "TRUE") TRUE else FALSE

# Create heatmap
ht <- Heatmap(
  mat,
  name = heatmap_name,
  col = col_fun,
  cluster_rows = cluster_rows_val,
  cluster_columns = cluster_cols_val,
  show_row_names = TRUE,
  show_column_names = FALSE,
  row_names_gp = gpar(fontsize = 8),
  column_names_gp = gpar(fontsize = 8)
)

# Draw and save
if (grepl("\\.pdf$", output_file)) {
  pdf(output_file, width = 10, height = 8)
} else {
  png(output_file, width = 3000, height = 2000, res = 300)
}

draw(ht)

dev.off()

cat("\n========================================\n")
cat("  Complete!\n")
cat("========================================\n")
cat("Output:", output_file, "\n\n")
