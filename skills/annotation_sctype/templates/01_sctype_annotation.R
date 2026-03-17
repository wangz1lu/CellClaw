#!/usr/bin/env Rscript
# ==============================================================================
# ScType Cell Type Annotation
# ==============================================================================

suppressPackageStartupMessages({
  library(Seurat)
  library(dplyr)
  library(HGNChelper)
  library(openxlsx)
})

# === Parse arguments ===
args <- commandArgs(trailingOnly = TRUE)

input_rds <- args[1] %||% "input.rds"
output_rds <- args[2] %||% "result_sctype_annotated.rds"
tissue <- args[3] %||% "Immune system"
use_db <- as.logical(args[4]) %||% TRUE  # TRUE: use built-in DB, FALSE: use custom markers

cat("========================================\n")
cat("  ScType Cell Type Annotation\n")
cat("========================================\n")
cat("Input:", input_rds, "\n")
cat("Tissue:", tissue, "\n")
cat("========================================\n\n")

`%||%` <- function(x, y) if (is.null(x)) y else x

# === 1. Load Data ===
cat("[1/6] Loading Seurat object...\n")
seu <- readRDS(input_rds)
cat("  Cells:", ncol(seu), "\n")
cat("  Clusters:", length(unique(Idents(seu))), "\n\n")

# === 2. Load ScType functions ===
cat("[2/6] Loading ScType functions...\n")
source("https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/R/gene_sets_prepare.R")
source("https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/R/sctype_score_.R")

# === 3. Prepare gene sets ===
cat("[3/6] Preparing gene sets...\n")

if (use_db) {
  # Use built-in database
  db_ <- "https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/ScTypeDB_full.xlsx"
  gs_list <- gene_sets_prepare(db_, tissue)
  cat("  Loaded gene sets for:", tissue, "\n\n")
} else {
  # Custom markers
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
    ),
    `Plasma cells` = list(
      positive = c("IGJ", "XBP1", "MZB1", "DERL3"),
      negative = c("CD3D", "CD79A")
    ),
    `Platelet` = list(
      positive = c("PPBP", "PF4", "SELPLG", "ITGA2B"),
      negative = c("CD3D", "CD79A")
    )
  )
  cat("  Using custom markers\n\n")
}

# === 4. Prepare expression matrix ===
cat("[4/6] Preparing expression matrix...\n")
seurat_package_v5 <- isFALSE('counts' %in% names(attributes(seu[["RNA"]])))

scRNAseqData_scaled <- if (seurat_package_v5) {
  as.matrix(seu[["RNA"]]$scale.data)
} else {
  as.matrix(seu[["RNA"]]@scale.data)
}
cat("  Expression matrix ready\n\n")

# === 5. Run ScType ===
cat("[5/6] Running ScType annotation...\n")
es.max <- sctype_score(
  scRNAseqData = scRNAseqData_scaled,
  scaled = TRUE,
  gs = gs_list$gs_positive,
  gs2 = gs_list$gs_negative
)

# Merge by cluster
cL_resutls <- do.call("rbind", lapply(unique(seu@meta.data$seurat_clusters), function(cl){
  es.max.cl <- sort(rowSums(es.max[, rownames(seu@meta.data[seu@meta.data$seurat_clusters == cl, ])]), decreasing = TRUE)
  head(data.frame(
    cluster = cl,
    type = names(es.max.cl),
    scores = es.max.cl,
    ncells = sum(seu@meta.data$seurat_clusters == cl)
  ), 10)
}))

# Get best match per cluster
sctype_scores <- cL_resutls %>% group_by(cluster) %>% top_n(n = 1, wt = scores)

# Set low confidence to "Unknown"
sctype_scores$type[as.numeric(as.character(sctype_scores$scores)) < sctype_scores$ncells/4] <- "Unknown"

# Add to Seurat
seu@meta.data$sctype_classification <- ""
for(j in unique(sctype_scores$cluster)){
  cl_type <- sctype_scores[sctype_scores$cluster == j, ]
  seu@meta.data$sctype_classification[seu@meta.data$seurat_clusters == j] <- as.character(cl_type$type[1])
}

cat("  Annotation complete\n")
cat("  Results:\n")
print(sctype_scores[, 1:3])
cat("\n")

# === 6. Save outputs ===
cat("[6/6] Saving outputs...\n")
saveRDS(seu, output_rds)

# Save annotation table
annotation_df <- data.frame(
  cell_id = colnames(seu),
  cluster = Idents(seu),
  sctype_classification = seu$sctype_classification,
  stringsAsFactors = FALSE
)
write.csv(annotation_df, "result_celltype_annotation.csv", row.names = FALSE)

# Save scores
write.csv(sctype_scores, "result_sctype_scores.csv", row.names = FALSE)

cat("\n========================================\n")
cat("  Analysis Complete!\n")
cat("========================================\n")
cat("Outputs:\n")
cat("  -", output_rds, "\n")
cat("  - result_celltype_annotation.csv\n")
cat("  - result_sctype_scores.csv\n")
cat("\n")
