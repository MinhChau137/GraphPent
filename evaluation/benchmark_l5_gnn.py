#!/usr/bin/env python3
"""
Benchmark L5 — GNN Risk Scoring Quality
=========================================
Measures the quality of the GNN layer (L5) risk scoring, node prioritization,
and attack path discovery.

Metrics
-------
M1  CVSS Calibration       Spearman ρ(risk_score, cvss_score) for CVE nodes
M2  Tier Accuracy          % nodes where risk_tier matches expected CVSS severity band
M3  High-CVE Precision@K   % of top-K risk nodes with cvss_score >= threshold
M4  Risk Boundedness       % nodes with risk_score in [0, 1]  (should be 100%)
M5  Tier Distribution      CRITICAL > HIGH > MEDIUM > LOW  (expected ordering)
M6  Attack Path Validity   % paths with hops > 0 and path_risk > 0
M7  Attack Path Coverage   Distinct source→target pairs found / test pairs requested
M8  Latency                Per-endpoint timing: compute-scores, high-risk-nodes, attack-paths
"""

import asyncio
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Dict, List, Optional, Tuple

import httpx

from evaluation.config import BenchmarkConfig

config = BenchmarkConfig()

# CVSS → expected risk_tier mapping (generous: allow one tier above/below)
# System tiers: CRITICAL >=0.75, HIGH >=0.50, MEDIUM >=0.25, LOW <0.25
CVSS_TIER_EXPECTED: List[Tuple[float, float, List[str]]] = [
    # (cvss_min, cvss_max, acceptable_tiers)
    (9.0, 10.0, ["CRITICAL"]),
    (7.0,  8.9, ["CRITICAL", "HIGH"]),
    (4.0,  6.9, ["HIGH", "MEDIUM"]),
    (0.1,  3.9, ["MEDIUM", "LOW"]),
]

# Known high-risk nodes that should appear in top-K (from ground truth)
KNOWN_HIGH_RISK_IDS = {
    "cwe-89",   # SQL Injection — broad impact
    "cwe-79",   # XSS — highly prevalent
    "cwe-287",  # Improper Authentication
    "cwe-352",  # CSRF
    "cwe-639",  # IDOR / Authorization Bypass
}

# Attack path test cases: (source_id, target_label)
ATTACK_PATH_TESTS = [
    {"source_id": "cwe-89",  "target_label": "CVE",      "max_hops": 3, "label": "SQLi->CVE"},
    {"source_id": "cwe-79",  "target_label": "CVE",      "max_hops": 3, "label": "XSS->CVE"},
    {"source_id": "cwe-287", "target_label": "CVE",      "max_hops": 4, "label": "Auth->CVE"},
    {"source_id": "cwe-352", "target_label": "CVE",      "max_hops": 3, "label": "CSRF->CVE"},
    {"source_id": "cwe-89",  "target_label": "Weakness", "max_hops": 2, "label": "SQLi->Weakness"},
]


async def compute_risk_scores() -> Dict:
    """Call POST /risk/compute-scores and return result + latency."""
    print("  Computing risk scores...", end=" ", flush=True)
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{config.base_url}/risk/compute-scores")
    latency = (time.perf_counter() - start) * 1000
    if resp.status_code != 200:
        print(f"FAILED ({resp.status_code})")
        return {"error": resp.status_code, "latency_ms": latency}
    data = resp.json()
    data["latency_ms"] = latency
    print(f"OK ({latency:.0f}ms) — method={data.get('pagerank', {}).get('method', '?')}, "
          f"nodes={data.get('pagerank', {}).get('nodes_updated', '?')}")
    return data


async def get_high_risk_nodes(limit: int = 200) -> Tuple[List[Dict], float]:
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{config.base_url}/risk/high-risk-nodes",
                                params={"limit": limit})
    latency = (time.perf_counter() - start) * 1000
    if resp.status_code != 200:
        print(f"  [WARN] /risk/high-risk-nodes {resp.status_code}: {resp.text[:100]}")
        return [], latency
    data = resp.json()
    nodes = data if isinstance(data, list) else data.get("nodes", data.get("results", []))
    return nodes, latency


async def call_attack_paths(source_id: str, target_label: str, max_hops: int) -> Tuple[List[Dict], float]:
    payload = {"source_id": source_id, "target_label": target_label, "max_hops": max_hops}
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{config.base_url}/risk/attack-paths", json=payload)
    latency = (time.perf_counter() - start) * 1000
    if resp.status_code != 200:
        return [], latency
    data = resp.json()
    paths = data if isinstance(data, list) else data.get("paths", data.get("results", []))
    return paths, latency


def _cvss_to_expected_tier(cvss: float) -> List[str]:
    for lo, hi, tiers in CVSS_TIER_EXPECTED:
        if lo <= cvss <= hi:
            return tiers
    return ["LOW"]


