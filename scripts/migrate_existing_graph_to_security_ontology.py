#!/usr/bin/env python3
"""Backfill the target security ontology from existing Vulnerability properties.

This script is intentionally conservative:
- default mode is a dry run;
- use --apply to create AffectedProduct/IMPACTS/VERSION_OF and
  Mitigation/RESOLVED_BY from existing Vulnerability properties;
- use --prune-non-ontology only when you explicitly want to remove labels and
  relationship types outside the canonical ontology.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domain.graph_schema import EXPECTED_NODE_LABELS, EXPECTED_RELATIONSHIP_TYPES


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9_.\-]+", "_", value)
    return value.strip("_") or "unknown"


def _product_base_id(vendor: str, product: str) -> str:
    vendor_part = _slug(vendor)
    product_part = _slug(product)
    return f"product-{vendor_part}-{product_part}" if vendor_part else f"product-{product_part}"


def _product_version_key(item: dict) -> str:
    parts = [
        item.get("version", ""),
        item.get("version_start_incl", ""),
        item.get("version_start_excl", ""),
        item.get("version_end_incl", ""),
        item.get("version_end_excl", ""),
    ]
    key = "_".join(_slug(p) for p in parts if p)
    return key or "all"


def _parse_cpe_affected(raw_items: Iterable) -> list[dict]:
    parsed = []
    for item in raw_items or []:
        if isinstance(item, dict):
            parsed.append(item)
            continue
        try:
            parsed.append(json.loads(item))
        except Exception:
            continue
    return parsed


def _affected_product_nodes(affected: list[dict]) -> list[dict]:
    products = []
    seen = set()
    for item in affected:
        vendor = item.get("vendor", "")
        product = item.get("product", "")
        if not product:
            continue
        base_id = _product_base_id(vendor, product)
        version_key = _product_version_key(item)
        node_id = f"{base_id}-{version_key}" if version_key != "all" else base_id
        if node_id in seen:
            continue
        seen.add(node_id)

        version = item.get("version", "")
        end_incl = item.get("version_end_incl", "")
        end_excl = item.get("version_end_excl", "")
        if version:
            version_label = version
        elif end_excl:
            version_label = f"< {end_excl}"
        elif end_incl:
            version_label = f"<= {end_incl}"
        else:
            version_label = "all affected versions"

        base_name = f"{vendor} {product}".strip() or product
        products.append({
            "id": node_id,
            "name": f"{base_name} {version_label}".strip(),
            "base_id": base_id,
            "base_name": base_name,
            "vendor": vendor,
            "product_name": product,
            "version": version,
            "version_start_incl": item.get("version_start_incl", ""),
            "version_start_excl": item.get("version_start_excl", ""),
            "version_end_incl": end_incl,
            "version_end_excl": end_excl,
            "criteria": item.get("criteria", ""),
            "status": "vulnerable",
        })
    return products


def get_driver():
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
    print(f"[OK] Connected: {uri}")
    return driver


_MERGE_PRODUCTS = """
UNWIND $rows AS row
UNWIND row.affected_products AS product
MERGE (p:AffectedProduct {id: product.id})
SET
    p.name               = product.name,
    p.vendor             = product.vendor,
    p.product_name       = product.product_name,
    p.version            = product.version,
    p.version_start_incl = product.version_start_incl,
    p.version_start_excl = product.version_start_excl,
    p.version_end_incl   = product.version_end_incl,
    p.version_end_excl   = product.version_end_excl,
    p.criteria           = product.criteria,
    p.status             = product.status,
    p.updated_at         = datetime()
MERGE (v:Vulnerability {id: row.id})
MERGE (v)-[impact:IMPACTS]->(p)
SET impact.source = 'ontology_migration',
    impact.confidence = 0.95,
    impact.updated_at = datetime()
WITH p, product
WHERE product.base_id IS NOT NULL AND product.base_id <> product.id
MERGE (base:AffectedProduct {id: product.base_id})
SET base.name = product.base_name,
    base.vendor = product.vendor,
    base.product_name = product.product_name,
    base.status = 'base',
    base.updated_at = datetime()
MERGE (p)-[version_rel:VERSION_OF]->(base)
SET version_rel.source = 'ontology_migration',
    version_rel.confidence = 0.90,
    version_rel.updated_at = datetime()
