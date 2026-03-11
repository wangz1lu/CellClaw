"""
Differential Expression Analysis Pipeline
"""

import scanpy as sc
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path


async def run_deg(session, group1: str = None, group2: str = None,
                  cluster_id: int = None, cluster_key: str = "leiden",
                  n_top_genes: int = 20, **kwargs) -> dict:
    """
    Run differential expression analysis.
    """
    if session.adata is None:
        return {"text": "❌ 请先加载数据并完成聚类。", "figures": [], "success": False}

    adata = session.adata
    fig_dir = session.get_figure_dir()
    figures = []
    messages = ["🔬 **开始差异表达分析...**"]

    if cluster_id is not None:
        # Marker genes for specific cluster
        sc.tl.rank_genes_groups(adata, cluster_key, method="wilcoxon",
                                groups=[str(cluster_id)], reference="rest")
        title = f"Cluster {cluster_id} vs Rest"
    elif group1 and group2:
        # Compare two conditions
        sc.tl.rank_genes_groups(adata, cluster_key, method="wilcoxon",
                                groups=[group1], reference=group2)
        title = f"{group1} vs {group2}"
    else:
        # All clusters vs rest
        sc.tl.rank_genes_groups(adata, cluster_key, method="wilcoxon")
        title = "All Clusters (vs Rest)"

    messages.append(f"✅ Wilcoxon 检验完成：{title}")

    # Plot top marker genes
    fig = sc.pl.rank_genes_groups(adata, n_genes=n_top_genes, show=False, return_fig=True)
    deg_plot = fig_dir / "deg_top_genes.png"
    fig.savefig(deg_plot, dpi=150, bbox_inches="tight")
    plt.close()
    figures.append(str(deg_plot))

    # Heatmap
    sc.pl.rank_genes_groups_heatmap(adata, n_genes=5, show=False)
    heatmap_plot = fig_dir / "deg_heatmap.png"
    plt.savefig(heatmap_plot, dpi=150, bbox_inches="tight")
    plt.close()
    figures.append(str(heatmap_plot))

    # Export top genes as table
    result = sc.get.rank_genes_groups_df(adata, group=None)
    top_genes = result.nlargest(10, "scores")
    messages.append(f"\n📋 **Top 10 差异基因：**\n```\n{top_genes[['names','scores','pvals_adj']].to_string(index=False)}\n```")

    return {"text": "\n".join(messages), "figures": figures, "success": True}
