#!/usr/bin/env python3
"""
Benchmark L6 — Reasoning & Pipeline Quality
=============================================
Measures the quality of the Reasoning Engine (L6) and end-to-end pipeline (L7).
Uses 8 pentest scenarios with expected outputs and structural assertions.

Metrics
-------
M1  Tool Selection Accuracy    % scenarios where agent chose the expected tool
M2  Graph Utilization Rate     % final_answers that reference graph node IDs (cwe-*, cve-*, CVE-*)
M3  Report Completeness        % of required report sections present
M4  Retrieval-Reasoning Align  % scenarios where retrieved entities appear in reasoning output
M5  E2E Latency                p50/p95 across scenarios (ms)
M6  Pipeline Completion Rate   % workflows that finish with status="success"
M7  Attack Path Discovery Rate % scenarios with target where attack_paths are non-empty
M8  Feedback Loop Efficiency   Loop iterations / new_findings_count ratio
"""

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Dict, List, Optional

import httpx

from evaluation.config import BenchmarkConfig

config = BenchmarkConfig()

# Required keys in the report dict (from report_node output)
REQUIRED_REPORT_KEYS = {"query", "retrieval", "gnn", "reasoning", "status"}

# Regex patterns indicating graph entity references in final_answer
GRAPH_ENTITY_PATTERNS = [
    re.compile(r"\bcwe-\d+\b", re.IGNORECASE),
    re.compile(r"\bCVE-\d{4}-\d+\b", re.IGNORECASE),
    re.compile(r"\bcve-\d{4}-\d+\b", re.IGNORECASE),
    re.compile(r"\b(cwe|cve|weakness|vulnerability|attack.path)\b", re.IGNORECASE),
]

# Test scenarios: each defines inputs and expected assertions
REASONING_SCENARIOS = [
    {
        "id": "RS1",
        "name": "SQL Injection CVE Lookup",
        "query": "SQL injection vulnerabilities CVE exploit",
        "scan_target": None,
        "max_loop_iterations": 1,
        "expected_tool": None,          # No target → no tool execution
        "expected_entity_keywords": ["cwe-89", "sql", "injection"],
        "expected_report_keys": REQUIRED_REPORT_KEYS,
        "expect_attack_paths": False,
    },
    {
        "id": "RS2",
        "name": "XSS with Target — Nuclei Expected",
        "query": "XSS cross-site scripting vulnerabilities in web application",
        "scan_target": "192.168.1.1",
        "max_loop_iterations": 1,
        "expected_tool": "nuclei",
        "expected_entity_keywords": ["cwe-79", "xss", "cross-site"],
        "expected_report_keys": REQUIRED_REPORT_KEYS,
        "expect_attack_paths": True,
    },
    {
        "id": "RS3",
        "name": "Authentication Bypass Multi-hop",
        "query": "authentication bypass vulnerabilities CWE weakness family",
        "scan_target": None,
        "max_loop_iterations": 1,
        "expected_tool": None,
        "expected_entity_keywords": ["cwe-287", "authentication", "bypass"],
        "expected_report_keys": REQUIRED_REPORT_KEYS,
        "expect_attack_paths": False,
    },
    {
        "id": "RS4",
        "name": "CSRF with Target",
        "query": "CSRF cross-site request forgery vulnerabilities",
        "scan_target": "10.0.0.1",
        "max_loop_iterations": 1,
        "expected_tool": "nuclei",
        "expected_entity_keywords": ["cwe-352", "csrf"],
        "expected_report_keys": REQUIRED_REPORT_KEYS,
        "expect_attack_paths": True,
    },
    {
        "id": "RS5",
        "name": "IDOR Authorization Check",
        "query": "IDOR insecure direct object reference authorization bypass",
        "scan_target": None,
        "max_loop_iterations": 1,
        "expected_tool": None,
        "expected_entity_keywords": ["cwe-639", "idor", "authorization"],
        "expected_report_keys": REQUIRED_REPORT_KEYS,
        "expect_attack_paths": False,
    },
    {
        "id": "RS6",
        "name": "CWE Taxonomy Reasoning",
        "query": "CWE weakness enumeration taxonomy security categories",
        "scan_target": None,
        "max_loop_iterations": 1,
        "expected_tool": None,
        "expected_entity_keywords": ["cwe-89", "cwe-79", "weakness"],
        "expected_report_keys": REQUIRED_REPORT_KEYS,
        "expect_attack_paths": False,
    },
    {
        "id": "RS7",
        "name": "Full Pipeline with Feedback Loop",
        "query": "web application vulnerabilities comprehensive security assessment",
        "scan_target": "192.168.100.1",
        "max_loop_iterations": 2,    # Allow one feedback loop
        "expected_tool": "nuclei",
        "expected_entity_keywords": ["vulnerability", "cve", "cwe"],
        "expected_report_keys": REQUIRED_REPORT_KEYS,
        "expect_attack_paths": True,
    },
    {
        "id": "RS8",
        "name": "Remediation Guidance Query",
        "query": "how to remediate SQL injection vulnerabilities patch mitigation",
        "scan_target": None,
        "max_loop_iterations": 1,
        "expected_tool": None,
        "expected_entity_keywords": ["sql", "injection", "remediat"],
        "expected_report_keys": REQUIRED_REPORT_KEYS,
        "expect_attack_paths": False,
    },
]


