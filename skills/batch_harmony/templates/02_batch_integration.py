#!/usr/bin/env python3
# ==============================================================================
# Batch Correction Methods (Python)
# Supports: Harmony, BBKNN, SCVI
# ==============================================================================

import scanpy as sc
import anndata as ad
import argparse
import warnings
warnings.filterwarnings('ignore')

# === Parse arguments ===
parser = argparse.ArgumentParser(description='Batch Correction Methods')
parser.add_argument('input_path', help='Path to input h5ad file')
parser.add_argument('--method', default='harmony', choices=['harmony', 'bbknn', 'scvi', 'ingest'],
                    help='Batch correction method')
parser.add_argument('--batch_key', default='batch', help='Batch key in obs')
parser.add_argument('--n_pcs', type=int, default=50, help='Number of PCs')
parser.add_argument('--n_neighbors', type=int, default=15, help='Number of neighbors')
parser.add_argument('--resolution', type=float, default=0.8, help='Clustering resolution')
parser.add_argument('--output', default='result_integrated.h5ad', help='Output file')
args = parser.parse_args()

print("=" * 50)
print("  Batch Correction: " + args.method.upper())
print("=" * 50)
print(f"Input: {args.input_path}")
print(f"Method: {args.method}")
print(f"Batch key: {args.batch_key")
print("=" * 50)

# === 1. Load Data ===
print("\n[1/5] Loading data...")
adata = sc.read_h5ad(args.input_path)
print(f"  Cells: {adata.n_obs}, Genes: {adata.n_vars}")

# === 2. PCA ===
print("\n[2/5] Running PCA...")
sc.pp.pca(adata, n_comps=args.n_pcs)

# === 3. Run Batch Correction ===
print(f"\n[3/5] Running {args.method}...")

if args.method == 'harmony':
    try:
        import harmonypy as hm
        hm.run_harmony(adata, args.batch_key, max_iter=10)
        use_rep = 'X_pca_harmony'
    except ImportError:
        print("  Installing harmonypy...")
        import subprocess
        subprocess.run(['pip', 'install', 'harmonypy'])
        import harmonypy as hm
        hm.run_harmony(adata, args.batch_key, max_iter=10)
        use_rep = 'X_pca_harmony'
    
elif args.method == 'bbknn':
    try:
        import bbknn
        bbknn.bbknn(adata, batch_key=args.batch_key, n_pcs=args.n_pcs)
    except ImportError:
        print("  Installing bbknn...")
        import subprocess
        subprocess.run(['pip', 'install', 'bbknn'])
        import bbknn
        bbknn.bbknn(adata, batch_key=args.batch_key, n_pcs=args.n_pcs)
    use_rep = 'X_pca'
    
elif args.method == 'scvi':
    try:
        import scvi
        scvi.settings.seed = 42
        scvi.model.SCVI.setup_anndata(adata, batch_key=args.batch_key)
        model = scvi.model.SCVI(adata, n_layers=2, n_latent=30)
        model.train()
        adata.obsm["X_scVI"] = model.get_latent_representation()
    except ImportError:
        print("  Installing scvi-tools...")
        import subprocess
        subprocess.run(['pip', 'install', 'scvi-tools'])
        import scvi
        scvi.settings.seed = 42
        scvi.model.SCVI.setup_anndata(adata, batch_key=args.batch_key)
        model = scvi.model.SCVI(adata, n_layers=2, n_latent=30)
        model.train()
        adata.obsm["X_scVI"] = model.get_latent_representation()
    use_rep = 'X_scVI'
    
elif args.method == 'ingest':
    # ingest requires reference data
    print("  Note: ingest requires reference data")
    print("  Using PCA-based neighbors instead")
    use_rep = 'X_pca'

print(f"  Using representation: {use_rep}")

# === 4. Clustering and UMAP ===
print("\n[4/5] Clustering and UMAP...")
sc.pp.neighbors(adata, use_rep=use_rep, n_neighbors=args.n_neighbors)
sc.tl.umap(adata)
sc.tl.leiden(adata, resolution=args.resolution)

# === 5. Save Outputs ===
print("\n[5/5] Saving outputs...")
adata.write_h5ad(args.output)

# Save coordinates
import pandas as pd
umap_df = pd.DataFrame({
    'cell_id': adata.obs_names,
    'UMAP_1': adata.obsm['X_umap'][:, 0],
    'UMAP_2': adata.obsm['X_umap'][:, 1],
    'batch': adata.obs[args.batch_key] if args.batch_key in adata.obs else 'NA',
    'leiden': adata.obs['leiden']
})
umap_df.to_csv('result_umap_coordinates.csv', index=False)

print("\n" + "=" * 50)
print("  Analysis Complete!")
print("=" * 50)
print("Outputs:")
print(f"  - {args.output}")
print(f"  - result_umap_coordinates.csv")
print("\n")
