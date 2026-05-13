#!/usr/bin/env python3
"""
link_service_cve.py — Tạo cạnh HAS_VULN từ Service → CVE
dựa trên CPE matching giữa thông tin Nmap (service.cpe / product / version)
và CPE affected data đã lưu trên Vulnerability nodes từ NVD.

Confidence tiers:
  1.0  — CPE exact match (vendor + product + version khớp hoàn toàn)
  0.85 — CPE version-range match (product khớp, version trong khoảng affected)
  0.65 — CPE product-only match (vendor + product khớp, không biết version)
  0.40 — product name fuzzy match (chỉ dùng khi không có CPE từ Nmap)

Usage:
    python scripts/link_service_cve.py
    python scripts/link_service_cve.py --min-confidence 0.65
    python scripts/link_service_cve.py --dry-run
    python scripts/link_service_cve.py --limit-services 50
"""

import argparse
import json
import os
import re
import sys
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

MIN_CONFIDENCE_DEFAULT = 0.60


# ── CPE normalization ─────────────────────────────────────────────────────────

# Nmap product name → (vendor, product) trong CPE
_PRODUCT_CPE_MAP = {
    "apache httpd":         ("apache", "http_server"),
    "apache http server":   ("apache", "http_server"),
    "apache tomcat":        ("apache", "tomcat"),
    "nginx":                ("nginx", "nginx"),
    "iis":                  ("microsoft", "internet_information_services"),
    "microsoft iis":        ("microsoft", "internet_information_services"),
    "openssh":              ("openbsd", "openssh"),
    "dropbear":             ("matt_johnston", "dropbear_ssh"),
    "dropbear sshd":        ("matt_johnston", "dropbear_ssh"),
    "mysql":                ("mysql", "mysql"),
    "mariadb":              ("mariadb", "mariadb"),
    "postgresql":           ("postgresql", "postgresql"),
    "postgresql db":        ("postgresql", "postgresql"),
    "redis":                ("redis", "redis"),
    "mongodb":              ("mongodb", "mongodb"),
    "proftpd":              ("proftpd", "proftpd"),
    "vsftpd":               ("beasts", "vsftpd"),
    "pure-ftpd":            ("pureftpd", "pure-ftpd"),
    "samba":                ("samba", "samba"),
    "exim":                 ("exim", "exim"),
    "exim smtpd":           ("exim", "exim"),
    "postfix":              ("postfix", "postfix"),
    "sendmail":             ("sendmail", "sendmail"),
    "dovecot":              ("dovecot", "dovecot"),
    "dovecot imapd":        ("dovecot", "dovecot"),
    "lighttpd":             ("lighttpd", "lighttpd"),
    "php":                  ("php", "php"),
    "wordpress":            ("wordpress", "wordpress"),
    "drupal":               ("drupal", "drupal"),
    "joomla":               ("joomla", "joomla"),
    "jenkins":              ("jenkins", "jenkins"),
    "elasticsearch":        ("elastic", "elasticsearch"),
    "kibana":               ("elastic", "kibana"),
    "influxdb":             ("influxdata", "influxdb"),
    "grafana":              ("grafana", "grafana"),
    "rabbitmq":             ("vmware", "rabbitmq"),
    "tomcat":               ("apache", "tomcat"),
    "spring":               ("vmware", "spring_framework"),
    "struts":               ("apache", "struts"),
    "log4j":                ("apache", "log4j"),
}


def _parse_cpe_str(cpe: str) -> Optional[dict]:
    """Parse CPE 2.3 hoặc 2.2 → dict{vendor, product, version}."""
    if not cpe:
        return None
    cpe = cpe.strip()
    if cpe.startswith("cpe:2.3:"):
        parts = cpe.split(":")
        if len(parts) >= 6:
            return {
                "vendor":  parts[3].lower(),
                "product": parts[4].lower(),
                "version": parts[5] if parts[5] not in ("*", "-", "") else "",
            }
    elif cpe.startswith("cpe:/"):
        inner = cpe[5:]
        parts = inner.split(":")
        if len(parts) >= 3:
            return {
                "vendor":  parts[1].lower(),
                "product": parts[2].lower(),
                "version": parts[3] if len(parts) > 3 else "",
            }
    return None


