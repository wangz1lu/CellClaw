#!/usr/bin/env Rscript
# =============================================================================
# OmicsClaw CellChat Skill — Script 01
# Single Dataset Cell-Cell Communication Analysis
# =============================================================================
# Usage:
#   Rscript 01_single_dataset_CCC.R \
#     --input  <path/to/seurat.rds or adata.h5ad> \
#     --format <seurat|anndata|matrix> \
#     --group  <cell_type_column_name> \
#     --species <human|mouse> \
#     --db     <Secreted|ECM|Contact|all> \
#     --method <triMean|truncatedMean> \
#     --trim   <0.1> \
#     --workers <4> \
#     --outdir <results/CCC/>
# =============================================================================

suppressPackageStartupMessages({
  library(CellChat)
  library(patchwork)
  library(optparse)
  library(ggplot2)
})

# ── Parse arguments ────────────────────────────────────────────────────────
option_list <- list(
  make_option("--input",   type="character", help="Input file (.rds / .h5ad)"),
  make_option("--format",  type="character", default="seurat",
              help="Input format: seurat | anndata | matrix [default: seurat]"),
  make_option("--group",   type="character", default="seurat_clusters",
              help="Cell type column name in meta.data [default: seurat_clusters]"),
  make_option("--species", type="character", default="human",
              help="Species: human | mouse [default: human]"),
  make_option("--db",      type="character", default="Secreted",
              help="DB subset: Secreted | ECM | Contact | all [default: Secreted]"),
  make_option("--method",  type="character", default="triMean",
              help="Avg expression method: triMean | truncatedMean [default: triMean]"),
  make_option("--trim",    type="double",    default=0.1,
              help="Trim value for truncatedMean [default: 0.1]"),
  make_option("--min_cells", type="integer", default=10,
              help="Min cells per group to retain [default: 10]"),
  make_option("--workers", type="integer",   default=4,
              help="Parallel workers [default: 4]"),
  make_option("--outdir",  type="character", default="results/CCC/single",
              help="Output directory [default: results/CCC/single]"),
  make_option("--pop_size",type="logical",   default=FALSE,
              help="Consider population size effect [default: FALSE]")
)
opt <- parse_args(OptionParser(option_list = option_list))

if (is.null(opt$input)) stop("--input is required")

dir.create(opt$outdir, recursive = TRUE, showWarnings = FALSE)
setwd(opt$outdir)
cat(sprintf("\n=== OmicsClaw CellChat: Single Dataset CCC ===\n"))
cat(sprintf("Input:   %s\n", opt$input))
cat(sprintf("Format:  %s\n", opt$format))
cat(sprintf("Species: %s\n", opt$species))
cat(sprintf("DB:      %s\n", opt$db))
cat(sprintf("Method:  %s\n", opt$method))
cat(sprintf("OutDir:  %s\n\n", opt$outdir))

ptm <- Sys.time()

# ── Step 1: Load input data ────────────────────────────────────────────────
cat("[1/7] Loading input data...\n")

if (opt$format == "seurat") {
  library(Seurat)
  obj <- readRDS(opt$input)
  data.input <- GetAssayData(obj, assay = "RNA", slot = "data")
  # Seurat v5 compatibility
  if (is.null(data.input) || ncol(data.input) == 0) {
    data.input <- obj[["RNA"]]$data
  }
  meta <- obj@meta.data
  meta$labels <- meta[[opt$group]]
  
} else if (opt$format == "anndata") {
  library(anndata)
  ad <- read_h5ad(opt$input)
  counts <- t(as.matrix(ad$X))
  # Normalize if needed (check if already normalized)
  if (max(counts, na.rm=TRUE) > 100) {
    cat("  Detected raw counts, normalizing...\n")
    library.size <- Matrix::colSums(counts)
    data.input <- as(log1p(Matrix::t(Matrix::t(counts)/library.size) * 10000), "dgCMatrix")
  } else {
    cat("  Detected normalized data, using as-is...\n")
    data.input <- as(counts, "dgCMatrix")
  }
  meta <- as.data.frame(ad$obs)
  meta$labels <- meta[[opt$group]]
  
} else if (opt$format == "matrix") {
  # Expects a list RDS with $data and $meta
  obj <- readRDS(opt$input)
  data.input <- obj$data
  meta <- obj$meta
  meta$labels <- meta[[opt$group]]
}

cat(sprintf("  Cells: %d | Genes: %d\n", ncol(data.input), nrow(data.input)))
cat(sprintf("  Cell types: %s\n", paste(unique(meta$labels), collapse=", ")))

# ── Step 2: Create CellChat object ────────────────────────────────────────
cat("[2/7] Creating CellChat object...\n")
cellchat <- createCellChat(object = data.input, meta = meta, group.by = "labels")
cat(sprintf("  Groups: %d | Levels: %s\n",
            length(levels(cellchat@idents)),
            paste(levels(cellchat@idents), collapse=", ")))

