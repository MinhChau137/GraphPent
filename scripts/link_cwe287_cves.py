#!/usr/bin/env python3
"""
Link CWE-287 → CVE nodes in Neo4j.

Workflow:
1. Scan cvelistV5 for CVEs with problemTypes.cweId matching any target CWE
2. Extract CVSS data from same file
3. Upsert CVE nodes into Neo4j
4. Create CLASSIFIED_AS edges  CWE → CVE

Target CWEs (authentication / access control family):
  CWE-287 Improper Authentication
  CWE-862 Missing Authorization
  CWE-284 Improper Access Control

Chạy:
    python scripts/link_cwe287_cves.py
    python scripts/link_cwe287_cves.py --dry-run
    python scripts/link_cwe287_cves.py --limit 100  # default 50
"""
import asyncio
import json
import re
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import AsyncGraphDatabase
from app.config.settings import settings

CVE_DIR = Path(__file__).parent.parent / "data" / "cvelistV5-main" / "cvelistV5-main" / "cves"
BATCH_SIZE = 100

# CWEs we want to link — maps canonical node id → CWE-XXX label used in files
TARGET_CWES = {
    "cwe-287": "CWE-287",
    "cwe-862": "CWE-862",
    "cwe-284": "CWE-284",
}


def _extract_cwe_ids(data: dict) -> list[str]:
    """Extract all CWE IDs from a cvelistV5 record's problemTypes."""
    cwe_ids = []
    try:
        problem_types = data["containers"]["cna"].get("problemTypes", [])
        for pt in problem_types:
            for desc in pt.get("descriptions", []):
                # New format: {"cweId": "CWE-287", "type": "CWE"}
                cwe_id = desc.get("cweId", "")
                if cwe_id:
                    cwe_ids.append(cwe_id.upper())
                    continue
                # Old format: {"value": "CWE-287 Improper Authentication", "type": "text"}
                val = desc.get("value", "")
                m = re.search(r"CWE-(\d+)", val, re.IGNORECASE)
                if m:
                    cwe_ids.append(f"CWE-{m.group(1)}")
    except (KeyError, TypeError):
        pass
    return cwe_ids


def _extract_cve_id(data: dict) -> str | None:
    """Extract canonical CVE ID from cvelistV5 record."""
    try:
        return data["cveMetadata"]["cveId"].upper()
    except (KeyError, TypeError):
        return None


def _extract_cvss(data: dict) -> dict | None:
    """Extract best available CVSS from cvelistV5 record."""
    try:
        metrics = data["containers"]["cna"].get("metrics", [])
    except (KeyError, TypeError):
        return None

    for priority_key in ("cvssV3_1", "cvssV3_0", "cvssV4_0", "cvssV2_0"):
        for metric in metrics:
            if priority_key in metric:
                cvss = metric[priority_key]
                score = cvss.get("baseScore")
                severity = cvss.get("baseSeverity", "").upper()
                if score is not None:
                    return {
                        "cvss_score": float(score),
                        "severity": severity or _score_to_severity(float(score)),
                        "cvss_vector": cvss.get("vectorString", ""),
                        "cvss_version": cvss.get("version", priority_key),
                    }
    return None


def _extract_description(data: dict) -> str:
    try:
        descs = data["containers"]["cna"].get("descriptions", [])
        for d in descs:
            if d.get("lang", "").startswith("en"):
                return d.get("value", "")[:500]
    except (KeyError, TypeError):
        pass
    return ""


def _score_to_severity(score: float) -> str:
    if score >= 9.0:
        return "CRITICAL"
    elif score >= 7.0:
        return "HIGH"
    elif score >= 4.0:
        return "MEDIUM"
    return "LOW"


def _scan_year(year_dir: Path, target_cwe_labels: set[str], limit: int) -> list[dict]:
    """Scan a year directory, return list of {cve_id, cwe_id, cvss, description}."""
    hits = []
    for range_dir in sorted(year_dir.iterdir()):
        if not range_dir.is_dir():
            continue
        for fpath in sorted(range_dir.glob("CVE-*.json")):
            if len(hits) >= limit:
                return hits
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                cwes = _extract_cwe_ids(data)
                matched = [c for c in cwes if c in target_cwe_labels]
                if not matched:
                    continue
                cve_id = _extract_cve_id(data)
                if not cve_id:
                    continue
                hits.append({
                    "cve_id": cve_id,
                    "matched_cwes": matched,
                    "cvss": _extract_cvss(data),
                    "description": _extract_description(data),
                })
            except Exception:
                pass
    return hits


