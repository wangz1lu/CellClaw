---
name: GSEA — GO/KEGG 富集分析
version: 1.0.0
scope: 差异基因的功能富集分析（GO, KEGG, Reactome, msigDB）
languages: [R, Python]
triggers: [gsea, go, kegg, enrichment, 富集, goenrich,ORA, overrepresentation, pathway, do, enrichr]
---
# Skill: GSEA — GO/KEGG 富集分析
# CellClaw Skill Knowledge Base
# Version: 1.0.0
# Author: CellClaw
# Scope: 差异基因的功能富集分析
# Based on: clusterProfiler, DOSE, enrichplot, msigdb

---

## 1. Skill 概述

**富集分析（Enrichment Analysis）** 用于识别差异基因在功能通路（GO、KEGG、Reactome）上的富集情况，帮助理解基因的生物学意义。

### 适用场景
| 场景 | 说明 |
|------|------|
| Cluster Marker 富集 | 某个 cluster 的 marker 基因参与什么通路？ |
| 疾病相关通路 | 处理组 vs 对照组的差异基因在哪些通路富集？ |
| 多组比较 | 多个 cluster 的通路富集对比 |

### 两种分析方法
| 方法 | 缩写 | 说明 | 适用场景 |
|------|------|------|---------|
| 超几何检验 | ORA | Over-representation Analysis | 有明确的差异基因列表 |
| 基因集富集分析 | GSEA | Gene Set Enrichment Analysis | 全部基因排序后分析 |

### 工具要求
- **R** ≥ 4.1.0
- **clusterProfiler** ≥ 4.8.0（`BiocManager::install("clusterProfiler")`）
- **DOSE**（`BiocManager::install("DOSE")`）
- **enrichplot**（可视化）
- **msigdb**（如果用 msigDB）

---

## 2. 输入数据要求

### ORA 必需输入
```
差异基因列表：gene symbol 向量（ENTREZ ID 或 gene symbol）
背景基因集：全部表达基因（用于超几何检验）
物种：human / mouse / rat 等
```

### GSEA 必需输入
```
全部基因的排序列表：按 log2FC 或 p 值排序
基因集：GO / KEGG / Reactome / HALLMARK
物种
```

### ⚠️ 重要注意事项
- **ORA 需要差异基因列表**，必须设定筛选阈值（padj, log2FC）
- **GSEA 需要全部基因排序**，不要筛选
- gene ID 统一：clusterProfiler 默认用 ENTREZ ID，需要 `bitr()` 转换
- 人类用 `org.Hs.eg.db`，小鼠用 `org.Mm.eg.db`

---

## 3. 标准分析流程

### Step 1: 数据准备
```r
library(clusterProfiler)
library(DOSE)
library(enrichplot)
library(dplyr)

# 假设已有 DEG 结果（来自 deg_analysis skill）
deg <- read.csv("result_deg_significant.csv", row.names = 1)
gene_list <- rownames(deg)  # gene symbols

# 转换 ID（SYMBOL → ENTREZ）
gene_df <- bitr(gene_list, fromType = "SYMBOL", 
                toType = "ENTREZID", 
                OrgDb = org.Hs.eg.db)
# 去重
gene_entrez <- unique(gene_df$ENTREZID)
```

### Step 2: GO 富集分析
```r
# BP (Biological Process)
go_bp <- enrichGO(
    gene = gene_entrez,
    OrgDb = org.Hs.eg.db,
    ont = "BP",               # BP / MF / CC / ALL
    pAdjustMethod = "BH",
    pvalueCutoff = 0.05,
    qvalueCutoff = 0.05,
    readable = TRUE           # ENTREZ → SYMBOL
)

# MF (Molecular Function)
go_mf <- enrichGO(gene = gene_entrez, OrgDb = org.Hs.eg.db, ont = "MF", ...)

# CC (Cellular Component)
go_cc <- enrichGO(gene = gene_entrez, OrgDb = org.Hs.eg.db, ont = "CC", ...)

# ALL（同时返回 BP, MF, CC）
go_all <- enrichGO(gene = gene_entrez, OrgDb = org.Hs.eg.db, ont = "ALL", ...)
```

### Step 3: KEGG 通路富集
```r
# KEGG
kegg <- enrichKEGG(
    gene = gene_entrez,
    organism = "hsa",           # hsa = human, mmu = mouse
    pAdjustMethod = "BH",
    pvalueCutoff = 0.05
)

# Reactome
reactome <- enrichReactome(gene_entrez, organism = "Homo sapiens")

# DO (Disease Ontology)
do <- enrichDO(gene_entrez, ...)
```