# ── Step 3: Set database ──────────────────────────────────────────────────
cat("[3/7] Setting ligand-receptor database...\n")
CellChatDB <- if (opt$species == "human") CellChatDB.human else CellChatDB.mouse

if (opt$db == "Secreted") {
  CellChatDB.use <- subsetDB(CellChatDB, search = "Secreted Signaling", key = "annotation")
} else if (opt$db == "ECM") {
  CellChatDB.use <- subsetDB(CellChatDB, search = "ECM-Receptor", key = "annotation")
} else if (opt$db == "Contact") {
  CellChatDB.use <- subsetDB(CellChatDB, search = "Cell-Cell Contact", key = "annotation")
} else {
  # all: exclude Non-protein Signaling
  CellChatDB.use <- subsetDB(CellChatDB)
}

cellchat@DB <- CellChatDB.use
cat(sprintf("  L-R pairs in DB: %d\n", nrow(CellChatDB.use$interaction)))

# ── Step 4: Preprocess ────────────────────────────────────────────────────
cat("[4/7] Preprocessing expression data...\n")
cellchat <- subsetData(cellchat)
future::plan("multisession", workers = opt$workers)
cellchat <- identifyOverExpressedGenes(cellchat)
cellchat <- identifyOverExpressedInteractions(cellchat)

# ── Step 5: Infer communication ───────────────────────────────────────────
cat("[5/7] Computing communication probabilities...\n")
if (opt$method == "truncatedMean") {
  cellchat <- computeCommunProb(cellchat, type = "truncatedMean",
                                 trim = opt$trim,
                                 population.size = opt$pop_size)
} else {
  cellchat <- computeCommunProb(cellchat, type = "triMean",
                                 population.size = opt$pop_size)
}

cellchat <- filterCommunication(cellchat, min.cells = opt$min_cells)
cellchat <- computeCommunProbPathway(cellchat)
cellchat <- aggregateNet(cellchat)

n_pathways <- length(cellchat@netP$pathways)
cat(sprintf("  Significant pathways: %d\n", n_pathways))
cat(sprintf("  Pathways: %s\n", paste(cellchat@netP$pathways, collapse=", ")))

# Export L-R table
df.LR <- subsetCommunication(cellchat)
write.csv(df.LR, "LR_interactions.csv", row.names = FALSE)
df.path <- subsetCommunication(cellchat, slot.name = "netP")
write.csv(df.path, "pathway_interactions.csv", row.names = FALSE)
cat(sprintf("  L-R interactions exported: %d rows\n", nrow(df.LR)))

# ── Step 6: Visualization ─────────────────────────────────────────────────
cat("[6/7] Generating visualizations...\n")

dir.create("01_overview",    showWarnings = FALSE)
dir.create("02_pathways",    showWarnings = FALSE)
dir.create("03_signaling_roles", showWarnings = FALSE)
dir.create("04_patterns",    showWarnings = FALSE)
dir.create("05_manifold",    showWarnings = FALSE)

groupSize <- as.numeric(table(cellchat@idents))

# --- Overview: circle plots ---
pdf("01_overview/circle_interactions.pdf", width=12, height=5)
par(mfrow=c(1,2), xpd=TRUE)
netVisual_circle(cellchat@net$count, vertex.weight=groupSize,
                 weight.scale=TRUE, label.edge=FALSE,
                 title.name="Number of interactions")
netVisual_circle(cellchat@net$weight, vertex.weight=groupSize,
                 weight.scale=TRUE, label.edge=FALSE,
                 title.name="Interaction weights/strength")
dev.off()

# Per cell type outgoing signal
pdf("01_overview/per_celltype_outgoing.pdf", width=12, height=9)
mat <- cellchat@net$weight
n_ct <- nrow(mat)
nr <- ceiling(sqrt(n_ct)); nc <- ceiling(n_ct / nr)
par(mfrow=c(nr, nc), xpd=TRUE)
for (i in 1:n_ct) {
  mat2 <- matrix(0, nrow=nrow(mat), ncol=ncol(mat), dimnames=dimnames(mat))
  mat2[i,] <- mat[i,]
  netVisual_circle(mat2, vertex.weight=groupSize, weight.scale=TRUE,
                   edge.weight.max=max(mat), title.name=rownames(mat)[i])
}
dev.off()

# --- Per pathway: hierarchy + chord + contribution ---
vertex.receiver <- seq(1, max(1, floor(length(levels(cellchat@idents))/2)))
pathways.all <- cellchat@netP$pathways
cat(sprintf("  Plotting %d pathways...\n", length(pathways.all)))

