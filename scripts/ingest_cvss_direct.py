#!/usr/bin/env python3
"""
ingest_cvss_direct.py — Đọc NVD JSON, trích CVSS trực tiếp, MERGE vào Neo4j.

Không dùng LLM. Không cần re-ingest qua pipeline.
Chạy độc lập, kết nối thẳng Neo4j qua bolt.

Usage:
    python scripts/ingest_cvss_direct.py
    python scripts/ingest_cvss_direct.py --file data/nvdcve-2.0-modified.json
    python scripts/ingest_cvss_direct.py --dry-run          # không ghi Neo4j
    python scripts/ingest_cvss_direct.py --batch-size 200   # tùy chỉnh batch
    python scripts/ingest_cvss_direct.py --limit 500        # chỉ xử lý N CVE đầu
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Fix Windows cp1252 terminal encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Load .env nếu có ──────────────────────────────────────────────────────────
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

DEFAULT_NVD_FILE  = Path(__file__).parent.parent / "data" / "nvdcve-2.0-modified.json"
DEFAULT_BATCH     = 100


# ── CVSS extractor ────────────────────────────────────────────────────────────

def _extract_cvss(metrics: dict) -> dict:
    """
    Ưu tiên: cvssMetricV31 → cvssMetricV3 → cvssMetricV2.
    Trả về dict với các key: cvss_version, cvss_score, cvss_severity, attack_vector, vector_string.
    Trả về {} nếu không có CVSS nào.
    """
    # Thứ tự ưu tiên CVSS
    for metric_key, version_label in [
        ("cvssMetricV31", "3.1"),
        ("cvssMetricV3",  "3.0"),
        ("cvssMetricV2",  "2.0"),
    ]:
        entries = metrics.get(metric_key, [])
        if not entries:
            continue

        # Ưu tiên source "Primary" nếu có
        primary = next((e for e in entries if e.get("type") == "Primary"), entries[0])
        cvss_data = primary.get("cvssData", {})
        if not cvss_data:
            continue

        base_score = cvss_data.get("baseScore")
        if base_score is None:
            continue

        # severity: v3 trong cvssData, v2 trong entry cha
        severity = (
            cvss_data.get("baseSeverity")
            or primary.get("baseSeverity")
            or _score_to_severity(float(base_score))
        ).upper()

        # attackVector: v3 field name; v2 dùng accessVector
        attack_vector = (
            cvss_data.get("attackVector")
            or cvss_data.get("accessVector")
            or "UNKNOWN"
        ).upper()

        return {
            "cvss_version":   version_label,
            "cvss_score":     float(base_score),
            "cvss_severity":  severity,
            "attack_vector":  attack_vector,
            "vector_string":  cvss_data.get("vectorString", ""),
        }

    return {}


def _score_to_severity(score: float) -> str:
    if score >= 9.0: return "CRITICAL"
    if score >= 7.0: return "HIGH"
    if score >= 4.0: return "MEDIUM"
    return "LOW"


def _extract_cpe_affected(configurations: list) -> list[dict]:
    """
    Trích danh sách CPE affected từ configurations array của NVD.
    Mỗi item: {"vendor": "apache", "product": "http_server", "version": "2.4.49",
               "criteria": "cpe:2.3:a:apache:http_server:2.4.49:...",
               "version_start": "", "version_end": ""}
    """
    results = []
    for config in configurations:
        for node in config.get("nodes", []):
            for match in node.get("cpeMatch", []):
                if not match.get("vulnerable", False):
                    continue
                criteria = match.get("criteria", "")
                parsed = _parse_cpe(criteria)
                if parsed:
                    parsed["criteria"] = criteria
                    parsed["version_start_incl"] = match.get("versionStartIncluding", "")
                    parsed["version_start_excl"] = match.get("versionStartExcluding", "")
                    parsed["version_end_incl"]   = match.get("versionEndIncluding", "")
                    parsed["version_end_excl"]   = match.get("versionEndExcluding", "")
                    results.append(parsed)
    # dedup by criteria
    seen = set()
    unique = []
    for r in results:
        key = r["criteria"]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _parse_cpe(cpe_str: str) -> dict | None:
    """
    Parse CPE 2.3: cpe:2.3:a:<vendor>:<product>:<version>:...
    Parse CPE 2.2: cpe:/<type>/<vendor>/<product>/<version>
    """
    if not cpe_str:
        return None
    if cpe_str.startswith("cpe:2.3:"):
        parts = cpe_str.split(":")
        # cpe:2.3:a:vendor:product:version:...
        if len(parts) >= 6:
            return {
                "vendor":  parts[3].lower().replace("\\", ""),
                "product": parts[4].lower().replace("\\", ""),
                "version": parts[5] if parts[5] not in ("*", "-", "") else "",
            }
    elif cpe_str.startswith("cpe:/"):
        # cpe:/a:vendor:product:version
        inner = cpe_str[5:]
        parts = inner.split(":")
        if len(parts) >= 3:
            return {
                "vendor":  parts[1].lower(),
                "product": parts[2].lower(),
                "version": parts[3] if len(parts) > 3 else "",
            }
    return None


def _extract_cwes(weaknesses: list) -> list[str]:
    """Lấy danh sách CWE IDs từ weaknesses array."""
    cwe_ids = []
    for w in weaknesses:
        for desc in w.get("description", []):
            val = desc.get("value", "")
            if val.startswith("CWE-") and val != "NVD-CWE-Other" and val != "NVD-CWE-noinfo":
                cwe_ids.append(val)  # e.g. "CWE-89"
    return list(set(cwe_ids))


def _get_en_description(descriptions: list) -> str:
    for d in descriptions:
        if d.get("lang") == "en":
            return d.get("value", "")
    return descriptions[0].get("value", "") if descriptions else ""


def parse_nvd_file(filepath: Path, limit: Optional[int] = None) -> list[dict]:
    """
    Đọc NVD JSON file, trả về list CVE records đã parse.
    Format: {"vulnerabilities": [{"cve": {...}}]}
    """
    print(f"[READ] Doc file: {filepath}")
    with open(filepath, encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    raw_items = data.get("vulnerabilities") or data.get("CVE_Items") or []
    if not raw_items:
        print("❌ Không tìm thấy key 'vulnerabilities' hoặc 'CVE_Items'")
        return []

    print(f"   Tổng CVE trong file: {len(raw_items):,}")
    if limit:
        raw_items = raw_items[:limit]
        print(f"   Giới hạn xử lý: {limit:,}")

    records = []
    skipped_no_cvss = 0

    for item in raw_items:
        cve_obj = item.get("cve") or item  # v2.0 API has nested "cve"

        cve_id = cve_obj.get("id") or cve_obj.get("CVE_data_meta", {}).get("ID")
        if not cve_id:
            continue

        metrics        = cve_obj.get("metrics", {})
        cvss           = _extract_cvss(metrics)
        cwes           = _extract_cwes(cve_obj.get("weaknesses", []))
        cpe_affected   = _extract_cpe_affected(cve_obj.get("configurations", []))
        desc           = _get_en_description(cve_obj.get("descriptions", []))
        pub            = (cve_obj.get("published") or "")[:10]

        if not cvss:
            skipped_no_cvss += 1
            continue

        records.append({
            "id":            cve_id.lower(),
            "cve_id":        cve_id,
            "description":   desc[:1000],
            "published_date": pub,
            "cvss_version":  cvss["cvss_version"],
            "cvss_score":    cvss["cvss_score"],
            "cvss_severity": cvss["cvss_severity"],
            "attack_vector": cvss["attack_vector"],
            "vector_string": cvss["vector_string"],
            "cwe_ids":       cwes,
            # CPE affected — danh sách vendor:product cho Service→CVE matching
            "cpe_vendors":   list({c["vendor"]  for c in cpe_affected if c["vendor"]}),
            "cpe_products":  list({c["product"] for c in cpe_affected if c["product"]}),
            "cpe_affected":  [json.dumps(c, ensure_ascii=False) for c in cpe_affected[:20]],
        })

    print(f"   Có CVSS: {len(records):,} | Không có CVSS: {skipped_no_cvss:,}")
    return records


# ── Neo4j writer ──────────────────────────────────────────────────────────────

def _neo4j_merge_batch(driver, batch: list[dict]) -> dict:
    """
    MERGE từng CVE node và tạo HAS_WEAKNESS edges đến CWE.
    Dùng transaction đơn cho toàn batch.
    """
    cypher_vuln = """
    UNWIND $rows AS row
    MERGE (v:Vulnerability {id: row.id})
    SET
        v.cve_id         = row.cve_id,
        v.name           = row.cve_id,
        v.description    = row.description,
        v.published_date = row.published_date,
        v.cvss_version   = row.cvss_version,
        v.cvss_score     = toFloat(row.cvss_score),
        v.cvss_severity  = row.cvss_severity,
        v.attack_vector  = row.attack_vector,
        v.vector_string  = row.vector_string,
        v.cpe_vendors    = row.cpe_vendors,
        v.cpe_products   = row.cpe_products,
        v.cpe_affected   = row.cpe_affected,
        v.updated_at     = datetime()
    """

    cypher_cwe = """
    UNWIND $rows AS row
    UNWIND row.cwe_ids AS cwe_id
    MERGE (c:CWE {id: toLower(cwe_id)})
    ON CREATE SET c.name = cwe_id
    MERGE (v:Vulnerability {id: row.id})
    MERGE (v)-[:HAS_WEAKNESS {source: 'nvd', confidence: 0.95}]->(c)
    """

    with driver.session() as session:
        session.run(cypher_vuln, rows=batch)

        # Chỉ chạy CWE merge cho rows có cwe_ids
        cwe_rows = [r for r in batch if r["cwe_ids"]]
        if cwe_rows:
            session.run(cypher_cwe, rows=cwe_rows)

    return {"nodes": len(batch), "cwe_edges": sum(len(r["cwe_ids"]) for r in batch)}


def run_ingest(records: list[dict], batch_size: int, dry_run: bool):
    total      = len(records)
    processed  = 0
    total_edges = 0
    t_start    = time.time()

    if dry_run:
        print(f"\n[DRY RUN] in 3 records mau (khong ghi Neo4j):\n")
        for r in records[:3]:
            print(json.dumps(r, indent=2, ensure_ascii=False))
        print(f"\n[OK] Dry run xong. Tong se xu ly: {total:,} CVE")
        return

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] Thieu driver: pip install neo4j")
        sys.exit(1)

    print(f"\n[NEO4J] Ket noi: {NEO4J_URI}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print("   [OK] Ket noi thanh cong\n")
    except Exception as e:
        print(f"   [ERR] Ket noi that bai: {e}")
        driver.close()
        sys.exit(1)

    # Tạo index nếu chưa có
    with driver.session() as s:
        s.run("CREATE INDEX vuln_id IF NOT EXISTS FOR (v:Vulnerability) ON (v.id)")
        s.run("CREATE INDEX cwe_id  IF NOT EXISTS FOR (c:CWE)           ON (c.id)")

    print(f"[RUN] Dang MERGE {total:,} CVE vao Neo4j (batch={batch_size})...\n")

    for start in range(0, total, batch_size):
        batch  = records[start : start + batch_size]
        stats  = _neo4j_merge_batch(driver, batch)
        processed  += stats["nodes"]
        total_edges += stats["cwe_edges"]

        pct     = processed / total * 100
        elapsed = time.time() - t_start
        rate    = processed / elapsed if elapsed > 0 else 0
        eta     = (total - processed) / rate if rate > 0 else 0

        print(
            f"  [{processed:>6,}/{total:,}] {pct:5.1f}%"
            f"  |  CWE edges: {total_edges:,}"
            f"  |  {rate:.0f} CVE/s"
            f"  |  ETA: {eta:.0f}s"
        )

    elapsed = time.time() - t_start
    print(f"\n[DONE] Hoan thanh!")
    print(f"   CVE nodes MERGE : {processed:,}")
    print(f"   HAS_WEAKNESS edges: {total_edges:,}")
    print(f"   Thoi gian: {elapsed:.1f}s  ({processed/elapsed:.0f} CVE/s)")

    driver.close()


# ── Verify results ────────────────────────────────────────────────────────────

def verify_neo4j(sample_n: int = 5):
    """Kiểm tra kết quả: đếm nodes và in sample."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    print("\n[STATS] Kiem tra Neo4j sau khi ingest:\n")

    with driver.session() as s:
        r = s.run("MATCH (v:Vulnerability) WHERE v.cvss_score IS NOT NULL RETURN count(v) AS n")
        count = r.single()["n"]
        print(f"   Vulnerability nodes co cvss_score: {count:,}")

        r = s.run("""
            MATCH (v:Vulnerability)
            WHERE v.cvss_severity IS NOT NULL
            RETURN v.cvss_severity AS sev, count(v) AS cnt
            ORDER BY cnt DESC
        """)
        print("\n   Phan bo severity:")
        for row in r:
            print(f"     {row['sev']:10s}  {row['cnt']:,}")

        r = s.run(f"""
            MATCH (v:Vulnerability)
            WHERE v.cvss_score IS NOT NULL
            RETURN v.cve_id, v.cvss_score, v.cvss_severity, v.attack_vector
            ORDER BY v.cvss_score DESC LIMIT {sample_n}
        """)
        print(f"\n   Top {sample_n} CVE theo cvss_score:")
        for row in r:
            cve_id   = row['v.cve_id']   or "N/A"
            severity = row['v.cvss_severity'] or "N/A"
            vector   = row['v.attack_vector'] or "N/A"
            print(f"     {cve_id:20s}  score={row['v.cvss_score']}  {severity:10s}  {vector}")

        r = s.run("MATCH ()-[r:HAS_WEAKNESS]->() RETURN count(r) AS n")
        print(f"\n   HAS_WEAKNESS edges tong: {r.single()['n']:,}")

    driver.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest CVSS scores from NVD JSON directly into Neo4j (no LLM)."
    )
    parser.add_argument(
        "--file", "-f",
        default=str(DEFAULT_NVD_FILE),
        help=f"Đường dẫn file NVD JSON (default: {DEFAULT_NVD_FILE})"
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int, default=DEFAULT_BATCH,
        help=f"Batch size cho Neo4j write (default: {DEFAULT_BATCH})"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int, default=None,
        help="Chỉ xử lý N CVE đầu tiên (để test nhanh)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse và in sample, không ghi Neo4j"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Sau khi ingest, in thống kê từ Neo4j"
    )
    args = parser.parse_args()

    nvd_path = Path(args.file)
    if not nvd_path.exists():
        print(f"❌ File không tồn tại: {nvd_path}")
        sys.exit(1)

    # 1. Parse
    records = parse_nvd_file(nvd_path, limit=args.limit)
    if not records:
        print("❌ Không có record nào để xử lý.")
        sys.exit(1)

    # 2. Ingest
    run_ingest(records, batch_size=args.batch_size, dry_run=args.dry_run)

    # 3. Verify (optional)
    if args.verify and not args.dry_run:
        verify_neo4j()


if __name__ == "__main__":
    main()
