#!/usr/bin/env Rscript
# ============================================================
# OmicsClaw Skill: DEG Analysis
# Template: 01_basic_deg.R
# ============================================================

# ── 0. 参数设置 ────────────────────────────────────────────────

args <- commandArgs(trailingOnly = TRUE)
input_file  <- args[1] %||% "input.rds"
output_dir  <- args[2] %||% "."
ident_col   <- args[3] %||% "seurat_clusters"   # 分组列
group1      <- args[4] %||% "1"                  # 比较组 1
group2      <- args[5] %||% "0"                  # 比较组 2（NULL = 与其他所有）
method      <- args[6] %||% "wilcox"             # wilcox / mast / t / presto

cat("=== OmicsClaw: DEG Analysis ===\n")
cat("输入:", input_file, "\n")
cat("分组列:", ident_col, "\n")
cat("比较:", group1, "vs", group2, "\n")
cat("方法:", method, "\n\n")

`%||%` <- function(x, y) if (is.null(x)) y else x

# ── 1. 加载库 ──────────────────────────────────────────────────

suppressPackageStartupMessages({
    library(Seurat)
    library(dplyr)
})

# ── 2. 数据加载 ────────────────────────────────────────────────

cat("Step 1: 加载数据...\n")
seu <- readRDS(input_file)
cat("  维度:", dim(seu), "\n")
cat("  Cluster 数:", length(unique(seu[[ident_col]])), "\n")

# 设置 identity
Idents(seu) <- ident_col

# ── 3. 差异分析 ────────────────────────────────────────────────

cat("Step 2: 运行 DEG 分析...\n")
deg <- FindMarkers(
    seu,
    ident.1 = group1,
    ident.2 = if (group2 == "NULL") NULL else group2,
    test.use = method,
    min.pct = 0.1,
    logfc.threshold = 0.25,
    only.pos = FALSE,
    return.thresh = 0.05
)

cat("  找到", nrow(deg), "个差异基因 (p_adj < 0.05)\n")
cat("  上调:", sum(deg$avg_log2FC > 0), "\n")
cat("  下调:", sum(deg$avg_log2FC < 0), "\n")

# 添加基因名列
deg$gene <- rownames(deg)

# ── 4. 结果导出 ────────────────────────────────────────────────

cat("Step 3: 导出结果...\n")

# 完整结果 CSV
csv_file <- file.path(output_dir, "result_deg_full.csv")
write.csv(deg, csv_file, row.names = TRUE)
cat("  保存:", csv_file, "\n")

# 显著 DEG（按 FC 排序）
sig_deg <- deg[deg$p_val_adj < 0.05 & abs(deg$avg_log2FC) > 0.5, ]
sig_deg <- sig_deg[order(sig_deg$avg_log2FC, decreasing = TRUE), ]
sig_file <- file.path(output_dir, "result_deg_significant.csv")
write.csv(sig_deg, sig_file, row.names = TRUE)
cat("  保存:", sig_file, "\n")

# Top 基因
top_n <- 50
top_up <- head(sig_deg[sig_deg$avg_log2FC > 0, ], top_n)
top_down <- head(sig_deg[sig_deg$avg_log2FC < 0, ], top_n)
top_file <- file.path(output_dir, "result_deg_top50.csv")
write.csv(rbind(top_up, top_down), top_file, row.names = TRUE)
cat("  保存:", top_file, "\n")

# ── 5. 可视化 ──────────────────────────────────────────────────

cat("Step 4: 生成可视化...\n")

# 热图（Top 20 基因）
top20 <- head(rownames(sig_deg), 20)
if (length(top20) >= 5) {
    hmap_file <- file.path(output_dir, "result_deg_heatmap.png")
    png(hmap_file, width = 12, height = 10, units = "in", res = 300)
    print(DoHeatmap(seu, features = top20, group.by = ident_col))
    dev.off()
    cat("  保存:", hmap_file, "\n")
}

# 小提琴图（Top 5 基因）
top5 <- head(rownames(sig_deg), 5)
if (length(top5) >= 1) {
    vln_file <- file.path(output_dir, "result_deg_violin.png")
    png(vln_file, width = 15, height = 5, units = "in", res = 300)
    print(VlnPlot(seu, features = top5, group.by = ident_col, ncol = 5))
    dev.off()
    cat("  保存:", vln_file, "\n")
}

cat("\n=== DEG 分析完成！===\n")