async def _upsert_cves_and_edges(driver, hits: list[dict], dry_run: bool) -> dict:
    """Upsert CVE nodes and create CLASSIFIED_AS edges."""
    if dry_run:
        for h in hits:
            cvss = h["cvss"]
            score = f"{cvss['cvss_score']:.1f}" if cvss else "N/A"
            sev = cvss["severity"] if cvss else "N/A"
            print(f"  [DRY] {h['cve_id']:25s} {score:>5} {sev:>10} <- {','.join(h['matched_cwes'])}")
        return {"upserted": len(hits), "edges": sum(len(h["matched_cwes"]) for h in hits)}

    # Build flat list for UNWIND
    node_rows = []
    edge_rows = []
    for h in hits:
        cvss = h["cvss"] or {}
        node_rows.append({
            "id": h["cve_id"].lower(),
            "name": h["cve_id"].upper(),
            "description": h["description"],
            "cvss_score": cvss.get("cvss_score"),
            "severity": cvss.get("severity", "UNKNOWN"),
            "cvss_vector": cvss.get("cvss_vector", ""),
            "cvss_version": cvss.get("cvss_version", ""),
        })
        for cwe_label in h["matched_cwes"]:
            # "CWE-287" → "cwe-287"
            cwe_node_id = cwe_label.lower()
            edge_rows.append({"cve_id": h["cve_id"].lower(), "cwe_id": cwe_node_id})

    async with driver.session() as session:
        # Upsert CVE nodes
        await session.run(
            """
            UNWIND $rows AS r
            MERGE (cve {id: r.id})
            ON CREATE SET cve:CVE, cve.name = r.name, cve.created_at = timestamp()
            SET cve:CVE,
                cve.name        = r.name,
                cve.description = r.description,
                cve.cvss_score  = CASE WHEN r.cvss_score IS NOT NULL THEN r.cvss_score ELSE cve.cvss_score END,
                cve.severity    = CASE WHEN r.severity IS NOT NULL   THEN r.severity   ELSE cve.severity   END,
                cve.cvss_vector = r.cvss_vector,
                cve.cvss_version= r.cvss_version,
                cve.updated_at  = timestamp()
            """,
            rows=node_rows,
        )

        # Create CLASSIFIED_AS edges CWE → CVE
        result = await session.run(
            """
            UNWIND $rows AS r
            MATCH (cwe {id: r.cwe_id})
            MATCH (cve {id: r.cve_id})
            MERGE (cwe)-[rel:CLASSIFIED_AS]->(cve)
            ON CREATE SET rel.inferred = false, rel.source = 'cvelistV5'
            RETURN count(rel) AS edges_created
            """,
            rows=edge_rows,
        )
        record = await result.single()
        edges_created = record["edges_created"] if record else 0

    return {"upserted": len(node_rows), "edges": edges_created}


async def run(dry_run: bool, limit: int, years: list[str] | None):
    neo4j_uri = settings.NEO4J_URI.replace("neo4j:7687", "localhost:7687")
    driver = AsyncGraphDatabase.driver(
        neo4j_uri, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    target_cwe_labels = set(TARGET_CWES.values())  # {"CWE-287", "CWE-862", "CWE-284"}
    print(f"Target CWEs: {target_cwe_labels}")
    print(f"Limit: {limit} CVEs per CWE (across all years)")

    all_hits = []
    year_dirs = sorted(CVE_DIR.iterdir(), reverse=True)  # newest first
    for yd in year_dirs:
        if not yd.is_dir():
            continue
        if years and yd.name not in years:
            continue
        remaining = limit - len(all_hits)
        if remaining <= 0:
            break
        print(f"  Scanning {yd.name}...", end=" ", flush=True)
        hits = _scan_year(yd, target_cwe_labels, remaining)
        all_hits.extend(hits)
        print(f"{len(hits)} hits (total={len(all_hits)})")

    print(f"\nTotal CVEs found: {len(all_hits)}")

    # Show breakdown by CWE
    from collections import Counter
    cwe_counts: Counter = Counter()
    for h in all_hits:
        for c in h["matched_cwes"]:
            cwe_counts[c] += 1
    for cwe, cnt in sorted(cwe_counts.items()):
        print(f"  {cwe}: {cnt} CVEs")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Upserting {len(all_hits)} CVE nodes + edges...")
    stats = await _upsert_cves_and_edges(driver, all_hits, dry_run)

    await driver.close()

    print("\n" + "=" * 55)
    print("CWE-287 Link Summary")
    print("=" * 55)
    print(f"  CVEs scanned from cvelistV5: {len(all_hits)}")
    for cwe, cnt in sorted(cwe_counts.items()):
        print(f"  {cwe} -> CVE links:             {cnt}")
    print(f"  Nodes upserted:              {stats['upserted']}")
    print(f"  Edges created:               {stats['edges']}")
    print(f"  Mode:                        {'DRY RUN' if dry_run else 'WRITTEN'}")
    print("=" * 55)

    if not dry_run:
        print("\nNext: re-run GNN scoring + L5 benchmark")
        print("  curl -X POST http://localhost:8000/risk/score")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--limit", type=int, default=50, help="Max CVEs per run (default 50)")
    parser.add_argument("--years", nargs="+", help="Only scan specific years e.g. --years 2023 2024")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit, years=args.years))
