#!/usr/bin/env python3
"""Audit Neo4j graph labels and relationship types against the target ontology.

Examples:
    python scripts/audit_graph_ontology.py --file data/graph_export/graph_export.cypher
    python scripts/audit_graph_ontology.py --neo4j
    python scripts/audit_graph_ontology.py --strict
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domain.graph_schema import EXPECTED_NODE_LABELS, EXPECTED_RELATIONSHIP_TYPES


DEFAULT_EXPORT = ROOT / "data" / "graph_export" / "graph_export.cypher"


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bump(counter: Dict[str, int], key: str, count: int) -> None:
    counter[key] = counter.get(key, 0) + count


def audit_cypher_export(path: Path) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Parse APOC cypher-shell UNWIND export enough to count labels/rels."""
    labels: Dict[str, int] = {}
    rels: Dict[str, int] = {}

    pending_node_count = 0
    pending_rel_count = 0
    id_pat = re.compile(r"\{id:")
    unique_id_pat = re.compile(r"\{_id:")
    start_pat = re.compile(r"\{start:")
    direct_label_pat = re.compile(r"CREATE \(n:([A-Za-z0-9_]+)\{")
    set_label_pat = re.compile(r"SET n:([A-Za-z0-9_]+)")
    rel_pat = re.compile(r"CREATE \(start\)-\[r:([A-Z_]+)\]->\(end\)")

    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("UNWIND ["):
                pending_node_count = len(id_pat.findall(line)) + len(unique_id_pat.findall(line))
                pending_rel_count = len(start_pat.findall(line))

            label = None
            direct_match = direct_label_pat.search(line)
            if direct_match:
                label = direct_match.group(1)
            set_match = set_label_pat.search(line)
            if set_match:
                label = set_match.group(1)
            if label:
                _bump(labels, label, pending_node_count or 1)
                pending_node_count = 0

            rel_match = rel_pat.search(line)
            if rel_match:
                _bump(rels, rel_match.group(1), pending_rel_count or 1)
                pending_rel_count = 0

    return labels, rels


def audit_neo4j() -> Tuple[Dict[str, int], Dict[str, int]]:
    _load_env()
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password123")
    if uri in ("neo4j:7687", "neo4j://neo4j:7687", "bolt://neo4j:7687"):
        uri = "bolt://localhost:7687"

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] Missing dependency: pip install neo4j")
        sys.exit(2)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    with driver.session() as session:
        label_rows = session.run(
            "MATCH (n) WITH labels(n)[0] AS label, count(n) AS count "
            "RETURN label, count ORDER BY label"
        )
        labels = {row["label"]: row["count"] for row in label_rows}

        rel_rows = session.run(
            "MATCH ()-[r]->() WITH type(r) AS rel, count(r) AS count "
            "RETURN rel, count ORDER BY rel"
        )
        rels = {row["rel"]: row["count"] for row in rel_rows}
    driver.close()
    return labels, rels


def print_section(title: str, rows: Dict[str, int]) -> None:
    print(f"\n=== {title} ===")
    if not rows:
        print("  (none)")
        return
    for key in sorted(rows):
        print(f"  {key:<30} {rows[key]:>10,}")


def print_delta(title: str, values: set[str]) -> None:
    print(f"\n{title}:")
    if not values:
        print("  (none)")
        return
    for value in sorted(values):
        print(f"  - {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit graph ontology labels and relationships.")
    parser.add_argument("--file", default=str(DEFAULT_EXPORT), help="Cypher export file to inspect")
    parser.add_argument("--neo4j", action="store_true", help="Inspect the live Neo4j database")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when missing/unexpected types exist")
    args = parser.parse_args()

    if args.neo4j:
        labels, rels = audit_neo4j()
        source = "live Neo4j"
    else:
        path = Path(args.file)
        if not path.exists():
            print(f"[ERR] File not found: {path}")
            return 2
        labels, rels = audit_cypher_export(path)
        source = str(path)

    expected_labels = set(EXPECTED_NODE_LABELS)
    expected_rels = set(EXPECTED_RELATIONSHIP_TYPES)
    found_labels = set(labels)
    found_rels = set(rels)

    print(f"Source: {source}")
    print(f"Expected labels: {len(expected_labels)} | Found labels: {len(found_labels)}")
    print(f"Expected rels  : {len(expected_rels)} | Found rels  : {len(found_rels)}")

    print_section("Node Counts", labels)
    print_section("Relationship Counts", rels)
    print_delta("Missing node labels", expected_labels - found_labels)
    print_delta("Unexpected node labels", found_labels - expected_labels)
    print_delta("Missing relationship types", expected_rels - found_rels)
    print_delta("Unexpected relationship types", found_rels - expected_rels)

    has_drift = bool(
        (expected_labels - found_labels)
        or (found_labels - expected_labels)
        or (expected_rels - found_rels)
        or (found_rels - expected_rels)
    )
    return 1 if args.strict and has_drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
