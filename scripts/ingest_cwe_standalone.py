#!/usr/bin/env python3
"""
ingest_cwe_standalone.py — Parse cwec_v4.x.xml và MERGE vào Neo4j.

Tạo CWE nodes với đầy đủ: id, cwe_id, name, description, abstraction.
Tạo CWE->CWE edges: CHILD_OF, CAN_PRECEDE, CAN_ALSO_BE.

Usage:
    python scripts/ingest_cwe_standalone.py
    python scripts/ingest_cwe_standalone.py --file data/cwec_v4.19.1.xml
    python scripts/ingest_cwe_standalone.py --dry-run
"""

import argparse
import os
import sys
import xml.etree.ElementTree as ET
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

DEFAULT_CWE_FILE = Path(__file__).parent.parent / "data" / "cwec_v4.19.1.xml"
NS = "http://cwe.mitre.org/cwe-7"


def _tag(name: str) -> str:
    return f"{{{NS}}}{name}"


def _text(elem, tag: str) -> str:
    child = elem.find(_tag(tag))
    if child is None:
        return ""
    # Concatenate all inner text (mixed content)
    parts = []
    if child.text:
        parts.append(child.text.strip())
    for sub in child:
        if sub.text:
            parts.append(sub.text.strip())
        if sub.tail:
            parts.append(sub.tail.strip())
    return " ".join(p for p in parts if p)[:600]


def parse_cwe_xml(xml_path: Path) -> tuple:
    """Returns (nodes, edges) as lists of dicts."""
    print(f"[PARSE] {xml_path}")
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    weaknesses_elem = root.find(_tag("Weaknesses"))
    if weaknesses_elem is None:
        print("[ERR] No <Weaknesses> element found in XML.")
        return [], []

    nodes = []
    edges = []

    for w in weaknesses_elem.findall(_tag("Weakness")):
        cwe_num = w.get("ID", "")
        if not cwe_num:
            continue

        cwe_id  = f"CWE-{cwe_num}"
        node_id = cwe_id.lower()
        name    = w.get("Name", "")
        abstraction = w.get("Abstraction", "")

        # Description
        desc = _text(w, "Description")
        ext_desc = _text(w, "Extended_Description")

        nodes.append({
            "id":          node_id,
            "cwe_id":      cwe_id,
            "name":        name,
            "description": desc[:500],
            "abstraction": abstraction,
        })

        # Related weaknesses → CWE->CWE edges
        rw_elem = w.find(_tag("Related_Weaknesses"))
        if rw_elem is not None:
            for rw in rw_elem.findall(_tag("Related_Weakness")):
                nature    = rw.get("Nature", "").upper()
                target_id = rw.get("CWE_ID", "")
                if not target_id:
                    continue
                # Map nature to edge type
                rel_map = {
                    "CHILDOF":      "CHILD_OF",
                    "PARENTOF":     "PARENT_OF",
                    "CANPRECEDE":   "CAN_PRECEDE",
                    "CANFOLLOW":    "CAN_FOLLOW",
                    "REQUIREDBY":   "REQUIRED_BY",
                    "REQUIRES":     "REQUIRES",
                    "CANALSOBEBE":  "CAN_ALSO_BE",
                    "PEERMEANINGOF": "PEER_OF",
                }
                rel_type = rel_map.get(nature.replace("_", "").replace(" ", ""), "RELATED_TO")
                edges.append({
                    "src":  node_id,
                    "dst":  f"cwe-{target_id}",
                    "type": rel_type,
                })

    print(f"  Parsed: {len(nodes):,} CWE nodes, {len(edges):,} edges")
    return nodes, edges


_CYPHER_MERGE_CWE = """
UNWIND $rows AS row
MERGE (c:CWE {id: row.id})
SET
    c.cwe_id      = row.cwe_id,
    c.name        = row.name,
    c.description = row.description,
    c.abstraction = row.abstraction,
    c.updated_at  = datetime()
"""

_CYPHER_MERGE_EDGE = """
UNWIND $rows AS row
MATCH (a:CWE {id: row.src})
MATCH (b:CWE {id: row.dst})
MERGE (a)-[r:RELATED_TO {nature: row.type}]->(b)
"""


def write_to_neo4j(nodes: list, edges: list, batch_size: int = 200):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"[NEO4J] Connected: {NEO4J_URI}")

    with driver.session() as s:
        s.run("CREATE INDEX cwe_id IF NOT EXISTS FOR (c:CWE) ON (c.id)")

    # Write nodes in batches
    written = 0
    for start in range(0, len(nodes), batch_size):
        batch = nodes[start: start + batch_size]
        with driver.session() as s:
            s.run(_CYPHER_MERGE_CWE, rows=batch)
        written += len(batch)

    print(f"  CWE nodes written: {written:,}")

    # Write edges (only between nodes that exist)
    written_edges = 0
    for start in range(0, len(edges), batch_size):
        batch = edges[start: start + batch_size]
        with driver.session() as s:
            try:
                s.run(_CYPHER_MERGE_EDGE, rows=batch)
                written_edges += len(batch)
            except Exception as e:
                # Some target CWEs may not exist — skip silently
                pass

    print(f"  CWE->CWE edges written: {written_edges:,}")
    driver.close()
    print("[DONE]")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest CWE XML into Neo4j."
    )
    parser.add_argument("--file", default=str(DEFAULT_CWE_FILE),
                        help="Path to cwec_vX.xml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    xml_path = Path(args.file)
    if not xml_path.exists():
        print(f"[ERR] File not found: {xml_path}")
        sys.exit(1)

    nodes, edges = parse_cwe_xml(xml_path)

    if args.dry_run:
        print("\n[DRY RUN] Sample nodes:")
        for n in nodes[:3]:
            print(f"  {n['cwe_id']}: {n['name']} ({n['abstraction']})")
        return

    write_to_neo4j(nodes, edges, args.batch_size)


if __name__ == "__main__":
    main()
