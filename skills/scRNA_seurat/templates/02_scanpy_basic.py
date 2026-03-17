#!/usr/bin/env python3
# ==============================================================================
# scRNA-seq Analysis using Scanpy
# ==============================================================================

import scanpy as sc
import argparse
import warnings
warnings.filterwarnings('ignore')

# === Parse arguments ===
parser = argparse.ArgumentParser(description='scRNA-seq Analysis using Scanpy')
parser.add_argument('input_path', help='Path to input file (10X or h5ad)')
parser.add_argument('--project', default='scRNA', help='Project name')
parser.add_argument('--min_cells', type=int, default=3, help='Min cells per gene')
parser.add_argument('--min_genes', type=int, default=200, help='Min genes per cell')
parser.add_argument('--mt_percent', type=float, default=5, help='Max mitochondrial percent')
parser.add_argument('--n_neighbors', type=int, default=15, help='Number of neighbors')
parser.add_argument('--npcs', type=int, default=30, help='Number of PCs')
parser.add_argument('--resolution', type=float, default=0.8, help='Clustering resolution')
parser.add_argument('--output', default='result_scanpy.h5ad', help='Output file')
args = parser.parse_args()

print("=" * 40)
print("  scRNA-seq Scanpy Analysis")
print("=" * 40)
print(f"Input: {args.input_path}")
print(f"Project: {args.project}")
print(f"Resolution: {args.resolution}")
print("=" * 40)

# === 1. Load Data ===
print("\n[1/8] Loading data...")
if args.input_path.endswith('.h5'):
    adata = sc.read_10x_h5(args.input_path)
elif args.input_path.endswith('.h5ad'):
    adata = sc.read_h5ad(args.input_path)
else:
    adata = sc.read_10x_mtx(args.input_path)

adata.var_names_make_unique()
print(f"  Cells: {adata.n_obs}, Genes: {adata.n_vars}")

# === 2. QC ===
print("\n[2/08] Quality control...")
# Mitochondrial genes
adata.var['mt'] = adata.var_names.str.startswith('MT-')
sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)

# Filter
sc.pp.filter_cells(adata, min_genes=args.min_genes)
sc.pp.filter_genes(adata, min_cells=args.min_cells)
adata = adata[adata.obs.pct_counts_mt < args.mt_percent, :]

print(f"  After QC - Cells: {adata.n_obs}, Genes: {adata.n_vars}")

# === 3. Normalization ===
print("\n[3/08] Normalizing...")
sc.pp.normalize_total(target_sum=1e4)
sc.pp.log1p(adata)

# === 4. Feature Selection ===
print("\n[4/08] Finding variable features...")
sc.pp.highly_variable_genes(adata, n_top_genes=2000)
print(f"  Variable genes: {sum(adata.var.highly_variable)}")

# === 5. Scaling ===
print("\n[5/08] Scaling...")
sc.pp.scale(adata, max_value=10)

# === 6. PCA ===
print("\n[6/08] Running PCA...")
sc.tl.pca(adata, n_comps=args.npcs)

# === 7. Clustering & Visualization ===
print(f"\n[7/08] Clustering (npcs={args.npcs}, resolution={args.resolution})...")
sc.pp.neighbors(adata, n_neighbors=args.n_neighbors, n_pcs=args.npcs)
sc.tl.umap(adata)
sc.tl.leiden(adata, resolution=args.resolution)

# === 8. Marker Genes ===
print("\n[8/08] Finding marker genes...")
sc.tl.rank_genes_groups(adata, 'leiden', method='t-test')
marker_genes = sc.get.rank_genes_groups_df(adata, group=None)
marker_genes.to_csv('result_cluster_markers.csv', index=False)

# === Save Outputs ===
print("\n[Saving outputs]")
adata.write_h5ad(args.output)

# Plots
sc.pl.umap(adata, color=['leiden'], save='result_umap.png', show=False)
sc.pl.pca(adata, color=['leiden'], save='result_pca.png', show=False)

# Cluster distribution
cluster_dist = adata.obs['leiden'].value_counts().sort_index()
cluster_dist.to_csv('result_cluster_distribution.csv')

print("\n" + "=" * 40)
print("  Analysis Complete!")
print("=" * 40)
print("Outputs:")
print(f"  - {args.output}")
print(f"  - result_cluster_markers.csv")
print(f"  - result_umap.png")
print(f"  - result_pca.png")
print(f"  - result_cluster_distribution.csv")
print("\nCluster summary:")
print(cluster_dist)