### Step 4: GSEA（需要排序基因列表）
```r
# 准备排序基因（全部基因，按 log2FC 排序）
deg_all <- read.csv("result_deg_full.csv")
deg_all <- deg_all[order(deg_all$avg_log2FC, decreasing = TRUE), ]

# 转换 ID
gene_list_symbol <- rownames(deg_all)
gene_list_entrez <- bitr(gene_list_symbol, fromType = "SYMBOL", 
                         toType = "ENTREZID", OrgDb = org.Hs.eg.db)

# 构建排序向量（ENTREZID → log2FC）
fc_vector <- deg_all$avg_log2FC
names(fc_vector) <- gene_list_entrez$ENTREZID[match(gene_list_symbol, gene_list_entrez$SYMBOL)]
fc_vector <- na.omit(fc_vector)
fc_vector <- sort(fc_vector, decreasing = TRUE)

# 运行 GSEA
gsea_go <- gseGO(
    geneList = fc_vector,
    OrgDb = org.Hs.eg.db,
    ont = "BP",
    minGSSize = 10,
    maxGSSize = 500,
    pvalueCutoff = 0.05
)

gsea_kegg <- gseKEGG(
    geneList = fc_vector,
    organism = "hsa",
    minGSSize = 10,
    maxGSSize = 500,
    pvalueCutoff = 0.05
)
```

---

## 4. 可视化

### 气泡图
```r
# GO
dotplot(go_bp, showCategory = 20)

# KEGG
dotplot(kegg, showCategory = 20)
```

### 网络图
```r
# GO 网络
emapplot(go_bp)

# KEGG 网络
emapplot(kegg)
```

### GSEA 富集图
```r
# GSEA 经典图
gseaplot(gsea_kegg, geneSetID = "hsa04110")

# 多个通路对比
gseaplot2(gsea_kegg, geneSetID = c("hsa04110", "hsa04218"), 
          pvalue_table = TRUE)
```

### 词云
```r
# GO 词云
cnetplot(go_bp, categorySize = "pvalue")
```

---

## 5. 输出文件规范

**⚠️ 所有输出文件名必须以 `result_` 开头！**

```r
# ORA 结果
write.csv(as.data.frame(go_bp), "result_go_enrichment_bp.csv", row.names = FALSE)
write.csv(as.data.frame(kegg), "result_kegg_enrichment.csv", row.names = FALSE)

# GSEA 结果
write.csv(as.data.frame(gsea_go), "result_gsea_go.csv", row.names = FALSE)
write.csv(as.data.frame(gsea_kegg), "result_gsea_kegg.csv", row.names = FALSE)

# PNG 可视化
png("result_go_dotplot.png", width = 12, height = 10, units = "in", res = 300)
print(dotplot(go_bp, showCategory = 20))
dev.off()

png("result_gsea_classic.png", width = 10, height = 8, units = "in", res = 300)
print(gseaplot(gsea_kegg, geneSetID = 1))
dev.off()

# RDS 对象（后续分析用）
saveRDS(go_bp, "result_go_bp_object.rds")
saveRDS(kegg, "result_kegg_object.rds")
```

---

## 6. 参数详解

### enrichGO 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `gene` | 必填 | ENTREZ ID 向量 |
| `OrgDb` | 必填 | org.Hs.eg.db / org.Mm.eg.db |
| `ont` | "BP" | BP / MF / CC / ALL |
| `pAdjustMethod` | "BH" | BH / bonferroni / holm |
| `pvalueCutoff` | 0.05 | p 值阈值 |
| `qvalueCutoff` | 0.05 | q 值阈值 |
| `readable` | FALSE | ENTREZ → SYMBOL |

### gseGO / gseKEGG 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `geneList` | 必填 | 排序好的基因向量（names = ENTREZID） |
| `minGSSize` | 10 | 基因集最小基因数 |
| `maxGSSize` | 500 | 基因集最大基因数 |
| `pvalueCutoff` | 0.05 | p 值阈值 |

---

## 7. 常见问题

### Q1: Error: no enrichment found
**原因**: 差异基因太少，或阈值太高

**解决**:
```r
# 降低阈值
deg <- read.csv("result_deg_full.csv")
gene_list <- rownames(deg[deg$p_val_adj < 0.1, ])  # 更宽松
```

### Q2: gene ID 转换失败
**原因**: 基因名不符合规范、有空格、重复

**解决**:
```r
# 清理基因名
gene_list <- unique(trimws(gene_list))
gene_df <- bitr(gene_list, fromType = "SYMBOL", toType = "ENTREZID", 
                OrgDb = org.Hs.eg.db, drop = FALSE)
```

### Q3: GSEA 结果为空
**原因**: 基因排序不正确，或基因集太严格

**解决**:
```r
# 检查排序
head(geneList)
# 确保是数值向量，不是 data.frame
```

---

## 8. 参考资料

- clusterProfiler: https://bioconductor.org/packages/release/bioc/vignettes/clusterProfiler/inst/doc/clusterProfiler.html
- enrichplot: https://bioconductor.org/packages/release/bioc/man/enrichplot/man/enrichplot-package.Rd
- GSEA 论文: https://www.pnas.org/doi/10.1073/pnas.0506580102
