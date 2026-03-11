#!/usr/bin/env Rscript
# =============================================================================
# OmicsClaw CellChat Skill — Script 02
# Multi-Dataset Comparison CCC Analysis
# =============================================================================
# Usage:
#   Rscript 02_comparison_CCC.R \
#     --inputs  cellchat_A.rds,cellchat_B.rds \
#     --names   ConditionA,ConditionB \
#     --outdir  results/CCC/comparison
#
# Note: Each input .rds must be a completed single-dataset CellChat object
#       (output of 01_single_dataset_CCC.R)
# =============================================================================

suppressPackageStartupMessages({
  library(CellChat)
  library(patchwork)
  library(optparse)
  library(ggplot2)
})

option_list <- list(
  make_option("--inputs",  type="character", help="Comma-sep list of CellChat RDS files"),
  make_option("--names",   type="character", help="Comma-sep condition names"),
  make_option("--outdir",  type="character", default="results/CCC/comparison",
              help="Output directory [default: results/CCC/comparison]"),
  make_option("--exclude_signal", type="character", default="MIF",
              help="Signals to exclude from scatter plots [default: MIF]")
)
opt <- parse_args(OptionParser(option_list = option_list))

if (is.null(opt$inputs)) stop("--inputs is required")
if (is.null(opt$names))  stop("--names is required")

input_files <- strsplit(opt$inputs, ",")[[1]]
cond_names  <- strsplit(opt$names,  ",")[[1]]
exclude_sig <- strsplit(opt$exclude_signal, ",")[[1]]

if (length(input_files) != length(cond_names)) {
  stop("Number of --inputs and --names must match")
}
if (length(input_files) < 2) stop("At least 2 datasets required for comparison")

dir.create(opt$outdir, recursive=TRUE, showWarnings=FALSE)
setwd(opt$outdir)

cat("\n=== OmicsClaw CellChat: Multi-Dataset Comparison ===\n")
for (i in seq_along(input_files)) {
  cat(sprintf("  [%d] %s : %s\n", i, cond_names[i], input_files[i]))
}
cat(sprintf("  OutDir: %s\n\n", opt$outdir))

ptm <- Sys.time()

# ── Load and merge ─────────────────────────────────────────────────────────
cat("[1/5] Loading CellChat objects...\n")
object.list <- lapply(input_files, readRDS)
names(object.list) <- cond_names

# Update old objects if needed
object.list <- lapply(object.list, function(x) {
  tryCatch(updateCellChat(x), error=function(e) x)
})

cat("[2/5] Merging CellChat objects...\n")
cellchat <- mergeCellChat(object.list, add.names=cond_names)
cat(sprintf("  Merged: %d datasets, %d total cells\n",
            length(object.list),
            sum(sapply(object.list, function(x) length(x@idents)))))

# Save merged object
save(object.list, file="cellchat_object_list.RData")
save(cellchat,    file="cellchat_merged.RData")

# ── Part I: Overall interaction changes ────────────────────────────────────
cat("[3/5] Visualizing overall interaction changes...\n")
dir.create("01_overall",   showWarnings=FALSE)
dir.create("02_pathways",  showWarnings=FALSE)
dir.create("03_roles",     showWarnings=FALSE)
dir.create("04_manifold",  showWarnings=FALSE)

# Compare total interactions
gg1 <- compareInteractions(cellchat, show.legend=FALSE, group=seq_along(cond_names))
gg2 <- compareInteractions(cellchat, show.legend=FALSE, group=seq_along(cond_names), measure="weight")
ggsave("01_overall/compare_total_interactions.pdf",
       plot=gg1+gg2, width=8, height=3, dpi=300)

# Pairwise diff network (works for 2 datasets)
if (length(object.list) == 2) {
  pdf("01_overall/diff_circle_count.pdf",  width=12, height=6)
  par(mfrow=c(1,2), xpd=TRUE)
  netVisual_diffInteraction(cellchat, weight.scale=TRUE)
  netVisual_diffInteraction(cellchat, weight.scale=TRUE, measure="weight")
  dev.off()
  
  gg_h1 <- netVisual_heatmap(cellchat)
  gg_h2 <- netVisual_heatmap(cellchat, measure="weight")
  ggsave("01_overall/diff_heatmap.pdf",
         plot=gg_h1+gg_h2, width=12, height=5, dpi=300)
}

# Per-dataset circle plots (same scale)
weight.max <- getMaxWeight(object.list, attribute=c("idents","count"))
pdf("01_overall/per_dataset_circles.pdf",
    width=6*length(object.list), height=6)
