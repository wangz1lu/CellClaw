#!/usr/bin/env python3
# ============================================================
# CellClaw Skill: Batch Correction (Python/Harmony)
# Template: 01_harmony_batch.py
# ============================================================

import argparse
import scanpy as sc
import pandas as pd
from pathlib import Path
from harmony import harmonize

# ── 参数设置 ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='CellClaw: Batch Correction with Harmony')
parser.add_argument('--input', '-i', default='input.h5ad', help='Input file (.h5ad)')
parser.add_argument('--output', '-o', default='.', help='Output directory')
parser.add_argument('--batch', '-b', default='batch', help='Batch column name')
parser.add_argument('--npcs', '-n', type=int, default=50, help='Number of PCs')
parser.add_argument('--resolution', '-r', type=float, default=0.5, help='Cluster resolution')
args = parser.parse_args()

print(f"=== CellClaw: Batch Correction (Python/Harmony) ===")
print(f"输入: {args.input}")
print(f"批次列: {args.batch}")
print(f"PCs: {args.npcs}")
print(f"Resolution: {args.resolution}\n")

output_dir = Path(args.output)
output_dir.mkdir(parents=True, exist_ok=True)

# ── 1. 加载数据 ────────────────────────────────────────────
print("Step 1: 加载数据...")

adata = sc.read_h5ad(args.input)
print(f"  细胞数: {adata.n_obs}")
print(f"  基因数: {adata.n_vars}")

# ── 2. 检查批次列 ──────────────────────────────────────────
if args.batch not in adata.obs.columns:
    raise ValueError(f"批次列 '{args.batch}' 不存在！可用列: {list(adata.obs.columns)}")

print(f"  批次: {adata.obs[args.batch].unique().tolist()}")
print(f"  各批次细胞数:")
print(adata.obs[args.batch].value_counts())

# ── 3. 预处理 ──────────────────────────────────────────────
print("\nStep 2: 预处理...")

# 确保数据是归一化的
if adata.raw is not None:
    adata_use = adata.raw.to_adata()
else:
    adata_use = adata.copy()

sc.pp.normalize_total(adata_use, target_sum=1e4)
sc.pp.log1p(adata_use)

# 特征选择
sc.pp.highly_variable_features(adata_use, n_top_genes=2000, flavor='seurat_v3')

# 标准化
sc.pp.scale(adata_use, max_value=10)

# PCA
sc.tl.pca(adata_use, n_comps=args.npcs, use_highly_variable=True)

print(f"  PCA 完成")

# ── 4. Harmony 校正 ────────────────────────────────────────
print("\nStep 3: Harmony 批次校正...")

# 获取批次标签
batch_labels = adata_use.obs[args.batch].values

# 运行 Harmony
adata_use.obsm['X_harmony'] = harmonize(
    adata_use.obsm['X_pca'],
    adata_use.obs,
    vars_to_regress=[args.batch],
    max_iter_harmony=10,
    random_state=42
)

print(f"  Harmony 完成")

# ── 5. UMAP + 聚类 ─────────────────────────────────────────
print("\nStep 4: UMAP + 聚类...")

# 用 Harmony 嵌入
sc.pp.neighbors(adata_use, use_rep='X_harmony', n_neighbors=15, n_pcs=args.npcs)
sc.tl.umap(adata_use, min_dist=0.3)

# Leiden 聚类
sc.tl.leiden(adata_use, resolution=args.resolution, key_added='leiden_harmony')

print(f"  Cluster 数: {adata_use.obs['leiden_harmony'].nunique()}")

# ── 6. 统计 ────────────────────────────────────────────────
print("\n=== 结果统计 ===")
print("各批次细胞数:")
print(adata_use.obs[args.batch].value_counts())
print("\n各 cluster 细胞数:")
print(adata_use.obs['leiden_harmony'].value_counts().sort_index())

# ── 7. 导出结果 ────────────────────────────────────────────
print("\nStep 5: 导出结果...")

# 保存 adata
adata_use.write(output_dir / 'result_adata_harmony.h5ad')
print(f"  保存: {output_dir / 'result_adata_harmony.h5ad'}")

# CSV
cluster_df = pd.DataFrame({
    'cell_id': adata_use.obs.index,
    'batch': adata_use.obs[args.batch],
    'cluster': adata_use.obs['leiden_harmony'],
    'UMAP_1': adata_use.obsm['X_umap'][:, 0],
    'UMAP_2': adata_use.obsm['X_umap'][:, 1]
})
cluster_df.to_csv(output_dir / 'result_batch_integration.csv', index=False)
print(f"  保存: {output_dir / 'result_batch_integration.csv'}")

# ── 8. 可视化 ─────────────────────────────────────────────
print("\nStep 6: 生成可视化...")

# 对比：原始 PCA vs Harmony
# 原始 PCA 的聚类（如果存在）
if 'leiden' in adata_use.obs:
    sc.pl.pca(adata_use, color=[args.batch, 'leiden'], 
              save=str(output_dir / 'result_pca_before.png'),
              show=False)

# Harmony 后的聚类
sc.pl.umap(adata_use, color=[args.batch, 'leiden_harmony'],
            save=str(output_dir / 'result_harmony_after.png'),
            show=False)

# 批次对比图
sc.pl.umap(adata_use, color=[args.batch], 
            save=str(output_dir / 'result_batch_umap.png'),
            show=False)

print("\n=== Harmony 批次校正完成！===")
