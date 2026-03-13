#!/usr/bin/env Rscript
# ============================================================
# OmicsClaw Skill: GSEA Enrichment Analysis
# Template: 01_basic_gsea.R
# ============================================================

args <- commandArgs(trailingOnly = TRUE)
deg_file   <- args[1] %||% "result_deg_significant.csv"
output_dir  <- args[2] %||% "."
species    <- args[3] %||% "human"       # human / mouse
method     <- args[4] %||% "ora"         # ora / gsea

cat("=== OmicsClaw: GSEA Enrichment ===\n")
cat("输入:", deg_file, "\n")
cat("物种:", species, "\n")
cat("方法:", method, "\n\n")

`%||%` <- function(x, y) if (is.null(x)) y else x

# ── 1. 加载库 ──────────────────────────────────────────────────

suppressPackageStartupMessages({
    library(clusterProfiler)
    library(DOSE)
    library(enrichplot)
    library(dplyr)
    if (species == "human") {
        library(org.Hs.eg.db)
    } else {
        library(org.Mm.eg.db)
    }
})

org_db <- if (species == "human") org.Hs.eg.db else org.Mm.eg.db
kegg_organism <- if (species == "human") "hsa" else "mmu"

# ── 2. 加载 DEG ────────────────────────────────────────────────

cat("Step 1: 加载差异基因...\n")
deg <- read.csv(deg_file, row.names = 1)
cat("  DEG 数量:", nrow(deg), "\n")

# ── 3. ID 转换 ──────────────────────────────────────────────────

cat("Step 2: 转换基因 ID (SYMBOL → ENTREZ)...\n")
gene_symbols <- rownames(deg)
gene_df <- bitr(gene_symbols, fromType = "SYMBOL", toType = "ENTREZID", 
                OrgDb = org_db, drop = FALSE)
gene_entrez <- unique(na.omit(gene_df$ENTREZID))
cat("  转换成功:", length(gene_entrez), "个\n")

# ── 4. GO 富集 ──────────────────────────────────────────────────

cat("Step 3: GO 富集分析...\n")

# BP
go_bp <- enrichGO(
    gene = gene_entrez,
    OrgDb = org_db,
    ont = "BP",
    pAdjustMethod = "BH",
    pvalueCutoff = 0.05,
    qvalueCutoff = 0.05,
    readable = TRUE
)

# MF
go_mf <- enrichGO(
    gene = gene_entrez,
    OrgDb = org_db,
    ont = "MF",
    pAdjustMethod = "BH",
    pvalueCutoff = 0.05,
    readable = TRUE
)

# CC
go_cc <- enrichGO(
    gene = gene_entrez,
    OrgDb = org_db,
    ont = "CC",
    pAdjustMethod = "BH",
    pvalueCutoff = 0.05,
    readable = TRUE
)

cat("  GO-BP:", nrow(go_bp), "个富集\n")
cat("  GO-MF:", nrow(go_mf), "个富集\n")
cat("  GO-CC:", nrow(go_cc), "个富集\n")

# ── 5. KEGG 富集 ────────────────────────────────────────────────

cat("Step 4: KEGG 富集分析...\n")

kegg <- enrichKEGG(
    gene = gene_entrez,
    organism = kegg_organism,
    pAdjustMethod = "BH",
    pvalueCutoff = 0.05
)

cat("  KEGG:", nrow(kegg), "个富集\n")

# ── 6. 导出结果 ────────────────────────────────────────────────

cat("Step 5: 导出结果...\n")

# CSV
if (nrow(go_bp) > 0) {
    write.csv(as.data.frame(go_bp), 
              file.path(output_dir, "result_go_bp.csv"), row.names = FALSE)
}
if (nrow(kegg) > 0) {
    write.csv(as.data.frame(kegg), 
              file.path(output_dir, "result_kegg.csv"), row.names = FALSE)
}

# ── 7. 可视化 ──────────────────────────────────────────────────

cat("Step 6: 生成可视化...\n")

# GO dotplot
if (nrow(go_bp) > 0) {
    png(file.path(output_dir, "result_go_dotplot.png"), 
        width = 12, height = 10, units = "in", res = 300)
    print(dotplot(go_bp, showCategory = 20) + ggtitle("GO BP Enrichment"))
    dev.off()
}

# KEGG dotplot
if (nrow(kegg) > 0) {
    png(file.path(output_dir, "result_kegg_dotplot.png"), 
        width = 12, height = 10, units = "in", res = 300)
    print(dotplot(kegg, showCategory = 20) + ggtitle("KEGG Pathway Enrichment"))
    dev.off()
}

# 网络图
if (nrow(go_bp) > 0) {
    png(file.path(output_dir, "result_go_network.png"), 
        width = 14, height = 12, units = "in", res = 300)
    print(emapplot(go_bp, showCategory = 30))
    dev.off()
}

cat("\n=== 富集分析完成！===\n")
