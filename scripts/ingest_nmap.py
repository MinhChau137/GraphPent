#!/usr/bin/env python3
"""
ingest_nmap.py — Parse Nmap XML và MERGE trực tiếp vào Neo4j (không qua LLM).

Dùng NmapAdapter để parse → upsert entities/relations qua Neo4jAdapter.

Usage (trong container):
    python /app/scripts/ingest_nmap.py --file /app/data/sample_nmap_scan.xml
    python /app/scripts/ingest_nmap.py --file /app/data/sample_nmap_scan.xml --dry-run
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from app.adapters.nmap_adapter import NmapAdapter
from app.adapters.neo4j_client import Neo4jAdapter
from app.core.logger import logger


async def ingest(xml_path: Path, dry_run: bool):
    adapter = NmapAdapter()
    neo4j   = Neo4jAdapter()

    print(f"[PARSE] {xml_path}")
    entities, relations = await adapter.parse_file(str(xml_path))
    summary = adapter.summarise(entities, relations)

    print(f"  Hosts   : {summary['hosts']}")
    print(f"  Ports   : {summary['open_ports']}")
    print(f"  Services: {summary['services']}")
    print(f"  IPs     : {sum(1 for e in entities if e.type == 'IP')}")
    print(f"  Relations: {len(relations)}")

    if dry_run:
        print("\n[DRY RUN] Khong ghi Neo4j.")
        # In sample
        for e in entities[:5]:
            print(f"  Entity: {e.type} | {e.id} | {e.name}")
        for r in relations[:5]:
            print(f"  Relation: {r.source_id} -[{r.type}]-> {r.target_id}")
        return

    print("\n[MERGE] Ghi vao Neo4j...")
    ok = err = 0
    for entity in entities:
        try:
            await neo4j.upsert_entity(
                entity_id=entity.id,
                label=entity.type,
                name=entity.name,
                properties=entity.properties or {},
            )
            ok += 1
        except Exception as e:
            err += 1
            if err <= 3:
                print(f"  [ERR] entity {entity.id}: {e}")

    print(f"  Entities: {ok} ok, {err} errors")

    ok = err = 0
    for rel in relations:
        try:
            await neo4j.upsert_relation(
                source_id=rel.source_id,
                target_id=rel.target_id,
                rel_type=rel.type,
                properties=rel.properties or {},
            )
            ok += 1
        except Exception as e:
            err += 1
            if err <= 3:
                print(f"  [ERR] relation {rel.source_id}->{rel.target_id}: {e}")

    print(f"  Relations: {ok} ok, {err} errors")
    print("\n[DONE]")


def main():
    parser = argparse.ArgumentParser(description="Ingest Nmap XML into Neo4j.")
    parser.add_argument("--file", required=True, help="Path to Nmap XML file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    xml_path = Path(args.file)
    if not xml_path.exists():
        print(f"[ERR] File not found: {xml_path}")
        sys.exit(1)

    asyncio.run(ingest(xml_path, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