par(mfrow=c(1, length(object.list)), xpd=TRUE)
for (i in seq_along(object.list)) {
  netVisual_circle(object.list[[i]]@net$count,
                   weight.scale=TRUE, label.edge=FALSE,
                   edge.weight.max=weight.max[2],
                   edge.width.max=12,
                   title.name=paste0("# interactions - ", cond_names[i]))
}
dev.off()

# Source/target comparison scatter (unified scale)
num.link <- sapply(object.list, function(x) {
  rowSums(x@net$count) + colSums(x@net$count) - diag(x@net$count)
})
weight.MinMax <- c(min(num.link), max(num.link))
gg_list <- lapply(seq_along(object.list), function(i) {
  netAnalysis_signalingRole_scatter(object.list[[i]],
                                    title=cond_names[i],
                                    weight.MinMax=weight.MinMax)
})
ggsave("03_roles/source_target_scatter.pdf",
       plot=patchwork::wrap_plots(plots=gg_list),
       width=5*length(object.list), height=4, dpi=300)

# Signaling changes per cell type (for all cell types)
all_celltypes <- levels(object.list[[1]]@idents)
for (ct in all_celltypes) {
  tryCatch({
    gg_chg <- netAnalysis_signalingChanges_scatter(cellchat,
                                                    idents.use=ct,
                                                    signaling.exclude=exclude_sig)
    safe_name <- gsub("[/ ]", "_", ct)
    ggsave(sprintf("03_roles/signaling_changes_%s.pdf", safe_name),
           plot=gg_chg, width=5, height=4, dpi=300)
  }, error=function(e) NULL)
}

# ── Part II: Pathway-level comparison ──────────────────────────────────────
cat("[4/5] Pathway comparison analysis...\n")

# Rank pathways by difference
tryCatch({
  gg_rank <- rankNet(cellchat, mode="comparison", stacked=TRUE, do.stat=TRUE)
  ggsave("02_pathways/pathway_rank_comparison.pdf",
         plot=gg_rank, width=8, height=6, dpi=300)
}, error=function(e) cat(sprintf("  rankNet skipped: %s\n", e$message)))

# Bubble plot comparison (2 datasets only)
if (length(object.list) == 2) {
  n_groups <- length(levels(object.list[[1]]@idents))
  tryCatch({
    gg_bub <- netVisual_bubble(cellchat,
                                comparison=c(1,2),
                                sources.use=seq(1, n_groups),
                                targets.use=seq(1, n_groups),
                                max.dataset=2,
                                title.name=paste0(cond_names[2], " vs ", cond_names[1]),
                                angle.x=45,
                                remove.isolate=TRUE)
    ggsave("02_pathways/bubble_comparison.pdf",
           plot=gg_bub, width=10, height=8, dpi=300)
  }, error=function(e) cat(sprintf("  Bubble comparison skipped: %s\n", e$message)))
}

# ── Part III: Joint manifold learning ──────────────────────────────────────
cat("[5/5] Joint manifold learning...\n")

# Structural similarity (works for any cell composition)
tryCatch({
  cellchat <- computeNetSimilarityPairwise(cellchat, type="structural")
  cellchat <- netEmbedding(cellchat, type="structural")
  cellchat <- netClustering(cellchat, type="structural")
  pdf("04_manifold/structural_embedding.pdf", width=8, height=6)
  netVisual_embeddingPairwise(cellchat, type="structural", label.size=3.5)
  dev.off()
}, error=function(e) cat(sprintf("  Structural embedding skipped: %s\n", e$message)))

# Functional similarity (only valid if same cell composition)
tryCatch({
  cellchat <- computeNetSimilarityPairwise(cellchat, type="functional")
  cellchat <- netEmbedding(cellchat, type="functional")
  cellchat <- netClustering(cellchat, type="functional")
  pdf("04_manifold/functional_embedding.pdf", width=8, height=6)
  netVisual_embeddingPairwise(cellchat, type="functional", label.size=3.5)
  dev.off()
}, error=function(e) cat(sprintf("  Functional embedding skipped: %s\n", e$message)))

# Save final merged object
save(cellchat, file="cellchat_merged_final.RData")

elapsed <- as.numeric(Sys.time() - ptm, units="mins")
cat(sprintf("\n=== Comparison Complete ===\n"))
cat(sprintf("Runtime: %.1f minutes\n", elapsed))
cat(sprintf("OutDir:  %s\n\n", opt$outdir))