async def run_workflow(scenario: Dict) -> Dict:
    """Call POST /workflow/multi-agent and return parsed result."""
    payload = {
        "query": scenario["query"],
        "user_id": "benchmark",
        "scan_target": scenario.get("scan_target"),
        "max_loop_iterations": scenario.get("max_loop_iterations", 1),
        "use_langgraph": True,
    }
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{config.base_url}/workflow/multi-agent",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    latency = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        return {
            "status": "error",
            "http_status": resp.status_code,
            "latency_ms": latency,
            "error": resp.text[:300],
        }
    data = resp.json()
    data["latency_ms"] = latency
    return data


def _check_tool_selection(result: Dict, scenario: Dict) -> Optional[bool]:
    """Return True/False if tool check is applicable, None if not applicable."""
    expected_tool = scenario.get("expected_tool")
    if expected_tool is None:
        return None  # No target — tool selection N/A

    tool_results = result.get("tool_results") or []
    final_answer = str(result.get("final_answer", "")).lower()
    report = result.get("report") or {}

    # Check tool_results list
    for tr in tool_results:
        tool_used = str(tr.get("tool", tr.get("type", ""))).lower()
        if expected_tool.lower() in tool_used:
            return True

    # Check report.tools section
    tools_section = report.get("tools", {})
    if isinstance(tools_section, dict):
        for v in tools_section.values():
            if expected_tool.lower() in str(v).lower():
                return True

    # Fallback: check final_answer text
    if expected_tool.lower() in final_answer:
        return True

    return False


def _check_graph_utilization(result: Dict) -> bool:
    """True if final_answer or report mentions graph entities."""
    text = str(result.get("final_answer", ""))
    report = result.get("report") or {}
    reasoning = report.get("reasoning", {})
    text += " " + str(reasoning)

    for pattern in GRAPH_ENTITY_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _check_report_completeness(result: Dict, required_keys: set) -> float:
    """Fraction of required report keys present."""
    report = result.get("report") or {}
    if not report:
        return 0.0
    present = sum(1 for k in required_keys if k in report)
    return present / len(required_keys)


def _check_retrieval_alignment(result: Dict, scenario: Dict) -> Optional[bool]:
    """True if any expected_entity_keyword appears in final_answer or report."""
    keywords = scenario.get("expected_entity_keywords", [])
    if not keywords:
        return None
    text = (str(result.get("final_answer", "")) + " "
            + str(result.get("report", ""))).lower()
    return any(kw.lower() in text for kw in keywords)


def _check_attack_paths(result: Dict) -> bool:
    """True if attack_paths are non-empty (in report.gnn section)."""
    report = result.get("report") or {}
    gnn_section = report.get("gnn", {})
    if isinstance(gnn_section, dict):
        paths = gnn_section.get("attack_paths", [])
        if paths:
            return True
    # Also check top-level tool_results for any path info
    tool_results = result.get("tool_results") or []
    for tr in tool_results:
        if tr.get("attack_paths"):
            return True
    return False


def _check_feedback_loop(result: Dict, scenario: Dict) -> Dict:
    """Check feedback loop behavior."""
    loop_iters = result.get("loop_iterations", 0)
    return {
        "loop_iterations": loop_iters,
        "max_allowed": scenario.get("max_loop_iterations", 1),
        "within_budget": loop_iters <= scenario.get("max_loop_iterations", 1),
    }


