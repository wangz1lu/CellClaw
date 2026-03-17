#!/usr/bin/env python3
# ==============================================================================
# scRNA-seq Analysis using Scanpy
# ==============================================================================

import scanpy as sc
import anndata as ad
import argparse
import warnings
warnings.filterwarnings('ignore')

# === Parse arguments ===
parser = argparse.ArgumentParser(description='scRNA-seq Analysis using Scanpy')
parser.add_argument('input_path', help='Path to input file (10X h5, h5ad, or matrix directory)')
parser.add_argument('--project', default='snRNA', help='Project name')
parser.add_argument('--min_genes', type=int, default=100, help='Min genes per cell')
parser.add_argument('--min_cells', type=int, default=3, help='Min cells per gene')
parser.add_argument('--mt_percent', type=float, default=20, help='Max mitochondrial percent')
parser.add_argument('--n_neighbors', type=int, default=15, help='Number of neighbors')
parser.add_argument('--npcs', type=int, default=50, help='Number of PCs')
parser.add_argument('--resolution', type=float, default=0.8, help='Clustering resolution')
parser.add_argument('--cluster', default='leiden', help='Clustering method: leiden or louvain')
parser.add_argument('--output', default='result_scanpy.h5ad', help='Output file')
args = parser.parse_args()

print("=" * 50)
print("  scRNA-seq Scanpy Analysis")
print("=" * 50)
print(f"Input: {args.input_path}")
print(f"Project: {args.project}")
print(f"Min genes: {args.min_genes}")
print(f"MT percent: {args.mt_percent}")
print(f"Resolution: {args.resolution}")
print("=" * 50)

# === 1. Load Data ===
print("\n[1/9] Loading data...")
if args.input_path.endswith('.h5ad'):
    adata = sc.read_h5ad(args.input_path)
elif args.input_path.endswith('.h5'):
    adata = sc.read_10x_h5(args.input_path)
else:
    adata = sc.read_10x_mtx(args.input_path)

adata.var_names_make_unique()
print(f"  Initial: {adata.n_obs} cells, {adata.n_vars} genes")

# === 2. QC ===
print("\n[2/9] Quality control...")
# Mitochondrial genes
adata.var["mt"] = adata.var_names.str.startswith("MT-")
# Ribosomal genes
adata.var["ribo"] = adata.var_names.str.startswith(("RPS", "RPL"))
# Hemoglobin genes  
adata.var["hb"] = adata.var_names.str.contains("^HB[^(P)]", regex=True)

# Calculate QC metrics
sc.pp.calculate_qc_metrics(adata, qc_vars=["mt", "ribo", "hb"], inplace=True)

# Filter cells and genes
sc.pp.filter_cells(adata, min_genes=args.min_genes)
sc.pp.filter_genes(adata, min_cells=args.min_cells)

# Filter by mitochondrial percentage
adata = adata[adata.obs.pct_counts_mt < args.mt_percent, :]

print(f"  After QC: {adata.n_obs} cells, {adata.n_vars} genes")

# === 3. Normalization ===
print("\n[3/9] Normalizing...")
sc.pp.normalize_total(target_sum=1e4)
sc.pp.log1p(adata)

# === 4. Feature Selection ===
print("\n[4/9] Finding variable features...")
sc.pp.highly_variable_genes(adata, n_top_genes=2000)
print(f"  Variable genes: {sum(adata.var.highly_variable)}")

# Store raw
adata.raw = adata.copy()

# === 5. Scaling ===
print("\n[5/9] Scaling...")
sc.pp.scale(adata, max_value=10)

# === 6. PCA ===
print("\n[6/9] Running PCA...")
sc.tl.pca(adata, n_comps=args.npcs)

# === 7. Clustering ===
print(f"\n[7/9] Clustering ({args.cluster}, resolution={args.resolution})...")
sc.pp.neighbors(adata, n_neighbors=args.n_neighbors, n_pcs=args.npcs)

if args.cluster == "leiden":
    sc.tl.leiden(adata, resolution=args.resolution)
else:
    sc.tl.louvain(adata, resolution=args.resolution)

# === 8. Visualization ===
print("\n[8/9] Running UMAP...")
sc.tl.umap(adata)

# === 9. Marker Genes ===
print("\n[9/9] Finding marker genes...")
sc.tl.rank_genes_groups(adata, groupby=args.cluster, method="t-test")
marker_genes = sc.get.rank_genes_groups_df(adata, group=None)
marker_genes.to_csv('result_cluster_markers.csv', index=False)

# === Save Outputs ===
print("\n[Saving outputs]")
adata.write_h5ad(args.output)

# Plots
sc.pl.umap(adata, color=[args.cluster], save='result_umap.png', show=False)
sc.pl.pca(adata, color=[args.cluster], save='result_pca.png', show=False)

# Cluster distribution
cluster_dist = adata.obs[args.cluster].value_counts().sort_index()
cluster_dist.to_csv('result_cluster_distribution.csv')

print("\n" + "=" * 50)
print("  Analysis Complete!")
print("=" * 50)
print("Outputs:")
print(f"  - {args.output}")
print(f"  - result_cluster_markers.csv")
print(f"  - result_umap.png")
print(f"  - result_pca.png")
print(f"  - result_cluster_distribution.csv")
print("\nCluster summary:")
print(cluster_dist)
