#!/usr/bin/env Rscript
# =============================================================================
# OmicsClaw CellChat Skill — Script 03
# Spatial Transcriptomics CCC Analysis
# =============================================================================
# Usage:
#   Rscript 03_spatial_CCC.R \
#     --input   seurat_spatial.rds \
#     --group   cell_type \
#     --species human \
#     --interaction_range 250 \
#     --contact_range     100 \
#     --scale_distance    0.01 \
#     --outdir  results/CCC/spatial
# =============================================================================

suppressPackageStartupMessages({
  library(CellChat)
  library(patchwork)
  library(optparse)
  library(ggplot2)
})

option_list <- list(
  make_option("--input",             type="character", help="Seurat spatial RDS or h5ad"),
  make_option("--group",             type="character", default="cell_type"),
  make_option("--species",           type="character", default="human"),
  make_option("--db",                type="character", default="Secreted"),
  make_option("--interaction_range", type="double",    default=250,
              help="Max communication distance in µm [default: 250]"),
  make_option("--contact_range",     type="double",    default=100,
              help="Direct contact range in µm [default: 100]"),
  make_option("--scale_distance",    type="double",    default=0.01,
              help="Distance decay scale factor [default: 0.01]"),
  make_option("--workers",           type="integer",   default=4),
  make_option("--outdir",            type="character", default="results/CCC/spatial")
)
opt <- parse_args(OptionParser(option_list=option_list))
if (is.null(opt$input)) stop("--input is required")

dir.create(opt$outdir, recursive=TRUE, showWarnings=FALSE)
setwd(opt$outdir)

cat("\n=== OmicsClaw CellChat: Spatial CCC ===\n")
cat(sprintf("Input: %s\n", opt$input))
cat(sprintf("Interaction range: %.0f µm\n", opt$interaction_range))
cat(sprintf("Contact range:     %.0f µm\n\n", opt$contact_range))

ptm <- Sys.time()

# ── Load spatial data ──────────────────────────────────────────────────────
cat("[1/6] Loading spatial data...\n")
library(Seurat)
obj <- readRDS(opt$input)

# Extract expression data
data.input <- GetAssayData(obj, assay="Spatial", slot="data")
if (is.null(data.input) || ncol(data.input) == 0) {
  data.input <- obj[["Spatial"]]$data
}

# Extract spatial coordinates
coords <- GetTissueCoordinates(obj)
spatial.locs <- coords[, c("imagerow", "imagecol")]

# Extract meta
meta <- obj@meta.data
meta$labels <- meta[[opt$group]]

cat(sprintf("  Spots: %d | Genes: %d\n", ncol(data.input), nrow(data.input)))

# ── Create CellChat spatial object ────────────────────────────────────────
cat("[2/6] Creating spatial CellChat object...\n")

# Determine scale factor from spot distances
distances <- as.matrix(dist(spatial.locs))
diag(distances) <- Inf
min_dist <- min(distances)
cat(sprintf("  Min spot distance: %.1f\n", min_dist))
cat(sprintf("  Adjusted interaction range: %.0f units\n",
            opt$interaction_range / min_dist * min_dist))

cellchat <- createCellChat(
  object       = data.input,
  meta         = meta,
  group.by     = "labels",
  datatype     = "spatial",
  coordinates  = spatial.locs,
  spatial.factors.use = "default"
)

# ── Set database ──────────────────────────────────────────────────────────
cat("[3/6] Setting database...\n")
CellChatDB <- if (opt$species == "human") CellChatDB.human else CellChatDB.mouse
if (opt$db == "Secreted") {
  cellchat@DB <- subsetDB(CellChatDB, search="Secreted Signaling", key="annotation")
} else {
  cellchat@DB <- subsetDB(CellChatDB)
}

# ── Preprocess ────────────────────────────────────────────────────────────
cat("[4/6] Preprocessing...\n")
cellchat <- subsetData(cellchat)
future::plan("multisession", workers=opt$workers)
cellchat <- identifyOverExpressedGenes(cellchat)
cellchat <- identifyOverExpressedInteractions(cellchat)

# ── Infer spatial communication ───────────────────────────────────────────
cat("[5/6] Computing spatial communication probabilities...\n")
cellchat <- computeCommunProb(
  cellchat,
  type               = "truncatedMean",
  trim               = 0.1,
  distance.use       = TRUE,
  interaction.range  = opt$interaction_range,
  scale.distance     = opt$scale_distance,
  contact.dependent  = TRUE,
  contact.range      = opt$contact_range
)
cellchat <- filterCommunication(cellchat, min.cells = 5)
cellchat <- computeCommunProbPathway(cellchat)
cellchat <- aggregateNet(cellchat)

n_pathways <- length(cellchat@netP$pathways)
cat(sprintf("  Significant pathways: %d\n", n_pathways))

# ── Visualization ─────────────────────────────────────────────────────────
cat("[6/6] Generating spatial visualizations...\n")
dir.create("01_spatial_plots", showWarnings=FALSE)
dir.create("02_pathways",      showWarnings=FALSE)

# Spatial communication network for each pathway
for (pw in cellchat@netP$pathways) {
  tryCatch({
    pdf(sprintf("01_spatial_plots/%s_spatial.pdf", pw), width=7, height=7)
    netVisual_aggregate(cellchat, signaling=pw, layout="spatial",
                        edge.width.max=2, vertex.size.max=1,
                        alpha.image=0.2, vertex.label.size=3.5)
    dev.off()
    
    # Also generate circle plot for comparison
    pdf(sprintf("02_pathways/%s_circle.pdf", pw), width=6, height=6)
    netVisual_aggregate(cellchat, signaling=pw, layout="circle")
    dev.off()
  }, error=function(e) NULL)
}

# Signaling roles
cellchat <- netAnalysis_computeCentrality(cellchat, slot.name="netP")
gg_scatter <- netAnalysis_signalingRole_scatter(cellchat)
ggsave("role_scatter.pdf", plot=gg_scatter, width=6, height=5, dpi=300)

ht1 <- netAnalysis_signalingRole_heatmap(cellchat, pattern="outgoing")
ht2 <- netAnalysis_signalingRole_heatmap(cellchat, pattern="incoming")
pdf("role_heatmap.pdf", width=14, height=6)
print(ht1 + ht2)
dev.off()

saveRDS(cellchat, "cellchat_spatial_result.rds")

elapsed <- as.numeric(Sys.time() - ptm, units="mins")
cat(sprintf("\n=== Spatial CCC Complete ===\n"))
cat(sprintf("Runtime: %.1f minutes\n", elapsed))
cat(sprintf("Pathways: %d | OutDir: %s\n\n", n_pathways, opt$outdir))
