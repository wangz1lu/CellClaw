#!/usr/bin/env Rscript
# ============================================================
# OmicsClaw Skill Template Script
# Skill: <skill_name>
# Template: 01_basic_workflow.R
# Description: <基础分析流程>
# ============================================================
#
# 使用说明：
#   这是参考模板，LLM 会根据用户的实际数据路径、参数需求来改写
#   模板中的 <<PLACEHOLDER>> 会被 LLM 替换为实际值
#
# 输出文件命名规则：
#   ⚠️ 所有输出文件名必须以 result_ 开头
#   这样 OmicsClaw 才能自动 SFTP 下载并发送到 Discord
#
# ============================================================

# ── 0. 参数设置 ────────────────────────────────────────────────

input_file  <- "<<INPUT_FILE>>"      # 输入文件路径（绝对路径）
output_dir  <- "<<OUTPUT_DIR>>"      # 输出目录（绝对路径）
species     <- "<<SPECIES>>"         # human / mouse

# ── 1. 加载库 ──────────────────────────────────────────────────

suppressPackageStartupMessages({
    library(核心包)
    # library(依赖包)
})

cat("=== OmicsClaw Skill: <skill_name> ===\n")
cat("输入文件:", input_file, "\n")
cat("输出目录:", output_dir, "\n\n")

# ── 2. 数据加载 ────────────────────────────────────────────────

cat("Step 1: 加载数据...\n")
data <- readRDS(input_file)
cat("  数据维度:", dim(data), "\n")

# ── 3. 核心分析 ────────────────────────────────────────────────

cat("Step 2: 运行分析...\n")
# result <- main_analysis(data)

# ── 4. 可视化 ──────────────────────────────────────────────────

cat("Step 3: 生成可视化...\n")

# PNG — Discord 直接预览
png_file <- file.path(output_dir, "result_skill_main_plot.png")
png(png_file, width = 10, height = 8, units = "in", res = 300)
# plot(result)
dev.off()
cat("  保存:", png_file, "\n")

# PDF — 高清矢量图
pdf_file <- file.path(output_dir, "result_skill_main_plot.pdf")
pdf(pdf_file, width = 10, height = 8)
# plot(result)
dev.off()
cat("  保存:", pdf_file, "\n")

# ── 5. 结果导出 ────────────────────────────────────────────────

cat("Step 4: 导出结果...\n")

# CSV 汇总表
csv_file <- file.path(output_dir, "result_skill_summary.csv")
# write.csv(summary_table, csv_file, row.names = FALSE)
cat("  保存:", csv_file, "\n")

# R 对象（可选，用于后续分析）
rds_file <- file.path(output_dir, "result_skill_object.rds")
# saveRDS(result, rds_file)
cat("  保存:", rds_file, "\n")

cat("\n=== 分析完成！===\n")
