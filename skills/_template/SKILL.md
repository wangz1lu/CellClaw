---
name: <Skill 显示名称>
version: 1.0.0
scope: <适用场景简述，如：单细胞降维聚类 / 轨迹推断 / 批次校正>
languages: [R]            # 或 [Python] 或 [R, Python]
triggers: [关键词1, 关键词2, keyword_en, 中文触发词]
# triggers 会被自动匹配：用户消息包含任意一个触发词 → 自动注入此 Skill
---

# Skill: <名称>
# CellClaw Skill Knowledge Base
# Version: 1.0.0
# Author: <你的名字>
# Source: <官方教程链接>
# Scope: <适用场景>

---

## 1. Skill 概述

**简要说明这个分析做什么。** 用 1-3 段话说清楚。

### 适用场景
| 场景 | 说明 |
|------|------|
| 场景 A | 什么时候用这个分析 |
| 场景 B | 另一个使用场景 |

### 工具要求
- **R** ≥ x.x.x 或 **Python** ≥ x.x.x
- **核心包**: `包名` ≥ x.x.x
- **依赖包**: `dep1`, `dep2`, `dep3`

---

## 2. 输入数据要求

### 必需输入
```
数据矩阵格式：什么样的矩阵？归一化/原始？
元数据要求：需要哪些注释列？
物种/基因组：是否影响分析？
```

### 支持的输入格式
| 格式 | 处理方式 |
|------|---------|
| Seurat 对象 (.rds) | 如何提取数据 |
| AnnData (.h5ad) | 如何读取 |
| 10X 目录 | Read10X() |
| CSV/TSV 矩阵 | read.csv() |

### ⚠️ 重要注意事项
- 注意事项 1（如：数据必须归一化）
- 注意事项 2（如：基因名格式要求）

---

## 3. 标准分析流程

### Step 1: 数据加载与预处理
```r
# 伪代码 — LLM 会根据用户实际数据改写
library(核心包)

# 加载数据
data <- readRDS("input.rds")

# 预处理步骤（如有）
data <- preprocess(data)
```

**关键参数说明：**
| 参数 | 默认值 | 说明 |
|------|--------|------|
| param1 | value | 什么意思 |
| param2 | value | 什么意思 |

### Step 2: 核心分析
```r
# 核心分析步骤
result <- main_analysis(data, param1 = "default")
```

**关键参数说明：**
| 参数 | 默认值 | 说明 |
|------|--------|------|
| method | "xxx" | 可选方法及适用场景 |

### Step 3: 可视化
```r
# 可视化输出 — 文件名必须以 result_ 开头！
# 这样 CellClaw 才能自动检测并发送到 Discord

# PNG（Discord 直接预览）
ggsave("result_分析名_图名.png", plot = p, width = 10, height = 8, dpi = 300)

# PDF（高清矢量图，Discord 作为附件下载）
pdf("result_分析名_图名.pdf", width = 10, height = 8)
print(p)
dev.off()
```

### Step 4: 结果导出
```r
# 导出关键结果为 CSV（用户可下载查看）
write.csv(result_table, "result_分析名_summary.csv", row.names = FALSE)

# 导出 R 对象（可用于后续分析）
saveRDS(result, "result_分析名_object.rds")
```

---

## 4. 常见问题与解决方案

### Q1: <常见错误信息>
**原因**: ...
**解决**: ...

### Q2: <另一个常见问题>
**原因**: ...
**解决**: ...

---

## 5. 高级用法（可选）

### 5.1 参数调优
- 什么时候需要调参？
- 推荐的参数范围？

### 5.2 与其他分析的衔接
- 上游：通常在什么分析之后做？
- 下游：结果可以用于什么后续分析？

---

## 6. 参考资料
- 官方文档: <URL>
- 论文: <引用>
- GitHub: <URL>
