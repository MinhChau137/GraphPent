#!/usr/bin/env python3
"""
Direct CVSS patcher — không dùng LLM.

Quy trình:
1. Query Neo4j lấy tất cả CVE-pattern node IDs
2. Map từng ID → file path trong cvelistV5 directory
3. Đọc JSON, extract baseScore + baseSeverity + vectorString
4. Batch UNWIND SET vào Neo4j

Chạy:
    python scripts/patch_cvss_direct.py
    python scripts/patch_cvss_direct.py --dry-run    # chỉ preview, không write
    python scripts/patch_cvss_direct.py --also-nvd   # thêm NVD JSON
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
NVD_FILE = Path(__file__).parent.parent / "data" / "nvdcve-2.0-modified.json"

BATCH_SIZE = 200  # nodes per Cypher UNWIND


def _cve_id_canonical(raw_id: str) -> str:
    """Normalize to uppercase: 'cve-2024-1234' → 'CVE-2024-1234'."""
    return raw_id.upper()


def _find_cvev5_file(cve_id: str) -> Path | None:
    """
    Map CVE-YEAR-NUM to cvelistV5 file path.
    CVE-2021-38289 → cves/2021/38xxx/CVE-2021-38289.json
    """
    m = re.match(r"CVE-(\d{4})-(\d+)$", cve_id, re.IGNORECASE)
    if not m:
        return None
    year = m.group(1)
    num = int(m.group(2))
    thousands = num // 1000
    range_dir = f"{thousands}xxx"
    candidate = CVE_DIR / year / range_dir / f"{cve_id.upper()}.json"
    return candidate if candidate.exists() else None


def _extract_cvss_from_v5(data: dict) -> dict | None:
    """Extract CVSS from cvelistV5 format."""
    try:
        metrics = data["containers"]["cna"].get("metrics", [])
    except (KeyError, TypeError):
        return None

    # Priority: cvssV3_1 > cvssV3_0 > cvssV4_0 > cvssV2_0
    for priority_key in ("cvssV3_1", "cvssV3_0", "cvssV4_0", "cvssV2_0"):
        for metric in metrics:
            if priority_key in metric:
                cvss = metric[priority_key]
                score = cvss.get("baseScore")
                severity = cvss.get("baseSeverity", "").upper()
                vector = cvss.get("vectorString", "")
                if score is not None:
                    return {
                        "cvss_score": float(score),
                        "severity": severity or _score_to_severity(float(score)),
                        "cvss_vector": vector,
                        "cvss_version": cvss.get("version", priority_key),
                    }
    return None


def _extract_cvss_from_nvd(item: dict) -> dict | None:
    """Extract CVSS from NVD CVE 2.0 format."""
    try:
        metrics = item.get("metrics", {})
        # Priority: v31 > v30 > v2
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            entries = metrics.get(key, [])
            for entry in entries:
                cvss = entry.get("cvssData", {})
                score = cvss.get("baseScore")
                severity = entry.get("baseSeverity", "").upper() or cvss.get("baseSeverity", "").upper()
                vector = cvss.get("vectorString", "")
                if score is not None:
                    return {
                        "cvss_score": float(score),
                        "severity": severity or _score_to_severity(float(score)),
                        "cvss_vector": vector,
                        "cvss_version": cvss.get("version", key),
                    }
    except Exception:
        pass
    return None


def _score_to_severity(score: float) -> str:
    if score >= 9.0:
        return "CRITICAL"
    elif score >= 7.0:
        return "HIGH"
    elif score >= 4.0:
        return "MEDIUM"
    else:
        return "LOW"


async def _get_cve_node_ids(driver) -> list[dict]:
    """Return list of {internal_id, node_id} for all CVE-pattern nodes."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (n) WHERE n.id =~ '(?i)CVE-.*' "
            "RETURN elementId(n) AS eid, n.id AS node_id, labels(n)[0] AS lbl"
        )
        return [{"eid": r["eid"], "node_id": r["node_id"], "lbl": r["lbl"]}
                async for r in result]


