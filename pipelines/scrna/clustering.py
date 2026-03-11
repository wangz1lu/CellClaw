"""
scRNA-seq Clustering Pipeline
Normalization → HVG → PCA → (Harmony) → KNN → UMAP → Leiden
"""

import scanpy as sc
import matplotlib.pyplot as plt
from pathlib import Path


async def run_clustering(session, resolution: float = 0.5, n_pcs: int = 30,
                         batch_key: str = None, **kwargs) -> dict:
    """
    Run dimensionality reduction and clustering.

    Steps:
    1. Normalization (normalize_total + log1p)
    2. Highly variable genes selection
    3. PCA
    4. Batch correction via Harmony (if batch_key provided)
    5. KNN graph construction
    6. UMAP
    7. Leiden clustering
    """
    if session.adata is None:
        return {"text": "❌ 请先运行 QC 或加载数据。", "figures": [], "success": False}

    adata = session.adata
    fig_dir = session.get_figure_dir()
    figures = []
    messages = ["🔬 **开始聚类分析...**"]

    # Normalization
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    messages.append("✅ 归一化完成（normalize_total + log1p）")

    # HVG
    sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
    n_hvg = adata.var.highly_variable.sum()
    adata = adata[:, adata.var.highly_variable].copy()
    messages.append(f"✅ 高变基因筛选：**{n_hvg}** 个 HVG")

    # Scale
    sc.pp.scale(adata, max_value=10)

    # PCA
    sc.tl.pca(adata, svd_solver="arpack", n_comps=50)
    messages.append(f"✅ PCA 完成（50 PCs）")

    # Batch correction (Harmony)
    if batch_key and batch_key in adata.obs.columns:
        import harmonypy as hm
        ho = hm.run_harmony(adata.obsm["X_pca"], adata.obs, batch_key)
        adata.obsm["X_pca_harmony"] = ho.Z_corr.T
        use_rep = "X_pca_harmony"
        messages.append(f"✅ Harmony 批次校正完成（batch_key={batch_key}）")
    else:
        use_rep = "X_pca"

    # Neighbors
    sc.pp.neighbors(adata, n_neighbors=15, n_pcs=n_pcs, use_rep=use_rep)

    # UMAP
    sc.tl.umap(adata)
    messages.append("✅ UMAP 计算完成")

    # Leiden clustering
    sc.tl.leiden(adata, resolution=resolution)
    n_clusters = adata.obs["leiden"].nunique()
    messages.append(f"✅ Leiden 聚类完成：**{n_clusters} 个聚类**（resolution={resolution}）")

    # Plot UMAP
    fig, ax = plt.subplots(figsize=(8, 6))
    sc.pl.umap(adata, color="leiden", ax=ax, show=False,
               title=f"UMAP Clustering (resolution={resolution})")
    plt.tight_layout()
    umap_plot = fig_dir / "umap_leiden.png"
    fig.savefig(umap_plot, dpi=150, bbox_inches="tight")
    plt.close()
    figures.append(str(umap_plot))

    session.adata = adata
    messages.append(f"\n🎉 聚类完成！共识别 **{n_clusters}** 个细胞群落。")

    return {"text": "\n".join(messages), "figures": figures, "success": True}
