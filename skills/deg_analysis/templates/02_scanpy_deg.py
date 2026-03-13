#!/usr/bin/env python3
# ============================================================
# OmicsClaw Skill: DEG Analysis (Python/Scanpy)
# Template: 01_basic_deg.py
# ============================================================

import argparse
import scanpy as sc
import pandas as pd
import numpy as np
from pathlib import Path

# ── 参数设置 ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='OmicsClaw: DEG Analysis')
parser.add_argument('--input', '-i', default='input.h5ad', help='Input file (.h5ad)')
parser.add_argument('--output', '-o', default='.', help='Output directory')
parser.add_argument('--group', '-g', default='leiden', help='Group column for comparison')
parser.add_argument('--group1', '-g1', default=None, help='Group 1 to compare')
parser.add_argument('--group2', '-g2', default=None, help='Group 2 to compare')
parser.add_argument('--method', '-m', default='t-test', 
                    choices=['t-test', 'wilcoxon', 'logreg'],
                    help='Statistical method')
args = parser.parse_args()

print(f"=== OmicsClaw: DEG Analysis (Python) ===")
print(f"输入: {args.input}")
print(f"分组列: {args.group}")
print(f"方法: {args.method}\n")

output_dir = Path(args.output)
output_dir.mkdir(parents=True, exist_ok=True)

# ── 1. 加载数据 ────────────────────────────────────────────
print("Step 1: 加载数据...")
adata = sc.read_h5ad(args.input)
print(f"  细胞数: {adata.n_obs}")
print(f"  基因数: {adata.n_vars}")

# ── 2. 设置分组 ────────────────────────────────────────────
if args.group not in adata.obs.columns:
    raise ValueError(f"分组列 '{args.group}' 不存在！可用列: {list(adata.obs.columns)}")

if args.group1:
    # 指定两组比较
    print(f"  比较: {args.group1} vs {args.group2}")
else:
    # 与所有其他组比较
    print(f"  比较所有组 vs 其余")

# ── 3. 差异分析 ────────────────────────────────────────────
print("Step 2: 运行 DEG 分析...")

sc.tl.rank_genes_groups(
    adata,
    groupby=args.group,
    groups=[args.group1] if args.group1 else None,
    reference=args.group2 if args.group2 else 'rest',
    method=args.method,
    n_genes=adata.n_vars,  # 全部基因
    tie_correct=True
)

# 提取结果
deg_results = []
for group in adata.uns['rank_genes_groups']['names'].dtype.names:
    for i in range(len(adata.uns['rank_genes_groups']['names'])):
        gene = adata.uns['rank_genes_groups']['names'][group][i]
        pval = adata.uns['rank_genes_groups']['pvals'][group][i]
        padj = adata.uns['rank_genes_groups']['pvals_adj'][group][i]
        logfc = adata.uns['rank_genes_groups']['logfoldchanges'][group][i]
        deg_results.append({
            'gene': gene,
            'cluster': group,
            'p_value': pval,
            'p_adj': padj,
            'log2FC': logfc
        })

deg_df = pd.DataFrame(deg_results)
print(f"  找到 {len(deg_df)} 个结果")

# ── 4. 筛选显著 DEG ─────────────────────────────────────────
sig_deg = deg_df[(deg_df['p_adj'] < 0.05) & (abs(deg_df['log2FC']) > 0.5)]
sig_deg = sig_deg.sort_values('log2FC', ascending=False)
print(f"  显著 DEG (p_adj<0.05, |log2FC|>0.5): {len(sig_deg)}")

# ── 5. 导出结果 ────────────────────────────────────────────
print("Step 3: 导出结果...")

# 完整结果
deg_df.to_csv(output_dir / 'result_deg_full.csv', index=False)
print(f"  保存: {output_dir / 'result_deg_full.csv'}")

# 显著结果
sig_deg.to_csv(output_dir / 'result_deg_significant.csv', index=False)
print(f"  保存: {output_dir / 'result_deg_significant.csv'}")

# Top 基因
top_n = 50
top_up = sig_deg[sig_deg['log2FC'] > 0].head(top_n)
top_down = sig_deg[sig_deg['log2FC'] < 0].head(top_n)
top_combined = pd.concat([top_up, top_down])
top_combined.to_csv(output_dir / 'result_deg_top50.csv', index=False)
print(f"  保存: {output_dir / 'result_deg_top50.csv'}")

# ── 6. 可视化 ────────────────────────────────────────────
print("Step 4: 生成可视化...")

# 热图
sc.pl.rank_genes_groups_heatmap(adata, n_genes=20, groupby=args.group, 
                                 save=str(output_dir / 'result_deg_heatmap.png'),
                                 show=False)

# 散点图
if len(sig_deg) > 0:
    top_genes = sig_deg.head(5)['gene'].tolist()
    sc.pl.violin(adata, keys=top_genes, groupby=args.group, 
                  save=str(output_dir / 'result_deg_violin.png'),
                  show=False)

print("\n=== DEG 分析完成！===")
