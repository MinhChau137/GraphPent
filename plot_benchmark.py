import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import glob

# Set style for better plots
sns.set_style("whitegrid")

# Find the latest benchmark results CSV
results_dir = 'evaluation/results'
csv_pattern = os.path.join(results_dir, 'benchmark_results_*.csv')
csv_files = glob.glob(csv_pattern)
if not csv_files:
    raise FileNotFoundError(f"No CSV files found in {results_dir}")

# Get the latest file by modification time
latest_csv = max(csv_files, key=os.path.getmtime)
print(f"Using latest CSV: {latest_csv}")

# Load the benchmark results CSV
df = pd.read_csv(latest_csv)

# Ensure output directory exists
output_dir = 'evaluation/results/charts'
os.makedirs(output_dir, exist_ok=True)

# 1. Bar Chart: Average Precision@10 by Query and Mode
grouped_precision = df.groupby(['query', 'mode'])['precision_10'].mean().unstack()
plt.figure(figsize=(10, 6))
grouped_precision.plot(kind='bar', ax=plt.gca())
plt.title('Average Precision@10 by Query and Mode')
plt.ylabel('Precision@10')
plt.xlabel('Query')
plt.legend(title='Mode')
plt.tight_layout()
plt.savefig(f'{output_dir}/precision_bar_chart.png')
plt.close()

# 2. Bar Chart: Average Latency by Query and Mode
grouped_latency = df.groupby(['query', 'mode'])['latency_ms'].mean().unstack()
plt.figure(figsize=(10, 6))
grouped_latency.plot(kind='bar', ax=plt.gca())
plt.title('Average Latency (ms) by Query and Mode')
plt.ylabel('Latency (ms)')
plt.xlabel('Query')
plt.legend(title='Mode')
plt.tight_layout()
plt.savefig(f'{output_dir}/latency_bar_chart.png')
plt.close()

# 3. Box Plot: Latency Distribution by Mode
plt.figure(figsize=(10, 6))
sns.boxplot(data=df, x='mode', y='latency_ms')
plt.title('Latency Distribution by Mode')
plt.ylabel('Latency (ms)')
plt.xlabel('Mode')
plt.tight_layout()
plt.savefig(f'{output_dir}/latency_box_plot.png')
plt.close()

# 4. Line Chart: Precision@10 over Runs for each Query and Mode
plt.figure(figsize=(12, 8))
for query in df['query'].unique():
    for mode in df['mode'].unique():
        subset = df[(df['query'] == query) & (df['mode'] == mode)]
        plt.plot(subset['run'], subset['precision_10'], label=f'{query} - {mode}', marker='o')
plt.title('Precision@10 over Runs')
plt.ylabel('Precision@10')
plt.xlabel('Run')
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig(f'{output_dir}/precision_line_chart.png')
plt.close()

# 5. Scatter Plot: Latency vs Precision@10
plt.figure(figsize=(10, 6))
sns.scatterplot(data=df, x='latency_ms', y='precision_10', hue='mode', style='query')
plt.title('Latency vs Precision@10')
plt.xlabel('Latency (ms)')
plt.ylabel('Precision@10')
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig(f'{output_dir}/latency_vs_precision_scatter.png')
plt.close()

# 6. Histogram: Distribution of Latency
plt.figure(figsize=(10, 6))
plt.hist(df['latency_ms'], bins=20, edgecolor='black')
plt.title('Distribution of Latency (ms)')
plt.xlabel('Latency (ms)')
plt.ylabel('Frequency')
plt.tight_layout()
plt.savefig(f'{output_dir}/latency_histogram.png')
plt.close()

# 7. Bar Chart: Average Recall@10 by Query and Mode
grouped_recall = df.groupby(['query', 'mode'])['recall_10'].mean().unstack()
plt.figure(figsize=(10, 6))
grouped_recall.plot(kind='bar', ax=plt.gca())
plt.title('Average Recall@10 by Query and Mode')
plt.ylabel('Recall@10')
plt.xlabel('Query')
plt.legend(title='Mode')
plt.tight_layout()
plt.savefig(f'{output_dir}/recall_bar_chart.png')
plt.close()

# 8. Heatmap: Correlation Matrix of Metrics
numeric_cols = ['latency_ms', 'precision_5', 'precision_10', 'recall_10', 'mrr', 'ndcg_10']
corr = df[numeric_cols].corr()
plt.figure(figsize=(8, 6))
sns.heatmap(corr, annot=True, cmap='coolwarm', vmin=-1, vmax=1)
plt.title('Correlation Matrix of Metrics')
plt.tight_layout()
plt.savefig(f'{output_dir}/correlation_heatmap.png')
plt.close()

print(f"All charts saved to {output_dir}/")