def run_m1_m2_m3(nodes: List[Dict]) -> Dict:
    """CVSS Calibration (M1), Tier Accuracy (M2), High-CVE Precision@K (M3)."""

    # Extract CVE nodes that have cvss_score
    cve_with_cvss = []
    for n in nodes:
        label = n.get("label", "").upper()
        node_id = str(n.get("id", "")).upper()
        # Identify CVE nodes by label or ID prefix
        is_cve = label == "CVE" or node_id.startswith("CVE-")
        if not is_cve:
            continue
        # Look for cvss_score in node data (top-level or under props)
        cvss = n.get("cvss_score") or n.get("props", {}).get("cvss_score")
        risk_score = n.get("risk_score")
        risk_tier = n.get("risk_tier", "")
        if cvss is not None and risk_score is not None:
            try:
                cve_with_cvss.append({
                    "id": n.get("id"),
                    "cvss_score": float(cvss),
                    "risk_score": float(risk_score),
                    "risk_tier": str(risk_tier).upper(),
                })
            except (ValueError, TypeError):
                pass

    # M1: Spearman ρ
    spearman_rho = None
    if len(cve_with_cvss) >= 3:
        # Rank by cvss, rank by risk_score
        sorted_by_cvss = sorted(cve_with_cvss, key=lambda x: x["cvss_score"], reverse=True)
        sorted_by_risk = sorted(cve_with_cvss, key=lambda x: x["risk_score"], reverse=True)
        rank_cvss = {x["id"]: i + 1 for i, x in enumerate(sorted_by_cvss)}
        rank_risk = {x["id"]: i + 1 for i, x in enumerate(sorted_by_risk)}
        n_cve = len(cve_with_cvss)
        d_sq_sum = sum((rank_cvss[x["id"]] - rank_risk[x["id"]]) ** 2 for x in cve_with_cvss)
        spearman_rho = 1 - (6 * d_sq_sum) / (n_cve * (n_cve ** 2 - 1))

    # M2: Tier Accuracy
    tier_correct = 0
    tier_total = len(cve_with_cvss)
    for x in cve_with_cvss:
        expected = _cvss_to_expected_tier(x["cvss_score"])
        if x["risk_tier"] in expected:
            tier_correct += 1
    tier_accuracy = tier_correct / tier_total if tier_total > 0 else None

    # M3: High-CVE P@K (how many of top-20/top-50 risk nodes are CVE with CVSS >= 7.0)
    top20 = nodes[:20]
    top50 = nodes[:50]
    high_cve_in_top20 = sum(
        1 for n in top20
        if (n.get("label", "").upper() == "CVE" or str(n.get("id", "")).upper().startswith("CVE-"))
        and float(n.get("cvss_score") or n.get("props", {}).get("cvss_score") or 0) >= 7.0
    )
    high_cve_in_top50 = sum(
        1 for n in top50
        if (n.get("label", "").upper() == "CVE" or str(n.get("id", "")).upper().startswith("CVE-"))
        and float(n.get("cvss_score") or n.get("props", {}).get("cvss_score") or 0) >= 7.0
    )

    return {
        "cve_nodes_with_cvss": len(cve_with_cvss),
        "spearman_rho": round(spearman_rho, 4) if spearman_rho is not None else None,
        "tier_accuracy": round(tier_accuracy, 4) if tier_accuracy is not None else None,
        "tier_correct": tier_correct,
        "tier_total": tier_total,
        "high_cve_precision_at_20": round(high_cve_in_top20 / min(20, len(top20)), 4) if top20 else None,
        "high_cve_precision_at_50": round(high_cve_in_top50 / min(50, len(top50)), 4) if top50 else None,
    }


def run_m4_m5(nodes: List[Dict]) -> Dict:
    """Risk Boundedness (M4) and Tier Distribution (M5)."""
    if not nodes:
        return {}

    scores = []
    tiers = Counter()
    out_of_bounds = 0

    for n in nodes:
        rs = n.get("risk_score")
        if rs is not None:
            try:
                s = float(rs)
                scores.append(s)
                if not (0.0 <= s <= 1.0):
                    out_of_bounds += 1
            except (ValueError, TypeError):
                pass
        tier = str(n.get("risk_tier", "UNKNOWN")).upper()
        tiers[tier] += 1

    boundedness = 1.0 - (out_of_bounds / len(scores)) if scores else None

    # Check tier ordering: CRITICAL count should decrease as tier lowers
    tier_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    tier_counts = [tiers.get(t, 0) for t in tier_order]
    # Monotone check: each consecutive pair
    monotone_violations = sum(
        1 for i in range(len(tier_counts) - 1)
        if tier_counts[i] < tier_counts[i + 1]
    )

    return {
        "total_scored_nodes": len(scores),
        "out_of_bounds_count": out_of_bounds,
        "risk_boundedness": round(boundedness, 4) if boundedness is not None else None,
        "score_min": round(min(scores), 4) if scores else None,
        "score_max": round(max(scores), 4) if scores else None,
        "score_mean": round(mean(scores), 4) if scores else None,
        "score_stdev": round(stdev(scores), 4) if len(scores) > 1 else None,
        "tier_CRITICAL": tiers.get("CRITICAL", 0),
        "tier_HIGH": tiers.get("HIGH", 0),
        "tier_MEDIUM": tiers.get("MEDIUM", 0),
        "tier_LOW": tiers.get("LOW", 0),
        "tier_monotone_violations": monotone_violations,
    }