def _normalize_product(product: str) -> tuple[str, str]:
    """Tra lookup table → (vendor, product) CPE normalized."""
    key = product.strip().lower()
    if key in _PRODUCT_CPE_MAP:
        return _PRODUCT_CPE_MAP[key]
    # Tìm partial match
    for k, v in _PRODUCT_CPE_MAP.items():
        if k in key or key in k:
            return v
    # Fallback: chỉ dùng product name normalize
    normalized = re.sub(r"[^a-z0-9]", "_", key).strip("_")
    return ("", normalized)


def _version_in_range(version: str, start_incl: str, start_excl: str,
                       end_incl: str, end_excl: str) -> bool:
    """So sánh version đơn giản theo dotted-number (vd 2.4.49)."""
    if not version:
        return False

    def _to_tuple(v: str):
        try:
            return tuple(int(x) for x in re.split(r"[.\-_]", v)[:4] if x.isdigit())
        except Exception:
            return (0,)

    v = _to_tuple(version)
    if start_incl and _to_tuple(start_incl) > v:
        return False
    if start_excl and _to_tuple(start_excl) >= v:
        return False
    if end_incl and v > _to_tuple(end_incl):
        return False
    if end_excl and v >= _to_tuple(end_excl):
        return False
    return True


# ── Matching logic ────────────────────────────────────────────────────────────

def _match_service_to_cve(svc: dict, vuln: dict) -> Optional[float]:
    """
    So khớp một Service node với một Vulnerability node.
    Trả về confidence [0,1] hoặc None nếu không match.
    """
    svc_cpe_str = (svc.get("cpe") or "").strip()
    svc_product = (svc.get("product") or "").strip()
    svc_version = (svc.get("version") or "").strip()

    cpe_affected_raw = vuln.get("cpe_affected") or []

    # Parse CPE list từ Vulnerability node
    cpe_affected = []
    for item in cpe_affected_raw:
        try:
            cpe_affected.append(json.loads(item) if isinstance(item, str) else item)
        except Exception:
            pass

    if not cpe_affected:
        # Vulnerability không có CPE data → dùng product-name fuzzy
        if not svc_product:
            return None
        vendor_norm, product_norm = _normalize_product(svc_product)
        vuln_products = [p.lower() for p in (vuln.get("cpe_products") or [])]
        if product_norm and any(product_norm in vp or vp in product_norm for vp in vuln_products):
            return 0.40
        return None

    best = None

    for cpe_item in cpe_affected:
        v_vendor  = cpe_item.get("vendor", "").lower()
        v_product = cpe_item.get("product", "").lower()
        v_version = cpe_item.get("version", "")

        # ── Path 1: Service có CPE từ Nmap ──────────────────────────────────
        if svc_cpe_str:
            svc_parsed = _parse_cpe_str(svc_cpe_str)
            if svc_parsed:
                s_vendor  = svc_parsed["vendor"]
                s_product = svc_parsed["product"]
                s_version = svc_parsed["version"]

                if s_vendor == v_vendor and s_product == v_product:
                    # Version exact match
                    if s_version and v_version and s_version == v_version:
                        return 1.0

                    # Version range match
                    in_range = _version_in_range(
                        s_version,
                        cpe_item.get("version_start_incl", ""),
                        cpe_item.get("version_start_excl", ""),
                        cpe_item.get("version_end_incl", ""),
                        cpe_item.get("version_end_excl", ""),
                    )
                    if in_range:
                        best = max(best or 0, 0.85)
                        continue

                    # Product only (version mismatch hoặc không rõ)
                    if not s_version or not v_version:
                        best = max(best or 0, 0.65)

        # ── Path 2: Dùng product name normalize ─────────────────────────────
        if svc_product:
            s_vendor_n, s_product_n = _normalize_product(svc_product)
            if s_product_n and (s_product_n == v_product or
                                 s_product_n in v_product or
                                 v_product in s_product_n):
                if s_vendor_n and s_vendor_n != v_vendor:
                    # Vendor mismatch — giảm confidence
                    pass
                else:
                    # Version range check với product name path
                    in_range = _version_in_range(
                        svc_version,
                        cpe_item.get("version_start_incl", ""),
                        cpe_item.get("version_start_excl", ""),
                        cpe_item.get("version_end_incl", ""),
                        cpe_item.get("version_end_excl", ""),
                    )
                    if in_range:
                        best = max(best or 0, 0.75)
                    elif not svc_version or not v_version:
                        best = max(best or 0, 0.50)

    return best


# ── Neo4j operations ──────────────────────────────────────────────────────────

_CYPHER_GET_SERVICES = """
MATCH (s:Service)
WHERE s.product IS NOT NULL
RETURN s.id AS id, s.product AS product, s.version AS version,
       s.cpe AS cpe, s.host AS host
ORDER BY s.id
SKIP $skip LIMIT $limit
"""

