#!/usr/bin/env python3
"""
backup_graph.py — Export/Import Neo4j knowledge graph qua APOC Cypher dump.

Export (backup):
    python scripts/backup_graph.py export
    python scripts/backup_graph.py export --out outputs/backups/my_backup.cypher

Import (restore):
    python scripts/backup_graph.py import --file outputs/backups/graph_20260511.cypher
    python scripts/backup_graph.py import --file outputs/backups/graph_20260511.cypher --wipe
"""

import argparse
import os
import sys
from datetime import datetime
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

DEFAULT_OUT = Path(__file__).parent.parent / "outputs" / "backups"


def get_driver():
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"[OK]  Connected: {NEO4J_URI}")
    return driver


# ── EXPORT ────────────────────────────────────────────────────────────────────

def export_via_apoc(driver) -> str:
    """Stream toàn bộ graph qua APOC, trả về chuỗi Cypher."""
    print("[APOC] Streaming graph via apoc.export.cypher.all ...")
    cypher_parts = []
    with driver.session() as s:
        result = s.run(
            "CALL apoc.export.cypher.all(null, "
            "{streamStatements: true, format: 'cypher-shell', useOptimizations: "
            "{type: 'UNWIND_BATCH', unwindBatchSize: 100}}) "
            "YIELD cypherStatements RETURN cypherStatements"
        )
        for record in result:
            stmt = record["cypherStatements"]
            if stmt:
                cypher_parts.append(stmt)
    return "\n".join(cypher_parts)


def export_manual(driver) -> str:
    """Fallback thủ công: tạo MERGE statements nếu APOC không có."""
    print("[MANUAL] Generating MERGE statements (APOC fallback) ...")
    lines = [
        "// GraphPent manual Cypher backup",
        f"// Generated: {datetime.now().isoformat()}",
        "// Import: cypher-shell -u neo4j -p <pass> --file graph_backup.cypher",
        "",
        "// --- CONSTRAINTS & INDEXES ---",
        "CREATE CONSTRAINT vuln_id IF NOT EXISTS FOR (n:Vulnerability) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT cwe_id  IF NOT EXISTS FOR (n:CWE)           REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT host_id IF NOT EXISTS FOR (n:Host)          REQUIRE n.id IS UNIQUE;",
        "",
        "// --- NODES ---",
    ]

    with driver.session() as s:
        labels_result = s.run("CALL db.labels() YIELD label RETURN label ORDER BY label")
        labels = [r["label"] for r in labels_result]

    for label in labels:
        with driver.session() as s:
            result = s.run(f"MATCH (n:`{label}`) RETURN properties(n) AS props")
            count = 0
            for record in result:
                props = dict(record["props"])
                node_id = props.get("id", "")
                if not node_id:
                    continue
                prop_str = _props_to_cypher(props)
                lines.append(f'MERGE (n:`{label}` {{id: {_val(node_id)}}}) SET n += {{{prop_str}}};')
                count += 1
        print(f"  [{label}] {count:,} nodes")

    lines += ["", "// --- RELATIONSHIPS ---"]

    with driver.session() as s:
        rel_result = s.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
        rel_types = [r["relationshipType"] for r in rel_result]

    for rel_type in rel_types:
        with driver.session() as s:
            result = s.run(f"""
                MATCH (a)-[r:`{rel_type}`]->(b)
                WHERE a.id IS NOT NULL AND b.id IS NOT NULL
                RETURN labels(a)[0] AS al, a.id AS aid,
                       labels(b)[0] AS bl, b.id AS bid,
                       properties(r) AS rprops
            """)
            count = 0
            for rec in result:
                prop_str = _props_to_cypher(rec["rprops"] or {})
                set_clause = f" SET r += {{{prop_str}}}" if prop_str else ""
                lines.append(
                    f'MATCH (a:`{rec["al"]}` {{id: {_val(rec["aid"])}}}) '
                    f'MATCH (b:`{rec["bl"]}` {{id: {_val(rec["bid"])}}}) '
                    f'MERGE (a)-[r:`{rel_type}`]->(b){set_clause};'
                )
                count += 1
        print(f"  [{rel_type}] {count:,} edges")

    return "\n".join(lines)


def _val(v) -> str:
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _props_to_cypher(props: dict) -> str:
    parts = []
    for k, v in props.items():
        if v is None:
            continue
        if isinstance(v, list):
            items = ", ".join(_val(i) for i in v)
            parts.append(f"{k}: [{items}]")
        else:
            parts.append(f"{k}: {_val(v)}")
    return ", ".join(parts)


