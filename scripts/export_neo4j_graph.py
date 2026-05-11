#!/usr/bin/env python3
"""
export_neo4j_graph.py — Export toàn bộ Neo4j knowledge graph ra file.

Output:
    outputs/graph_export/nodes.json      — tất cả nodes theo label
    outputs/graph_export/edges.json      — tất cả relationships
    outputs/graph_export/nodes.csv       — nodes dạng flat (cho Gephi/Cytoscape)
    outputs/graph_export/edges.csv       — edges dạng flat
    outputs/graph_export/summary.txt     — thống kê

Usage:
    python scripts/export_neo4j_graph.py
    python scripts/export_neo4j_graph.py --format json     # chỉ JSON
    python scripts/export_neo4j_graph.py --format csv      # chỉ CSV
    python scripts/export_neo4j_graph.py --format both     # cả hai (default)
    python scripts/export_neo4j_graph.py --label Vulnerability CWE  # chỉ export label cụ thể
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load .env
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

OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "graph_export"


def connect(uri, user, password):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print(f"[OK] Connected to {uri}")
    return driver


def get_all_labels(driver) -> list[str]:
    with driver.session() as s:
        result = s.run("CALL db.labels() YIELD label RETURN label ORDER BY label")
        return [r["label"] for r in result]


def get_all_rel_types(driver) -> list[str]:
    with driver.session() as s:
        result = s.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
        return [r["relationshipType"] for r in result]


def export_nodes(driver, labels_filter: list[str] | None = None) -> dict[str, list[dict]]:
    """Export all nodes grouped by label."""
    all_labels = get_all_labels(driver)
    if labels_filter:
        all_labels = [l for l in all_labels if l in labels_filter]

    nodes_by_label: dict[str, list[dict]] = {}
    total = 0

    for label in all_labels:
        with driver.session() as s:
            result = s.run(f"MATCH (n:`{label}`) RETURN properties(n) AS props, elementId(n) AS eid")
            rows = []
            for r in result:
                row = dict(r["props"])
                row["_neo4j_id"] = r["eid"]
                row["_label"] = label
                rows.append(row)
        nodes_by_label[label] = rows
        total += len(rows)
        print(f"  [{label}] {len(rows):,} nodes")

    print(f"  Total nodes: {total:,}")
    return nodes_by_label


def export_edges(driver) -> list[dict]:
    """Export all relationships."""
    rel_types = get_all_rel_types(driver)
    edges = []

    for rel_type in rel_types:
        with driver.session() as s:
            result = s.run(f"""
                MATCH (a)-[r:`{rel_type}`]->(b)
                RETURN
                    elementId(a) AS source_id,
                    labels(a)[0] AS source_label,
                    a.id AS source_node_id,
                    elementId(b) AS target_id,
                    labels(b)[0] AS target_label,
                    b.id AS target_node_id,
                    type(r) AS rel_type,
                    properties(r) AS props
            """)
            count = 0
            for r in result:
                edge = {
                    "source_id":      r["source_id"],
                    "source_label":   r["source_label"],
                    "source_node_id": r["source_node_id"],
                    "target_id":      r["target_id"],
                    "target_label":   r["target_label"],
                    "target_node_id": r["target_node_id"],
                    "type":           r["rel_type"],
                }
                edge.update(r["props"] or {})
                edges.append(edge)
                count += 1
        print(f"  [{rel_type}] {count:,} edges")

    print(f"  Total edges: {len(edges):,}")
    return edges


def save_json(nodes_by_label: dict, edges: list, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes_path = out_dir / "nodes.json"
    with open(nodes_path, "w", encoding="utf-8") as f:
        json.dump(nodes_by_label, f, ensure_ascii=False, indent=2, default=str)
    print(f"  [JSON] nodes -> {nodes_path}")

    edges_path = out_dir / "edges.json"
    with open(edges_path, "w", encoding="utf-8") as f:
        json.dump(edges, f, ensure_ascii=False, indent=2, default=str)
    print(f"  [JSON] edges -> {edges_path}")


def save_csv(nodes_by_label: dict, edges: list, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Nodes CSV — flatten tất cả labels thành 1 file
    all_nodes = [n for nodes in nodes_by_label.values() for n in nodes]
    if all_nodes:
        all_keys = sorted({k for n in all_nodes for k in n.keys()})
        nodes_path = out_dir / "nodes.csv"
        with open(nodes_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            for node in all_nodes:
                writer.writerow({k: node.get(k, "") for k in all_keys})
        print(f"  [CSV]  nodes -> {nodes_path}")

    # Edges CSV
    if edges:
        all_keys = sorted({k for e in edges for k in e.keys()})
        edges_path = out_dir / "edges.csv"
        with open(edges_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            for edge in edges:
                writer.writerow({k: edge.get(k, "") for k in all_keys})
        print(f"  [CSV]  edges -> {edges_path}")


def save_summary(nodes_by_label: dict, edges: list, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.txt"

    lines = [
        f"GraphPent Neo4j Export",
        f"Exported at: {datetime.now().isoformat()}",
        f"",
        f"=== NODES ===",
    ]
    total_nodes = 0
    for label, nodes in sorted(nodes_by_label.items()):
        lines.append(f"  {label:<30} {len(nodes):>8,}")
        total_nodes += len(nodes)
    lines += [
        f"  {'TOTAL':<30} {total_nodes:>8,}",
        f"",
        f"=== EDGES ===",
    ]
    from collections import Counter
    edge_counts = Counter(e["type"] for e in edges)
    for rel_type, count in sorted(edge_counts.items()):
        lines.append(f"  {rel_type:<30} {count:>8,}")
    lines += [
        f"  {'TOTAL':<30} {len(edges):>8,}",
    ]

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  [TXT]  summary -> {summary_path}")
    print("\n" + "\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Export Neo4j knowledge graph to files.")
    parser.add_argument("--format", choices=["json", "csv", "both"], default="both")
    parser.add_argument("--label", nargs="+", default=None,
                        help="Chỉ export các label cụ thể, vd: --label Vulnerability CWE")
    parser.add_argument("--out", default=str(OUTPUT_DIR),
                        help=f"Output directory (default: {OUTPUT_DIR})")
    args = parser.parse_args()

    out_dir = Path(args.out)

    print(f"\n[CONNECT] {NEO4J_URI}")
    driver = connect(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    print("\n[NODES] Exporting nodes...")
    nodes_by_label = export_nodes(driver, labels_filter=args.label)

    print("\n[EDGES] Exporting relationships...")
    edges = export_edges(driver)

    print(f"\n[SAVE] Output -> {out_dir}")
    if args.format in ("json", "both"):
        save_json(nodes_by_label, edges, out_dir)
    if args.format in ("csv", "both"):
        save_csv(nodes_by_label, edges, out_dir)
    save_summary(nodes_by_label, edges, out_dir)

    driver.close()
    print("\n[DONE]")


if __name__ == "__main__":
    main()
