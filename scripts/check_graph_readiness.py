#!/usr/bin/env python3
"""
check_graph_readiness.py — Kiểm tra graph đã đủ để train GNN chưa.

Chạy từ host (không cần Docker):
    python scripts/check_graph_readiness.py

Output:
  - Node counts per label
  - Edge counts per type
  - Cross-group connectivity (Service→CVE)
  - Feature coverage (nodes có property CVSS, CPE, v.v.)
  - GNN readiness assessment
"""

import os
import sys
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

# ── Queries ───────────────────────────────────────────────────────────────────

NODE_COUNT_Q = """
CALL apoc.meta.stats() YIELD labels
RETURN labels
"""

# Fallback nếu không có APOC
NODE_LABELS_Q = """
CALL db.labels() YIELD label
CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) AS cnt', {})
YIELD value
RETURN label, value.cnt AS count
ORDER BY count DESC
"""

# Direct count — không cần APOC
COUNTS_Q = """
MATCH (n)
WITH labels(n)[0] AS label, count(n) AS cnt
RETURN label, cnt
ORDER BY cnt DESC
"""

REL_COUNTS_Q = """
MATCH ()-[r]->()
WITH type(r) AS rel_type, count(r) AS cnt
RETURN rel_type, cnt
ORDER BY cnt DESC
"""

CROSS_GROUP_Q = """
MATCH (s:Service)-[r:HAS_VULN]->(v:Vulnerability)
RETURN
  count(r)                                    AS total_edges,
  count(DISTINCT s)                           AS services_with_vuln,
  count(DISTINCT v)                           AS cves_linked,
  avg(r.confidence)                           AS avg_confidence,
  min(r.confidence)                           AS min_confidence,
  max(r.confidence)                           AS max_confidence
"""

METHOD_Q = """
MATCH ()-[r:HAS_VULN]->()
RETURN r.match_method AS method, count(r) AS cnt
ORDER BY cnt DESC
"""

FEATURE_COVERAGE_Q = """
MATCH (s:Service)
RETURN
  count(s)                                                AS total_services,
  count(s.product)                                        AS has_product,
  count(s.version)                                        AS has_version,
  count(s.cpe)                                            AS has_cpe,
  count(CASE WHEN s.cpe IS NOT NULL AND s.cpe <> '' THEN 1 END) AS has_cpe_nonempty
"""

CVE_FEATURE_Q = """
MATCH (v:Vulnerability)
RETURN
  count(v)                                               AS total_cves,
  count(v.cvss_score)                                    AS has_cvss,
  count(v.cpe_products)                                  AS has_cpe_products,
  count(CASE WHEN size(v.cpe_products) > 0 THEN 1 END)  AS has_cpe_nonempty,
  avg(v.cvss_score)                                      AS avg_cvss
"""

METAPATH_Q = """
MATCH path = (h:Host)-[:HAS_PORT]->(:Port)-[:RUNS_SERVICE]->(s:Service)-[:HAS_VULN]->(v:Vulnerability)-[:HAS_WEAKNESS]->(c:CWE)
RETURN
  count(path)       AS metapath_instances,
  count(DISTINCT h) AS hosts_in_path,
  count(DISTINCT v) AS cves_in_path,
  count(DISTINCT c) AS cwes_in_path
LIMIT 1
"""

