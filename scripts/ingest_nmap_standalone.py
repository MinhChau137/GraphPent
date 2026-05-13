#!/usr/bin/env python3
"""
ingest_nmap_standalone.py — Parse Nmap XML và MERGE vào Neo4j.
Chạy trực tiếp từ host, không cần Docker container.

Usage:
    python scripts/ingest_nmap_standalone.py --file data/sample_nmap_scan.xml
    python scripts/ingest_nmap_standalone.py --file data/sample_nmap_scan.xml --dry-run
    python scripts/ingest_nmap_standalone.py --file data/sample_nmap_scan.xml --wipe-group1
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


# ── Vendor lookup (same as nmap_adapter.py) ───────────────────────────────────

_VENDOR_MAP = {
    "apache": "apache", "apache httpd": "apache", "apache http server": "apache",
    "apache tomcat": "apache", "tomcat": "apache", "struts": "apache",
    "nginx": "nginx",
    "iis": "microsoft", "microsoft iis": "microsoft",
    "openssh": "openbsd",
    "dropbear": "matt_johnston", "dropbear sshd": "matt_johnston",
    "mysql": "oracle", "mysql community server": "oracle",
    "mariadb": "mariadb",
    "postgresql": "postgresql",
    "redis": "redis",
    "mongodb": "mongodb",
    "proftpd": "proftpd",
    "vsftpd": "beasts",
    "pure-ftpd": "pureftpd",
    "samba": "samba",
    "exim": "exim", "exim smtpd": "exim",
    "postfix": "postfix",
    "sendmail": "sendmail",
    "dovecot": "dovecot", "dovecot imapd": "dovecot",
    "lighttpd": "lighttpd",
    "php": "php",
    "wordpress": "wordpress",
    "drupal": "drupal",
    "joomla": "joomla",
    "jenkins": "jenkins",
    "elasticsearch": "elastic",
    "kibana": "elastic",
    "influxdb": "influxdata",
    "grafana": "grafana",
    "rabbitmq": "vmware",
    "spring": "vmware",
    "log4j": "apache",
}

_WEB_PORTS = {80, 443, 8080, 8443, 8888, 9000, 9090, 3000, 4443,
              8161, 4848, 7001, 8090, 8000, 8008, 9200, 5601}


def _vendor(product: str) -> str:
    key = product.strip().lower()
    if key in _VENDOR_MAP:
        return _VENDOR_MAP[key]
    for k, v in _VENDOR_MAP.items():
        if k in key or key in k:
            return v
    return ""


# ── Nmap XML parser ───────────────────────────────────────────────────────────

def parse_nmap_xml(xml_data: str):
    """Returns (entities, relations) as lists of dicts."""
    entities = []
    relations = []
    seen_zones = {}
    seen_apps  = {}

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        print(f"[ERR] XML parse error: {e}")
        return [], []

    for host_elem in root.findall("host"):
        status = host_elem.find("status")
        if status is None or status.get("state") != "up":
            continue

        ip = None
        for addr in host_elem.findall("address"):
            if addr.get("addrtype") == "ipv4":
                ip = addr.get("addr")
                break
        if not ip:
            continue

        mac = None
        for addr in host_elem.findall("address"):
            if addr.get("addrtype") == "mac":
                mac = addr.get("addr")
                break

        hostname = None
        hostnames = host_elem.find("hostnames")
        if hostnames is not None:
            hn = hostnames.find("hostname")
            if hn is not None:
                hostname = hn.get("name")

        os_name = None
        os_elem = host_elem.find("os")
        if os_elem is not None:
            match = os_elem.find("osmatch")
            if match is not None:
                os_name = match.get("name")

        subnet  = ".".join(ip.split(".")[:3]) + ".0/24"
        zone_id = f"zone-{subnet.replace('/', '_')}"

        if zone_id not in seen_zones:
            seen_zones[zone_id] = True
            entities.append({"label": "NetworkZone", "id": zone_id, "name": subnet,
                              "subnet": subnet, "cidr": "/24",
                              "network": ".".join(ip.split(".")[:3]) + ".0"})

        entities.append({"label": "IP", "id": f"ip-{ip}", "name": ip,
                         "address": ip, "version": "ipv4", "subnet": subnet})

        entities.append({"label": "Host", "id": f"host-{ip}", "name": hostname or ip,
                         "ip": ip, "hostname": hostname or "", "os": os_name or "",
                         "mac": mac or "", "status": "up", "subnet": subnet})

        relations.append({"type": "HAS_IP",      "src": f"host-{ip}", "dst": f"ip-{ip}"})
        relations.append({"type": "LOCATED_IN",  "src": f"host-{ip}", "dst": zone_id})
        relations.append({"type": "LOCATED_IN",  "src": f"ip-{ip}",   "dst": zone_id})

        if hostname:
            domain_id = f"domain-{hostname.lower()}"
            entities.append({"label": "Domain", "id": domain_id, "name": hostname,
                             "fqdn": hostname, "host_ip": ip})
            relations.append({"type": "HAS_HOSTNAME", "src": f"host-{ip}", "dst": domain_id})

        ports_elem = host_elem.find("ports")
        if ports_elem is None:
            continue

        for port_elem in ports_elem.findall("port"):
            state_elem = port_elem.find("state")
            if state_elem is None or state_elem.get("state") != "open":
                continue

            portid   = port_elem.get("portid", "0")
            protocol = port_elem.get("protocol", "tcp")
            port_key = f"port-{ip}-{protocol}-{portid}"

            entities.append({"label": "Port", "id": port_key,
                             "name": f"{portid}/{protocol}",
                             "port": int(portid), "protocol": protocol,
                             "state": "open", "host": ip})
            relations.append({"type": "HAS_PORT", "src": f"host-{ip}", "dst": port_key})

            service_elem = port_elem.find("service")
            if service_elem is None:
                continue

            svc_name    = service_elem.get("name", "unknown")
            svc_product = service_elem.get("product", "")
            svc_version = service_elem.get("version", "")
            svc_extra   = service_elem.get("extrainfo", "")
            svc_tunnel  = service_elem.get("tunnel", "")
            svc_cpe     = service_elem.get("cpe", "")
            if not svc_cpe:
                cpe_elem = service_elem.find("cpe")
                if cpe_elem is not None and cpe_elem.text:
                    svc_cpe = cpe_elem.text.strip()

            svc_key = f"service-{ip}-{portid}"
            entities.append({"label": "Service", "id": svc_key, "name": svc_name,
                             "product": svc_product, "version": svc_version,
                             "port": int(portid), "protocol": protocol, "host": ip,
                             "extrainfo": svc_extra, "tunnel": svc_tunnel,
                             "full_name": f"{svc_product} {svc_version}".strip() or svc_name,
                             "cpe": svc_cpe})

            relations.append({"type": "RUNS_SERVICE", "src": port_key,   "dst": svc_key})
            relations.append({"type": "EXPOSES",      "src": f"host-{ip}", "dst": svc_key})

            if svc_product:
                app_slug = re.sub(r"[^a-z0-9]+", "-",
                                  f"{svc_product}-{svc_version}".lower()).strip("-")
                app_id = f"app-{app_slug}"
                if app_id not in seen_apps:
                    seen_apps[app_id] = True
                    entities.append({"label": "Application", "id": app_id,
                                    "name": f"{svc_product} {svc_version}".strip(),
                                    "product": svc_product, "version": svc_version,
                                    "vendor": _vendor(svc_product), "cpe": svc_cpe})
                relations.append({"type": "RUNS", "src": svc_key,       "dst": app_id})
                relations.append({"type": "RUNS", "src": f"host-{ip}",  "dst": app_id,
                                  "port": int(portid)})

            if int(portid) in _WEB_PORTS:
                is_ssl = (svc_tunnel == "ssl" or
                          portid in ("443", "8443", "4443") or
                          "https" in svc_name)
                scheme  = "https" if is_ssl else "http"
                url_str = f"{scheme}://{ip}:{portid}"
                url_id  = f"url-{ip}-{portid}"
                entities.append({"label": "URL", "id": url_id, "name": url_str,
                                 "url": url_str, "scheme": scheme,
                                 "host": ip, "port": int(portid), "path": "/"})
                relations.append({"type": "EXPOSES",   "src": svc_key,       "dst": url_id})
                relations.append({"type": "HOSTED_ON", "src": url_id,        "dst": f"host-{ip}"})

    return entities, relations


# ── Neo4j writer ──────────────────────────────────────────────────────────────

_MERGE_NODE = """
MERGE (n {id: $id})
SET n.name = $name
WITH n
CALL apoc.create.addLabels(n, [$label]) YIELD node
SET node += $props
"""

_MERGE_NODE_SIMPLE = """
MERGE (n {id: $id})
SET n += $props, n.name = $name
"""

_MERGE_REL = """
MATCH (a {id: $src})
MATCH (b {id: $dst})
MERGE (a)-[r:%s]->(b)
SET r += $props
"""

_WIPE_G1 = """
MATCH (n)
WHERE any(l IN labels(n) WHERE l IN
  ['Host','IP','Port','Service','Application','URL','NetworkZone','Domain'])
