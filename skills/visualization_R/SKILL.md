---
name: Visualization — R 可视化
version: 1.0.0
scope: R 语言 ggplot2 可视化
languages: [R]
triggers: [ggplot2, visualization, plot, 可视化, 绘图, 图表, ggplot]
---

# Skill: Visualization — R ggplot2

## 1. 概述

ggplot2 是 R 语言最强大的数据可视化包，基于 Grammar of Graphics 语法。

### 核心概念

| 概念 | 说明 |
|------|------|
| `ggplot()` | 初始化画布 |
| `aes()` | 美学映射（x, y, color, fill 等） |
| `geom_*()` | 几何对象（点、线、面等） |
| `theme()` | 主题设置 |
| `facet_*()` | 分面 |

---

## 2. 基础语法

```r
# 基础结构
ggplot(data, aes(x=变量1, y=变量2)) +
  geom_类型() +
  labs(title="标题", x="X轴", y="Y轴") +
  theme_主题()
```

```r
library(ggplot2)

# 散点图示例
ggplot(mtcars, aes(x=disp, y=mpg)) +
  geom_point() +
  labs(title="发动机排量 vs 里程", x="排量", y="英里/加仑")
```

---

## 3. 图形类型

### 3.1 散点图 (Scatterplot)

```r
# 基本散点图
ggplot(midwest, aes(x=area, y=poptotal)) +
  geom_point()

# 添加颜色、大小映射
ggplot(midwest, aes(x=area, y=poptotal, color=state, size=popdensity)) +
  geom_point()

# 添加平滑曲线
ggplot(midwest, aes(x=area, y=poptotal)) +
  geom_point() +
  geom_smooth(method="loess", se=FALSE)

# 抖动点图 (jitter)
ggplot(mpg, aes(x=cty, y=hwy)) +
  geom_jitter(width=0.5, size=1)

# 计数图 (count)
ggplot(mpg, aes(x=cty, y=hwy)) +
  geom_count()
```

### 3.2 线图 (Line Plot)

```r
# 时间序列线图
ggplot(economics, aes(x=date, y=psavert)) +
  geom_line()

# 多条线
ggplot(economics_long, aes(x=date, y=value, color=variable)) +
  geom_line()
```

### 3.3 条形图 (Bar Chart)

```r
# 基本条形图
ggplot(mpg, aes(x=manufacturer)) +
  geom_bar()

# 填充颜色
ggplot(mpg, aes(x=manufacturer, fill=class)) +
  geom_bar(width=0.5)

# 排序条形图
cty_mpg <- aggregate(mpg$cty, by=list(mpg$manufacturer), FUN=mean)
cty_mpg <- cty_mpg[order(cty_mpg$x), ]
ggplot(cty_mpg, aes(x=Group.1, y=x)) +
  geom_bar(stat="identity", fill="tomato3")
```

### 3.4 直方图 (Histogram)

```r
# 自动分箱
ggplot(mpg, aes(x=displ)) +
  geom_histogram()

# 指定分箱数
ggplot(mpg, aes(x=displ)) +
  geom_histogram(bins=5)

# 分类直方图
ggplot(mpg, aes(x=displ, fill=class)) +
  geom_histogram(bins=10)
```

### 3.5 密度图 (Density Plot)

```r
# 密度图
ggplot(mpg, aes(x=cty)) +
  geom_density()

# 分组密度图
ggplot(mpg, aes(x=cty, fill=factor(cyl))) +
  geom_density(alpha=0.8)
```

### 3.6 箱线图 (Boxplot)

```r
# 基本箱线图
ggplot(mpg, aes(x=class, y=cty)) +
  geom_boxplot()

# 带点
ggplot(mpg, aes(x=class, y=cty)) +
  geom_boxplot() +
  geom_dotplot(binaxis='y', stackdir='center', dotsize=0.5)

# 小提琴图
ggplot(mpg, aes(x=class, y=cty)) +
  geom_violin()
```

### 3.7 热图 (Heatmap)

```r
# 相关性热图
library(ggcorrplot)
corr <- cor(mtcars)
ggcorrplot(corr, 
           hc.order=FALSE, 
           type="lower",
           lab=TRUE,
           colors=c("tomato2", "white", "springgreen3"))
```

### 3.8 面积图 (Area Plot)

```r
# 面积图
ggplot(economics[1:100,], aes(x=date, y=psavert)) +
  geom_area()

# 堆叠面积图
ggplot(df, aes(x=date, y=value, fill=variable)) +
  geom_area()
```

### 3.9 饼图 (Pie Chart)

```r
# 饼图
df <- table(mpg$class)
df <- as.data.frame(df)
ggplot(df, aes(x="", y=Freq, fill=Var1)) +
  geom_bar(width=1, stat="identity") +
  coord_polar(theta="y", start=0)
```

### 3.10 树图 (Treemap)

```r
library(treemapify)
ggplot(G20, aes(area=gdp_mil_usd, fill=hdi, label=country)) +
  geom_treemap() +
  geom_treemap_text(fontface="italic", place="centre")
```

---

## 4. 高级图形

### 4.1 分面 (Faceting)

```r
# 按列分面
ggplot(mpg, aes(x=displ, y=cty)) +
  geom_point() +
  facet_wrap(~class)

# 按行和列分面
ggplot(mpg, aes(x=displ, y=cty)) +
  geom_point() +
  facet_grid(year~class)
```

