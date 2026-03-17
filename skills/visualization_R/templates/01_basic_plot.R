#!/usr/bin/env Rscript
# ==============================================================================
# ggplot2 Visualization Template
# ==============================================================================

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
})

# === Parse arguments ===
args <- commandArgs(trailingOnly = TRUE)

input_file <- args[1] %||% "data.csv"
output_file <- args[2] %||% "result_plot.png"
plot_type <- args[3] %||% "scatter"
x_col <- args[4] %||% "x"
y_col <- args[5] %||% "y"
color_col <- args[6] %||% ""

cat("========================================\n")
cat("  ggplot2 Visualization\n")
cat("========================================\n")
cat("Input:", input_file, "\n")
cat("Plot type:", plot_type, "\n")
cat("X:", x_col, "\n")
cat("Y:", y_col, "\n")
cat("========================================\n\n")

`%||%` <- function(x, y) if (is.null(x)) y else x

# === Load Data ===
cat("[1/2] Loading data...\n")

# Try to load as CSV or use built-in data
if (file.exists(input_file)) {
  data <- read.csv(input_file)
} else {
  # Use mtcars as demo data
  data <- mtcars
  cat("  Using mtcars as demo data\n")
}

cat("  Rows:", nrow(data), "\n")
cat("  Columns:", ncol(data), "\n\n")

# === Create Plot ===
cat("[2/2] Creating plot...\n")

p <- ggplot(data, aes_string(x=x_col, y=y_col))

if (plot_type == "scatter") {
  p <- p + geom_point()
} else if (plot_type == "line") {
  p <- p + geom_line()
} else if (plot_type == "bar") {
  p <- p + geom_bar(stat="identity")
} else if (plot_type == "boxplot") {
  p <- p + geom_boxplot()
} else if (plot_type == "violin") {
  p <- p + geom_violin()
} else if (plot_type == "histogram") {
  p <- p + geom_histogram()
} else if (plot_type == "density") {
  p <- p + geom_density()
} else {
  p <- p + geom_point()  # default
}

# Add color if specified
if (color_col != "" && color_col %in% colnames(data)) {
  p <- p + aes_string(color=color_col)
}

# Add labels
p <- p + labs(title=paste(plot_type, "plot"), x=x_col, y=y_col)

# Set theme
p <- p + theme_bw()

# Save
ggsave(output_file, p, width=10, height=8, dpi=300)

cat("\n========================================\n")
cat("  Complete!\n")
cat("========================================\n")
cat("Output:", output_file, "\n\n")
