#!/usr/bin/env Rscript
# ============================================================
# OmicsClaw Skill: Standard DimRed and Clustering
# Template: 01_standard_workflow.R
# ============================================================

args <- commandArgs(trailingOnly = TRUE)
input_path  <- args[1] %||% "input.rds"
output_dir  <- args[2] %||% "."
npcs        <- as.integer(args[3] %||% "30")
resolution  <- as.numeric(args[4] %||% "0.5")
use_leiden  <- as.logical(args[5] %||% "TRUE")

cat("=== OmicsClaw: Standard DimRed & Clustering ===\n")
cat("输入:", input_path, "\n")
cat("PCs:", npcs, "\n")
cat("Resolution:", resolution, "\n")
cat("Leiden:", use_leiden, "\n\n")

`%||%` <- function(x, y) if (is.null(x)) y else x

# ── 1. 加载库 ──────────────────────────────────────────────────

suppressPackageStartupMessages({
    library(Seurat)
    library(ggplot2)
    library(patchwork)
})

# ── 2. 加载数据 ────────────────────────────────────────────────

cat("Step 1: 加载数据...\n")
if (grepl("\\.rds$", input_path)) {
    seu <- readRDS(input_path)
} else if (dir.exists(input_path)) {
    seu <- Read10X(input_path) %>% CreateSeuratObject()
} else {
    stop("不支持的输入格式: ", input_path)
}
cat("  初始细胞数:", ncol(seu), "\n")
cat("  基因数:", nrow(seu), "\n")

# ── 3. QC ─────────────────────────────────────────────────────

cat("Step 2: 质控...\n")
seu[["percent.mt"]] <- PercentageFeatureSet(seu, pattern = "^MT-")
seu[["percent.rb"]] <- PercentageFeatureSet(seu, pattern = "^RP[SL]")

# 默认 QC 阈值（可调）
seu <- subset(seu, 
    nFeature_RNA > 200 & nFeature_RNA < 5000 &
    nCount_RNA > 500 & nCount_RNA < 50000 &
    percent.mt < 20
)
cat("  QC 后细胞数:", ncol(seu), "\n")

# ── 4. 归一化 + 特征选择 ────────────────────────────────────────

cat("Step 3: 归一化 + 特征选择...\n")
seu <- NormalizeData(seu, normalization.method = "LogNormalize", scale.factor = 10000)
seu <- FindVariableFeatures(seu, selection.method = "vst", nfeatures = 2000)
cat("  高变基因数:", length(VariableFeatures(seu)), "\n")

# ── 5. 标准化 ──────────────────────────────────────────────────

cat("Step 4: 标准化...\n")
all.genes <- rownames(seu)
seu <- ScaleData(seu, features = all.genes, vars.to.regress = c("percent.mt"))

# ── 6. PCA ────────────────────────────────────────────────────

cat("Step 5: PCA 降维...\n")
seu <- RunPCA(seu, features = VariableFeatures(seu), npcs = npcs, verbose = FALSE)

# ── 7. UMAP ───────────────────────────────────────────────────

cat("Step 6: UMAP 降维...\n")
seu <- RunUMAP(seu, dims = 1:npcs, reduction = "pca", 
               n.neighbors = 30, min.dist = 0.3, metric = "cosine")

# ── 8. 聚类 ───────────────────────────────────────────────────

cat("Step 7: 聚类 (resolution =", resolution, ")...\n")
seu <- FindNeighbors(seu, dims = 1:npcs, reduction = "pca")

if (use_leiden) {
    seu <- FindClusters(seu, resolution = resolution, algorithm = 4, method = "igraph")
} else {
    seu <- FindClusters(seu, resolution = resolution, algorithm = 1)
}
cat("  Cluster 数:", length(unique(Idents(seu))), "\n")

# ── 9. 导出结果 ────────────────────────────────────────────────

cat("Step 8: 导出结果...\n")

# RDS
saveRDS(seu, file.path(output_dir, "result_seurat_clustered.rds"))

# Cluster 分配
cluster_df <- data.frame(
    cell_id = colnames(seu),
    cluster = Idents(seu),
    UMAP_1 = seu@reductions$umap@cell.embeddings[,1],
    UMAP_2 = seu@reductions$umap@cell.embeddings[,2]
)
write.csv(cluster_df, file.path(output_dir, "result_cluster_assignments.csv"), 
          row.names = FALSE)

# ── 10. 可视化 ────────────────────────────────────────────────

cat("Step 9: 生成可视化...\n")

# UMAP cluster
p1 <- DimPlot(seu, reduction = "umap", label = TRUE, repel = TRUE) + 
    ggtitle("UMAP Clustering")
ggsave(file.path(output_dir, "result_umap_clusters.png"), 
       p1, width = 10, height = 8, dpi = 300)

# QC violin
p2 <- VlnPlot(seu, features = c("nFeature_RNA", "nCount_RNA", "percent.mt"), 
              ncol = 3, pt.size = 0.1)
ggsave(file.path(output_dir, "result_qc_violin.png"), 
       p2, width = 14, height = 5, dpi = 300)

# Elbow plot
p3 <- ElbowPlot(seu, ndims = npcs)
ggsave(file.path(output_dir, "result_elbow_plot.png"), 
       p3, width = 6, height = 4, dpi = 300)

# ── 11. Cluster 统计 ─────────────────────────────────────────

cat("\n=== Cluster 统计 ===\n")
print(table(Idents(seu)))

cat("\n=== 分析完成！===\n")