async def _batch_update(driver, updates: list[dict], dry_run: bool):
    """
    updates: [{node_id, cvss_score, severity, cvss_vector, cvss_version}, ...]
    Matches by toLower(n.id) = toLower($node_id) to handle mixed case.
    """
    if dry_run:
        for u in updates:
            print(f"  [DRY] {u['node_id']:30s} cvss={u['cvss_score']:.1f}  {u['severity']}")
        return len(updates)

    async with driver.session() as session:
        await session.run(
            """
            UNWIND $updates AS u
            MATCH (n)
            WHERE toLower(n.id) = toLower(u.node_id)
            SET n.cvss_score   = u.cvss_score,
                n.severity     = u.severity,
                n.cvss_vector  = u.cvss_vector,
                n.cvss_version = u.cvss_version
            """,
            updates=updates,
        )
    return len(updates)


def _load_nvd_index(nvd_file: Path) -> dict[str, dict]:
    """Load NVD JSON and index by uppercase CVE ID."""
    if not nvd_file.exists():
        print(f"[WARN] NVD file not found: {nvd_file}")
        return {}
    print(f"Loading NVD JSON ({nvd_file.stat().st_size / 1_048_576:.1f} MB)...", end=" ", flush=True)
    with open(nvd_file, encoding="utf-8") as f:
        data = json.load(f)
    index = {}
    items = data.get("vulnerabilities", data.get("CVE_Items", []))
    for item in items:
        cve_obj = item.get("cve", item)
        cve_id = (cve_obj.get("id") or
                  cve_obj.get("CVE_data_meta", {}).get("ID", ""))
        if cve_id:
            cvss = _extract_cvss_from_nvd(item if "metrics" in item else cve_obj)
            if cvss:
                index[cve_id.upper()] = cvss
    print(f"{len(index):,} entries indexed.")
    return index


async def run(dry_run: bool, also_nvd: bool):
    # When running outside Docker, override neo4j hostname → localhost
    neo4j_uri = settings.NEO4J_URI.replace("neo4j:7687", "localhost:7687")
    driver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )

    print("Querying Neo4j for CVE-pattern nodes...")
    nodes = await _get_cve_node_ids(driver)
    print(f"Found {len(nodes)} CVE-pattern nodes in Neo4j.")

    # Optional: NVD index for fallback
    nvd_index = _load_nvd_index(NVD_FILE) if also_nvd else {}

    updates = []
    found_v5 = 0
    found_nvd = 0
    not_found = 0

    for node in nodes:
        raw_id = node["node_id"]
        canonical = _cve_id_canonical(raw_id)

        cvss = None

        # Try cvelistV5 first
        fpath = _find_cvev5_file(canonical)
        if fpath:
            try:
                with open(fpath, encoding="utf-8") as f:
                    jdata = json.load(f)
                cvss = _extract_cvss_from_v5(jdata)
                if cvss:
                    found_v5 += 1
            except Exception as e:
                print(f"  [WARN] Failed to read {fpath.name}: {e}")

        # Fallback to NVD index
        if cvss is None and canonical in nvd_index:
            cvss = nvd_index[canonical]
            found_nvd += 1

        if cvss is None:
            not_found += 1
            continue

        updates.append({"node_id": raw_id, **cvss})

        # Flush batch
        if len(updates) >= BATCH_SIZE:
            written = await _batch_update(driver, updates, dry_run)
            print(f"  Patched {written} nodes (running total: {found_v5+found_nvd})")
            updates = []

    # Final batch
    if updates:
        await _batch_update(driver, updates, dry_run)

    await driver.close()

    print("\n" + "=" * 55)
    print("CVSS Patch Summary")
    print("=" * 55)
    print(f"  Total CVE nodes in Neo4j:  {len(nodes)}")
    print(f"  Patched via cvelistV5:     {found_v5}")
    print(f"  Patched via NVD JSON:      {found_nvd}")
    print(f"  Not found in any source:   {not_found}")
    print(f"  Mode:                      {'DRY RUN' if dry_run else 'WRITTEN'}")
    print("=" * 55)

    if not dry_run and (found_v5 + found_nvd) > 0:
        print("\nNext step: re-run GNN scoring to recalculate risk_score")
        print("  curl -X POST http://localhost:8000/risk/score")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only, do not write to Neo4j")
    parser.add_argument("--also-nvd", action="store_true",
                        help="Use NVD JSON as fallback when cvelistV5 file not found")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, also_nvd=args.also_nvd))