def run_m6_known_nodes(nodes: List[Dict]) -> Dict:
    """Check that KNOWN_HIGH_RISK_IDS appear in top-K scored nodes."""
    top20_ids = {str(n.get("id", "")).lower() for n in nodes[:20]}
    top50_ids = {str(n.get("id", "")).lower() for n in nodes[:50]}
    top100_ids = {str(n.get("id", "")).lower() for n in nodes[:100]}
    known = {k.lower() for k in KNOWN_HIGH_RISK_IDS}

    hits_20  = known & top20_ids
    hits_50  = known & top50_ids
    hits_100 = known & top100_ids

    return {
        "known_nodes_in_top20":  len(hits_20),
        "known_nodes_in_top50":  len(hits_50),
        "known_nodes_in_top100": len(hits_100),
        "recall_at_20":  round(len(hits_20)  / len(known), 4),
        "recall_at_50":  round(len(hits_50)  / len(known), 4),
        "recall_at_100": round(len(hits_100) / len(known), 4),
        "missing_from_top100": sorted(known - top100_ids),
    }


async def run_attack_path_tests() -> List[Dict]:
    """M6 + M7: Attack path validity and coverage."""
    print("\n[L5-M6/M7] Attack Path Validity & Coverage")
    results = []
    for test in ATTACK_PATH_TESTS:
        print(f"  {test['label']}...", end=" ", flush=True)
        paths, latency = await call_attack_paths(
            test["source_id"], test["target_label"], test["max_hops"]
        )

        valid_paths = [
            p for p in paths
            if p.get("hops", 0) > 0 and p.get("path_risk", 0) > 0
        ]
        validity_rate = len(valid_paths) / len(paths) if paths else 0.0
        found = len(paths) > 0

        result = {
            "label": test["label"],
            "source_id": test["source_id"],
            "target_label": test["target_label"],
            "max_hops": test["max_hops"],
            "paths_found": len(paths),
            "valid_paths": len(valid_paths),
            "validity_rate": round(validity_rate, 4),
            "coverage": 1 if found else 0,
            "latency_ms": round(latency, 1),
            "top_path_risk": round(float(paths[0].get("path_risk", 0)), 4) if paths else None,
            "min_hops": min(p.get("hops", 99) for p in paths) if paths else None,
        }
        results.append(result)
        print(f"found={len(paths)}, valid={len(valid_paths)}, "
              f"validity={validity_rate:.2%}, latency={latency:.0f}ms")
    return results


