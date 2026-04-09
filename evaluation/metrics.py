import numpy as np
from typing import List, Dict, Any

def precision_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    if not retrieved:
        return 0.0
    retrieved_k = retrieved[:k]
    return len(set(retrieved_k) & set(relevant)) / k

def recall_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    if not relevant:
        return 0.0
    retrieved_k = retrieved[:k]
    return len(set(retrieved_k) & set(relevant)) / len(relevant)

def mrr(retrieved: List[str], relevant: List[str]) -> float:
    for i, item in enumerate(retrieved):
        if item in relevant:
            return 1.0 / (i + 1)
    return 0.0

def ndcg_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    # Simple nDCG implementation (binary relevance)
    dcg = sum(1.0 / np.log2(i + 2) for i, item in enumerate(retrieved[:k]) if item in relevant)
    idcg = sum(1.0 / np.log2(i + 2) for i in range(min(k, len(relevant))))
    return dcg / idcg if idcg > 0 else 0.0

def compute_f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)