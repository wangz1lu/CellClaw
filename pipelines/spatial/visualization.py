"""
Spatial Visualization Pipeline
"""

import squidpy as sq
import scanpy as sc
import matplotlib.pyplot as plt
from pathlib import Path


async def spatial_plot(session, gene: str = None, color: str = None, **kwargs) -> dict:
    """Generate spatial gene expression visualization."""
    if session.adata is None:
        return {"text": "❌ 请先加载空间转录组数据。", "figures": [], "success": False}

    adata = session.adata
    fig_dir = session.get_figure_dir()
    target = gene or color

    if target and target not in adata.var_names and target not in adata.obs.columns:
        return {
            "text": f"❌ 未找到基因或注释列 `{target}`。\n"
                    f"请检查基因名是否正确（区分大小写）。",
            "figures": [], "success": False
        }

    fig, ax = plt.subplots(figsize=(8, 8))
    sq.pl.spatial_scatter(adata, color=target, ax=ax, show=False,
                          title=f"Spatial Expression: {target}")
    plt.tight_layout()

    plot_path = fig_dir / f"spatial_{target}.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()

    return {
        "text": f"📊 **{target}** 的空间表达图已生成。",
        "figures": [str(plot_path)],
        "success": True
    }
