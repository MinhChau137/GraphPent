#!/usr/bin/env python3
"""
Benchmark Runner - GraphRAG Pentest Evaluation
Chạy 5 scenarios × 7 modes × num_runs, tính toàn bộ metrics, in bảng kết quả.
"""

import asyncio
import httpx
import json
import csv
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import List, Dict

try:
    from tqdm.asyncio import tqdm
except ImportError:
    tqdm = None

from evaluation.config import BenchmarkConfig
from evaluation.scenarios import TEST_SCENARIOS
from evaluation.ground_truth import load_ground_truth
from evaluation.metrics import precision_at_k, recall_at_k, mrr, ndcg_at_k, compute_f1

config = BenchmarkConfig()
GROUND_TRUTH = load_ground_truth()

# Maps config mode keys → API {mode, alpha} payload fields
MODE_MAP: Dict[str, Dict] = {
    "B1_vector_only": {"mode": "vector_only", "alpha": 1.0},
    "B2_graph_only":  {"mode": "graph_only",  "alpha": 0.0},
    "G_0.1":          {"mode": "hybrid",       "alpha": 0.1},
    "G_0.2":          {"mode": "hybrid",       "alpha": 0.2},
    "G_0.3":          {"mode": "hybrid",       "alpha": 0.3},
    "G_0.5":          {"mode": "hybrid",       "alpha": 0.5},
    "G_0.7":          {"mode": "hybrid",       "alpha": 0.7},
}

# Display labels for paper tables
MODE_LABELS: Dict[str, str] = {
    "B1_vector_only": "B1 (Vector-only)",
    "B2_graph_only":  "B2 (Graph-only)",
    "G_0.1":          "G-0.1 (Hybrid)",
    "G_0.2":          "G-0.2 (Hybrid)",
    "G_0.3":          "G-0.3 (Hybrid) *",
    "G_0.5":          "G-0.5 (Hybrid) *",
    "G_0.7":          "G-0.7 (Hybrid)",
}


async def call_retrieve(query: str, mode_key: str) -> dict:
    """Call API /retrieve/query with correct mode and alpha."""
    api_params = MODE_MAP[mode_key]
    payload = {
        "query": query,
        "limit": 20,
        "mode": api_params["mode"],
        "alpha": api_params["alpha"],
        "use_cache": False,
    }

    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{config.base_url}/retrieve/query",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    latency = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        print(f"[WARN] API {resp.status_code} for query={query!r} mode={mode_key}")
        return {"results": [], "latency": latency}

    data = resp.json()
    retrieved_ids = [
        r.get("id") or r.get("cve_id") or r.get("cwe_id") or r.get("name", "")
        for r in data.get("results", [])
    ]
    return {"results": retrieved_ids, "latency": latency}


