#!/usr/bin/env python3
# ============================================================
# CellClaw Skill: Standard DimRed & Clustering (Python/Scanpy)
# Template: 01_standard_workflow.py
# ============================================================

import argparse
import scanpy as sc
import pandas as pd
from pathlib import Path

# ── 参数设置 ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='CellClaw: Standard DimRed & Clustering')
parser.add_argument('--input', '-i', default='input.h5ad', help='Input file')
parser.add_argument('--output', '-o', default='.', help='Output directory')
parser.add_argument('--npcs', '-n', type=int, default=50, help='Number of PCs')
parser.add_argument('--resolution', '-r', type=float, default=0.5, help='Cluster resolution')
parser.add_argument('--n_neighbors', type=int, default=15, help='UMAP neighbors')
parser.add_argument('--min_dist', type=float, default=0.3, help='UMAP min_dist')
parser.add_argument('--mt-prefix', default='^MT-', help='Mitochondrial gene pattern')
parser.add_argument('--rb-prefix', default='^RP[SL]', help='Ribosomal gene pattern')
args = parser.parse_args()

print(f"=== CellClaw: Standard DimRed & Clustering (Python) ===")
print(f"输入: {args.input}")
print(f"PCs: {args.npcs}")
print(f"Resolution: {args.resolution}")
print(f"UMAP: n_neighbors={args.n_neighbors}, min_dist={args.min_dist}\n")

output_dir = Path(args.output)
output_dir.mkdir(parents=True, exist_ok=True)

# ── 1. 加载数据 ────────────────────────────────────────────
print("Step 1: 加载数据...")

if args.input.endswith('.h5ad'):
    adata = sc.read_h5ad(args.input)
elif args.input.endswith('.csv'):
    adata = sc.read_csv(args.input)
elif args.input.endswith('.mtx'):
    adata = sc.read_mtx(args.input).T
else:
    raise ValueError(f"不支持的格式: {args.input}")

print(f"  初始细胞数: {adata.n_obs}")
print(f"  基因数: {adata.n_vars}")

# ── 2. QC ──────────────────────────────────────────────────
print("Step 2: 质控...")

# 线粒体基因
adata.var['mt'] = adata.var_names.str.startswith('MT-')
adata.var['rb'] = adata.var_names.str.match(args.rb_prefix)

# 计算 QC 指标
sc.pp.calculate_qc_metrics(adata, qc_vars=['mt', 'rb'], percent_top=None, log1p=False, inplace=True)

# 过滤
sc.pp.filter_cells(adata, min_genes=200)
sc.pp.filter_genes(adata, min_cells=3)

# 过滤高表达线粒体
adata = adata[adata.obs['pct_counts_mt'] < 20, :]

print(f"  QC 后细胞数: {adata.n_obs}")
print(f"  基因数: {adata.n_vars}")

# ── 3. 归一化 ──────────────────────────────────────────────
print("Step 3: 归一化...")

sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

# 保存原始数据
adata.raw = adata

# ── 4. 特征选择 ────────────────────────────────────────────
print("Step 4: 特征选择...")

sc.pp.highly_variable_features(adata, n_top_genes=2000, flavor='seurat_v3')
print(f"  高变基因数: {sum(adata.var.highly_variable)}")

# ── 5. 标准化 ──────────────────────────────────────────────
print("Step 5: 标准化...")

sc.pp.scale(adata, max_value=10)

# ── 6. PCA ─────────────────────────────────────────────────
print("Step 6: PCA 降维...")

sc.tl.pca(adata, n_comps=args.npcs, use_highly_variable=True)

# Elbow plot
sc.pl.pca_variance_ratio(adata, n_pcs=args.npcs, 
                          save=str(output_dir / 'result_elbow_plot.png'),
                          show=False)

# ── 7. UMAP ────────────────────────────────────────────────
print("Step 7: UMAP 降维...")

sc.pp.neighbors(adata, n_neighbors=args.n_neighbors, n_pcs=args.npcs)
sc.tl.umap(adata, min_dist=args.min_dist)

# ── 8. 聚类 ───────────────────────────────────────────────
print("Step 8: 聚类...")

# Leiden 聚类 (推荐)
sc.tl.leiden(adata, resolution=args.resolution, key_added='leiden')

print(f"  Cluster 数: {adata.obs['leiden'].nunique()}")

# 也尝试 Louvain
sc.tl.louvain(adata, resolution=args.resolution, key_added='louvain')
print(f"  Louvain Cluster 数: {adata.obs['louvain'].nunique()}")

# ── 9. 统计 ────────────────────────────────────────────────
print("\n=== Cluster 统计 ===")
print(adata.obs['leiden'].value_counts().sort_index())

# ── 10. 导出 ──────────────────────────────────────────────
print("\nStep 9: 导出结果...")

# AnnData
adata.write(output_dir / 'result_adata_clustered.h5ad')
print(f"  保存: {output_dir / 'result_adata_clustered.h5ad'}")

# CSV
cluster_df = pd.DataFrame({
    'cell_id': adata.obs.index,
    'leiden': adata.obs['leiden'],
    'louvain': adata.obs['louvain'],
    'UMAP_1': adata.obsm['X_umap'][:, 0],
    'UMAP_2': adata.obsm['X_umap'][:, 1]
})
cluster_df.to_csv(output_dir / 'result_cluster_assignments.csv', index=False)
print(f"  保存: {output_dir / 'result_cluster_assignments.csv'}")

# ── 11. 可视化 ─────────────────────────────────────────────
print("Step 10: 生成可视化...")

# UMAP cluster
sc.pl.umap(adata, color=['leiden', 'louvain'], 
            save=str(output_dir / 'result_umap_clusters.png'),
            show=False)

# QC violin
sc.pl.violin(adata, keys=['n_genes', 'n_counts', 'pct_counts_mt'], 
              groupby='leiden', multi_panel=True,
              save=str(output_dir / 'result_qc_violin.png'),
              show=False)

print("\n=== 分析完成！===")
