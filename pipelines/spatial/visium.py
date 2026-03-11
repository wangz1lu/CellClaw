"""
Spatial Transcriptomics - 10x Visium Pipeline
"""

import squidpy as sq
import scanpy as sc
import matplotlib.pyplot as plt
from pathlib import Path


async def load_visium(session, path: str = None, **kwargs) -> dict:
    """Load and preprocess 10x Visium spatial transcriptomics data."""
    if not path:
        return {"text": "❌ 请提供 Visium 数据目录路径。", "figures": [], "success": False}

    fig_dir = session.get_figure_dir()
    figures = []
    messages = [f"🔬 **正在加载 Visium 数据：`{path}`**"]

    try:
        adata = sc.read_visium(path)
    except Exception as e:
        return {"text": f"❌ Visium 数据加载失败：{e}", "figures": [], "success": False}

    n_spots = adata.n_obs
    n_genes = adata.n_vars
    messages.append(f"✅ 加载成功：**{n_spots:,} spots** × **{n_genes:,} 基因**")

    # Basic QC
    adata.var["mt"] = adata.var_names.str.startswith("MT-")
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], inplace=True)

    # Spatial scatter plot (total counts)
    fig, ax = plt.subplots(figsize=(8, 8))
    sq.pl.spatial_scatter(adata, color="total_counts", ax=ax, show=False)
    plt.tight_layout()
    spatial_qc = fig_dir / "spatial_total_counts.png"
    fig.savefig(spatial_qc, dpi=150, bbox_inches="tight")
    plt.close()
    figures.append(str(spatial_qc))

    session.adata = adata
    messages.append("\n✅ Visium 数据已加载，可以开始空间分析。\n"
                    "💡 尝试：`show spatial expression of <gene>`")

    return {"text": "\n".join(messages), "figures": figures, "success": True}