async def run_benchmark():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(config.output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    output_file = results_dir / f"benchmark_{timestamp}.csv"

    rows = []
    scenarios_iter = TEST_SCENARIOS
    if tqdm:
        scenarios_iter = tqdm(TEST_SCENARIOS, desc="Scenarios")

    for scenario in scenarios_iter:
        for query in scenario["queries"]:
            relevant = GROUND_TRUTH.get(query, {}).get("relevant_ids", [])
            for mode_key in MODE_MAP:
                latencies = []
                p5_vals, r5_vals = [], []
                p10_vals, r10_vals, mrr_vals, ndcg_vals = [], [], [], []

                for run in range(config.num_runs):
                    result = await call_retrieve(query, mode_key)
                    latencies.append(result["latency"])
                    ids = result["results"]
                    p5_vals.append(precision_at_k(ids, relevant, 5))
                    r5_vals.append(recall_at_k(ids, relevant, 5))
                    p10_vals.append(precision_at_k(ids, relevant, 10))
                    r10_vals.append(recall_at_k(ids, relevant, 10))
                    mrr_vals.append(mrr(ids, relevant))
                    ndcg_vals.append(ndcg_at_k(ids, relevant, 10))

                p10_avg = sum(p10_vals) / len(p10_vals)
                r10_avg = sum(r10_vals) / len(r10_vals)
                row = {
                    "scenario_id":    scenario["id"],
                    "scenario_name":  scenario["name"],
                    "query":          query,
                    "mode":           mode_key,
                    "alpha":          MODE_MAP[mode_key]["alpha"],
                    "latency_avg_ms": round(sum(latencies) / len(latencies), 1),
                    "P@5":            round(sum(p5_vals) / len(p5_vals), 4),
                    "R@5":            round(sum(r5_vals) / len(r5_vals), 4),
                    "P@10":           round(p10_avg, 4),
                    "R@10":           round(r10_avg, 4),
                    "F1@10":          round(compute_f1(p10_avg, r10_avg), 4),
                    "MRR":            round(sum(mrr_vals) / len(mrr_vals), 4),
                    "NDCG@10":        round(sum(ndcg_vals) / len(ndcg_vals), 4),
                    "relevant_count": len(relevant),
                }
                rows.append(row)

    # Save full CSV
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nResults saved: {output_file}")
    _print_summary(rows)
    return rows


def _print_summary(rows: List[dict]):
    """Print aggregated tables matching the paper (Table 3 and Table 4)."""

    # --- Table 3: average across all scenarios per mode ---
    agg: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        m = r["mode"]
        agg[m]["P@5"].append(r["P@5"])
        agg[m]["R@5"].append(r["R@5"])
        agg[m]["P@10"].append(r["P@10"])
        agg[m]["R@10"].append(r["R@10"])
        agg[m]["F1@10"].append(r["F1@10"])
        agg[m]["MRR"].append(r["MRR"])
        agg[m]["NDCG@10"].append(r["NDCG@10"])
        agg[m]["latency"].append(r["latency_avg_ms"])

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0.0

    print("\n" + "=" * 88)
    print("Table 3. Retrieval Comparison (avg across all scenarios)")
    print("=" * 88)
    hdr = (f"{'Mode':<22} {'P@5':>5} {'R@5':>5} {'P@10':>6} {'R@10':>6} "
           f"{'F1@10':>6} {'MRR':>6} {'NDCG@10':>8} {'Latency':>9}")
    print(hdr)
    print("-" * 88)

    best_ndcg = max(avg(agg[m]["NDCG@10"]) for m in MODE_MAP if agg[m]["NDCG@10"])
    for mode_key in MODE_MAP:
        d = agg[mode_key]
        if not d["P@10"]:
            continue
        label = MODE_LABELS.get(mode_key, mode_key)
        ndcg_val = avg(d["NDCG@10"])
        marker = " <--" if abs(ndcg_val - best_ndcg) < 0.0001 else ""
        print(
            f"{label:<22} "
            f"{avg(d['P@5']):>5.4f} "
            f"{avg(d['R@5']):>5.4f} "
            f"{avg(d['P@10']):>6.4f} "
            f"{avg(d['R@10']):>6.4f} "
            f"{avg(d['F1@10']):>6.4f} "
            f"{avg(d['MRR']):>6.4f} "
            f"{ndcg_val:>8.4f} "
            f"{avg(d['latency']):>8.1f}ms"
            f"{marker}"
        )

    # --- Table 4: NDCG@10 per scenario (B1, B2, best hybrid G_0.3) ---
    key_modes = ["B1_vector_only", "B2_graph_only", "G_0.3"]
    scenario_ndcg: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["mode"] in key_modes:
            scenario_ndcg[r["scenario_name"]][r["mode"]].append(r["NDCG@10"])

    print("\n" + "=" * 72)
    print("Table 4. NDCG@10 per Scenario")
    print("=" * 72)
    print(f"{'Scenario':<28} {'B1 (Vector)':>12} {'B2 (Graph)':>12} {'G-0.3 (Hybrid)':>15}")
    print("-" * 72)
    for sc in TEST_SCENARIOS:
        name = sc["name"]
        d = scenario_ndcg.get(name, {})
        b1 = avg(d.get("B1_vector_only", [0]))
        b2 = avg(d.get("B2_graph_only", [0]))
        g3 = avg(d.get("G_0.3", [0]))
        best = max(b1, b2, g3)
        markers = {b1: " *" if b1 == best else "",
                   b2: " *" if b2 == best else "",
                   g3: " *" if g3 == best else ""}
        print(f"{name:<28} {b1:>12.4f}{markers[b1]:2s} "
              f"{b2:>10.4f}{markers[b2]:2s} "
              f"{g3:>13.4f}{markers[g3]:2s}")
    print("=" * 72)

    # --- Alpha comparison table (find optimal alpha) ---
    hybrid_modes = [m for m in MODE_MAP if m.startswith("G_")]
    print("\n" + "=" * 60)
    print("Table 5. Alpha Optimization (Hybrid modes)")
    print("=" * 60)
    print(f"{'Mode':<18} {'alpha':>6} {'NDCG@10':>9} {'P@10':>7} {'MRR':>7}")
    print("-" * 60)
    for mode_key in ["B2_graph_only"] + hybrid_modes + ["B1_vector_only"]:
        d = agg[mode_key]
        if not d["NDCG@10"]:
            continue
        alpha = MODE_MAP[mode_key]["alpha"]
        ndcg_val = avg(d["NDCG@10"])
        label = MODE_LABELS.get(mode_key, mode_key)
        marker = " <--" if abs(ndcg_val - best_ndcg) < 0.0001 else ""
        print(f"{label:<18} {alpha:>6.1f} {ndcg_val:>9.4f} "
              f"{avg(d['P@10']):>7.4f} {avg(d['MRR']):>7.4f}{marker}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
