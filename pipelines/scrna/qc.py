"""
scRNA-seq QC Pipeline
"""

import scanpy as sc
import matplotlib.pyplot as plt
import scrublet as scr
import numpy as np
from pathlib import Path


async def run_qc(session, filepath: str = None, min_genes: int = 200,
                 max_mito_pct: float = 20.0, detect_doublets: bool = True, **kwargs) -> dict:
    """
    Run quality control on scRNA-seq data.

    Steps:
    1. Load data (if filepath provided)
    2. Calculate QC metrics
    3. Filter low-quality cells
    4. Detect doublets (optional)
    5. Generate QC plots
    """
    fig_dir = session.get_figure_dir()
    figures = []
    messages = []

    # Load data
    if filepath:
        messages.append(f"📂 正在加载数据：`{filepath}`...")
        try:
            adata = session.load_adata(filepath)
        except Exception as e:
            return {"text": f"❌ 数据加载失败：{e}", "figures": [], "success": False}
    elif session.adata is not None:
        adata = session.adata
    else:
        return {
            "text": "❌ 请先上传数据文件（.h5ad 或 .h5 格式）或指定文件路径。",
            "figures": [], "success": False
        }

    n_cells_raw = adata.n_obs
    n_genes_raw = adata.n_vars
    messages.append(f"✅ 加载成功：**{n_cells_raw:,} 个细胞** × **{n_genes_raw:,} 个基因**")

    # Calculate QC metrics
    adata.var["mt"] = adata.var_names.str.startswith("MT-")
    sc.pp.calculate_qc_metrics(
        adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True
    )

    # Generate QC violin plot
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    sc.pl.violin(adata, ["n_genes_by_counts", "total_counts", "pct_counts_mt"],
                 jitter=0.4, ax=axes, show=False)
    fig.suptitle("QC Metrics", fontsize=14)
    plt.tight_layout()
    qc_plot = fig_dir / "qc_violin.png"
    fig.savefig(qc_plot, dpi=150, bbox_inches="tight")
    plt.close()
    figures.append(str(qc_plot))

    # Filter cells
    before = adata.n_obs
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=3)
    adata = adata[adata.obs.pct_counts_mt < max_mito_pct].copy()
    after = adata.n_obs
    removed = before - after
    messages.append(
        f"✅ 过滤完成：保留 **{after:,} 个细胞**（移除 {removed:,} 个低质量细胞）\n"
        f"   - 过滤标准：min_genes={min_genes}, max_mito={max_mito_pct}%"
    )

    # Doublet detection
    if detect_doublets and after > 100:
        scrub = scr.Scrublet(adata.X)
        doublet_scores, predicted_doublets = scrub.scrub_doublets(verbose=False)
        adata.obs["doublet_score"] = doublet_scores
        adata.obs["predicted_doublet"] = predicted_doublets
        n_doublets = predicted_doublets.sum()
        adata = adata[~adata.obs["predicted_doublet"]].copy()
        messages.append(f"✅ Doublet 检测：移除 **{n_doublets}** 个潜在 doublet")

    session.adata = adata
    messages.append(f"\n🎉 QC 完成！最终数据集：**{adata.n_obs:,} 个细胞**")

    return {
        "text": "\n".join(messages),
        "figures": figures,
        "success": True
    }