def _print_summary(compute_result, nodes, m1m2m3, m4m5, m6_known, path_results, node_latency):
    total = len(nodes)

    print("\n" + "=" * 70)
    print("Table L5.1  GNN Risk Scoring — CVSS Calibration")
    print("=" * 70)
    print(f"  CVE nodes with CVSS score:    {m1m2m3['cve_nodes_with_cvss']}")
    if m1m2m3["spearman_rho"] is not None:
        interp = ("strong" if abs(m1m2m3["spearman_rho"]) >= 0.7
                  else "moderate" if abs(m1m2m3["spearman_rho"]) >= 0.4
                  else "weak")
        print(f"  Spearman rho (risk vs CVSS):  {m1m2m3['spearman_rho']:.4f}  ({interp})")
    else:
        print("  Spearman rho:                 N/A (need >=3 CVE nodes with CVSS)")
    if m1m2m3["tier_accuracy"] is not None:
        print(f"  Tier Accuracy:                {m1m2m3['tier_accuracy']:.2%}  "
              f"({m1m2m3['tier_correct']}/{m1m2m3['tier_total']} correct)")
    print(f"  High-CVE P@20:                "
          f"{m1m2m3['high_cve_precision_at_20']:.4f}" if m1m2m3["high_cve_precision_at_20"] else "  High-CVE P@20: N/A")
    print(f"  High-CVE P@50:                "
          f"{m1m2m3['high_cve_precision_at_50']:.4f}" if m1m2m3["high_cve_precision_at_50"] else "  High-CVE P@50: N/A")
    print("=" * 70)

    print("\n" + "=" * 70)
    print("Table L5.2  GNN Risk Scoring — Score Distribution & Boundedness")
    print("=" * 70)
    print(f"  Total scored nodes:     {m4m5.get('total_scored_nodes', 0)}")
    print(f"  Risk boundedness:       {m4m5.get('risk_boundedness', 'N/A')}"
          + (f"  ({m4m5['out_of_bounds_count']} out-of-bounds)" if m4m5.get("out_of_bounds_count") else ""))
    print(f"  Score range:            [{m4m5.get('score_min', '?')} – {m4m5.get('score_max', '?')}]")
    print(f"  Score mean ± stdev:     {m4m5.get('score_mean', '?')} ± {m4m5.get('score_stdev', '?')}")
    print(f"  Tier counts:            CRITICAL={m4m5.get('tier_CRITICAL', 0)}  "
          f"HIGH={m4m5.get('tier_HIGH', 0)}  "
          f"MEDIUM={m4m5.get('tier_MEDIUM', 0)}  "
          f"LOW={m4m5.get('tier_LOW', 0)}")
    violations = m4m5.get("tier_monotone_violations", 0)
    print(f"  Tier monotone order:    {'OK' if violations == 0 else f'VIOLATED ({violations} inversions)'}")
    print("=" * 70)

    print("\n" + "=" * 70)
    print("Table L5.3  GNN — Known High-Risk Node Recall")
    print("=" * 70)
    print(f"  Known nodes total:      {len(KNOWN_HIGH_RISK_IDS)}")
    print(f"  Recall@20:              {m6_known['recall_at_20']:.4f}  ({m6_known['known_nodes_in_top20']} found)")
    print(f"  Recall@50:              {m6_known['recall_at_50']:.4f}  ({m6_known['known_nodes_in_top50']} found)")
    print(f"  Recall@100:             {m6_known['recall_at_100']:.4f}  ({m6_known['known_nodes_in_top100']} found)")
    if m6_known["missing_from_top100"]:
        print(f"  Missing from top-100:   {m6_known['missing_from_top100']}")
    print("=" * 70)

    print("\n" + "=" * 80)
    print("Table L5.4  GNN — Attack Path Validity & Coverage")
    print("=" * 80)
    print(f"{'Test':<18} {'Paths':>6} {'Valid':>6} {'Validity':>9} {'MinHop':>7} "
          f"{'TopRisk':>8} {'Lat(ms)':>8}")
    print("-" * 80)
    for r in path_results:
        print(f"{r['label']:<18} {r['paths_found']:>6} {r['valid_paths']:>6} "
              f"{r['validity_rate']:>9.2%} "
              f"{str(r['min_hops']):>7} "
              f"{str(r['top_path_risk']):>8} "
              f"{r['latency_ms']:>8.0f}")
    coverage = sum(r["coverage"] for r in path_results) / len(path_results) if path_results else 0
    validity_avg = mean(r["validity_rate"] for r in path_results) if path_results else 0
    print("-" * 80)
    print(f"  Coverage rate:  {coverage:.2%}  |  "
          f"Avg validity: {validity_avg:.2%}  |  "
          f"Node query latency: {node_latency:.0f}ms")
    print("=" * 80)


async def run_l5_benchmark() -> Dict:
    print("\n" + "#" * 76)
    print("# L5 BENCHMARK — GNN Risk Scoring Quality")
    print("#" * 76)

    # Step 1: Compute fresh scores
    print("\n[L5-Pre] Computing fresh risk scores")
    compute_result = await compute_risk_scores()

    # Step 2: Fetch scored nodes
    print("\n[L5-M1-M5] Fetching top-100 risk nodes...", end=" ", flush=True)
    nodes, node_latency = await get_high_risk_nodes(limit=100)
    print(f"fetched={len(nodes)}, latency={node_latency:.0f}ms")

    # Step 3: Compute per-metric results
    m1m2m3 = run_m1_m2_m3(nodes)
    m4m5 = run_m4_m5(nodes)
    m6_known = run_m6_known_nodes(nodes)

    # Step 4: Attack paths
    path_results = await run_attack_path_tests()

    _print_summary(compute_result, nodes, m1m2m3, m4m5, m6_known, path_results, node_latency)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "benchmark": "L5_GNN",
        "timestamp": timestamp,
        "compute_scores": compute_result,
        "node_query_latency_ms": round(node_latency, 1),
        "total_nodes_fetched": len(nodes),
        "cvss_calibration": m1m2m3,
        "score_distribution": m4m5,
        "known_node_recall": m6_known,
        "attack_paths": path_results,
    }

    results_dir = Path(config.output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    out_file = results_dir / f"benchmark_l5_{timestamp}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {out_file}")
    return output


if __name__ == "__main__":
    asyncio.run(run_l5_benchmark())
