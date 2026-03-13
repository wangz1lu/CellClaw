#!/usr/bin/env python3
# ============================================================
# OmicsClaw Skill: Cell Type Annotation (Python/CellTypist)
# Template: 01_celltypist_annotation.py
# ============================================================

import argparse
import scanpy as sc
import pandas as pd
from pathlib import Path
from celltypist import models, annotate

# ── 参数设置 ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='OmicsClaw: Cell Type Annotation')
parser.add_argument('--input', '-i', default='input.h5ad', help='Input file (.h5ad)')
parser.add_argument('--output', '-o', default='.', help='Output directory')
parser.add_argument('--model', '-m', default='Immune_All_Low.pkl',
                    help='CellTypist model name')
parser.add_argument('--majority-voting', action='store_true',
                    help='Use majority voting for cell-level prediction')
args = parser.parse_args()

print(f"=== OmicsClaw: Cell Type Annotation (Python) ===")
print(f"输入: {args.input}")
print(f"模型: {args.model}")
print(f"Majority voting: {args.majority_voting}\n")

output_dir = Path(args.output)
output_dir.mkdir(parents=True, exist_ok=True)

# ── 1. 加载数据 ────────────────────────────────────────────
print("Step 1: 加载数据...")

adata = sc.read_h5ad(args.input)
print(f"  细胞数: {adata.n_obs}")
print(f"  基因数: {adata.n_vars}")

# ── 2. 预处理 ──────────────────────────────────────────────
print("Step 2: 预处理...")

# 确保有 raw 数据或用已有的
if adata.raw is not None:
    adata_use = adata.raw.to_adata()
else:
    adata_use = adata.copy()

# CellTypist 需要 counts
sc.pp.normalize_total(adata_use, target_sum=1e4)
sc.pp.log1p(adata_use)

print(f"  预处理完成")

# ── 3. 下载/加载模型 ────────────────────────────────────────
print("Step 3: 加载 CellTypist 模型...")

# 下载模型（首次）
try:
    model = models.Model.load(model=args.model)
except:
    print(f"  模型 {args.model} 不存在，下载...")
    models.download_models(['Immune_All_Low.pkl'])
    model = models.Model.load(model='Immune_All_Low.pkl')

print(f"  模型加载完成: {model.description}")

# ── 4. 注释 ────────────────────────────────────────────────
print("Step 4: 运行注释...")

# 方法 1: 直接注释
predictions = annotate(adata_use, model=model, majority_voting=args.majority_voting)

# 添加结果到 adata
adata.obs['celltype_celltypist'] = predictions.predicted_labels.values
if args.majority_voting:
    adata.obs['celltype_majority'] = predictions.majority_voting.values

print(f"  注释完成")
print(f"\n=== 注释结果 ===")
print(adata.obs['celltype_celltypist'].value_counts())

# ── 5. Marker 基因验证 ─────────────────────────────────────
print("\nStep 5: 生成标记基因可视化...")

# 常用免疫细胞 marker
marker_genes = {
    'CD4+ T': ['CD3D', 'CD4', 'IL7R'],
    'CD8+ T': ['CD3D', 'CD8A', 'GZMA'],
    'NK': ['NKG7', 'GNLY', 'KLRD1'],
    'B': ['CD79A', 'MS4A1', 'CD19'],
    'Monocyte': ['CD14', 'FCGR3A', 'LYZ'],
    'Macrophage': ['CD163', 'MS4A4A', 'CX3CR1'],
    'DC': ['CD1C', 'FCER1A', 'CST3'],
    'Platelet': ['PPBP', 'PF4']
}

# 选择存在的 marker
available_markers = []
for genes in marker_genes.values():
    for g in genes:
        if g in adata.var_names:
            available_markers.append(g)
            if len(available_markers) >= 12:
                break
    if len(available_markers) >= 12:
        break

if len(available_markers) > 0:
    sc.pl.violin(adata, keys=available_markers[:8], groupby='celltype_celltypist',
                  rotation=45, save=str(output_dir / 'result_marker_violin.png'),
                  show=False)
    
    sc.pl.dotplot(adata, var_names=available_markers[:12], groupby='celltype_celltypist',
                   standard_scale='var', save=str(output_dir / 'result_marker_dotplot.png'),
                   show=False)

# ── 6. 导出结果 ────────────────────────────────────────────
print("\nStep 6: 导出结果...")

# 保存 annotated adata
adata.write(output_dir / 'result_adata_annotated.h5ad')
print(f"  保存: {output_dir / 'result_adata_annotated.h5ad'}")

# CSV
annotation_df = pd.DataFrame({
    'cell_id': adata.obs.index,
    'cluster': adata.obs.get('leiden', 'unknown'),
    'celltype': adata.obs['celltype_celltypist'],
    'UMAP_1': adata.obsm['X_umap'][:, 0] if 'X_umap' in adata.obsm else None,
    'UMAP_2': adata.obsm['X_umap'][:, 1] if 'X_umap' in adata.obsm else None
})
annotation_df.to_csv(output_dir / 'result_celltype.csv', index=False)
print(f"  保存: {output_dir / 'result_celltype.csv'}")

# ── 7. 可视化 ─────────────────────────────────────────────
print("Step 7: 生成可视化...")

if 'X_umap' in adata.obsm:
    sc.pl.umap(adata, color=['celltype_celltypist'], 
                save=str(output_dir / 'result_celltype_umap.png'),
                show=False)

print("\n=== 注释完成！===")
