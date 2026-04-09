# Benchmark Chart Generator

This script generates multiple types of charts from the benchmark results CSV file for comprehensive analysis and inclusion in reports.

## Usage

1. Ensure the CSV file `evaluation/results/benchmark_results_20260408_212150.csv` exists.
2. Install dependencies: `pip install pandas matplotlib seaborn`
3. Run the script: `python plot_benchmark.py`
4. Charts will be saved in `evaluation/results/charts/` directory

## Generated Charts

1. **precision_bar_chart.png**: Bar chart showing average Precision@10 by query and mode
2. **latency_bar_chart.png**: Bar chart showing average latency (ms) by query and mode
3. **latency_box_plot.png**: Box plot of latency distribution by mode
4. **precision_line_chart.png**: Line chart of Precision@10 over runs for each query and mode
5. **latency_vs_precision_scatter.png**: Scatter plot of latency vs Precision@10, colored by mode and styled by query
6. **latency_histogram.png**: Histogram of latency distribution
7. **recall_bar_chart.png**: Bar chart showing average Recall@10 by query and mode
8. **correlation_heatmap.png**: Heatmap of correlation matrix between numeric metrics

## Description

The charts provide various visualizations of the benchmark data including:
- Performance metrics (precision, recall) across different retrieval modes
- Latency analysis and distributions
- Trends over multiple runs
- Relationships between metrics

## Troubleshooting

- If the CSV file is missing, ensure the evaluation has been run.
- If matplotlib/seaborn fails to save images, check write permissions in the evaluation/results/charts directory.
- For headless environments, all plots are saved without displaying.
- Ensure all dependencies are installed in the Python environment.