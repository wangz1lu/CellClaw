"""
Code Generator
==============
Dynamically generates analysis scripts tailored to the user's data
and requested analysis type.

The generated scripts:
  - Use the user's existing conda environment (no new installs)
  - Save all results to a specified output directory
  - Are self-contained and runnable with `python script.py`
  - Include progress logging (visible in /job log)
  - Handle common errors gracefully

Skill KB templates are embedded here as best-practice defaults.
Future versions will load from skills/knowledge_base/.
"""

from __future__ import annotations
import textwrap
from pathlib import PurePosixPath
from typing import Optional


class CodeGenerator:

    # ------------------------------------------------------------------ #
    # Query generation (synchronous, < 60s)
    # ------------------------------------------------------------------ #

    def generate_query(
        self,
        filepath: Optional[str],
        question: str,
        conda_env: Optional[str] = None,
    ) -> str:
        """
        Generate a short Python snippet that answers a specific question
        about an AnnData object.
        """
        if not filepath:
            return self._no_data_snippet()

        # Detect query type from question
        q = question.lower()

        if any(k in q for k in ["多少细胞", "how many cells", "n_obs", "细胞数"]):
            return self._query_n_cells(filepath)

        elif any(k in q for k in ["cluster", "聚类", "群"]) and any(
            k in q for k in ["多少", "分布", "几个"]
        ):
            return self._query_cluster_dist(filepath)

        elif any(k in q for k in ["umi", "count", "深度", "测序深度", "平均umi"]):
            return self._query_umi_stats(filepath)

        elif any(k in q for k in ["基因", "gene", "高变", "hvg"]):
            return self._query_gene_stats(filepath)

        elif any(k in q for k in ["线粒体", "mito", "mt-"]):
            return self._query_mito(filepath)

        else:
            # Generic: dump basic info
            return self._query_basic_info(filepath)

    def _query_n_cells(self, fp: str) -> str:
        return textwrap.dedent(f"""\
            import anndata as ad
            adata = ad.read_h5ad({fp!r}, backed='r')
            print(f"细胞数：{{adata.n_obs:,}}")
            print(f"基因数：{{adata.n_vars:,}}")
        """)

    def _query_cluster_dist(self, fp: str) -> str:
        return textwrap.dedent(f"""\
            import anndata as ad, pandas as pd
            adata = ad.read_h5ad({fp!r}, backed='r')
            cluster_cols = [c for c in adata.obs.columns if 'leiden' in c or 'louvain' in c or 'cluster' in c.lower()]
            if cluster_cols:
                col = cluster_cols[0]
                dist = adata.obs[col].value_counts().sort_index()
                print(f"聚类列：{{col}}")
                print(dist.to_string())
                print(f"\\n共 {{len(dist)}} 个聚类，总计 {{dist.sum():,}} 个细胞")
            else:
                print("未找到聚类结果，obs列：", list(adata.obs.columns))
        """)

    def _query_umi_stats(self, fp: str) -> str:
        return textwrap.dedent(f"""\
            import anndata as ad
            adata = ad.read_h5ad({fp!r}, backed='r')
            if 'total_counts' in adata.obs.columns:
                s = adata.obs['total_counts']
            elif 'n_counts' in adata.obs.columns:
                s = adata.obs['n_counts']
            else:
                import numpy as np
                s = adata.X.sum(axis=1).A1 if hasattr(adata.X, 'A1') else adata.X.sum(axis=1)
            import numpy as np
            print(f"UMI 统计（{len(s):,} 个细胞）：")
            print(f"  平均值：{{np.mean(s):,.1f}}")
            print(f"  中位数：{{np.median(s):,.1f}}")
            print(f"  最小值：{{np.min(s):,.0f}}")
            print(f"  最大值：{{np.max(s):,.0f}}")
        """)

    def _query_mito(self, fp: str) -> str:
        return textwrap.dedent(f"""\
            import anndata as ad, numpy as np
            adata = ad.read_h5ad({fp!r}, backed='r')
            if 'pct_counts_mt' in adata.obs.columns:
                s = adata.obs['pct_counts_mt']
                print(f"线粒体比例统计：")
                print(f"  平均：{{np.mean(s):.2f}}%")
                print(f"  中位数：{{np.median(s):.2f}}%")
                print(f"  >20%：{{(s > 20).sum()}} 个细胞（{{(s>20).mean()*100:.1f}}%）")
                print(f"  >30%：{{(s > 30).sum()}} 个细胞")
            else:
                mt_genes = [g for g in adata.var_names if g.startswith('MT-')]
                print(f"未找到 pct_counts_mt 列，MT- 基因数：{{len(mt_genes)}}")
        """)

    def _query_gene_stats(self, fp: str) -> str:
        return textwrap.dedent(f"""\
            import anndata as ad
            adata = ad.read_h5ad({fp!r}, backed='r')
            if 'n_genes_by_counts' in adata.obs.columns:
                s = adata.obs['n_genes_by_counts']
                import numpy as np
                print(f"每细胞检测基因数：")
                print(f"  平均：{{np.mean(s):,.0f}}")
                print(f"  中位数：{{np.median(s):,.0f}}")
                print(f"  <200基因：{{(s<200).sum()}} 个细胞")
            hvg = adata.var.get('highly_variable')
            if hvg is not None:
                print(f"高变基因（HVG）：{{hvg.sum()}} 个")
            print(f"总基因数：{{adata.n_vars:,}}")
        """)

    def _query_basic_info(self, fp: str) -> str:
        return textwrap.dedent(f"""\
            import anndata as ad, json
            adata = ad.read_h5ad({fp!r}, backed='r')
            print(f"=== 数据概览 ===")
            print(f"细胞数：{{adata.n_obs:,}}")
            print(f"基因数：{{adata.n_vars:,}}")
            print(f"obs列：{{list(adata.obs.columns)}}")
            print(f"obsm键：{{list(adata.obsm.keys())}}")
            print(f"uns键：{{list(adata.uns.keys())}}")
            print(f"基因示例：{{list(adata.var_names[:5])}}")
        """)

    def _no_data_snippet(self) -> str:
        return 'print("请先指定数据文件路径")'

    # ------------------------------------------------------------------ #
    # Analysis script generation (background jobs)
    # ------------------------------------------------------------------ #

    def generate_analysis(
        self,
        filepath: str,
        analysis_type: str,
        file_info: dict,
        result_dir: Optional[str],
        conda_env: Optional[str] = None,
    ) -> str:
        """
        Generate a complete analysis script based on analysis_type.
        Tailored to file_info (e.g. skip PCA if already done).
        """
        out_dir = result_dir or str(PurePosixPath(filepath).parent / "omicsclaw_results")

        if analysis_type == "full":
            return self._script_full_pipeline(filepath, file_info, out_dir)
        elif analysis_type == "qc":
            return self._script_qc(filepath, out_dir)
        elif analysis_type == "cluster":
            return self._script_cluster(filepath, file_info, out_dir)
        elif analysis_type == "annotate":
            return self._script_annotate(filepath, file_info, out_dir)
        elif analysis_type == "deg":
            return self._script_deg(filepath, file_info, out_dir)
        elif analysis_type == "spatial":
            return self._script_spatial(filepath, out_dir)
        elif analysis_type == "batch_integration":
            return self._script_batch_integration(filepath, file_info, out_dir)
        else:
            return self._script_full_pipeline(filepath, file_info, out_dir)

    # ── Best-practice templates (distilled from Nature Methods 2019) ──

    def _script_header(self, out_dir: str) -> str:
        return textwrap.dedent(f"""\
            import scanpy as sc
            import numpy as np
            import pandas as pd
            import matplotlib
            matplotlib.use('Agg')   # non-interactive backend for servers
            import matplotlib.pyplot as plt
            import os, warnings
            warnings.filterwarnings('ignore')

            OUT_DIR = {out_dir!r}
            os.makedirs(OUT_DIR, exist_ok=True)

            sc.settings.verbosity = 2
            sc.settings.figdir = OUT_DIR
            print(f"Results will be saved to: {{OUT_DIR}}")
        """)

    def _script_full_pipeline(self, fp: str, info: dict, out_dir: str) -> str:
        has_umap = "X_umap" in info.get("obsm_keys", [])
        has_cluster = any(
            "leiden" in c or "louvain" in c
            for c in info.get("obs_columns", [])
        )
        steps = ["QC & 预处理", "降维 & 聚类", "Marker基因计算", "可视化出图"]
        steps_str = " → ".join(steps)

        return self._script_header(out_dir) + textwrap.dedent(f"""\

            print("=" * 50)
            print("CellClaw scRNA-seq 完整分析流程")
            print("流程：{steps_str}")
            print("=" * 50)

            # ── 1. 数据加载 ──────────────────────────────────────────
            print("\\n[1/6] 加载数据...")
            adata = sc.read_h5ad({fp!r})
            print(f"  原始数据：{{adata.n_obs:,}} 细胞 × {{adata.n_vars:,}} 基因")

            # ── 2. QC（基于 Luecken & Theis 2019 best practices）─────
            print("\\n[2/6] 质控过滤...")
            adata.var['mt'] = adata.var_names.str.startswith('MT-')
            sc.pp.calculate_qc_metrics(adata, qc_vars=['mt'], percent_top=None, log1p=False, inplace=True)

            # QC plots
            sc.pl.violin(adata, ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'],
                         jitter=0.4, save='_qc_violin.png', show=False)

            # Filter (推荐参数 per Nature Methods 2019)
            sc.pp.filter_cells(adata, min_genes=200)
            sc.pp.filter_genes(adata, min_cells=3)
            adata = adata[adata.obs.pct_counts_mt < 20].copy()
            print(f"  过滤后：{{adata.n_obs:,}} 细胞 × {{adata.n_vars:,}} 基因")

            # ── 3. 预处理 ─────────────────────────────────────────────
            print("\\n[3/6] 归一化与特征选择...")
            sc.pp.normalize_total(adata, target_sum=1e4)
            sc.pp.log1p(adata)
            sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
            print(f"  高变基因：{{adata.var.highly_variable.sum()}} 个")
            adata = adata[:, adata.var.highly_variable].copy()
            sc.pp.scale(adata, max_value=10)

            # ── 4. 降维 & 聚类 ────────────────────────────────────────
            print("\\n[4/6] PCA + UMAP + Leiden 聚类...")
            sc.tl.pca(adata, svd_solver='arpack', n_comps=50)
            sc.pp.neighbors(adata, n_neighbors=15, n_pcs=30)
            sc.tl.umap(adata)
            sc.tl.leiden(adata, resolution=0.5)
            n_clusters = adata.obs['leiden'].nunique()
            print(f"  Leiden 聚类完成：{{n_clusters}} 个聚类")

            # UMAP plot
            sc.pl.umap(adata, color=['leiden'], save='_leiden.png', show=False)

            # ── 5. Marker 基因 ────────────────────────────────────────
            print("\\n[5/6] 计算 Marker 基因（Wilcoxon）...")
            sc.tl.rank_genes_groups(adata, 'leiden', method='wilcoxon')
            sc.pl.rank_genes_groups(adata, n_genes=15, save='_markers.png', show=False)

            # Export top markers
            import pandas as pd
            markers_df = sc.get.rank_genes_groups_df(adata, group=None)
            markers_df.to_csv(os.path.join(OUT_DIR, 'marker_genes.csv'), index=False)

            # ── 6. 保存结果 ───────────────────────────────────────────
            print("\\n[6/6] 保存结果...")
            output_h5ad = os.path.join(OUT_DIR, 'analyzed.h5ad')
            adata.write_h5ad(output_h5ad)

            print("\\n" + "=" * 50)
            print(f"✅ 分析完成！")
            print(f"  细胞数：{{adata.n_obs:,}}")
            print(f"  聚类数：{{n_clusters}}")
            print(f"  结果目录：{{OUT_DIR}}")
            print("=" * 50)
        """)

    def _script_qc(self, fp: str, out_dir: str) -> str:
        return self._script_header(out_dir) + textwrap.dedent(f"""\

            print("CellClaw QC 分析")
            adata = sc.read_h5ad({fp!r})
            print(f"原始数据：{{adata.n_obs:,}} × {{adata.n_vars:,}}")

            adata.var['mt'] = adata.var_names.str.startswith('MT-')
            sc.pp.calculate_qc_metrics(adata, qc_vars=['mt'], percent_top=None, log1p=False, inplace=True)

            sc.pl.violin(adata, ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'],
                         jitter=0.4, save='_qc.png', show=False)
            sc.pl.scatter(adata, x='total_counts', y='pct_counts_mt', save='_mito.png', show=False)
            sc.pl.scatter(adata, x='total_counts', y='n_genes_by_counts', save='_genes.png', show=False)

            # QC report
            report = f\"\"\"QC Report
            ==============================
            Raw: {{adata.n_obs:,}} cells x {{adata.n_vars:,}} genes
            Median UMI: {{adata.obs['total_counts'].median():,.0f}}
            Median genes: {{adata.obs['n_genes_by_counts'].median():,.0f}}
            Median mito%: {{adata.obs['pct_counts_mt'].median():.2f}}%
            Cells >20% mito: {{(adata.obs['pct_counts_mt']>20).sum()}}
            \"\"\"
            with open(os.path.join(OUT_DIR, 'qc_report.txt'), 'w') as f:
                f.write(report)
            print(report)
        """)

    def _script_cluster(self, fp: str, info: dict, out_dir: str) -> str:
        has_pca = "X_pca" in info.get("obsm_keys", [])
        _preprocess_comment = "# PCA 已存在，跳过预处理" if has_pca else "# 执行预处理"
        _preprocess_code = "pass" if has_pca else textwrap.dedent("""
            sc.pp.normalize_total(adata, target_sum=1e4)
            sc.pp.log1p(adata)
            sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
            adata = adata[:, adata.var.highly_variable].copy()
            sc.pp.scale(adata, max_value=10)
            sc.tl.pca(adata, svd_solver='arpack', n_comps=50)
        """).strip()
        return self._script_header(out_dir) + textwrap.dedent(f"""\

            print("CellClaw 聚类分析")
            adata = sc.read_h5ad({fp!r})

            {_preprocess_comment}
            {_preprocess_code}

            sc.pp.neighbors(adata, n_neighbors=15, n_pcs=30)
            sc.tl.umap(adata)
            sc.tl.leiden(adata, resolution=0.5)
            n_clusters = adata.obs['leiden'].nunique()
            print(f"Leiden 聚类：{{n_clusters}} 个聚类")

            sc.pl.umap(adata, color=['leiden'], save='_leiden.png', show=False)
            adata.write_h5ad(os.path.join(OUT_DIR, 'clustered.h5ad'))
            print(f"✅ 完成，结果保存至 {{OUT_DIR}}")
        """)

    def _script_annotate(self, fp: str, info: dict, out_dir: str) -> str:
        return self._script_header(out_dir) + textwrap.dedent(f"""\

            print("CellClaw 细胞类型注释")
            adata = sc.read_h5ad({fp!r})

            cluster_cols = [c for c in adata.obs.columns if 'leiden' in c or 'louvain' in c]
            if not cluster_cols:
                raise ValueError("未找到聚类结果，请先运行聚类分析")
            cluster_key = cluster_cols[0]

            sc.tl.rank_genes_groups(adata, cluster_key, method='wilcoxon')

            # Dotplot of canonical markers
            canonical_markers = ['CD3D', 'CD3E', 'CD4', 'CD8A', 'CD19', 'CD79A',
                                  'GNLY', 'NKG7', 'CD14', 'LYZ', 'FCGR3A', 'MS4A7',
                                  'FCER1A', 'PPBP', 'HBB']
            valid = [g for g in canonical_markers if g in adata.var_names]
            if valid:
                sc.pl.dotplot(adata, valid, groupby=cluster_key,
                              save='_annotation_dotplot.png', show=False)

            sc.pl.rank_genes_groups(adata, n_genes=10, save='_markers.png', show=False)

            # Export marker table
            df = sc.get.rank_genes_groups_df(adata, group=None)
            df.to_csv(os.path.join(OUT_DIR, 'markers_for_annotation.csv'), index=False)
            print(f"✅ Marker 基因已导出，请参考 markers_for_annotation.csv 进行注释")
        """)

    def _script_deg(self, fp: str, info: dict, out_dir: str) -> str:
        return self._script_header(out_dir) + textwrap.dedent(f"""\

            print("CellClaw 差异表达分析")
            adata = sc.read_h5ad({fp!r})

            cluster_cols = [c for c in adata.obs.columns if 'leiden' in c or 'louvain' in c]
            if not cluster_cols:
                raise ValueError("请先完成聚类")
            cluster_key = cluster_cols[0]

            sc.tl.rank_genes_groups(adata, cluster_key, method='wilcoxon')
            sc.pl.rank_genes_groups_heatmap(adata, n_genes=5, save='_deg_heatmap.png', show=False)
            sc.pl.rank_genes_groups_dotplot(adata, n_genes=5, save='_deg_dotplot.png', show=False)

            df = sc.get.rank_genes_groups_df(adata, group=None)
            df.to_csv(os.path.join(OUT_DIR, 'DEG_results.csv'), index=False)
            print(f"✅ DEG 完成，{{len(df)}} 条结果保存至 {{OUT_DIR}}/DEG_results.csv")
        """)

    def _script_spatial(self, fp: str, out_dir: str) -> str:
        return self._script_header(out_dir) + textwrap.dedent(f"""\
            import squidpy as sq

            print("CellClaw 空间转录组分析")
            adata = sc.read_h5ad({fp!r})

            sc.pp.normalize_total(adata, target_sum=1e4)
            sc.pp.log1p(adata)
            sc.pp.highly_variable_genes(adata, flavor='seurat', n_top_genes=2000)
            sc.pp.scale(adata)
            sc.tl.pca(adata)
            sc.pp.neighbors(adata)
            sc.tl.umap(adata)
            sc.tl.leiden(adata, resolution=0.5)

            sq.pl.spatial_scatter(adata, color=['leiden', 'total_counts'],
                                  save=os.path.join(OUT_DIR, 'spatial_clusters.png'), show=False)

            sq.gr.spatial_neighbors(adata)
            sq.gr.spatial_autocorr(adata, mode='moran')
            top_svgs = adata.uns['moranI'].head(10)
            top_svgs.to_csv(os.path.join(OUT_DIR, 'spatially_variable_genes.csv'))
            print(f"✅ 空间分析完成，结果保存至 {{OUT_DIR}}")
        """)

    def _script_batch_integration(self, fp: str, info: dict, out_dir: str) -> str:
        return self._script_header(out_dir) + textwrap.dedent(f"""\
            import harmonypy as hm

            print("CellClaw 批次整合（Harmony）")
            adata = sc.read_h5ad({fp!r})

            batch_cols = [c for c in adata.obs.columns if 'batch' in c.lower() or 'sample' in c.lower()]
            if not batch_cols:
                raise ValueError("未找到 batch/sample 列，请确认数据中有批次信息")
            batch_key = batch_cols[0]
            print(f"批次列：{{batch_key}}，批次数：{{adata.obs[batch_key].nunique()}}")

            sc.pp.normalize_total(adata, target_sum=1e4)
            sc.pp.log1p(adata)
            sc.pp.highly_variable_genes(adata, batch_key=batch_key)
            adata = adata[:, adata.var.highly_variable].copy()
            sc.pp.scale(adata)
            sc.tl.pca(adata)

            ho = hm.run_harmony(adata.obsm['X_pca'], adata.obs, batch_key)
            adata.obsm['X_pca_harmony'] = ho.Z_corr.T

            sc.pp.neighbors(adata, use_rep='X_pca_harmony')
            sc.tl.umap(adata)
            sc.tl.leiden(adata, resolution=0.5)

            sc.pl.umap(adata, color=[batch_key, 'leiden'], save='_harmony.png', show=False)
            adata.write_h5ad(os.path.join(OUT_DIR, 'integrated.h5ad'))
            print(f"✅ 批次整合完成，结果保存至 {{OUT_DIR}}")
        """)