### 4.2 哑铃图 (Dumbbell Plot)

```r
library(ggalt)
ggplot(health, aes(x=pct_2013, xend=pct_2014, y=Area)) +
  geom_dumbbell(color="#a3c4dc", 
                size=0.75,
                point.colour.l="#0e668b")
```

### 4.3 边际图 (Marginal Plot)

```r
library(ggExtra)
g <- ggplot(mpg, aes(cty, hwy)) + geom_count() + geom_smooth(method="lm")

# 边际直方图
ggMarginal(g, type="histogram")

# 边际箱线图
ggMarginal(g, type="boxplot")

# 边际密度图
ggMarginal(g, type="density")
```

### 4.4 双向条形图 (Diverging Bars)

```r
# 偏离条形图
ggplot(mtcars, aes(x=car, y=mpg_z, fill=mpg_type)) +
  geom_bar(stat="identity") +
  coord_flip()
```

### 4.5 棒棒糖图 (Lollipop)

```r
# 棒棒糖图
ggplot(cty_mpg, aes(x=make, y=mileage)) +
  geom_point(size=3) +
  geom_segment(aes(x=make, xend=make, y=0, yend=mileage))
```

### 4.6 环形图 (Donut Chart)

```r
ggplot(df, aes(x=2, y=Freq, fill=Var1)) +
  geom_bar(stat="identity") +
  coord_polar(theta="y") +
  xlim(0.5, 2.5)
```

### 4.7 时间序列日历热图

```r
library(zoo)
ggplot(df, aes(x=week, y=weekday, fill=VIX.Close)) +
  geom_tile(colour="white") +
  facet_grid(year~monthf) +
  scale_fill_gradient(low="red", high="green")
```

---

## 5. 主题与美化

### 5.1 预设主题

```r
theme_set(theme_bw())      # 黑白主题
theme_set(theme_classic()) # 经典主题
theme_set(theme_minimal()) # 简约主题
theme_set(theme_tufte())   # Tufte 主题
```

### 5.2 自定义主题

```r
ggplot(mpg, aes(x=cty, y=hwy)) +
  geom_point() +
  theme(
    plot.title = element_text(hjust=0.5, size=14, face="bold"),
    axis.text.x = element_text(angle=45, vjust=0.6),
    legend.position = "bottom"
  )
```

### 5.3 颜色

```r
# 手动配色
scale_fill_manual(values=c("red", "blue", "green"))

# 调色板
scale_fill_brewer(palette="Set3")
scale_fill_brewer(palette="Dark2")

# 渐变色
scale_fill_gradient(low="red", high="green")
scale_fill_gradient2(low="red", mid="white", high="blue")
```

---

## 6. 单细胞数据可视化

### 6.1 Seurat 基础绘图

```r
library(Seurat)

# DimPlot - UMAP/t-SNE
DimPlot(seu, reduction="umap")
DimPlot(seu, reduction="umap", group.by="seurat_clusters")
DimPlot(seu, reduction="umap", split.by="orig.ident")

# FeaturePlot - 基因表达
FeaturePlot(seu, features=c("CD3D", "CD4", "CD8A"))

# VlnPlot - 小提琴图
VlnPlot(seu, features=c("CD3D", "CD4"))

# DoHeatmap - 热图
DoHeatmap(seu, features=top_genes)

# DotPlot - 点图
DotPlot(seu, features=c("CD3D", "MS4A1"), group.by="seurat_clusters")
```

### 6.2 自定义 Seurat 绘图

```r
# 带边框的点图
FeaturePlot(seu, features="CD3D", outline.color="black", outline.size=1)

# 自定义颜色
FeaturePlot(seu, features="CD3D", cols=c("lightgrey", "red"))

# 多基因
FeaturePlot(seu, features=c("CD3D", "CD4", "CD8A"), ncol=2)
```

---

## 7. 输出与保存

```r
# 保存为 PNG
ggsave("plot.png", width=10, height=8, dpi=300)

# 保存为 PDF
ggsave("plot.pdf", width=10, height=8)

# 保存最近画的图
ggsave("last_plot.png")
```

---

## 8. 示例命令

```
# 基本散点图
帮我画一个散点图，x是displacement，y是mpg

# 带颜色的散点图
按cyl分颜色画一下

# 条形图
按manufacturer画平均cty的条形图

# 热图
画一个mtcars的相关性热图

# Seurat可视化
帮我画一下UMAP和marker基因
```

---

## 9. 常用参数速查

| 函数 | 参数 | 说明 |
|------|------|------|
| `ggplot()` | data, aes() | 数据和美学映射 |
| `geom_point()` | size, color, shape | 点的大小、颜色、形状 |
| `geom_line()` | linetype, size | 线型、粗细 |
| `geom_bar()` | stat, fill, width | 统计变换、填充、宽度 |
| `labs()` | title, subtitle, x, y | 标题和轴标签 |
| `theme()` | plot.title, legend.position | 主题元素 |
| `scale_*_manual()` | values | 手动设置颜色/形状 |
| `facet_wrap()` | ~变量 | 按变量分面 |

---

## 10. 参考资料

- **ggplot2 官网**: https://ggplot2.tidyverse.org
- **R Graphics Cookbook**: https://r-graphics.org
- **ggplot2 cheat sheet**: https://raw.githubusercontent.com/rstudio/cheatsheets/main/data-visualization.pdf
