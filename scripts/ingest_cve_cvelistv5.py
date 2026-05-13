#!/usr/bin/env python3
"""
ingest_cve_cvelistv5.py — Ingest CVE từ cvelistV5 vào Neo4j, lọc theo sản phẩm
trong Nmap scan. Tạo Vulnerability + CWE nodes với schema chuẩn hoá.

Schema output (tương thích với link_service_cve.py):
  Vulnerability {id, cve_id, cvss_score, cvss_severity, cvss_vector,
                 attack_vector, published_date, description,
                 cpe_vendors[], cpe_products[], cpe_affected[json]}
  CWE           {id, cwe_id, name}
  (Vulnerability)-[:HAS_WEAKNESS]->(CWE)

Usage:
    python scripts/ingest_cve_cvelistv5.py
    python scripts/ingest_cve_cvelistv5.py --year-from 2015
    python scripts/ingest_cve_cvelistv5.py --dry-run
    python scripts/ingest_cve_cvelistv5.py --limit 2000
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

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

CVE_BASE = Path(__file__).parent.parent / "data" / "cvelistV5-main" / "cvelistV5-main" / "cves"

# ── Products in our Nmap scan (keywords for fast pre-filter) ─────────────────

TARGET_KEYWORDS = {
    b"openssh", b"apache", b"nginx", b"mysql", b"mariadb", b"postgresql",
    b"mongodb", b"redis", b"elasticsearch", b"samba", b"exim", b"postfix",
    b"dovecot", b"proftpd", b"vsftpd", b"lighttpd", b"grafana", b"activemq",
    b"confluence", b"zookeeper", b"couchdb", b"bind9", b"bind ", b"dropbear",
    b"filezilla", b"jupyter", b"prometheus", b"sonarqube", b"dnsmasq",
    b"weblogic", b"internet_information", b"iis", b"sendmail", b"cyrus",
    b"pureftpd", b"pure-ftpd", b"tomcat", b"kibana", b"influxdb",
    b"rabbitmq", b"log4j", b"jenkins", b"drupal", b"joomla", b"wordpress",
    b"snmp", b"net-snmp", b"php",
}

# ── Vendor/product normalization to CPE style ────────────────────────────────

_VENDOR_NORM = {
    "openbsd project": "openbsd",
    "openbsd": "openbsd",
    "the apache software foundation": "apache",
    "apache software foundation": "apache",
    "apache": "apache",
    "nginx, inc.": "nginx",
    "nginx, inc": "nginx",
    "nginx": "nginx",
    "oracle corporation": "oracle",
    "oracle": "oracle",
    "mysql ab": "mysql",
    "mariadb corporation ab": "mariadb",
    "mariadb": "mariadb",
    "the postgresql global development group": "postgresql",
    "postgresql global development group": "postgresql",
    "postgresql": "postgresql",
    "mongodb, inc.": "mongodb",
    "mongodb, inc": "mongodb",
    "mongodb inc": "mongodb",
    "mongodb": "mongodb",
    "redis ltd.": "redis",
    "redis": "redis",
    "elastic n.v.": "elastic",
    "elastic": "elastic",
    "samba": "samba",
    "grafana labs": "grafana",
    "grafana": "grafana",
    "atlassian": "atlassian",
    "internet systems consortium": "isc",
    "isc": "isc",
    "microsoft": "microsoft",
    "the proftpd project": "proftpd",
    "proftpd": "proftpd",
    "pureftpd": "pureftpd",
    "dovecot": "dovecot",
    "the postfix project": "postfix",
    "postfix": "postfix",
    "sendmail": "sendmail",
    "sendmail consortium": "sendmail",
    "jenkins": "jenkins",
    "jenkins project": "jenkins",
    "sonarsource": "sonarsource",
    "sonarqube": "sonarsource",
    "matt johnston": "matt_johnston",
    "filezilla project": "filezilla-project",
    "filezilla": "filezilla-project",
    "project jupyter": "jupyter",
    "jupyter": "jupyter",
    "prometheus": "prometheus",
    "vmware, inc.": "vmware",
    "vmware": "vmware",
    "apache activemq": "apache",
    "atlassian pty ltd": "atlassian",
    "thekelleys": "thekelleys",
    "simon kelley": "thekelleys",
    "beasts.org": "beasts",
    "beasts": "beasts",
    "lighttpd": "lighttpd",
    "n/a": "",
}

_PRODUCT_NORM = {
    "openssh": "openssh",
    "openssl": "openssl",
    "apache http server": "http_server",
    "apache httpd": "http_server",
    "http server": "http_server",
    "httpd": "http_server",
    "apache tomcat": "tomcat",
    "tomcat": "tomcat",
    "nginx": "nginx",
    "mysql": "mysql",
    "mysql community server": "mysql",
    "mysql server": "mysql",
    "mariadb": "mariadb",
    "mariadb server": "mariadb",
    "postgresql": "postgresql",
    "mongodb": "mongodb",
    "redis": "redis",
    "elasticsearch": "elasticsearch",
    "kibana": "kibana",
    "logstash": "logstash",
    "samba": "samba",
    "exim": "exim",
    "postfix": "postfix",
    "sendmail": "sendmail",
    "dovecot": "dovecot",
    "proftpd": "proftpd",
    "vsftpd": "vsftpd",
    "pure-ftpd": "pure-ftpd",
    "lighttpd": "lighttpd",
    "grafana": "grafana",
    "activemq": "activemq",
    "confluence": "confluence",
    "zookeeper": "zookeeper",
    "couchdb": "couchdb",
    "apache couchdb": "couchdb",
    "bind": "bind",
    "bind9": "bind",
    "named": "bind",
    "dropbear": "dropbear_ssh",
    "dropbear ssh": "dropbear_ssh",
    "filezilla server": "filezilla_server",
    "jupyter notebook": "notebook",
    "jupyter": "notebook",
    "prometheus": "prometheus",
    "sonarqube": "sonarqube",
    "dnsmasq": "dnsmasq",
    "oracle weblogic server": "weblogic_server",
    "weblogic server": "weblogic_server",
    "weblogic": "weblogic_server",
    "internet information services": "internet_information_services",
    "internet information server": "internet_information_services",
    "iis": "internet_information_services",
    "windows server 2008": "windows_server_2008",
    "windows server 2012": "windows_server_2012",
    "windows server 2016": "windows_server_2016",
    "windows server 2019": "windows_server_2019",
    "windows server 2022": "windows_server_2022",
    "remote desktop services": "remote_desktop_services",
    "net-snmp": "net-snmp",
    "rabbitmq": "rabbitmq",
    "spring framework": "spring_framework",
    "spring": "spring_framework",
    "log4j": "log4j",
    "log4j2": "log4j2",
    "jenkins": "jenkins",
    "drupal": "drupal",
    "joomla": "joomla",
    "joomla!": "joomla",
    "wordpress": "wordpress",
    "php": "php",
    "cyrus imap": "cyrus-imapd",
    "cyrus imapd": "cyrus-imapd",
    "influxdb": "influxdb",
}


def _norm_vendor(v: str) -> str:
    key = v.strip().lower()
    if key in _VENDOR_NORM:
        return _VENDOR_NORM[key]
    for k, val in _VENDOR_NORM.items():
        if k in key:
            return val
    return re.sub(r"[^a-z0-9_]", "_", key).strip("_")


def _norm_product(p: str) -> str:
    key = p.strip().lower()
    if key in _PRODUCT_NORM:
        return _PRODUCT_NORM[key]
    for k, val in _PRODUCT_NORM.items():
        if k == key or k in key:
            return val
    return re.sub(r"[^a-z0-9_.\-]", "_", key).strip("_")


# ── cvelistV5 parser ──────────────────────────────────────────────────────────

def _extract_cvss_v5(cna: dict) -> dict:
    """Extract CVSS from cvelistV5 cna.metrics[]."""
    metrics = cna.get("metrics", [])
    for m in metrics:
        for key, label in [("cvssV3_1", "3.1"), ("cvssV3_0", "3.0"),
                            ("cvssV3", "3.0"), ("cvssV2_0", "2.0")]:
            if key in m:
                cv = m[key]
                score = cv.get("baseScore")
                if score is None:
                    continue
                sev = cv.get("baseSeverity", "")
                if not sev:
                    s = float(score)
                    sev = "CRITICAL" if s >= 9 else "HIGH" if s >= 7 else "MEDIUM" if s >= 4 else "LOW"
                av = cv.get("attackVector") or cv.get("accessVector") or "UNKNOWN"
                return {
                    "cvss_version": label,
                    "cvss_score":   float(score),
                    "cvss_severity": sev.upper(),
                    "attack_vector": av.upper(),
                    "vector_string": cv.get("vectorString", ""),
                }
    return {}


def _extract_cwes_v5(cna: dict) -> list:
    cwes = []
    for pt in cna.get("problemTypes", []):
        for desc in pt.get("descriptions", []):
            cwe_id = desc.get("cweId", "")
            if cwe_id.startswith("CWE-"):
                cwes.append(cwe_id)
            else:
                # Try to extract from description text
                m = re.search(r"CWE-(\d+)", desc.get("description", ""))
                if m:
                    cwes.append(f"CWE-{m.group(1)}")
    return list(set(cwes))


def _versions_to_ranges(versions: list) -> list:
    """Convert cvelistV5 versions[] to CPE-style range dicts."""
    ranges = []
    for v in versions:
        if v.get("status", "").lower() != "affected":
            continue
        ver = v.get("version", "")
        if ver in ("0", "0.0", "0.0.0", "n/a", "unspecified", "*", ""):
            ver = ""
        entry = {
            "version":             ver,
            "version_start_incl":  ver if ver else "",
            "version_start_excl":  "",
            "version_end_incl":    v.get("lessThanOrEqual", ""),
            "version_end_excl":    v.get("lessThan", ""),
        }
        ranges.append(entry)
    return ranges


def _extract_affected_v5(cna: dict) -> list:
    """
    Transform cna.affected[] into CPE-style list:
    [{"vendor":..., "product":..., "version":...,
      "version_start_incl":..., "version_end_excl":..., "criteria":...}]
    """
    results = []
    for aff in cna.get("affected", []):
        raw_vendor  = aff.get("vendor", "") or ""
        raw_product = aff.get("product", "") or ""
        vendor  = _norm_vendor(raw_vendor)
        product = _norm_product(raw_product)
        if not product:
            continue

        versions = aff.get("versions", [])
        if versions:
            for vrange in _versions_to_ranges(versions):
                results.append({
                    "vendor":             vendor,
                    "product":            product,
                    "version":            vrange["version"],
                    "version_start_incl": vrange["version_start_incl"],
                    "version_start_excl": vrange["version_start_excl"],
                    "version_end_incl":   vrange["version_end_incl"],
                    "version_end_excl":   vrange["version_end_excl"],
                    "criteria":           f"cve5:{vendor}:{product}",
                })
        else:
            results.append({
                "vendor": vendor, "product": product, "version": "",
                "version_start_incl": "", "version_start_excl": "",
                "version_end_incl":   "", "version_end_excl":   "",
                "criteria": f"cve5:{vendor}:{product}",
            })

    # Dedup by (vendor, product, version_end_excl)
    seen = set()
    unique = []
    for r in results:
        key = (r["vendor"], r["product"], r["version_end_excl"], r["version_end_incl"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _is_relevant(content_bytes: bytes) -> bool:
    """Fast byte-level pre-filter before JSON parse."""
    low = content_bytes.lower()
    return any(kw in low for kw in TARGET_KEYWORDS)


def parse_one_file(path: Path) -> Optional[dict]:
    """Parse a single cvelistV5 JSON file → record dict or None."""
    try:
        content = path.read_bytes()
        if not _is_relevant(content):
            return None

        d = json.loads(content.decode("utf-8", errors="replace"))
        meta = d.get("cveMetadata", {})
        state = meta.get("state", "")
        if state not in ("PUBLISHED", "MODIFIED", ""):
            return None

        cve_id = meta.get("cveId", "")
        if not cve_id:
            return None

        cna = d.get("containers", {}).get("cna", {})
        if not cna:
            return None

        cvss = _extract_cvss_v5(cna)
        if not cvss:
            return None  # Skip CVEs without CVSS (not useful for risk scoring)

        cwes      = _extract_cwes_v5(cna)
        affected  = _extract_affected_v5(cna)
        if not affected:
            return None  # Skip if no product info

        descs = cna.get("descriptions", [])
        desc  = next((x.get("value", "") for x in descs if x.get("lang", "").startswith("en")), "")
        pub   = (meta.get("datePublished") or cna.get("datePublic") or "")[:10]

        return {
            "id":            cve_id.lower(),
            "cve_id":        cve_id,
            "description":   desc[:800],
            "published_date": pub,
            "cvss_version":  cvss["cvss_version"],
            "cvss_score":    cvss["cvss_score"],
            "cvss_severity": cvss["cvss_severity"],
            "attack_vector": cvss["attack_vector"],
            "vector_string": cvss["vector_string"],
            "cwe_ids":       cwes,
            "cpe_vendors":   list({a["vendor"]  for a in affected if a["vendor"]}),
            "cpe_products":  list({a["product"] for a in affected if a["product"]}),
            "cpe_affected":  [json.dumps(a, ensure_ascii=False) for a in affected[:30]],
        }
    except Exception:
        return None


def scan_files(year_from: int, limit: Optional[int], workers: int) -> list:
    """Walk cvelistV5 directory, parse relevant CVE files in parallel."""
    all_files = []
    for year_dir in sorted(CVE_BASE.iterdir()):
        if not year_dir.is_dir():
            continue
        try:
            if int(year_dir.name) < year_from:
                continue
        except ValueError:
            continue
        all_files.extend(year_dir.rglob("CVE-*.json"))

    total_files = len(all_files)
    print(f"[SCAN] {total_files:,} CVE files from {year_from}+ "
          f"({'no limit' if not limit else f'limit {limit}'})")

    records = []
    processed = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(parse_one_file, f): f for f in all_files}
        for future in as_completed(futures):
            rec = future.result()
            processed += 1
            if rec:
                records.append(rec)
            if processed % 10000 == 0:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed else 0
                eta  = (total_files - processed) / rate if rate else 0
                print(f"  {processed:>6,}/{total_files:,}  matched={len(records):,}"
                      f"  {rate:.0f} f/s  ETA={eta:.0f}s")
            if limit and len(records) >= limit:
                pool.shutdown(wait=False, cancel_futures=True)
                break

    elapsed = time.time() - t0
    print(f"[SCAN] Done: {len(records):,} CVEs matched in {elapsed:.1f}s")
    return records


# ── Neo4j writer ──────────────────────────────────────────────────────────────

_CYPHER_VULN = """
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