_CYPHER_GET_VULNS = """
MATCH (v:Vulnerability)
WHERE v.cpe_products IS NOT NULL AND size(v.cpe_products) > 0
RETURN v.id AS id, v.cve_id AS cve_id, v.cvss_score AS cvss_score,
       v.cvss_severity AS severity,
       v.cpe_vendors AS cpe_vendors,
       v.cpe_products AS cpe_products,
       v.cpe_affected AS cpe_affected
"""

_CYPHER_MERGE_EDGE = """
MATCH (s:Service {id: $svc_id})
MATCH (v:Vulnerability {id: $vuln_id})
MERGE (s)-[r:HAS_VULN]->(v)
SET
    r.confidence    = $confidence,
    r.source        = $source,
    r.match_method  = $method,
    r.created_at    = datetime(),
    r.updated_at    = datetime()
RETURN type(r) AS rel
"""


def run(min_confidence: float, dry_run: bool, limit_services: Optional[int]):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"[OK]  Connected: {NEO4J_URI}\n")

    # Load toàn bộ Vulnerability nodes có CPE data
    print("[LOAD] Loading Vulnerability nodes with CPE data...")
    with driver.session() as s:
        result = s.run(_CYPHER_GET_VULNS)
        vulns = [dict(r) for r in result]
    print(f"       {len(vulns):,} vulnerabilities with CPE data\n")

    if not vulns:
        print("[WARN] Khong co Vulnerability node nao co cpe_products.")
        print("       Hay chay ingest_cvss_direct.py truoc de load CPE data tu NVD.")
        driver.close()
        return

    # Xử lý từng batch Service
    page_size = 200
    skip = 0
    total_edges = 0
    total_services = 0

    while True:
        with driver.session() as s:
            result = s.run(_CYPHER_GET_SERVICES, skip=skip, limit=page_size)
            services = [dict(r) for r in result]

        if not services:
            break

        for svc in services:
            total_services += 1
            svc_id = svc["id"]
            matches = []

            for vuln in vulns:
                conf = _match_service_to_cve(svc, vuln)
                if conf is not None and conf >= min_confidence:
                    # Xác định method
                    if conf >= 0.90:
                        method = "cpe_exact"
                    elif conf >= 0.80:
                        method = "cpe_version_range"
                    elif conf >= 0.60:
                        method = "cpe_product_match"
                    else:
                        method = "product_name_fuzzy"

                    matches.append({
                        "vuln_id":    vuln["id"],
                        "cve_id":     vuln["cve_id"],
                        "confidence": round(conf, 3),
                        "method":     method,
                    })

            if matches:
                matches.sort(key=lambda x: -x["confidence"])
                if not dry_run:
                    with driver.session() as s:
                        for m in matches:
                            s.run(
                                _CYPHER_MERGE_EDGE,
                                svc_id=svc_id,
                                vuln_id=m["vuln_id"],
                                confidence=m["confidence"],
                                source="nmap_cpe_match",
                                method=m["method"],
                            )
                total_edges += len(matches)
                print(
                    f"  {svc_id:<40}  product={svc.get('product',''):<20}"
                    f"  -> {len(matches)} CVE  "
                    f"  (best: {matches[0]['cve_id']} conf={matches[0]['confidence']})"
                )

        skip += page_size
        if limit_services and total_services >= limit_services:
            break

    driver.close()

    mode = "[DRY RUN]" if dry_run else "[DONE]"
    print(f"\n{mode}")
    print(f"  Services processed : {total_services:,}")
    print(f"  HAS_VULN edges {'would create' if dry_run else 'created'}: {total_edges:,}")
    if dry_run:
        print("\n  Chay lai khong co --dry-run de ghi vao Neo4j.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Create Service->CVE edges via CPE matching."
    )
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE_DEFAULT,
                        help=f"Nguong confidence toi thieu (default: {MIN_CONFIDENCE_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Chay thu, khong ghi Neo4j")
    parser.add_argument("--limit-services", type=int, default=None,
                        help="Gioi han so Service nodes xu ly (de test)")
    parser.add_argument("--uri", default=None)
    args = parser.parse_args()

    global NEO4J_URI
    if args.uri:
        NEO4J_URI = args.uri

    run(
        min_confidence=args.min_confidence,
        dry_run=args.dry_run,
        limit_services=args.limit_services,
    )


if __name__ == "__main__":
    main()
