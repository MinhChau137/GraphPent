#!/usr/bin/env python3
"""
export_graph_for_gnn.py — Export subgraph từ Neo4j ra format JSON/numpy
để train GNN link predictor (Service → CVE).

Output tại data/gnn/:
    nodes.json        — danh sách node {id, type, features}
    edges.json        — danh sách edge {src, dst, rel_type, weight}
    node_index.json   — ánh xạ node_id (string) → index (int)
    meta.json         — thống kê graph

Usage:
    python scripts/export_graph_for_gnn.py
    python scripts/export_graph_for_gnn.py --out data/gnn
"""

import argparse
import json
import os
import sys
import hashlib
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

NEO4J_URI      = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password123")
if NEO4J_URI in ("neo4j:7687", "neo4j://neo4j:7687", "bolt://neo4j:7687"):
    NEO4J_URI = "bolt://localhost:7687"

# ── Node type → feature extraction ───────────────────────────────────────────

_SEVERITY_MAP = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25, "unknown": 0.1}
_ATTACK_VEC   = {"network": 1.0, "adjacent": 0.75, "local": 0.5, "physical": 0.25}
_PROTOCOL_MAP = {"tcp": 1.0, "udp": 0.5, "sctp": 0.25}


def _str_hash(s: str) -> float:
    """Stable float hash [0,1] for a string — used to embed product/vendor names."""
    if not s:
        return 0.0
    h = int(hashlib.md5(s.lower().encode()).hexdigest(), 16)
    return (h % 10000) / 10000.0


def _service_features(props: dict) -> list[float]:
    """10-dim feature vector for Service nodes."""
    port     = min(float(props.get("port") or 0), 65535) / 65535.0
    proto    = _PROTOCOL_MAP.get((props.get("protocol") or "tcp").lower(), 0.5)
    has_cpe  = 1.0 if props.get("cpe") else 0.0
    has_ver  = 1.0 if props.get("version") else 0.0
    prod_h   = _str_hash(props.get("product") or "")
    ver_h    = _str_hash(props.get("version") or "")
    vendor_h = _str_hash(props.get("vendor") or "")
    is_web   = 1.0 if int(props.get("port") or 0) in {80,443,8080,8443,8888,9090,3000} else 0.0
    return [port, proto, has_cpe, has_ver, prod_h, ver_h, vendor_h, is_web, 0.0, 0.0]


def _vuln_features(props: dict) -> list[float]:
    """10-dim feature vector for Vulnerability nodes."""
    cvss     = min(float(props.get("cvss_score") or 0), 10.0) / 10.0
    sev_str  = (props.get("cvss_severity") or "unknown").lower()
    sev      = _SEVERITY_MAP.get(sev_str, 0.1)
    av_str   = (props.get("attack_vector") or "").lower()
    av       = _ATTACK_VEC.get(av_str, 0.5)
    n_prod   = min(len(props.get("cpe_products") or []), 20) / 20.0
    n_vendor = min(len(props.get("cpe_vendors") or []), 10) / 10.0
    has_cpe  = 1.0 if props.get("cpe_affected") else 0.0
    return [cvss, sev, av, n_prod, n_vendor, has_cpe, 0.0, 0.0, 0.0, 0.0]


def _cwe_features(props: dict) -> list[float]:
    cwe_id = props.get("id") or ""
    num = 0.0
    try:
        num = float(cwe_id.replace("cwe-", "")) / 1000.0
    except Exception:
        pass
    return [num] + [0.0] * 9


def _host_features(props: dict) -> list[float]:
    subnet_h = _str_hash(props.get("subnet") or "")
    os_h     = _str_hash(props.get("os") or "")
    return [subnet_h, os_h] + [0.0] * 8


def _app_features(props: dict) -> list[float]:
    prod_h   = _str_hash(props.get("product") or "")
    ver_h    = _str_hash(props.get("version") or "")
    vendor_h = _str_hash(props.get("vendor") or "")
    has_cpe  = 1.0 if props.get("cpe") else 0.0
    return [prod_h, ver_h, vendor_h, has_cpe] + [0.0] * 6


_FEATURE_FN = {
    "Service":       _service_features,
    "Vulnerability": _vuln_features,
    "CWE":           _cwe_features,
    "Host":          _host_features,
    "Application":   _app_features,
}

# ── Queries ───────────────────────────────────────────────────────────────────

_Q_NODES = {
    "Service": """
        MATCH (n:Service) WHERE n.product IS NOT NULL
        RETURN n.id AS id, 'Service' AS type, properties(n) AS props
    """,
    "Vulnerability": """
        MATCH (n:Vulnerability)
        RETURN n.id AS id, 'Vulnerability' AS type, properties(n) AS props
    """,
    "CWE": """
        MATCH (n:CWE)
        RETURN n.id AS id, 'CWE' AS type, properties(n) AS props
    """,
    "Host": """
        MATCH (n:Host)
        RETURN n.id AS id, 'Host' AS type, properties(n) AS props
    """,
    "Application": """
        MATCH (n:Application)
        RETURN n.id AS id, 'Application' AS type, properties(n) AS props
    """,
}