DETACH DELETE n
"""

_CREATE_INDEXES = [
    "CREATE INDEX host_id   IF NOT EXISTS FOR (n:Host)        ON (n.id)",
    "CREATE INDEX ip_id     IF NOT EXISTS FOR (n:IP)          ON (n.id)",
    "CREATE INDEX port_id   IF NOT EXISTS FOR (n:Port)        ON (n.id)",
    "CREATE INDEX svc_id    IF NOT EXISTS FOR (n:Service)     ON (n.id)",
    "CREATE INDEX app_id    IF NOT EXISTS FOR (n:Application) ON (n.id)",
    "CREATE INDEX url_id    IF NOT EXISTS FOR (n:URL)         ON (n.id)",
    "CREATE INDEX zone_id   IF NOT EXISTS FOR (n:NetworkZone) ON (n.id)",
    "CREATE INDEX domain_id IF NOT EXISTS FOR (n:Domain)      ON (n.id)",
]


def _label_props(entity: dict) -> dict:
    """Tách label + id + name ra, còn lại là props."""
    skip = {"label", "id", "name"}
    return {k: v for k, v in entity.items()
            if k not in skip and isinstance(v, (str, int, float, bool)) and v is not None and v != ""}


def merge_entities(session, entities: list, use_apoc: bool = False):
    ok = err = 0
    for e in entities:
        props = _label_props(e)
        props["id"] = e["id"]
        # Set label via dynamic Cypher
        cypher = f"MERGE (n:{e['label']} {{id: $id}}) SET n += $props, n.name = $name"
        try:
            session.run(cypher, id=e["id"], name=e.get("name", ""), props=props)
            ok += 1
        except Exception as ex:
            err += 1
            if err <= 3:
                print(f"  [ERR] entity {e['id']}: {ex}")
    return ok, err


def merge_relations(session, relations: list):
    ok = err = 0
    for r in relations:
        rel_type = r["type"]
        props = {k: v for k, v in r.items()
                 if k not in {"type", "src", "dst"}
                 and isinstance(v, (str, int, float, bool))}
        cypher = f"""
        MATCH (a {{id: $src}})
        MATCH (b {{id: $dst}})
        MERGE (a)-[rel:{rel_type}]->(b)
        SET rel += $props
        """
        try:
            session.run(cypher, src=r["src"], dst=r["dst"], props=props)
            ok += 1
        except Exception as ex:
            err += 1
            if err <= 3:
                print(f"  [ERR] rel {r['src']}-[{rel_type}]->{r['dst']}: {ex}")
    return ok, err


def ingest(xml_path: Path, dry_run: bool, wipe_group1: bool):
    print(f"[PARSE] {xml_path}")
    xml_data = xml_path.read_text(encoding="utf-8", errors="replace")
    entities, relations = parse_nmap_xml(xml_data)

    by_label = {}
    for e in entities:
        by_label.setdefault(e["label"], 0)
        by_label[e["label"]] += 1

    print(f"  Parsed entities : {len(entities):,}")
    for label, cnt in sorted(by_label.items()):
        print(f"    {label:<15} {cnt:>5,}")
    print(f"  Parsed relations: {len(relations):,}")

    if dry_run:
        print("\n[DRY RUN] Khong ghi Neo4j.")
        print("\n  Sample entities:")
        for e in entities[:5]:
            print(f"    [{e['label']}] {e['id']} | {e.get('name','')}")
        print("\n  Sample relations:")
        for r in relations[:5]:
            print(f"    {r['src']} -[{r['type']}]-> {r['dst']}")
        return

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"\n[OK] Connected: {NEO4J_URI}")

    with driver.session() as session:
        # Indexes
        for idx in _CREATE_INDEXES:
            session.run(idx)

        if wipe_group1:
            print("[WIPE] Xoa toan bo Group 1 nodes...")
            session.run(_WIPE_G1)
            print("  Done.")

        print(f"\n[MERGE] Entities...")
        ok, err = merge_entities(session, entities)
        print(f"  {ok:,} ok, {err} errors")

        print(f"[MERGE] Relations...")
        ok, err = merge_relations(session, relations)
        print(f"  {ok:,} ok, {err} errors")

    driver.close()
    print("\n[DONE]")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to Nmap XML file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--wipe-group1", action="store_true",
                        help="Xoa sach Group 1 nodes truoc khi ingest (re-ingest)")
    args = parser.parse_args()

    xml_path = Path(args.file)
    if not xml_path.exists():
        print(f"[ERR] File not found: {xml_path}")
        sys.exit(1)

    ingest(xml_path, dry_run=args.dry_run, wipe_group1=args.wipe_group1)


if __name__ == "__main__":
    main()
