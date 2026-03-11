#!/usr/bin/env Rscript
# =============================================================================
# OmicsClaw CellChat Skill — Script 04
# Input from Python/Anndata (Scanpy h5ad)
# =============================================================================
# For users whose workflow is Python-based (scanpy/anndata).
# Converts .h5ad → CellChat-compatible format and runs full CCC analysis.
#
# Usage:
#   Rscript 04_from_anndata.R \
#     --input  adata.h5ad \
#     --group  leiden \        # obs column with cell type labels
#     --species human \
#     --outdir results/CCC/
# =============================================================================

suppressPackageStartupMessages({
  library(CellChat)
  library(patchwork)
  library(optparse)
  library(Matrix)
})

option_list <- list(
  make_option("--input",   type="character", help="Path to .h5ad file"),
  make_option("--group",   type="character", default="leiden",
              help="obs column with cell type labels [default: leiden]"),
  make_option("--species", type="character", default="human"),
  make_option("--db",      type="character", default="Secreted"),
  make_option("--method",  type="character", default="triMean"),
  make_option("--trim",    type="double",    default=0.1),
  make_option("--workers", type="integer",   default=4),
  make_option("--outdir",  type="character", default="results/CCC/")
)
opt <- parse_args(OptionParser(option_list=option_list))
if (is.null(opt$input)) stop("--input is required")

dir.create(opt$outdir, recursive=TRUE, showWarnings=FALSE)

cat("\n=== OmicsClaw CellChat: Anndata → CellChat ===\n")
cat(sprintf("Input:  %s\n", opt$input))
cat(sprintf("Group:  %s\n\n", opt$group))
ptm <- Sys.time()

# ── Method 1: anndata R package ──────────────────────────────────────────
# This is the most reliable way to read h5ad in R
cat("[1/2] Reading h5ad file...\n")

use_anndata_pkg <- requireNamespace("anndata", quietly=TRUE)

if (use_anndata_pkg) {
  library(anndata)
  ad <- read_h5ad(opt$input)
  
  # Extract expression matrix
  # h5ad .X may be raw counts or normalized — detect and handle
  X <- t(as.matrix(ad$X))
  
  max_val <- max(X[1:min(100, nrow(X)), 1:min(100, ncol(X))], na.rm=TRUE)
  if (max_val > 50) {
    # Looks like raw counts, normalize
    cat("  Detected raw counts, applying normalize_total + log1p...\n")
    lib_size <- Matrix::colSums(X)
    X_norm <- as(log1p(t(t(X) / lib_size) * 10000), "dgCMatrix")
  } else if ("X_norm" %in% names(ad$layers)) {
    cat("  Using normalized layer X_norm...\n")
    X_norm <- as(t(as.matrix(ad$layers[["X_norm"]])), "dgCMatrix")
  } else {
    cat("  Using X as-is (assuming normalized)...\n")
    X_norm <- as(X, "dgCMatrix")
  }
  
  meta <- as.data.frame(ad$obs)
  
} else {
  # Method 2: Read via Python (reticulate) if anndata R pkg not available
  cat("  anndata R package not found, trying reticulate...\n")
  library(reticulate)
  ad_py <- import("anndata")
  ad    <- ad_py$read_h5ad(opt$input)
  
  X <- t(as.matrix(ad$X))
  lib_size <- Matrix::colSums(X)
  max_val <- max(X[1:min(50, nrow(X)), 1:min(50, ncol(X))], na.rm=TRUE)
  
  if (max_val > 50) {
    X_norm <- as(log1p(t(t(X) / lib_size) * 10000), "dgCMatrix")
  } else {
    X_norm <- as(X, "dgCMatrix")
  }
  meta <- as.data.frame(py_to_r(ad$obs))
}

# Validate group column
if (!opt$group %in% colnames(meta)) {
  available <- paste(colnames(meta), collapse=", ")
  stop(sprintf("Column '%s' not found in obs. Available: %s", opt$group, available))
}

meta$labels <- as.character(meta[[opt$group]])

cat(sprintf("  Cells: %d | Genes: %d\n", ncol(X_norm), nrow(X_norm)))
cat(sprintf("  Cell type column: %s\n", opt$group))
cat(sprintf("  Cell types (%d): %s\n",
            length(unique(meta$labels)),
            paste(unique(meta$labels), collapse=", ")))

# ── Create CellChat object and run analysis ────────────────────────────────
cat("[2/2] Creating CellChat object...\n")
cellchat <- createCellChat(object=X_norm, meta=meta, group.by="labels")

CellChatDB <- if (opt$species == "human") CellChatDB.human else CellChatDB.mouse
if (opt$db == "Secreted") {
  cellchat@DB <- subsetDB(CellChatDB, search="Secreted Signaling", key="annotation")
} else {
  cellchat@DB <- subsetDB(CellChatDB)
}

cellchat <- subsetData(cellchat)
future::plan("multisession", workers=opt$workers)
cellchat <- identifyOverExpressedGenes(cellchat)
cellchat <- identifyOverExpressedInteractions(cellchat)

if (opt$method == "truncatedMean") {
  cellchat <- computeCommunProb(cellchat, type="truncatedMean", trim=opt$trim)
} else {
  cellchat <- computeCommunProb(cellchat, type="triMean")
}

cellchat <- filterCommunication(cellchat, min.cells=10)
cellchat <- computeCommunProbPathway(cellchat)
cellchat <- aggregateNet(cellchat)
cellchat <- netAnalysis_computeCentrality(cellchat, slot.name="netP")

# Basic visualizations
setwd(opt$outdir)
groupSize <- as.numeric(table(cellchat@idents))
pdf("circle_interactions.pdf", width=12, height=5)
par(mfrow=c(1,2), xpd=TRUE)
netVisual_circle(cellchat@net$count, vertex.weight=groupSize, weight.scale=TRUE,
                 label.edge=FALSE, title.name="Number of interactions")
netVisual_circle(cellchat@net$weight, vertex.weight=groupSize, weight.scale=TRUE,
                 label.edge=FALSE, title.name="Interaction strength")
dev.off()

ht1 <- netAnalysis_signalingRole_heatmap(cellchat, pattern="outgoing")
ht2 <- netAnalysis_signalingRole_heatmap(cellchat, pattern="incoming")
pdf("role_heatmap.pdf", width=14, height=6)
print(ht1 + ht2)
dev.off()

# Export tables
df.LR <- subsetCommunication(cellchat)
write.csv(df.LR, "LR_interactions.csv", row.names=FALSE)

saveRDS(cellchat, "cellchat_result.rds")

elapsed <- as.numeric(Sys.time() - ptm, units="mins")
cat(sprintf("\n=== Done! %.1f minutes | Pathways: %d | OutDir: %s ===\n\n",
            elapsed,
            length(cellchat@netP$pathways),
            opt$outdir))
