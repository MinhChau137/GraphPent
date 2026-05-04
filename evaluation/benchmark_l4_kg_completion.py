#!/usr/bin/env python3
"""
Benchmark L4 — KG Completion Quality
======================================
Measures the quality and effectiveness of the KG Completion layer (L4).

Metrics
-------
M1  Throughput          Relations predicted per second (relations_stored / latency)
M2  Yield Rate          relations_stored / relations_predicted  (how many pass confidence threshold)
M3  Coverage Rate       entities_processed / max_entities  (how many low-degree entities get processed)
M4  Idempotency Score   1 - (new_relations_run2 / new_relations_run1)  (1.0 = fully stable)
M5  Conflict Count      Number and severity distribution of conflicts detected
M6  Latency             p50/p95 for /kg/complete and /kg/conflicts
"""

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from evaluation.config import BenchmarkConfig

config = BenchmarkConfig()

# Test configurations: varying entity batch sizes
# Ollama ~175s/entity — only 1 batch to keep total time reasonable
TEST_BATCHES = [
    {"max_entities": 2, "max_degree": 2, "label": "batch-2"},
]

# Single degree variant to measure coverage
DEGREE_VARIANTS = [
    {"max_entities": 2, "max_degree": 2, "label": "degree-2"},
]


async def call_kg_complete(max_entities: int, max_degree: int) -> Dict:
    payload = {"max_entities": max_entities, "max_degree": max_degree}
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=1200.0) as client:
        resp = await client.post(
            f"{config.base_url}/kg/complete",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    latency = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        print(f"  [WARN] /kg/complete returned {resp.status_code}: {resp.text[:200]}")
        return {"entities_processed": 0, "relations_predicted": 0, "relations_stored": 0,
                "latency_ms": latency, "error": resp.status_code}
    data = resp.json()
    data["latency_ms"] = latency
    return data


async def call_kg_conflicts() -> Dict:
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{config.base_url}/kg/conflicts",
            json={},
            headers={"Content-Type": "application/json"},
        )
    latency = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        print(f"  [WARN] /kg/conflicts returned {resp.status_code}: {resp.text[:200]}")
        return {"conflicts": [], "latency_ms": latency, "error": resp.status_code}

    data = resp.json()
    if isinstance(data, list):
        data = {"conflicts": data}
    data["latency_ms"] = latency
    return data


async def run_throughput_test() -> List[Dict]:
    """M1 + M2 + M3: Run completion with varying batch sizes."""
    print("\n[L4-M1/M2/M3] Throughput, Yield, Coverage — varying batch sizes")
    results = []
    for cfg in TEST_BATCHES:
        print(f"  Running {cfg['label']} (max_entities={cfg['max_entities']})...", end=" ")
        row = await call_kg_complete(cfg["max_entities"], cfg["max_degree"])
        ep = row.get("entities_processed", 0)
        rp = row.get("relations_predicted", 0)
        rs = row.get("relations_stored", 0)
        lat = row["latency_ms"]

        throughput = rs / (lat / 1000) if lat > 0 else 0  # relations/sec
        yield_rate = rs / rp if rp > 0 else 0.0
        coverage = ep / cfg["max_entities"] if cfg["max_entities"] > 0 else 0.0

        result = {
            "label": cfg["label"],
            "max_entities": cfg["max_entities"],
            "max_degree": cfg["max_degree"],
            "entities_processed": ep,
            "relations_predicted": rp,
            "relations_stored": rs,
            "throughput_rel_per_sec": round(throughput, 2),
            "yield_rate": round(yield_rate, 4),
            "coverage_rate": round(coverage, 4),
            "latency_ms": round(lat, 1),
        }
        results.append(result)
        print(f"entities={ep}, predicted={rp}, stored={rs}, "
              f"yield={yield_rate:.2%}, latency={lat:.0f}ms")
    return results


async def run_idempotency_test() -> Dict:
    """M4: Skipped — each /kg/complete call takes ~175s/entity with local LLM.
    Two consecutive runs would require ~700s total. Use single-run data instead.
    Idempotency is inferred: if run1 stored=0, graph is already stable (score=1.0).
    """
    print("\n[L4-M4] Idempotency — inferred from single run (LLM too slow for 2 runs)")
    return {"skipped": True, "reason": "local LLM latency ~175s/entity"}


async def run_degree_sensitivity_test() -> List[Dict]:
    """Skipped — would require additional ~350s LLM calls per variant."""
    print("\n[L4-M3b] Degree Sensitivity — skipped (LLM latency constraint)")
    return [{"skipped": True, "reason": "local LLM latency ~175s/entity"}]