"""


_MERGE_MITIGATIONS = """
UNWIND $rows AS row
WITH row
WHERE row.patch_available = true
MERGE (m:Mitigation {id: 'mitigation-' + row.id})
SET
    m.name          = 'Patch or upgrade for ' + row.cve_id,
    m.description   = CASE
        WHEN row.patch_date IS NULL OR row.patch_date = ''
        THEN 'Apply vendor patch or upgrade for ' + row.cve_id
        ELSE 'Apply vendor patch or upgrade for ' + row.cve_id + ' confirmed on ' + row.patch_date
    END,
    m.patch_date    = row.patch_date,
    m.effectiveness = 'high',
    m.updated_at    = datetime()
MERGE (v:Vulnerability {id: row.id})
MERGE (v)-[r:RESOLVED_BY]->(m)
SET r.source = 'ontology_migration',
    r.confidence = 0.85,
    r.updated_at = datetime()
"""


def load_rows(driver, limit: int | None) -> list[dict]:
    query = """
    MATCH (v:Vulnerability)
    WHERE v.cpe_affected IS NOT NULL OR v.patch_available = true
    RETURN v.id AS id, coalesce(v.cve_id, v.name, v.id) AS cve_id,
           v.cpe_affected AS cpe_affected,
           coalesce(v.patch_available, false) AS patch_available,
           coalesce(v.patch_date, '') AS patch_date
    ORDER BY v.id
    """
    if limit:
        query += " LIMIT $limit"
    with driver.session() as session:
        records = session.run(query, limit=limit)
        rows = []
        for record in records:
            affected = _parse_cpe_affected(record["cpe_affected"])
            rows.append({
                "id": record["id"],
                "cve_id": record["cve_id"],
                "patch_available": bool(record["patch_available"]),
                "patch_date": record["patch_date"] or "",
                "affected_products": _affected_product_nodes(affected),
            })
    return rows


def apply_backfill(driver, rows: list[dict], batch_size: int) -> dict:
    stats = {"vulnerabilities": len(rows), "products": 0, "patched_vulns": 0}
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        stats["products"] += sum(len(row["affected_products"]) for row in batch)
        stats["patched_vulns"] += sum(1 for row in batch if row["patch_available"])
        with driver.session() as session:
            session.run(_MERGE_PRODUCTS, rows=batch)
            session.run(_MERGE_MITIGATIONS, rows=batch)
    return stats


def prune_non_ontology(driver) -> None:
    with driver.session() as session:
        rel_result = session.run(
            "MATCH ()-[r]->() WHERE NOT type(r) IN $allowed WITH r DELETE r RETURN count(*) AS deleted",
            allowed=list(EXPECTED_RELATIONSHIP_TYPES),
        ).single()
        node_result = session.run(
            "MATCH (n) WHERE none(label IN labels(n) WHERE label IN $allowed) "
            "WITH n DETACH DELETE n RETURN count(*) AS deleted",
            allowed=list(EXPECTED_NODE_LABELS),
        ).single()
    print(f"[PRUNE] Deleted relationships: {rel_result['deleted'] if rel_result else 0:,}")
    print(f"[PRUNE] Deleted nodes        : {node_result['deleted'] if node_result else 0:,}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill target security ontology from existing graph.")
    parser.add_argument("--apply", action="store_true", help="Write ontology backfill to Neo4j")
    parser.add_argument("--limit", type=int, default=None, help="Limit vulnerabilities for testing")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--prune-non-ontology", action="store_true",
                        help="Delete labels/relationships outside the canonical ontology")
    args = parser.parse_args()

    driver = get_driver()
    rows = load_rows(driver, args.limit)
    product_count = sum(len(row["affected_products"]) for row in rows)
    patched_count = sum(1 for row in rows if row["patch_available"])

    print(f"[SCAN] Vulnerabilities considered : {len(rows):,}")
    print(f"[SCAN] AffectedProduct rows       : {product_count:,}")
    print(f"[SCAN] Patchable vulnerabilities  : {patched_count:,}")

    if args.apply:
        stats = apply_backfill(driver, rows, args.batch_size)
        print(f"[APPLY] Vulnerabilities processed: {stats['vulnerabilities']:,}")
        print(f"[APPLY] Product relationships    : {stats['products']:,}")
        print(f"[APPLY] Resolution relationships : {stats['patched_vulns']:,}")
        if args.prune_non_ontology:
            prune_non_ontology(driver)
    else:
        print("[DRY-RUN] No writes performed. Add --apply to update Neo4j.")
        if args.prune_non_ontology:
            print("[DRY-RUN] --prune-non-ontology is ignored without --apply.")

    driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