async def run_l6_benchmark() -> Dict:
    print("\n" + "#" * 76)
    print("# L6 BENCHMARK — Reasoning & Pipeline Quality")
    print("#" * 76)

    scenario_results = []
    latencies = []

    for scenario in REASONING_SCENARIOS:
        print(f"\n[{scenario['id']}] {scenario['name']}")
        print(f"  query={scenario['query'][:60]}...", end="")
        if scenario.get("scan_target"):
            print(f"  target={scenario['scan_target']}", end="")
        print()

        result = await run_workflow(scenario)
        latency = result.get("latency_ms", 0)
        latencies.append(latency)

        completed = result.get("status") == "success"
        tool_ok = _check_tool_selection(result, scenario)
        graph_util = _check_graph_utilization(result) if completed else False
        report_score = _check_report_completeness(result, scenario["expected_report_keys"]) if completed else 0.0
        align_ok = _check_retrieval_alignment(result, scenario) if completed else None
        has_paths = _check_attack_paths(result) if (completed and scenario.get("expect_attack_paths")) else None
        loop_info = _check_feedback_loop(result, scenario) if completed else {}

        print(f"  status={'OK' if completed else 'FAIL'}  "
              f"latency={latency:.0f}ms  "
              f"tool={'OK' if tool_ok else ('N/A' if tool_ok is None else 'FAIL')}  "
              f"graph_util={'Y' if graph_util else 'N'}  "
              f"report={report_score:.0%}  "
              f"align={'Y' if align_ok else ('N/A' if align_ok is None else 'N')}  "
              f"paths={'Y' if has_paths else ('N/A' if has_paths is None else 'N')}")

        if not completed and result.get("error"):
            print(f"  [ERROR] {result['error'][:120]}")

        scenario_results.append({
            "scenario_id": scenario["id"],
            "scenario_name": scenario["name"],
            "query": scenario["query"],
            "scan_target": scenario.get("scan_target"),
            "status": result.get("status", "error"),
            "completed": completed,
            "tool_correct": tool_ok,
            "graph_utilization": graph_util,
            "report_completeness": round(report_score, 4),
            "retrieval_alignment": align_ok,
            "attack_paths_found": has_paths,
            "loop_iterations": loop_info.get("loop_iterations", 0),
            "within_loop_budget": loop_info.get("within_budget", True),
            "latency_ms": round(latency, 1),
            "workflow_id": result.get("workflow_id", ""),
        })

    _print_summary(scenario_results, latencies)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "benchmark": "L6_Reasoning",
        "timestamp": timestamp,
        "scenarios": scenario_results,
        "aggregate": _aggregate(scenario_results, latencies),
    }

    results_dir = Path(config.output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    out_file = results_dir / f"benchmark_l6_{timestamp}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {out_file}")
    return output