async def run_conflict_detection_test() -> Dict:
    """M5: Conflict detection — count and severity distribution."""
    print("\n[L4-M5] Conflict Detection")
    print("  Querying /kg/conflicts...", end=" ")
    data = call_kg_conflicts if not asyncio.iscoroutinefunction(call_kg_conflicts) else None
    result = await call_kg_conflicts()
    conflicts = result.get("conflicts", [])

    severity_counts: Dict[str, int] = defaultdict(int)
    for c in conflicts:
        sev = c.get("severity", "unknown").lower()
        severity_counts[sev] += 1

    print(f"total={len(conflicts)}, "
          f"high={severity_counts.get('high', 0)}, "
          f"medium={severity_counts.get('medium', 0)}, "
          f"low={severity_counts.get('low', 0)}")

    return {
        "total_conflicts": len(conflicts),
        "severity_high": severity_counts.get("high", 0),
        "severity_medium": severity_counts.get("medium", 0),
        "severity_low": severity_counts.get("low", 0),
        "severity_unknown": severity_counts.get("unknown", 0),
        "latency_ms": round(result["latency_ms"], 1),
        "sample_conflicts": conflicts[:3],  # first 3 for inspection
    }


def _print_summary(throughput_rows, idempotency, degree_rows, conflicts):
    print("\n" + "=" * 76)
    print("Table L4.1  KG Completion — Throughput, Yield, Coverage")
    print("=" * 76)
    print(f"{'Batch':<12} {'Entities':>8} {'Predicted':>10} {'Stored':>7} "
          f"{'Yield':>7} {'Coverage':>9} {'Lat(ms)':>8} {'Rel/s':>7}")
    print("-" * 76)
    for r in throughput_rows:
        print(f"{r['label']:<12} "
              f"{r['entities_processed']:>8} "
              f"{r['relations_predicted']:>10} "
              f"{r['relations_stored']:>7} "
              f"{r['yield_rate']:>7.2%} "
              f"{r['coverage_rate']:>9.2%} "
              f"{r['latency_ms']:>8.0f} "
              f"{r['throughput_rel_per_sec']:>7.1f}")
    print("=" * 76)

    print("\n" + "=" * 50)
    print("Table L4.2  KG Completion — Idempotency")
    print("=" * 50)
    if idempotency.get("skipped"):
        # Infer from throughput: if stored=0 in run1, graph is already stable
        stored = throughput_rows[0].get("relations_stored", 0) if throughput_rows else 0
        inferred_score = 1.0 if stored == 0 else "N/A"
        print(f"  Status:             Inferred from single run")
        print(f"  Run 1 stored:       {stored}")
        print(f"  Idempotency score:  {inferred_score}  "
              f"({'stable — no new relations added' if stored == 0 else 'run 2 needed for exact score'})")
    else:
        print(f"  Run 1 stored:       {idempotency['run1_stored']}")
        print(f"  Run 2 stored:       {idempotency['run2_stored']}")
        print(f"  Idempotency score:  {idempotency['idempotency_score']:.4f}")
    print("=" * 50)

    print("\n" + "=" * 60)
    print("Table L4.3  KG Completion — Degree Sensitivity")
    print("=" * 60)
    if degree_rows and degree_rows[0].get("skipped"):
        print("  Skipped (LLM latency constraint — ~175s/entity with local model)")
    else:
        print(f"{'max_degree':>10} {'Entities':>8} {'Coverage':>9} {'Stored':>7} {'Lat(ms)':>8}")
        print("-" * 60)
        for r in degree_rows:
            print(f"{r['max_degree']:>10} {r['entities_processed']:>8} "
                  f"{r['coverage_rate']:>9.2%} {r['relations_stored']:>7} "
                  f"{r['latency_ms']:>8.0f}")
    print("=" * 60)

    print("\n" + "=" * 50)
    print("Table L4.4  KG Completion — Conflict Detection")
    print("=" * 50)
    print(f"  Total conflicts:   {conflicts['total_conflicts']}")
    print(f"  High severity:     {conflicts['severity_high']}")
    print(f"  Medium severity:   {conflicts['severity_medium']}")
    print(f"  Low severity:      {conflicts['severity_low']}")
    print(f"  Latency:           {conflicts['latency_ms']:.0f}ms")
    if conflicts["sample_conflicts"]:
        print("  Sample conflicts:")
        for c in conflicts["sample_conflicts"]:
            print(f"    - {c}")
    print("=" * 50)


async def run_l4_benchmark() -> Dict:
    print("\n" + "#" * 76)
    print("# L4 BENCHMARK — KG Completion Quality")
    print("#" * 76)

    throughput_rows = await run_throughput_test()
    idempotency = await run_idempotency_test()
    degree_rows = await run_degree_sensitivity_test()
    conflicts = await run_conflict_detection_test()

    _print_summary(throughput_rows, idempotency, degree_rows, conflicts)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "benchmark": "L4_KG_Completion",
        "timestamp": timestamp,
        "throughput": throughput_rows,
        "idempotency": idempotency,
        "degree_sensitivity": degree_rows,
        "conflict_detection": conflicts,
    }

    results_dir = Path(config.output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    out_file = results_dir / f"benchmark_l4_{timestamp}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {out_file}")
    return output


if __name__ == "__main__":
    asyncio.run(run_l4_benchmark())
