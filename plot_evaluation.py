import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
from pathlib import Path

# Set style for better plots
sns.set_style("whitegrid")

# Output directory for plots
output_dir = Path('outputs/charts')
output_dir.mkdir(parents=True, exist_ok=True)

# Load the summary CSVs
retrieval_df = pd.read_csv('outputs/retrieval_summary.csv')
cve_df = pd.read_csv('outputs/cve_linking_summary.csv')
correlation_df = pd.read_csv('outputs/correlation_summary.csv')
multi_hop_df = pd.read_csv('outputs/multi_hop_summary.csv')
remediation_df = pd.read_csv('outputs/remediation_summary.csv')

# 1. Retrieval Metrics Bar Charts
fig, axes = plt.subplots(2, 3, figsize=(18, 12))
fig.suptitle('Retrieval Evaluation Metrics by Mode', fontsize=16)

# Precision@1, @3, @5
retrieval_df.plot(x='mode', y=['precision@1', 'precision@3', 'precision@5'], kind='bar', ax=axes[0,0])
axes[0,0].set_title('Precision@K')
axes[0,0].set_ylabel('Precision')
axes[0,0].legend(loc='upper left')

# Recall@1, @3, @5
retrieval_df.plot(x='mode', y=['recall@1', 'recall@3', 'recall@5'], kind='bar', ax=axes[0,1])
axes[0,1].set_title('Recall@K')
axes[0,1].set_ylabel('Recall')

# Hit@1, @3, @5
retrieval_df.plot(x='mode', y=['hit@1', 'hit@3', 'hit@5'], kind='bar', ax=axes[0,2])
axes[0,2].set_title('Hit@K')
axes[0,2].set_ylabel('Hit Rate')

# NDCG@1, @3, @5
retrieval_df.plot(x='mode', y=['ndcg@1', 'ndcg@3', 'ndcg@5'], kind='bar', ax=axes[1,0])
axes[1,0].set_title('NDCG@K')
axes[1,0].set_ylabel('NDCG')

# MRR
retrieval_df.plot(x='mode', y='mrr', kind='bar', ax=axes[1,1], color='orange')
axes[1,1].set_title('Mean Reciprocal Rank (MRR)')
axes[1,1].set_ylabel('MRR')

# Alpha values
retrieval_df.plot(x='mode', y='alpha', kind='bar', ax=axes[1,2], color='green')
axes[1,2].set_title('Alpha Values')
axes[1,2].set_ylabel('Alpha')

plt.tight_layout()
plt.savefig(output_dir / 'retrieval_metrics.png', dpi=300, bbox_inches='tight')
plt.close()

# 2. CVE Linking Metrics
fig, ax = plt.subplots(figsize=(10, 6))
cve_df.plot(x='mode', y=['precision', 'recall', 'f1'], kind='bar', ax=ax)
ax.set_title('CVE Linking Evaluation Metrics by Mode')
ax.set_ylabel('Score')
ax.legend(loc='upper left')
plt.tight_layout()
plt.savefig(output_dir / 'cve_linking_metrics.png', dpi=300, bbox_inches='tight')
plt.close()

# 3. Finding Correlation Metrics
fig, axes = plt.subplots(1, 2, figsize=(15, 6))
fig.suptitle('Finding Correlation Evaluation Metrics by Mode', fontsize=16)

# CWE metrics
correlation_df.plot(x='mode', y=['cwe_precision', 'cwe_recall', 'cwe_f1'], kind='bar', ax=axes[0])
axes[0].set_title('CWE Metrics')
axes[0].set_ylabel('Score')
axes[0].legend(loc='upper left')

# Decision metrics
correlation_df.plot(x='mode', y=['decision_accuracy', 'false_positive_reduction_rate'], kind='bar', ax=axes[1])
axes[1].set_title('Decision Metrics')
axes[1].set_ylabel('Score')

plt.tight_layout()
plt.savefig(output_dir / 'finding_correlation_metrics.png', dpi=300, bbox_inches='tight')
plt.close()

# 4. Multi-Hop Reasoning Metrics
fig, axes = plt.subplots(1, 2, figsize=(15, 6))
fig.suptitle('Multi-Hop Reasoning Evaluation Metrics by Mode', fontsize=16)

# Accuracy
multi_hop_df.plot(x='mode', y='average_accuracy', kind='bar', ax=axes[0], color='orange')
axes[0].set_title('Average Accuracy')
axes[0].set_ylabel('Accuracy')

# Steps
multi_hop_df.plot(x='mode', y='average_steps', kind='bar', ax=axes[1], color='red')
axes[1].set_title('Average Steps')
axes[1].set_ylabel('Steps')

plt.tight_layout()
plt.savefig(output_dir / 'multi_hop_reasoning_metrics.png', dpi=300, bbox_inches='tight')
plt.close()

# 5. Remediation Quality Metrics
fig, ax = plt.subplots(figsize=(10, 6))
remediation_df.plot(x='mode', y=['precision', 'recall', 'f1'], kind='bar', ax=ax)
ax.set_title('Remediation Quality Evaluation Metrics by Mode')
ax.set_ylabel('Score')
ax.legend(loc='upper left')
plt.tight_layout()
plt.savefig(output_dir / 'remediation_quality_metrics.png', dpi=300, bbox_inches='tight')
plt.close()

# 6. Combined Performance Overview
fig, axes = plt.subplots(3, 2, figsize=(16, 18))
fig.suptitle('Evaluation Performance Overview', fontsize=16)

# Retrieval: Precision@5 and MRR
retrieval_df.plot(x='mode', y=['precision@5', 'mrr'], kind='bar', ax=axes[0,0])
axes[0,0].set_title('Retrieval Performance')
axes[0,0].set_ylabel('Score')

# CVE Linking: F1
cve_df.plot(x='mode', y='f1', kind='bar', ax=axes[0,1], color='skyblue')
axes[0,1].set_title('CVE Linking F1 Score')
axes[0,1].set_ylabel('F1 Score')

# Correlation: CWE F1 and Decision Accuracy
correlation_df.plot(x='mode', y=['cwe_f1', 'decision_accuracy'], kind='bar', ax=axes[1,0])
axes[1,0].set_title('Finding Correlation Performance')
axes[1,0].set_ylabel('Score')

# Multi-Hop: Accuracy and Steps
multi_hop_df.plot(x='mode', y='average_accuracy', kind='bar', ax=axes[1,1], color='orange')
axes[1,1].set_title('Multi-Hop Accuracy')
axes[1,1].set_ylabel('Accuracy')

# Remediation: F1
remediation_df.plot(x='mode', y='f1', kind='bar', ax=axes[2,0], color='purple')
axes[2,0].set_title('Remediation F1 Score')
axes[2,0].set_ylabel('F1 Score')

# Steps comparison
multi_hop_df.plot(x='mode', y='average_steps', kind='bar', ax=axes[2,1], color='red')
axes[2,1].set_title('Multi-Hop Steps')
axes[2,1].set_ylabel('Steps')

plt.tight_layout()
plt.savefig(output_dir / 'performance_overview.png', dpi=300, bbox_inches='tight')
plt.close()

print(f"Charts saved to {output_dir}/")
print("Generated files:")
for file in output_dir.glob('*.png'):
    print(f"  - {file.name}")