---
name: Visualization — R 可视化
version: 1.1.0
scope: R 语言可视化 (ggplot2 + ComplexHeatmap)
languages: [R]
triggers: [ggplot2, complexheatmap, visualization, plot, 可视化, 绘图, 图表, heatmap]
---

# Skill: Visualization — R 可视化

> Part 1: ggplot2 (见上一部分)
> Part 2: ComplexHeatmap

---

# Part 2: ComplexHeatmap

## 1. 概述

ComplexHeatmap 是 R 语言最强大的热图和基因组数据可视化包，支持：
- 单热图和多热图
- 行列注释
- 聚类与分切
- 自定义图形
- 图例定制

---

## 2. 基础语法

```r
library(ComplexHeatmap)
library(circlize)

# 基础热图
Heatmap(mat)
```

### 核心函数

| 函数 | 说明 |
|------|------|
| `Heatmap()` | 创建单个热图 |
| `HeatmapAnnotation()` | 创建行列注释 |
| `rowAnnotation()` | 行注释（简写）|
| `draw()` | 绘制热图 |
| `Legend()` | 创建图例 |

---

## 3. 基础热图

### 3.1 简单热图

```r
set.seed(123)
mat <- matrix(rnorm(100), 10, 10)
rownames(mat) <- paste0("row", 1:10)
colnames(mat) <- paste0("col", 1:10)

Heatmap(mat)
```

### 3.2 自定义颜色

```r
library(circlize)

# 连续型颜色
col_fun <- colorRamp2(c(-2, 0, 2), c("blue", "white", "red"))

Heatmap(mat, name = "expression", col = col_fun)
```

### 3.3 聚类

```r
# 行和列都聚类
Heatmap(mat, 
        name = "mat",
        cluster_rows = TRUE,
        cluster_columns = TRUE)

# 只聚类行
Heatmap(mat, 
        cluster_columns = FALSE)

# 使用自定义距离方法
Heatmap(mat, 
        clustering_distance_rows = "pearson",
        clustering_method = "ward.D")
```

### 3.4 分切热图

```r
# 按行分切
Heatmap(mat, name = "mat", km = 2)

# 按列分切
Heatmap(mat, name = "mat", column_km = 2)

# 自定义分切
Heatmap(mat, name = "mat", row_split = rep(c("A", "B"), each = 5))
```

---

## 4. 注释 (Annotations)

### 4.1 简单注释

```r
# 列注释
ha <- HeatmapAnnotation(
  foo1 = runif(10),
  bar1 = anno_barplot(runif(10))
)

Heatmap(mat, name = "mat", top_annotation = ha)

# 行注释
row_ha <- rowAnnotation(
  foo2 = runif(10),
  bar2 = anno_barplot(runif(10))
)

Heatmap(mat, name = "mat", right_annotation = row_ha)
```

### 4.2 分类注释

```r
# 离散变量注释
ha <- HeatmapAnnotation(
  group = sample(c("A", "B", "C"), 10, replace = TRUE),
  col = list(group = c(A = "red", B = "green", C = "blue"))
)

Heatmap(mat, name = "mat", top_annotation = ha)
```

### 4.3 连续变量注释

```r
library(circlize)
col_fun <- colorRamp2(c(0, 1), c("white", "red"))

ha <- HeatmapAnnotation(
  score = runif(10),
  col = list(score = col_fun)
)

Heatmap(mat, name = "mat", top_annotation = ha)
```

### 4.4 复杂注释函数

```r
# 点注释
anno_points()

# 条形注释
anno_barplot()

# 箱线图注释
anno_boxplot()

# 简笔注释
anno_simple()

# 空注释（用于占位）
anno_empty()
```

---

## 5. 热图列表

### 5.1 水平拼接

```r
ht1 <- Heatmap(mat[1:10, ], name = "ht1")
ht2 <- Heatmap(mat[11:20, ], name = "ht2")

ht1 + ht2
```

### 5.2 垂直拼接

```r
ht1 %v% ht2
```

### 5.3 调整对齐

```r
# 热图列表自动调整行/列对齐
ht_list <- ht1 + ht2 + rowAnnotation(...)
draw(ht_list)
```

---

## 6. 图例 (Legends)

### 6.1 自定义图例

