#!/usr/bin/env python3
"""
Master Benchmark Runner — GraphPent Full Evaluation
=====================================================
Runs all 4 benchmark suites in sequence and produces a combined summary.

Usage
-----
  # All layers
  python -m evaluation.run_all

  # Single layer only
  python -m evaluation.run_all --layer l3
  python -m evaluation.run_all --layer l4
  python -m evaluation.run_all --layer l5
  python -m evaluation.run_all --layer l6

  # Skip slow layers
  python -m evaluation.run_all --skip l4 --skip l6
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from evaluation.config import BenchmarkConfig

config = BenchmarkConfig()


async def run_l3():
    from evaluation.runner import run_benchmark
    return await run_benchmark()


async def run_l4():
    from evaluation.benchmark_l4_kg_completion import run_l4_benchmark
    return await run_l4_benchmark()


async def run_l5():
    from evaluation.benchmark_l5_gnn import run_l5_benchmark
    return await run_l5_benchmark()


async def run_l6():
    from evaluation.benchmark_l6_reasoning import run_l6_benchmark
    return await run_l6_benchmark()


LAYER_RUNNERS = {
    "l3": ("L3 GraphRAG Retrieval",  run_l3),
    "l4": ("L4 KG Completion",       run_l4),
    "l5": ("L5 GNN Risk Scoring",    run_l5),
    "l6": ("L6 Reasoning Pipeline",  run_l6),
}


def _extract_key_metrics(layer: str, result) -> dict:
    """Pull the single most important metric from each layer's result."""
    try:
        if layer == "l3":
            # result is list of CSV rows
            rows = result if isinstance(result, list) else []
            g03_rows = [r for r in rows if r.get("mode") == "G_0.3"]
            ndcg_vals = [r["NDCG@10"] for r in g03_rows if "NDCG@10" in r]
            return {
                "primary_metric": "NDCG@10 (G-0.3)",
                "value": round(sum(ndcg_vals) / len(ndcg_vals), 4) if ndcg_vals else None,
            }
        elif layer == "l4":
            rows = result.get("throughput", [{}])
            row10 = next((r for r in rows if r.get("label") == "batch-10"), rows[0] if rows else {})
            return {
                "primary_metric": "Yield Rate (batch-10)",
                "value": row10.get("yield_rate"),
                "idempotency": result.get("idempotency", {}).get("idempotency_score"),
                "conflicts_detected": result.get("conflict_detection", {}).get("total_conflicts"),
            }
        elif layer == "l5":
            calib = result.get("cvss_calibration", {})
            dist  = result.get("score_distribution", {})
            recall = result.get("known_node_recall", {})
            paths = result.get("attack_paths", [])
            valid_paths = [p for p in paths if p.get("validity_rate", 0) > 0]
            return {
                "primary_metric": "Spearman rho (CVSS vs risk_score)",
                "value": calib.get("spearman_rho"),
                "tier_accuracy": calib.get("tier_accuracy"),
                "risk_boundedness": dist.get("risk_boundedness"),
                "known_recall_at_20": recall.get("recall_at_20"),
                "attack_path_coverage": round(len(valid_paths) / len(paths), 4) if paths else None,
            }
        elif layer == "l6":
            agg = result.get("aggregate", {})
            return {
                "primary_metric": "Completion Rate",
                "value": agg.get("M6_completion_rate"),
                "tool_accuracy": agg.get("M1_tool_selection_accuracy"),
                "graph_utilization": agg.get("M2_graph_utilization_rate"),
                "report_completeness": agg.get("M3_avg_report_completeness"),
                "latency_p50_ms": agg.get("M5_latency_p50_ms"),
            }
    except Exception as e:
        return {"error": str(e)}
    return {}


async def main():
    parser = argparse.ArgumentParser(description="GraphPent Full Benchmark Runner")
    parser.add_argument("--layer", choices=["l3", "l4", "l5", "l6"],
                        help="Run only this layer (default: all)")
    parser.add_argument("--skip", action="append", default=[],
                        choices=["l3", "l4", "l5", "l6"],
                        help="Skip this layer (repeatable)")
    args = parser.parse_args()

    layers_to_run = (
        [args.layer] if args.layer
        else [k for k in LAYER_RUNNERS if k not in args.skip]
    )

    print("=" * 76)
    print("  GraphPent Full Benchmark Suite")
    print(f"  Layers: {', '.join(layers_to_run).upper()}")
    print(f"  Date:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 76)

    all_results = {}
    timings = {}

    for layer_key in layers_to_run:
        label, runner_fn = LAYER_RUNNERS[layer_key]
        print(f"\n{'='*76}")
        print(f"  Running {label}")
        print(f"{'='*76}")
        t0 = time.perf_counter()
        try:
            result = await runner_fn()
            elapsed = time.perf_counter() - t0
            all_results[layer_key] = result
            timings[layer_key] = round(elapsed, 1)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            print(f"\n[ERROR] {label} failed: {exc}")
            all_results[layer_key] = {"error": str(exc)}
            timings[layer_key] = round(elapsed, 1)

    # Final combined summary
    print("\n" + "=" * 76)
    print("  COMBINED BENCHMARK SUMMARY")
    print("=" * 76)
    print(f"{'Layer':<8} {'Name':<32} {'Primary Metric':<30} {'Value':>8} {'Time':>7}")
    print("-" * 76)
    for layer_key in layers_to_run:
        label = LAYER_RUNNERS[layer_key][0]
        metrics = _extract_key_metrics(layer_key, all_results.get(layer_key, {}))
        val = metrics.get("value")
        val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
        elapsed_str = f"{timings.get(layer_key, 0):.0f}s"
        print(f"{layer_key.upper():<8} {label:<32} "
              f"{metrics.get('primary_metric', 'N/A'):<30} "
              f"{val_str:>8} {elapsed_str:>7}")
        # Print secondary metrics
        for k, v in metrics.items():
            if k in ("primary_metric", "value"):
                continue
            if v is not None:
                v_str = f"{v:.4f}" if isinstance(v, float) else str(v)
                print(f"{'':8} {'':32}   {k:<28} {v_str:>8}")
    print("=" * 76)

    # Save combined results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(config.output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    out_file = results_dir / f"benchmark_all_{timestamp}.json"

    combined = {
        "benchmark": "GraphPent_Full",
        "timestamp": timestamp,
        "layers_run": layers_to_run,
        "timings_sec": timings,
        "results": {
            k: _extract_key_metrics(k, v)
            for k, v in all_results.items()
        },
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
    print(f"\nCombined summary saved: {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
