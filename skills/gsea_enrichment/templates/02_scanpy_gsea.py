#!/usr/bin/env python3
# ============================================================
# CellClaw Skill: GSEA Enrichment (Python)
# Template: 01_gsea_enrichment.py
# ============================================================

import argparse
import pandas as pd
import numpy as np
from pathlib import Path
import gseapy as gp
from gseapy.plot import dotplot

# ── 参数设置 ─────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='CellClaw: GSEA Enrichment')
parser.add_argument('--deg', '-d', default='result_deg_significant.csv', 
                    help='DEG result file')
parser.add_argument('--input', '-i', default=None, 
                    help='Full DEG file with log2FC (if no --deg)')
parser.add_argument('--output', '-o', default='.', help='Output directory')
parser.add_argument('--species', '-s', default='Human', 
                    choices=['Human', 'Mouse'],
                    help='Species')
parser.add_argument('--method', '-m', default='ora', 
                    choices=['ora', 'gsea'],
                    help='Enrichment method')
args = parser.parse_args()

print(f"=== CellClaw: GSEA Enrichment (Python) ===")
print(f"输入: {args.deg}")
print(f"物种: {args.species}")
print(f"方法: {args.method}\n")

output_dir = Path(args.output)
output_dir.mkdir(parents=True, exist_ok=True)

# ── 1. 加载 DEG ────────────────────────────────────────────
print("Step 1: 加载差异基因...")

if args.deg and Path(args.deg).exists():
    deg_df = pd.read_csv(args.deg)
    gene_list = deg_df['gene'].unique().tolist()
    print(f"  DEG 数量: {len(gene_list)}")
elif args.input and Path(args.input).exists():
    # 用完整 DEG 列表，按 log2FC 排序
    deg_df = pd.read_csv(args.input)
    deg_df = deg_df.sort_values('log2FC', ascending=False)
    gene_list = deg_df['gene'].tolist()
    print(f"  基因列表: {len(gene_list)}")
else:
    raise ValueError("需要提供 --deg 或 --input 文件")

# ── 2. GO/KEGG 富集 (ORA) ──────────────────────────────────
if args.method == 'ora':
    print("Step 2: 运行 ORA 富集分析...")
    
    # GO enrichment
    print("  运行 GO...")
    enr_go = gp.enrichr(
        gene_list=gene_list,
        gene_sets='GO_Biological_Process_2021',
        organism=args.species,
        outdir=str(output_dir / 'go_enrichment'),
        no_plot=True
    )
    
    if len(enr_go.results) > 0:
        go_df = enr_go.results
        go_df.to_csv(output_dir / 'result_go_enrichment.csv', index=False)
        print(f"  GO 富集: {len(go_df)} 个")
    
    # KEGG enrichment
    print("  运行 KEGG...")
    kegg_sets = 'KEGG_2021_Human' if args.species == 'Human' else 'KEGG_2021_Mouse'
    enr_kegg = gp.enrichr(
        gene_list=gene_list,
        gene_sets=kegg_sets,
        organism=args.species,
        outdir=str(output_dir / 'kegg_enrichment'),
        no_plot=True
    )
    
    if len(enr_kegg.results) > 0:
        kegg_df = enr_kegg.results
        kegg_df.to_csv(output_dir / 'result_kegg_enrichment.csv', index=False)
        print(f"  KEGG 富集: {len(kegg_df)} 个")

# ── 3. GSEA ────────────────────────────────────────────────
elif args.method == 'gsea':
    print("Step 2: 运行 GSEA...")
    
    # 需要排序的基因列表
    if 'log2FC' in deg_df.columns:
        # 构建排序向量
        gene_ranking = deg_df[['gene', 'log2FC']].drop_duplicates()
        gene_ranking = gene_ranking.sort_values('log2FC', ascending=False)
        gene_list_gsea = gene_ranking['log2FC'].values
        gene_names = gene_ranking['gene'].values
        
        # GSEA
        print("  运行 GSEA (GO)...")
        gsea_go = gp.prerank(
            rnk=gene_list_gsea,
            gene_sets='GO_Biological_Process_2021',
            outdir=str(output_dir / 'gsea_go'),
            no_plot=True,
            min_size=10,
            max_size=500
        )
        
        if hasattr(gsea_go, 'results') and len(gsea_go.results) > 0:
            gsea_go.results.to_csv(output_dir / 'result_gsea_go.csv', index=False)
            print(f"  GSEA GO: {len(gsea_go.results)} 个")
        
        # GSEA KEGG
        print("  运行 GSEA (KEGG)...")
        kegg_sets = 'KEGG_2021_Human' if args.species == 'Human' else 'KEGG_2021_Mouse'
        gsea_kegg = gp.prerank(
            rnk=gene_list_gsea,
            gene_sets=kegg_sets,
            outdir=str(output_dir / 'gsea_kegg'),
            no_plot=True,
            min_size=10,
            max_size=500
        )
        
        if hasattr(gsea_kegg, 'results') and len(gsea_kegg.results) > 0:
            gsea_kegg.results.to_csv(output_dir / 'result_gsea_kegg.csv', index=False)
            print(f"  GSEA KEGG: {len(gsea_kegg.results)} 个")

# ── 4. 可视化 ────────────────────────────────────────────
print("Step 3: 生成可视化...")

try:
    if 'go_df' in dir() and len(go_df) > 0:
        dotplot(go_df.head(20), 
                title="GO Enrichment",
                ofname=str(output_dir / 'result_go_dotplot.png'))
except:
    pass

try:
    if 'kegg_df' in dir() and len(kegg_df) > 0:
        dotplot(kegg_df.head(20),
                title="KEGG Enrichment", 
                ofname=str(output_dir / 'result_kegg_dotplot.png'))
except:
    pass

print("\n=== 富集分析完成！===")