ISOLATION_Q = """
MATCH (s:Service)
WHERE NOT (s)-[:HAS_VULN]->()
RETURN count(s) AS isolated_services
"""


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def run():
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)

    print(f"[CONNECT] {NEO4J_URI}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
        print("[OK] Connected\n")
    except Exception as e:
        print(f"[ERR] {e}")
        sys.exit(1)

    with driver.session() as s:

        # ── 1. Node counts ────────────────────────────────────────────────────
        section("NODE COUNTS")
        rows = s.run(COUNTS_Q)
        group1 = {"Host", "IP", "Port", "Service", "Application", "URL", "NetworkZone", "Domain"}
        group2 = {"Vulnerability", "CVE", "CWE"}
        g1_total = g2_total = 0
        for row in rows:
            label, cnt = row["label"], row["cnt"]
            tag = "[G1]" if label in group1 else "[G2]" if label in group2 else "    "
            print(f"  {tag} {label:<20} {cnt:>8,}")
            if label in group1: g1_total += cnt
            if label in group2: g2_total += cnt
        print(f"\n  Group 1 total: {g1_total:,}  |  Group 2 total: {g2_total:,}")

        # ── 2. Edge counts ────────────────────────────────────────────────────
        section("EDGE COUNTS")
        rows = s.run(REL_COUNTS_Q)
        for row in rows:
            cross = " <-- CROSS-GROUP" if row["rel_type"] == "HAS_VULN" else ""
            print(f"  {row['rel_type']:<30} {row['cnt']:>8,}{cross}")

        # ── 3. Cross-group connectivity ───────────────────────────────────────
        section("CROSS-GROUP CONNECTIVITY (Service -> CVE)")
        row = s.run(CROSS_GROUP_Q).single()
        if row and row["total_edges"]:
            print(f"  HAS_VULN edges         : {row['total_edges']:,}")
            print(f"  Services with vuln     : {row['services_with_vuln']:,}")
            print(f"  CVEs linked            : {row['cves_linked']:,}")
            print(f"  Confidence avg/min/max : {row['avg_confidence']:.3f} / {row['min_confidence']:.2f} / {row['max_confidence']:.2f}")

            row2 = s.run(METHOD_Q)
            print(f"\n  Match method breakdown:")
            for r in row2:
                print(f"    {r['method']:<25} {r['cnt']:>6,}")
        else:
            print("  [WARN] Khong co HAS_VULN edges!")
            print("         -> Chay: python scripts/link_service_cve.py")

        # ── 4. Feature coverage ───────────────────────────────────────────────
        section("FEATURE COVERAGE")
        row = s.run(FEATURE_COVERAGE_Q).single()
        if row and row["total_services"]:
            total = row["total_services"]
            print(f"  Service nodes          : {total:,}")
            print(f"  Has product            : {row['has_product']:,} ({row['has_product']/total*100:.0f}%)")
            print(f"  Has version            : {row['has_version']:,} ({row['has_version']/total*100:.0f}%)")
            print(f"  Has CPE (non-empty)    : {row['has_cpe_nonempty']:,} ({row['has_cpe_nonempty']/total*100:.0f}%)")
        else:
            print("  [WARN] Khong co Service nodes!")
            print("         -> Chay ingest_nmap.py truoc")

        row = s.run(CVE_FEATURE_Q).single()
        if row and row["total_cves"]:
            total = row["total_cves"]
            print(f"\n  Vulnerability nodes    : {total:,}")
            print(f"  Has CVSS score         : {row['has_cvss']:,} ({row['has_cvss']/total*100:.0f}%)")
            print(f"  Has CPE products       : {row['has_cpe_nonempty']:,} ({row['has_cpe_nonempty']/total*100:.0f}%)")
            print(f"  Avg CVSS score         : {row['avg_cvss']:.2f}" if row['avg_cvss'] else "  Avg CVSS: N/A")

        # ── 5. Metapath instances ─────────────────────────────────────────────
        section("METAPATH INSTANCES (Host->Port->Service->CVE->CWE)")
        row = s.run(METAPATH_Q).single()
        if row and row["metapath_instances"]:
            print(f"  Instances              : {row['metapath_instances']:,}")
            print(f"  Distinct hosts         : {row['hosts_in_path']:,}")
            print(f"  Distinct CVEs          : {row['cves_in_path']:,}")
            print(f"  Distinct CWEs          : {row['cwes_in_path']:,}")
        else:
            print("  [WARN] Khong co metapath instances (cross-group chua co)")

        # ── 6. Isolated nodes ─────────────────────────────────────────────────
        section("ISOLATION CHECK")
        row = s.run(ISOLATION_Q).single()
        isolated = row["isolated_services"] if row else 0
        total_svc_row = s.run("MATCH (s:Service) RETURN count(s) AS c").single()
        total_svc = total_svc_row["c"] if total_svc_row else 0
        if total_svc:
            pct = isolated / total_svc * 100
            print(f"  Services without vuln  : {isolated:,} / {total_svc:,} ({pct:.0f}%)")
            print(f"  Services with vuln     : {total_svc-isolated:,} ({100-pct:.0f}%)")

        # ── 7. GNN readiness ──────────────────────────────────────────────────
        section("GNN READINESS ASSESSMENT")
        checks = []

        # Check Group 1 exists
        host_count = s.run("MATCH (h:Host) RETURN count(h) AS c").single()["c"]
        svc_count  = s.run("MATCH (s:Service) RETURN count(s) AS c").single()["c"]
        vuln_count = s.run("MATCH (v:Vulnerability) RETURN count(v) AS c").single()["c"]
        edge_count = s.run("MATCH ()-[r:HAS_VULN]->() RETURN count(r) AS c").single()["c"]
        cwe_count  = s.run("MATCH (c:CWE) RETURN count(c) AS c").single()["c"]

        checks.append(("Host nodes >= 10",       host_count >= 10,    host_count))
        checks.append(("Service nodes >= 50",     svc_count  >= 50,    svc_count))
        checks.append(("Vulnerability nodes >= 100", vuln_count >= 100, vuln_count))
        checks.append(("CWE nodes >= 10",         cwe_count  >= 10,    cwe_count))
        checks.append(("HAS_VULN edges >= 20",    edge_count >= 20,    edge_count))
        checks.append(("Metapath Host->CVE->CWE", edge_count > 0 and cwe_count > 0, "yes" if edge_count > 0 else "no"))

        all_pass = True
        for name, passed, value in checks:
            status = "[PASS]" if passed else "[FAIL]"
            if not passed: all_pass = False
            print(f"  {status} {name:<40} (current: {value})")

        print()
        if all_pass:
            print("  => GRAPH SAN SANG DE TRAIN GNN")
            print("     Buoc tiep theo: export subgraph va setup HeCo/R-GCN")
        else:
            print("  => GRAPH CHUA DU. Chay cac buoc con thieu:")
            if host_count == 0:
                print("     1. python scripts/ingest_nmap_standalone.py --file data/sample_nmap_scan.xml")
            if edge_count == 0 and svc_count > 0:
                print("     2. python scripts/link_service_cve.py --min-confidence 0.60")
            if edge_count == 0 and svc_count == 0:
                print("     2. (sau khi ingest Nmap) python scripts/link_service_cve.py")

    driver.close()


if __name__ == "__main__":
    run()