```r
library(circlize)
col_fun <- colorRamp2(c(-2, 0, 2), c("blue", "white", "red"))

# 创建图例
lgd <- Legend(col_fun = col_fun, title = "Expression")

# 绘制
draw(ht, heatmap_legend = lgd)
```

### 6.2 图例位置

```r
# 在右侧（默认）
draw(ht, heatmap_legend_side = "right")

# 在左侧
draw(ht, heatmap_legend_side = "left")

# 在底部
draw(ht, heatmap_legend_side = "bottom")
```

### 6.3 多个图例

```r
lgd1 <- Legend(col_fun = col_fun, title = "Expr")
lgd2 <- Legend(at = c("A", "B"), title = "Group")

draw(ht, 
      heatmap_legend = lgd1, 
      annotation_legend = lgd2)
```

---

## 7. 图形装饰 (Decoration)

### 7.1 添加文本

```r
ht <- Heatmap(mat, name = "mat")
ht <- draw(ht)

# 在热图主体上添加文本
decorate_heatmap_body("mat", {
  grid.text("label", 0.5, 0.5)
})
```

### 7.2 添加边框

```r
# 在行名称处添加矩形
decorate_row_names("mat", {
  grid.rect(gp = gpar(fill = "red"))
})
```

### 7.3 添加分割线

```r
# 在列 dendrogram 处添加分割
decorate_column_dend("mat", {
  grid.rect(x = 0.5, width = 0.5, 
            gp = gpar(fill = "blue", alpha = 0.3))
})
```

---

## 8. 单细胞数据可视化

### 8.1 标记基因热图

```r
library(Seurat)
library(ComplexHeatmap)

# 获取 marker 基因
markers <- FindAllMarkers(seu, only.pos = TRUE, max.cells.per.ident = 100)
top_markers <- markers %>% group_by(cluster) %>% top_n(20, avg_log2FC)

# 提取表达矩阵
mat <- GetAssayData(seu, slot = "data")[unique(top_markers$gene), ]

# 标准化
mat <- scale(mat)
mat <- mat[complete.cases(mat), ]

# 绘制热图
Heatmap(mat,
        name = "expression",
        cluster_rows = TRUE,
        cluster_columns = TRUE,
        show_row_names = TRUE,
        show_column_names = FALSE)
```

### 8.2 添加细胞类型注释

```r
# 添加列注释（细胞类型）
ha <- HeatmapAnnotation(
  cell_type = Idents(seu),
  col = list(cell_type = c("B" = "red", "T" = "blue", "NK" = "green"))
)

Heatmap(mat,
        name = "expression",
        top_annotation = ha)
```

### 8.3 多组学整合可视化

```r
# ATAC + RNA 整合
ht_rna <- Heatmap(rna_mat, name = "RNA")
ht_atac <- Heatmap(atac_mat, name = "ATAC")

ht_rna + ht_atac
```

---

## 9. 高级应用

### 9.1 UpSet 图

```r
# 创建 UpSet 图
UpSet(melist)
```

### 9.2 互动热图

```r
# 转换为互动版本
library(InteractiveComplexHeatmap)
makeInteractive(ht)
```

### 9.3 保存热图

```r
# 保存为 PDF
pdf("heatmap.pdf")
draw(ht)
dev.off()

# 保存为 PNG
png("heatmap.png", width = 3000, height = 2000, res = 300)
draw(ht)
dev.off()
```

---

## 10. 输出文件规范

**⚠️ 所有输出文件名必须以 `result_` 开头！**

```r
# 保存为 PDF
pdf("result_heatmap.pdf", width = 10, height = 8)
draw(ht)
dev.off()

# 保存为 PNG
png("result_heatmap.png", width = 3000, height = 2000, res = 300)
draw(ht)
dev.off()

# 保存为 SVG
svg("result_heatmap.svg", width = 10, height = 8)
draw(ht)
dev.off()
```

---

## 11. 示例命令

```
# 基础热图
帮我画一个热图

# 带注释
加上细胞类型注释

# 多热图
把两个表达矩阵拼在一起

# 保存
保存为PDF
```

---

## 12. 参考资料

- **ComplexHeatmap 官网**: https://jokergoo.github.io/ComplexHeatmap-reference/
- **ComplexHeatmap 论文**: https://doi.org/10.1093/bioinformatics/btx313
- **circlize 包**: https://jokergoo.github.io/circlize/