_CYPHER_CWE = """
UNWIND $rows AS row
UNWIND row.cwe_ids AS cwe_id
MERGE (c:CWE {id: toLower(cwe_id)})
ON CREATE SET c.name = cwe_id, c.cwe_id = cwe_id
MERGE (v:Vulnerability {id: row.id})
MERGE (v)-[:HAS_WEAKNESS {source: 'nvd', confidence: 0.95}]->(c)
"""


def write_to_neo4j(records: list, batch_size: int):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"[NEO4J] Connected: {NEO4J_URI}")

    with driver.session() as s:
        s.run("CREATE INDEX vuln_id IF NOT EXISTS FOR (v:Vulnerability) ON (v.id)")
        s.run("CREATE INDEX cwe_id  IF NOT EXISTS FOR (c:CWE)           ON (c.id)")

    total = len(records)
    written = 0
    t0 = time.time()

    for start in range(0, total, batch_size):
        batch = records[start: start + batch_size]
        with driver.session() as s:
            s.run(_CYPHER_VULN, rows=batch)
            cwe_rows = [r for r in batch if r["cwe_ids"]]
            if cwe_rows:
                s.run(_CYPHER_CWE, rows=cwe_rows)
        written += len(batch)
        pct  = written / total * 100
        rate = written / (time.time() - t0) if time.time() > t0 else 0
        print(f"  [{written:>5,}/{total:,}] {pct:5.1f}%  {rate:.0f} CVE/s")

    driver.close()
    print(f"\n[DONE] {written:,} Vulnerability nodes written.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest CVE from cvelistV5 into Neo4j (filtered for nmap products)."
    )
    parser.add_argument("--year-from",  type=int,  default=2014,
                        help="Only include CVEs from this year onward (default: 2014)")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Parse files but do not write to Neo4j")
    parser.add_argument("--limit",      type=int,  default=None,
                        help="Stop after N matching CVEs (for testing)")
    parser.add_argument("--batch-size", type=int,  default=200)
    parser.add_argument("--workers",    type=int,  default=8,
                        help="Parallel file reader threads (default: 8)")
    args = parser.parse_args()

    records = scan_files(args.year_from, args.limit, args.workers)

    if not records:
        print("[WARN] No matching CVEs found. Check TARGET_KEYWORDS or --year-from.")
        return

    # Stats
    from collections import Counter
    prod_counter = Counter()
    for r in records:
        for p in r["cpe_products"]:
            prod_counter[p] += 1
    print("\n[STATS] Top products matched:")
    for p, cnt in prod_counter.most_common(20):
        print(f"  {p:<35} {cnt:>5,}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(records):,} CVEs to Neo4j.")
        print("  Sample:")
        for r in records[:2]:
            print(f"    {r['cve_id']}  cvss={r['cvss_score']}  "
                  f"products={r['cpe_products'][:3]}")
        return

    write_to_neo4j(records, args.batch_size)


if __name__ == "__main__":
    main()
