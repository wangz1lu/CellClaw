#!/usr/bin/env python3
# ==============================================================================
# CellTypist Cell Type Annotation
# ==============================================================================

import scanpy as sc
import celltypist
from celltypist import models
import argparse
import warnings
warnings.filterwarnings('ignore')

# === Parse arguments ===
parser = argparse.ArgumentParser(description='CellTypist Cell Type Annotation')
parser.add_argument('input_path', help='Path to input h5ad file')
parser.add_argument('--model', default='Immune_All_Low.pkl', help='Model name')
parser.add_argument('--majority_voting', action='store_true', help='Use majority voting')
parser.add_argument('--mode', default='best match', choices=['best match', 'prob match'], help='Prediction mode')
parser.add_argument('--p_thres', type=float, default=0.5, help='Probability threshold for prob match mode')
parser.add_argument('--output', default='result_celltypist_annotated.h5ad', help='Output file')
args = parser.parse_args()

print("=" * 50)
print("  CellTypist Cell Type Annotation")
print("=" * 50)
print(f"Input: {args.input_path}")
print(f"Model: {args.model}")
print(f"Mode: {args.mode}")
print(f"Majority voting: {args.majority_voting}")
print("=" * 50)

# === 1. Load Data ===
print("\n[1/5] Loading data...")
adata = sc.read_h5ad(args.input_path)
print(f"  Cells: {adata.n_obs}, Genes: {adata.n_vars}")

# Check if data is log-normalized
if adata.X.sum(axis=0).max() > 100:
    print("  WARNING: Data appears to be raw counts, normalizing...")
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

# === 2. Download/Load Model ===
print("\n[2/5] Loading model...")
try:
    model = models.Model.load(model=args.model)
    print(f"  Loaded: {args.model}")
    print(f"  Cell types: {len(model.cell_types)}")
except:
    print(f"  Downloading model: {args.model}")
    models.download_models(force_update=True)
    model = models.Model.load(model=args.model)

# === 3. Run Annotation ===
print(f"\n[3/5] Running annotation...")
predictions = celltypist.annotate(
    adata,
    model=args.model,
    majority_voting=args.majority_voting,
    mode=args.mode,
    p_thres=args.p_thres if args.mode == 'prob match' else 0.5
)
print(f"  Prediction complete")

# === 4. Process Results ===
print("\n[4/5] Processing results...")
# Convert to AnnData with predictions
adata_result = predictions.to_adata()

# Show prediction summary
print("\n  Prediction summary:")
print(adata_result.obs['predicted_labels'].value_counts())

# === 5. Save Outputs ===
print("\n[5/5] Saving outputs...")
adata_result.write_h5ad(args.output)

# Save annotation table
annotation_df = adata_result.obs[['predicted_labels', 'majority_voting', 'conf_score']].copy()
annotation_df.to_csv('result_celltype_annotation.csv')

# Save model (optional)
# model.write('result_celltypist_model.pkl')

print("\n" + "=" * 50)
print("  Analysis Complete!")
print("=" * 50)
print("Outputs:")
print(f"  - {args.output}")
print(f"  - result_celltype_annotation.csv")
print("\n")
