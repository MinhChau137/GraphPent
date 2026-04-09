#!/usr/bin/env python3
"""
Benchmark Runner - GraphRAG Pentest Evaluation
Chạy tự động 5 scenarios, 3 modes, tính toàn bộ metrics
"""

import asyncio
import httpx
import json
import csv
import time
from pathlib import Path
from datetime import datetime
from tqdm.asyncio import tqdm
from evaluation.config import BenchmarkConfig
from evaluation.scenarios import TEST_SCENARIOS
from app.core.logger import logger

# Import metrics from eval_pipeline
from evaluation.eval_pipeline import GraphRAGEvaluationPipeline, BaseRetriever, RetrievedItem, load_json

config = BenchmarkConfig()
GROUND_TRUTH = load_json("ground_truth.json")


class RealGraphRAGRetriever(BaseRetriever):
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def search(self, query: str, mode: str, top_k: int = 10, alpha: float = 0.7) -> List[RetrievedItem]:
        payload = {
            "query": query,
            "limit": top_k,
            "alpha": alpha
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/retrieve/query",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

        if resp.status_code != 200:
            logger.error(f"API error: {resp.status_code} for query: {query}")
            return []

        data = resp.json()
        results = data.get("results", [])
        return [
            RetrievedItem(
                item_id=r.get("id"),
                score=r.get("score", 0.0),
                text=r.get("text", ""),
                metadata=r.get("metadata", {})
            ) for r in results
        ]

    def correlate_finding(self, finding_text: str, mode: str, top_k: int = 5, alpha: float = 0.7) -> Dict[str, Any]:
        # Implement if needed, for now return empty
        return {
            "matched_cwes": [],
            "matched_cves": [],
            "decision_true_positive": False
        }

async def call_retrieve(query: str, mode: str) -> dict:
    """Call API /retrieve/query với mode tương ứng"""
    alpha = config.alpha_values[mode]

    payload = {
        "query": query,
        "limit": 15,
        "alpha": alpha
    }

    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{config.base_url}/retrieve/query",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
    latency = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        logger.error(f"API error: {resp.status_code} for query: {query}")
        return {"results": [], "latency": latency}

    data = resp.json()
    retrieved_ids = [r.get("id") for r in data.get("results", [])]
    return {
        "results": retrieved_ids,
        "full_results": data.get("results", []),
        "latency": latency,
        "mode": mode
    }


async def run_benchmark():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path("evaluation/results") / f"benchmark_results_{timestamp}.csv"

    Path("evaluation/results").mkdir(parents=True, exist_ok=True)

    results = []

    for scenario in tqdm(TEST_SCENARIOS, desc="Running scenarios"):
        for query in scenario["queries"]:
            for mode_name, alpha in config.alpha_values.items():
                for run in range(config.num_runs):
                    result = await call_retrieve(query, mode_name)

                    # Tính metrics
                    relevant = set(GROUND_TRUTH.get(query, {}).get("relevant_ids", []))

                    row = {
                        "scenario_id": scenario["id"],
                        "scenario_name": scenario["name"],
                        "query": query,
                        "mode": mode_name,
                        "run": run + 1,
                        "latency_ms": round(result["latency"], 2),
                        "precision_5": precision_at_k(result["results"], relevant, 5),
                        "precision_10": precision_at_k(result["results"], relevant, 10),
                        "recall_10": recall_at_k(result["results"], relevant, 10),
                        "mrr": mrr(result["results"], relevant),
                        "ndcg_10": ndcg_at_k(result["results"], relevant, 10),
                        "relevant_count": len(relevant),
                        "retrieved_count": len(result["results"])
                    }
                    results.append(row)

    # Lưu CSV
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    logger.info(f"Benchmark completed. Results saved to {output_file}")
    print(f"\n✅ Benchmark hoàn tất! Kết quả lưu tại: {output_file}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())