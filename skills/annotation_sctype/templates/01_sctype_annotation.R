#!/usr/bin/env Rscript
# ============================================================
# OmicsClaw Skill: Cell Type Annotation
# Template: 01_sctype_annotation.R
# ============================================================

args <- commandArgs(trailingOnly = TRUE)
input_file  <- args[1] %||% "input.rds"
output_dir  <- args[2] %||% "."
method      <- args[3] %||% "sctype"    # sctype / singler

cat("=== OmicsClaw: Cell Type Annotation ===\n")
cat("输入:", input_file, "\n")
cat("方法:", method, "\n\n")

`%||%` <- function(x, y) if (is.null(x)) y else x

# ── 1. 加载库 ──────────────────────────────────────────────────

suppressPackageStartupMessages({
    library(Seurat)
    library(dplyr)
})

# ── 2. 加载数据 ────────────────────────────────────────────────

cat("Step 1: 加载数据...\n")
seu <- readRDS(input_file)
cat("  细胞数:", ncol(seu), "\n")
cat("  Cluster 数:", length(unique(Idents(seu))), "\n")

# ── 3. 定义 Marker ────────────────────────────────────────────

cat("Step 2: 定义细胞类型 Marker...\n")

gs_list <- list(
    # T cells
    "CD4+ T" = c("CD3D", "CD3E", "CD4", "IL7R"),
    "CD8+ T" = c("CD3D", "CD3E", "CD8A", "GZMA"),
    "NK" = c("NKG7", "GNLY", "KLRD1", "GZMB"),
    
    # B cells
    "B cells" = c("CD79A", "CD79B", "MS4A1", "CD19"),
    "Plasma" = c("IGJ", "XBP1", "MZB1"),
    
    # Myeloid
    "Monocyte" = c("CD14", "FCGR3A", "LYZ", "S100A9"),
    "Macrophage" = c("CD163", "MS4A4A", "CX3CR1", "MARCO"),
    "DC" = c("CD1C", "FCER1A", "CST3", "CLEC9A"),
    "Mast" = c("TPSAB1", "TPSB2", "MS4A2", "HDC"),
    
    # Other
    "Proliferating" = c("MKI67", "TOP2A", "PCNA"),
    "Platelet" = c("PPBP", "PF4", "SELPLG")
)

# ── 4. 尝试加载 scType ────────────────────────────────────────

annotation_result <- NULL

if (method == "sctype") {
    cat("Step 3: 运行 scType 注释...\n")
    tryCatch({
        library(scType)
        
        expr <- GetAssayData(seu, slot = "data")
        
        # 运行 scType
        result <- scType(expression_matrix = expr, gs_list = gs_list, species = "Human")
        
        annotation_result <- result$cell_type
        names(annotation_result) <- colnames(seu)
        
        seu$celltype_sctype <- annotation_result
        cat("  scType 完成！\n")
    }, error = function(e) {
        cat("  scType 加载失败:", conditionMessage(e), "\n")
        cat("  回退到 Manual 注释...\n")
        method <- "manual"
    })
}

# ── 5. Manual 注释 ────────────────────────────────────────────

if (method == "manual" || is.null(annotation_result)) {
    cat("Step 3: 运行 Manual 注释...\n")
    
    # 先找 marker
    markers <- FindAllMarkers(seu, only.pos = TRUE, logfc.threshold = 0.5, min.pct = 0.25)
    top10 <- markers %>% group_by(cluster) %>% top_n(10, avg_log2FC)
    
    # 简单规则注释（可根据实际情况修改）
    cluster_annot <- character()
    
    for (cl in unique(Idents(seu))) {
        cl_markers <- markers[markers$cluster == cl, ]
        top_genes <- tolower(head(cl_markers$gene, 20))
        
        # 简单规则匹配
        if (any(c("cd4", "il7r") %in% top_genes)) {
            cluster_annot[as.character(cl)] <- "CD4+ T"
        } else if (any(c("cd8a", "cd8b", "gzm") %in% top_genes)) {
            cluster_annot[as.character(cl)] <- "CD8+ T"
        } else if (any(c("cd79", "ms4a1", "cd19") %in% top_genes)) {
            cluster_annot[as.character(cl)] <- "B cells"
        } else if (any(c("cd14", "fcgr3a", "lyz") %in% top_genes)) {
            cluster_annot[as.character(cl)] <- "Monocyte"
        } else if (any(c("cd163", "cx3cr1", "ms4a4a") %in% top_genes)) {
            cluster_annot[as.character(cl)] <- "Macrophage"
        } else if (any(c("nkg7", "gnly", "klrd1") %in% top_genes)) {
            cluster_annot[as.character(cl)] <- "NK"
        } else if (any(c("mki67", "top2a", "pcna") %in% top_genes)) {
            cluster_annot[as.character(cl)] <- "Proliferating"
        } else {
            cluster_annot[as.character(cl)] <- paste0("Unknown_", cl)
        }
    }
    
    seu$celltype_manual <- unname(cluster_annot[as.character(Idents(seu))])
    cat("  Manual 注释完成！\n")
}

# ── 6. 统计 ──────────────────────────────────────────────────

cat("\n=== 注释结果统计 ===\n")
if (!is.null(seu$celltype_sctype)) {
    print(table(seu$celltype_sctype))
} else {
    print(table(seu$celltype_manual))
}

# ── 7. 导出 ──────────────────────────────────────────────────

cat("Step 4: 导出结果...\n")

# CSV
annotation_df <- data.frame(
    cell_id = colnames(seu),
    cluster = Idents(seu),
    celltype = seu$celltype_sctype %||% seu$celltype_manual,
    UMAP_1 = seu@reductions$umap@cell.embeddings[,1],
    UMAP_2 = seu@reductions$umap@cell.embeddings[,2]
)
write.csv(annotation_df, file.path(output_dir, "result_celltype.csv"), row.names = FALSE)

# RDS
saveRDS(seu, file.path(output_dir, "result_seurat_annotated.rds"))

# ── 8. 可视化 ──────────────────────────────────────────────────

cat("Step 5: 生成可视化...\n")

celltype_col <- if (!is.null(seu$celltype_sctype)) "celltype_sctype" else "celltype_manual"

# UMAP
p1 <- DimPlot(seu, reduction = "umap", group.by = celltype_col, label = TRUE, repel = TRUE) +
    ggtitle("Cell Type Annotation")
ggsave(file.path(output_dir, "result_celltype_umap.png"), p1, width = 12, height = 8, dpi = 300)

# Marker 热图
marker_genes <- c("CD3D", "CD4", "CD8A", "CD79A", "MS4A1", "CD14", "CD163", "NKG7", "MKI67")
marker_genes <- marker_genes[marker_genes %in% rownames(seu)]
if (length(marker_genes) >= 5) {
    p2 <- DoHeatmap(seu, features = marker_genes, group.by = celltype_col)
    ggsave(file.path(output_dir, "result_marker_heatmap.png"), p2, width = 12, height = 8, dpi = 300)
}

cat("\n=== 注释完成！===\n")
