"""
Cell Type Annotation Pipeline
Marker gene-based annotation for scRNA-seq clusters
"""

import scanpy as sc
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from pathlib import Path


# Canonical marker gene database (Human)
MARKER_DB = {
    "T cell": ["CD3D", "CD3E", "CD3G", "TRAC"],
    "CD4+ T cell": ["CD3D", "CD4", "IL7R"],
    "CD8+ T cell": ["CD3D", "CD8A", "CD8B"],
    "B cell": ["CD19", "CD79A", "CD79B", "MS4A1"],
    "NK cell": ["GNLY", "NKG7", "KLRD1", "NCAM1"],
    "CD14+ Monocyte": ["CD14", "LYZ", "CST3", "FCGR3A"],
    "CD16+ Monocyte": ["FCGR3A", "MS4A7"],
    "Dendritic cell": ["FCER1A", "CST3", "IL3RA", "CLEC4C"],
    "Platelet": ["PPBP", "PF4"],
    "Erythrocyte": ["HBB", "HBA1", "HBA2"],
    "Neutrophil": ["S100A8", "S100A9", "FCGR3B"],
    # Tissue-specific
    "Epithelial": ["EPCAM", "KRT18", "KRT19"],
    "Fibroblast": ["COL1A1", "COL3A1", "DCN", "VIM"],
    "Endothelial": ["PECAM1", "VWF", "CDH5"],
    "Macrophage": ["CD68", "CSF1R", "MRC1"],
    "Mast cell": ["TPSAB1", "TPSB2", "CPA3"],
}


async def run_annotation(session, cluster_key: str = "leiden",
                         species: str = "human", **kwargs) -> dict:
    """
    Annotate cell clusters using marker genes.

    Steps:
    1. Rank genes per cluster (Wilcoxon test)
    2. Score clusters against marker database
    3. Generate dotplot of top markers
    4. Return annotation suggestions
    """
    if session.adata is None:
        return {"text": "❌ 请先运行聚类分析。", "figures": [], "success": False}

    adata = session.adata
    if cluster_key not in adata.obs.columns:
        return {"text": f"❌ 未找到聚类结果列 `{cluster_key}`，请先运行聚类。",
                "figures": [], "success": False}

    fig_dir = session.get_figure_dir()
    figures = []
    messages = ["🔬 **开始细胞类型注释...**"]

    # Rank genes per cluster
    sc.tl.rank_genes_groups(adata, cluster_key, method="wilcoxon")
    messages.append("✅ Wilcoxon 差异基因检验完成")

    # Score against marker database
    sc.tl.score_genes(adata, list(MARKER_DB.values())[0])  # placeholder
    annotation_results = _score_clusters(adata, cluster_key)

    # Generate dotplot of canonical markers
    flat_markers = []
    for markers in MARKER_DB.values():
        flat_markers.extend(markers[:2])  # top 2 per cell type
    flat_markers = [g for g in flat_markers if g in adata.var_names]

    if flat_markers:
        fig = sc.pl.dotplot(adata, flat_markers[:30], groupby=cluster_key,
                            show=False, return_fig=True)
        dotplot_path = fig_dir / "annotation_dotplot.png"
        fig.savefig(dotplot_path, dpi=150, bbox_inches="tight")
        plt.close()
        figures.append(str(dotplot_path))

    # Generate UMAP with annotation suggestions
    adata.obs["cell_type_predicted"] = adata.obs[cluster_key].map(annotation_results)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    sc.pl.umap(adata, color=cluster_key, ax=axes[0], show=False, title="Clusters")
    sc.pl.umap(adata, color="cell_type_predicted", ax=axes[1], show=False, title="Predicted Cell Types")
    plt.tight_layout()
    umap_annot = fig_dir / "umap_annotated.png"
    fig.savefig(umap_annot, dpi=150, bbox_inches="tight")
    plt.close()
    figures.append(str(umap_annot))

    # Format annotation table
    messages.append("\n📋 **细胞类型预测结果：**")
    for cluster, cell_type in sorted(annotation_results.items()):
        n_cells = (adata.obs[cluster_key] == cluster).sum()
        messages.append(f"  - Cluster **{cluster}** ({n_cells:,} cells) → **{cell_type}**")

    session.adata = adata
    messages.append("\n💡 这是基于 marker gene 的预测结果，建议结合领域知识进行最终确认。")

    return {"text": "\n".join(messages), "figures": figures, "success": True}


def _score_clusters(adata, cluster_key: str) -> dict:
    """Score each cluster against the marker database."""
    clusters = adata.obs[cluster_key].unique()
    annotation = {}

    for cluster in clusters:
        cluster_cells = adata[adata.obs[cluster_key] == cluster]
        best_type = "Unknown"
        best_score = 0

        for cell_type, markers in MARKER_DB.items():
            present = [m for m in markers if m in adata.var_names]
            if not present:
                continue
            # Mean expression of marker genes in this cluster
            expr = cluster_cells[:, present].X
            if hasattr(expr, "toarray"):
                expr = expr.toarray()
            score = float(np.mean(expr))
            if score > best_score:
                best_score = score
                best_type = cell_type

        annotation[cluster] = best_type

    return annotation