for (pw in pathways.all) {
  tryCatch({
    # Hierarchy
    pdf(sprintf("02_pathways/%s_hierarchy.pdf", pw), width=8, height=5.5)
    netVisual_aggregate(cellchat, signaling=pw, vertex.receiver=vertex.receiver)
    dev.off()
    # Chord
    pdf(sprintf("02_pathways/%s_chord.pdf", pw), width=6, height=6)
    par(mfrow=c(1,1))
    netVisual_aggregate(cellchat, signaling=pw, layout="chord")
    dev.off()
    # L-R contribution
    gg <- netAnalysis_contribution(cellchat, signaling=pw)
    ggsave(sprintf("02_pathways/%s_LR_contribution.pdf", pw),
           plot=gg, width=4, height=2.5, dpi=300)
  }, error = function(e) {
    cat(sprintf("    Warning: failed to plot pathway %s: %s\n", pw, e$message))
  })
}

# Bubble plot: all pathways, all source->target
tryCatch({
  n_groups <- length(levels(cellchat@idents))
  gg <- netVisual_bubble(cellchat,
                          sources.use = seq(1, n_groups),
                          targets.use = seq(1, n_groups),
                          remove.isolate = TRUE,
                          return.data = FALSE)
  ggsave("02_pathways/bubble_all.pdf", plot=gg, width=10, height=8, dpi=300)
}, error = function(e) cat(sprintf("  Bubble plot skipped: %s\n", e$message)))

# --- Signaling roles ---
cellchat <- netAnalysis_computeCentrality(cellchat, slot.name="netP")

gg_scatter <- netAnalysis_signalingRole_scatter(cellchat)
ggsave("03_signaling_roles/role_scatter.pdf", plot=gg_scatter, width=6, height=5)

ht1 <- netAnalysis_signalingRole_heatmap(cellchat, pattern="outgoing")
ht2 <- netAnalysis_signalingRole_heatmap(cellchat, pattern="incoming")
pdf("03_signaling_roles/role_heatmap.pdf", width=14, height=6)
print(ht1 + ht2)
dev.off()

# --- Communication patterns ---
tryCatch({
  library(NMF)
  library(ggalluvial)
  
  # Select K
  pdf("04_patterns/selectK_outgoing.pdf", width=7, height=3)
  selectK(cellchat, pattern="outgoing")
  dev.off()
  pdf("04_patterns/selectK_incoming.pdf", width=7, height=3)
  selectK(cellchat, pattern="incoming")
  dev.off()
  
  # Fit patterns (default k=5 if not auto-selected)
  nP_out <- 5; nP_in <- 3
  cellchat <- identifyCommunicationPatterns(cellchat, pattern="outgoing",  k=nP_out, width=5, height=7)
  gg_riv_out <- netAnalysis_river(cellchat, pattern="outgoing",  return.object=TRUE)
  gg_dot_out <- netAnalysis_dot(cellchat,   pattern="outgoing",  return.object=TRUE)
  ggsave("04_patterns/outgoing_river.pdf", plot=gg_riv_out, width=8, height=5)
  ggsave("04_patterns/outgoing_dot.pdf",   plot=gg_dot_out, width=8, height=5)
  
  cellchat <- identifyCommunicationPatterns(cellchat, pattern="incoming", k=nP_in,  width=5, height=7)
  gg_riv_in <- netAnalysis_river(cellchat, pattern="incoming", return.object=TRUE)
  gg_dot_in <- netAnalysis_dot(cellchat,   pattern="incoming", return.object=TRUE)
  ggsave("04_patterns/incoming_river.pdf", plot=gg_riv_in, width=8, height=5)
  ggsave("04_patterns/incoming_dot.pdf",   plot=gg_dot_in, width=8, height=5)
}, error = function(e) cat(sprintf("  Pattern analysis skipped: %s\n", e$message)))

# --- Manifold learning ---
tryCatch({
  for (sim_type in c("functional", "structural")) {
    cellchat <- computeNetSimilarity(cellchat, type=sim_type)
    cellchat <- netEmbedding(cellchat, type=sim_type)
    cellchat <- netClustering(cellchat, type=sim_type)
    pdf(sprintf("05_manifold/%s_embedding.pdf", sim_type), width=8, height=6)
    netVisual_embedding(cellchat, type=sim_type, label.size=3.5)
    dev.off()
  }
}, error = function(e) cat(sprintf("  Manifold learning skipped: %s\n", e$message)))

# ── Step 7: Save ──────────────────────────────────────────────────────────
cat("[7/7] Saving CellChat object...\n")
saveRDS(cellchat, file="cellchat_result.rds")

elapsed <- as.numeric(Sys.time() - ptm, units="mins")
cat(sprintf("\n=== Analysis Complete ===\n"))
cat(sprintf("Runtime:    %.1f minutes\n", elapsed))
cat(sprintf("Pathways:   %d\n", n_pathways))
cat(sprintf("Output dir: %s\n", opt$outdir))
cat(sprintf("Saved:      cellchat_result.rds\n\n"))