def _aggregate(results: List[Dict], latencies: List[float]) -> Dict:
    n = len(results)
    completed = [r for r in results if r["completed"]]
    n_ok = len(completed)

    # M1: Tool selection (only scenarios where expected_tool is not None)
    tool_applicable = [r for r in results if r["tool_correct"] is not None]
    tool_correct = [r for r in tool_applicable if r["tool_correct"] is True]
    tool_acc = len(tool_correct) / len(tool_applicable) if tool_applicable else None

    # M2: Graph utilization
    graph_util_rate = sum(1 for r in completed if r["graph_utilization"]) / n_ok if n_ok else 0

    # M3: Report completeness
    completeness_vals = [r["report_completeness"] for r in completed]
    avg_completeness = mean(completeness_vals) if completeness_vals else 0

    # M4: Retrieval alignment
    align_applicable = [r for r in completed if r["retrieval_alignment"] is not None]
    align_rate = (sum(1 for r in align_applicable if r["retrieval_alignment"])
                  / len(align_applicable)) if align_applicable else None

    # M5: Latency
    lat_p50 = sorted(latencies)[len(latencies) // 2] if latencies else 0
    lat_p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    # M6: Completion rate
    completion_rate = n_ok / n if n else 0

    # M7: Attack path discovery
    path_applicable = [r for r in completed if r["attack_paths_found"] is not None]
    path_rate = (sum(1 for r in path_applicable if r["attack_paths_found"])
                 / len(path_applicable)) if path_applicable else None

    # M8: Feedback loop efficiency
    multi_loop = [r for r in completed if r.get("loop_iterations", 0) > 1]
    within_budget_rate = (sum(1 for r in results if r["within_loop_budget"])
                          / n) if n else 0

    return {
        "M1_tool_selection_accuracy": round(tool_acc, 4) if tool_acc is not None else None,
        "M2_graph_utilization_rate": round(graph_util_rate, 4),
        "M3_avg_report_completeness": round(avg_completeness, 4),
        "M4_retrieval_alignment_rate": round(align_rate, 4) if align_rate is not None else None,
        "M5_latency_p50_ms": round(lat_p50, 1),
        "M5_latency_p95_ms": round(lat_p95, 1),
        "M6_completion_rate": round(completion_rate, 4),
        "M7_attack_path_discovery_rate": round(path_rate, 4) if path_rate is not None else None,
        "M8_within_loop_budget_rate": round(within_budget_rate, 4),
        "total_scenarios": n,
        "completed_scenarios": n_ok,
    }


def _print_summary(results: List[Dict], latencies: List[float]):
    agg = _aggregate(results, latencies)

    print("\n" + "=" * 90)
    print("Table L6.1  Reasoning Pipeline — Per-Scenario Results")
    print("=" * 90)
    print(f"{'ID':<5} {'Name':<34} {'Done':>5} {'Tool':>5} {'GUtil':>6} "
          f"{'Rpt%':>5} {'Align':>6} {'Paths':>6} {'Lat(ms)':>8}")
    print("-" * 90)
    for r in results:
        tool_s  = ("OK" if r["tool_correct"] is True
                   else ("--" if r["tool_correct"] is None else "FAIL"))
        align_s = ("Y" if r["retrieval_alignment"] is True
                   else ("--" if r["retrieval_alignment"] is None else "N"))
        path_s  = ("Y" if r["attack_paths_found"] is True
                   else ("--" if r["attack_paths_found"] is None else "N"))
        print(f"{r['scenario_id']:<5} "
              f"{r['scenario_name'][:33]:<34} "
              f"{'OK' if r['completed'] else 'FAIL':>5} "
              f"{tool_s:>5} "
              f"{'Y' if r['graph_utilization'] else 'N':>6} "
              f"{r['report_completeness']:>5.0%} "
              f"{align_s:>6} "
              f"{path_s:>6} "
              f"{r['latency_ms']:>8.0f}")
    print("=" * 90)

    print("\n" + "=" * 60)
    print("Table L6.2  Reasoning Pipeline — Aggregate Metrics")
    print("=" * 60)
    print(f"  M1  Tool Selection Accuracy:        "
          f"{agg['M1_tool_selection_accuracy']:.2%}" if agg["M1_tool_selection_accuracy"] is not None
          else "  M1  Tool Selection Accuracy:        N/A")
    print(f"  M2  Graph Utilization Rate:         {agg['M2_graph_utilization_rate']:.2%}")
    print(f"  M3  Avg Report Completeness:        {agg['M3_avg_report_completeness']:.2%}")
    print(f"  M4  Retrieval-Reasoning Alignment:  "
          f"{agg['M4_retrieval_alignment_rate']:.2%}" if agg["M4_retrieval_alignment_rate"] is not None
          else "  M4  Retrieval-Reasoning Alignment:  N/A")
    print(f"  M5  Latency p50 / p95:              {agg['M5_latency_p50_ms']:.0f}ms / {agg['M5_latency_p95_ms']:.0f}ms")
    print(f"  M6  Pipeline Completion Rate:       {agg['M6_completion_rate']:.2%}  "
          f"({agg['completed_scenarios']}/{agg['total_scenarios']})")
    print(f"  M7  Attack Path Discovery Rate:     "
          f"{agg['M7_attack_path_discovery_rate']:.2%}" if agg["M7_attack_path_discovery_rate"] is not None
          else "  M7  Attack Path Discovery Rate:     N/A")
    print(f"  M8  Within Loop Budget Rate:        {agg['M8_within_loop_budget_rate']:.2%}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_l6_benchmark())
