#!/usr/bin/env Rscript
# ============================================================
# OmicsClaw Skill: Batch Correction with Harmony
# Template: 01_harmony_integration.R
# ============================================================

args <- commandArgs(trailingOnly = TRUE)
input_files <- unlist(strsplit(args[1] %||% "sample1.rds,sample2.rds", ","))
output_dir  <- args[2] %||% "."
batch_names <- unlist(strsplit(args[3] %||% paste0("batch", 1:length(input_files)), ","))
theta       <- as.numeric(args[4] %||% "2")
resolution  <- as.numeric(args[5] %||% "0.5")

cat("=== OmicsClaw: Batch Correction with Harmony ===\n")
cat("输入文件:", paste(input_files, collapse = ", "), "\n")
cat("批次名称:", paste(batch_names, collapse = ", "), "\n")
cat("Theta:", theta, "\n")
cat("Resolution:", resolution, "\n\n")

`%||%` <- function(x, y) if (is.null(x)) y else x

# ── 1. 加载库 ──────────────────────────────────────────────────

suppressPackageStartupMessages({
    library(Seurat)
    library(harmony)
    library(ggplot2)
    library(patchwork)
})

# ── 2. 合并数据 ────────────────────────────────────────────────

cat("Step 1: 加载并合并样本...\n")

# 读取所有样本
seu.list <- lapply(input_files, readRDS)

# 合并
seu <- seu.list[[1]]
if (length(seu.list) > 1) {
    for (i in 2:length(seu.list)) {
        seu <- merge(seu, seu.list[[i]], add.cell.ids = c(batch_names[1:(i-1)], batch_names[i]))
    }
} else {
    # 单一文件，按细胞数分割
    n_cells <- ncol(seu)
    seu$batch <- sample(batch_names, n_cells, replace = TRUE)
}

# 确保 batch 列存在
if (!"batch" %in% colnames(seu@meta.data)) {
    seu$batch <- batch_names[1]
}

cat("  总细胞数:", ncol(seu), "\n")
cat("  批次:", paste(unique(seu$batch), collapse = ", "), "\n")

# ── 3. 预处理 ──────────────────────────────────────────────────

cat("Step 2: 预处理（归一化 → 特征选择 → 标准化 → PCA）...\n")

seu <- NormalizeData(seu, normalization.method = "LogNormalize", scale.factor = 10000)
seu <- FindVariableFeatures(seu, selection.method = "vst", nfeatures = 2000)

all.genes <- rownames(seu)
seu <- ScaleData(seu, features = all.genes)

seu <- RunPCA(seu, npcs = 50, verbose = FALSE)
cat("  PCA 完成\n")

# ── 4. Harmony 校正 ───────────────────────────────────────────

cat("Step 3: Harmony 批次校正...\n")

seu <- RunHarmony(
    seu,
    group.by.vars = "batch",
    dims.use = 1:30,
    theta = theta,
    lambda = 1,
    sigma = 0.1,
    nclust = 50,
    tau = 0,
    max.iter.cluster = 20,
    method = "equal",
    verbose = FALSE
)

cat("  Harmony 完成\n")

# ── 5. UMAP + 聚类 ────────────────────────────────────────────

cat("Step 4: UMAP + 聚类...\n")

seu <- RunUMAP(seu, reduction = "harmony", dims = 1:30, n.neighbors = 30, min.dist = 0.3)
seu <- FindNeighbors(seu, reduction = "harmony", dims = 1:30)
seu <- FindClusters(seu, resolution = resolution, algorithm = 1)

cat("  Cluster 数:", length(unique(Idents(seu))), "\n")

# ── 6. 统计 ────────────────────────────────────────────────────

cat("\n=== 结果统计 ===\n")
cat("各批次细胞数:\n")
print(table(seu$batch))

cat("\n各 cluster 细胞数:\n")
print(table(Idents(seu)))

# ── 7. 导出 ──────────────────────────────────────────────────

cat("\nStep 5: 导出结果...\n")

# RDS
saveRDS(seu, file.path(output_dir, "result_seurat_harmony.rds"))

# CSV
cluster_df <- data.frame(
    cell_id = colnames(seu),
    batch = seu$batch,
    cluster = Idents(seu),
    UMAP_1 = seu@reductions$umap@cell.embeddings[,1],
    UMAP_2 = seu@reductions$umap@cell.embeddings[,2]
)
write.csv(cluster_df, file.path(output_dir, "result_batch_integration.csv"), row.names = FALSE)

# ── 8. 可视化 ──────────────────────────────────────────────────

cat("Step 6: 生成可视化...\n")

# 批次对比（PCA vs Harmony）
p1 <- DimPlot(seu, reduction = "pca", group.by = "batch", pt.size = 0.1) + ggtitle("Before Harmony (PCA)")
p2 <- DimPlot(seu, reduction = "umap", group.by = "batch", pt.size = 0.1) + ggtitle("After Harmony (UMAP)")
p3 <- DimPlot(seu, reduction = "umap", group.by = "seurat_clusters", label = TRUE) + ggtitle("Clusters")

ggsave(file.path(output_dir, "result_batch_comparison.png"), 
       p1 + p2, width = 14, height = 6, dpi = 300)

ggsave(file.path(output_dir, "result_harmony_clusters.png"), 
       p3, width = 10, height = 8, dpi = 300)

# 按批次的 marker 表达
# 选择一些 marker
markers <- c("CD3D", "CD4", "CD8A", "CD79A", "MS4A1", "CD14", "NKG7")
markers <- markers[markers %in% rownames(seu)]

if (length(markers) > 0) {
    p4 <- FeaturePlot(seu, features = markers, reduction = "umap", ncol = min(4, length(markers)))
    ggsave(file.path(output_dir, "result_batch_markers.png"), 
           p4, width = min(16, 4 * length(markers)), height = 4 * ceiling(length(markers)/4), dpi = 150)
}

cat("\n=== Harmony 批次校正完成！===\n")