def cmd_export(args):
    DEFAULT_OUT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = DEFAULT_OUT / f"graph_{timestamp}.cypher"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    driver = get_driver()

    # Stats trước khi export
    with driver.session() as s:
        n_nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        n_edges = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    print(f"[INFO] Graph: {n_nodes:,} nodes, {n_edges:,} edges\n")

    # Thử APOC trước
    try:
        cypher_text = export_via_apoc(driver)
        method = "apoc"
    except Exception as e:
        print(f"[WARN] APOC failed ({e}), dùng fallback thủ công ...")
        cypher_text = export_manual(driver)
        method = "manual"

    driver.close()

    # Header
    header = "\n".join([
        f"// GraphPent Knowledge Graph Backup",
        f"// Date     : {datetime.now().isoformat()}",
        f"// Source   : {NEO4J_URI}",
        f"// Nodes    : {n_nodes:,}",
        f"// Edges    : {n_edges:,}",
        f"// Method   : {method}",
        f"//",
        f"// Restore  : python scripts/backup_graph.py import --file {out_path.name}",
        f"// Or       : cypher-shell -u {NEO4J_USER} -p <password> --file {out_path.name}",
        "",
    ])

    out_path.write_text(header + cypher_text, encoding="utf-8")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\n[DONE] Backup saved: {out_path}")
    print(f"       Size: {size_mb:.2f} MB | Method: {method}")


# ── IMPORT ────────────────────────────────────────────────────────────────────

def cmd_import(args):
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERR] File not found: {file_path}")
        sys.exit(1)

    driver = get_driver()

    if args.wipe:
        confirm = input("\n[WARN] --wipe se xoa TOAN BO graph hien tai. Tiep tuc? (yes/no): ").strip()
        if confirm.lower() != "yes":
            print("Huy.")
            driver.close()
            return
        with driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
        print("[OK]  Graph cleared.")

    print(f"\n[IMPORT] Doc file: {file_path}")
    cypher_text = file_path.read_text(encoding="utf-8")

    # Tách từng statement (kết thúc bằng ;)
    statements = [
        s.strip() for s in cypher_text.split(";")
        if s.strip() and not s.strip().startswith("//")
    ]
    print(f"[INFO] {len(statements):,} statements to execute\n")

    ok = err = 0
    with driver.session() as s:
        for i, stmt in enumerate(statements, 1):
            if not stmt:
                continue
            try:
                s.run(stmt)
                ok += 1
            except Exception as e:
                err += 1
                if err <= 5:
                    print(f"  [ERR] stmt #{i}: {e}")
            if i % 500 == 0:
                print(f"  {i:,}/{len(statements):,} done ...")

    driver.close()

    with get_driver().session() as s:
        n_nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        n_edges = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

    print(f"\n[DONE] Import complete.")
    print(f"       OK: {ok:,} | Errors: {err:,}")
    print(f"       Graph now: {n_nodes:,} nodes, {n_edges:,} edges")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backup/Restore Neo4j knowledge graph.")
    parser.add_argument("--uri",  default=None, help="Neo4j URI (default: NEO4J_URI env or bolt://localhost:7687)")
    parser.add_argument("--user", default=None, help="Neo4j username")
    parser.add_argument("--password", default=None, help="Neo4j password")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="Export graph ra file Cypher")
    p_export.add_argument("--out", default=None, help="Output file path (.cypher)")

    p_import = sub.add_parser("import", help="Import graph tu file Cypher")
    p_import.add_argument("--file", required=True, help="File .cypher can import")
    p_import.add_argument("--wipe", action="store_true",
                          help="Xoa toan bo graph hien tai truoc khi import")

    args = parser.parse_args()

    # CLI flags override env vars
    global NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    if args.uri:
        NEO4J_URI = args.uri
    elif NEO4J_URI in ("neo4j:7687", "neo4j://neo4j:7687", "bolt://neo4j:7687"):
        NEO4J_URI = "bolt://localhost:7687"
    if args.user:
        NEO4J_USER = args.user
    if args.password:
        NEO4J_PASSWORD = args.password

    if args.cmd == "export":
        cmd_export(args)
    elif args.cmd == "import":
        cmd_import(args)


if __name__ == "__main__":
    main()