_Q_EDGES = {
    "HAS_VULN": """
        MATCH (s:Service)-[r:HAS_VULN]->(v:Vulnerability)
        RETURN s.id AS src, v.id AS dst, 'HAS_VULN' AS rel,
               coalesce(r.confidence, 0.7) AS weight
    """,
    "HAS_WEAKNESS": """
        MATCH (v:Vulnerability)-[r:HAS_WEAKNESS]->(c:CWE)
        RETURN v.id AS src, c.id AS dst, 'HAS_WEAKNESS' AS rel,
               coalesce(r.confidence, 0.9) AS weight
    """,
    "RUNS_SERVICE": """
        MATCH (p)-[r:RUNS_SERVICE]->(s:Service)
        RETURN p.id AS src, s.id AS dst, 'RUNS_SERVICE' AS rel, 1.0 AS weight
    """,
    "RUNS": """
        MATCH (s:Service)-[r:RUNS]->(a:Application)
        RETURN s.id AS src, a.id AS dst, 'RUNS' AS rel, 1.0 AS weight
    """,
    "HAS_PORT": """
        MATCH (h:Host)-[r:HAS_PORT]->(p)
        MATCH (p)-[:RUNS_SERVICE]->(s:Service)
        RETURN h.id AS src, s.id AS dst, 'HOST_SERVICE' AS rel, 1.0 AS weight
    """,
}


def export(out_dir: Path):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"[OK] Connected: {NEO4J_URI}\n")
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Nodes ─────────────────────────────────────────────────────────────────
    all_nodes = []
    type_counts = {}
    with driver.session() as s:
        for ntype, query in _Q_NODES.items():
            rows = s.run(query)
            cnt = 0
            for row in rows:
                nid   = row["id"]
                props = dict(row["props"])
                feat_fn = _FEATURE_FN.get(ntype, lambda p: [0.0]*10)
                features = feat_fn(props)
                all_nodes.append({"id": nid, "type": ntype, "features": features})
                cnt += 1
            type_counts[ntype] = cnt
            print(f"  [{ntype}] {cnt:,} nodes")

    # Build index
    node_index = {n["id"]: i for i, n in enumerate(all_nodes)}
    print(f"\n  Total nodes: {len(all_nodes):,}")

    # ── Edges ─────────────────────────────────────────────────────────────────
    all_edges = []
    edge_counts = {}
    has_vuln_edges = []
    with driver.session() as s:
        for rel_type, query in _Q_EDGES.items():
            rows = s.run(query)
            cnt = 0
            for row in rows:
                src, dst = row["src"], row["dst"]
                if src not in node_index or dst not in node_index:
                    continue
                edge = {
                    "src": src, "dst": dst,
                    "src_idx": node_index[src],
                    "dst_idx": node_index[dst],
                    "rel_type": row["rel"],
                    "weight": float(row["weight"]),
                }
                all_edges.append(edge)
                if row["rel"] == "HAS_VULN":
                    has_vuln_edges.append(edge)
                cnt += 1
            edge_counts[rel_type] = cnt
            print(f"  [{rel_type}] {cnt:,} edges")

    print(f"\n  Total edges: {len(all_edges):,}")
    print(f"  HAS_VULN (positive labels): {len(has_vuln_edges):,}")

    if len(has_vuln_edges) == 0:
        print("\n[WARN] Khong co HAS_VULN edges!")
        print("       Chay link_service_cve.py truoc:")
        print("       python scripts/link_service_cve.py --min-confidence 0.60")

    # ── Write ─────────────────────────────────────────────────────────────────
    (out_dir / "nodes.json").write_text(
        json.dumps(all_nodes, ensure_ascii=False), encoding="utf-8")
    (out_dir / "edges.json").write_text(
        json.dumps(all_edges, ensure_ascii=False), encoding="utf-8")
    (out_dir / "node_index.json").write_text(
        json.dumps(node_index, ensure_ascii=False), encoding="utf-8")

    meta = {
        "node_counts":       type_counts,
        "edge_counts":       edge_counts,
        "total_nodes":       len(all_nodes),
        "total_edges":       len(all_edges),
        "positive_labels":   len(has_vuln_edges),
        "feature_dim":       10,
        "node_types":        list(_Q_NODES.keys()),
        "edge_types":        list(_Q_EDGES.keys()),
        "target_edge":       "HAS_VULN",
        "target_src_type":   "Service",
        "target_dst_type":   "Vulnerability",
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    driver.close()
    print(f"\n[DONE] Exported to {out_dir}/")
    print("       Buoc tiep theo:")
    print("       python scripts/train_gnn_link_predictor.py --data data/gnn")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/gnn")
    args = parser.parse_args()
    export(Path(args.out))


if __name__ == "__main__":
    main()
