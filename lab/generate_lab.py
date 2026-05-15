#!/usr/bin/env python3
"""
generate_lab.py — parse nmap XML, produce docker-compose file(s)

Each scanned host → one 'anchor' container (gets a static lab IP) +
N sidecar containers sharing the same IP via network_mode.

IP mapping: 192.168.A.B → 172.30.A.B  (subnet 172.30.0.0/16)

Usage:
    python lab/generate_lab.py                          # one big compose file
    python lab/generate_lab.py --batch-size 5           # 20+ batch files in lab/batches/
    python lab/generate_lab.py --input data/my.xml      # custom XML source
    python lab/generate_lab.py --output lab/dc.yml      # custom output (single mode)
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ── Service → Docker image mapping ───────────────────────────────────────
#
# priority: higher = preferred as anchor (the container that owns the IP).
# env/cmd: forwarded verbatim into the compose service.
# "custom" images reference build contexts in lab/; others are Docker Hub.

ANCHORS: dict[str, dict] = {
    "http":         {"image": "lab-webserver",                       "priority": 90, "env": {}, "cmd": ""},
    "https":        {"image": "lab-webserver",                       "priority": 90, "env": {}, "cmd": ""},
    "mysql":        {"image": "mysql:5.7",                           "priority": 85,
                     "env": {"MYSQL_ROOT_PASSWORD": "root", "MYSQL_ROOT_HOST": "%"}, "cmd": ""},
    "postgresql":   {"image": "postgres:14",                         "priority": 85,
                     "env": {"POSTGRES_PASSWORD": "root", "POSTGRES_HOST_AUTH_METHOD": "trust"}, "cmd": ""},
    "http-proxy":   {"image": "tomcat:9.0.65-jdk11-openjdk-slim",    "priority": 80, "env": {}, "cmd": ""},
    "redis":        {"image": "redis:6.2.6",                         "priority": 75, "env": {},
                     "cmd": "redis-server --bind 0.0.0.0 --protected-mode no"},
    "ftp":          {"image": "lab-fileserver",                      "priority": 70, "env": {}, "cmd": ""},
    "smtp":         {"image": "lab-mailserver",                      "priority": 70, "env": {}, "cmd": ""},
    "imap":         {"image": "lab-mailserver",                      "priority": 68, "env": {}, "cmd": ""},
    "pop3":         {"image": "lab-mailserver",                      "priority": 68, "env": {}, "cmd": ""},
    "submission":   {"image": "lab-mailserver",                      "priority": 68, "env": {}, "cmd": ""},
    "microsoft-ds": {"image": "lab-fileserver",                      "priority": 65, "env": {}, "cmd": ""},
    "ssh":          {"image": "lab-ssh",                             "priority": 10, "env": {}, "cmd": ""},
}

# Services that share the same image — only ONE container is created per host.
# e.g. a host with both http + https → one lab-webserver (handles both ports).
DEDUP: dict[str, str] = {
    "https":        "http",
    "imap":         "smtp",
    "pop3":         "smtp",
    "submission":   "smtp",
    "microsoft-ds": "ftp",
}

# Custom images → build context relative to docker-compose.full.yml location (lab/)
# Explicit port list: covers all services in sample_nmap_scan.xml
# (--top-ports 1000 misses 6379 Redis, 1521 Oracle, etc.)
NMAP_PORTS = (
    "21,22,23,25,53,80,110,111,139,143,443,445,587,993,995,"
    "1521,3306,3389,5432,5900,6379,8080,8443,8888,27017"
)

CUSTOM_BUILD: dict[str, str] = {
    "lab-ssh":        "./ssh",
    "lab-webserver":  "./webserver",
    "lab-fileserver": "./fileserver",
    "lab-mailserver": "./mailserver",
}


# ── IP helpers ────────────────────────────────────────────────────────────

def lab_ip(ip: str) -> str:
    """192.168.A.B  →  172.30.A.B"""
    p = ip.split(".")
    return f"172.30.{p[2]}.{p[3]}"


def svc_name(ip: str, suffix: str = "") -> str:
    """Compose service name, e.g. host-1-10  or  host-1-10-mysql"""
    p = ip.split(".")
    base = f"host-{p[2]}-{p[3]}"
    return f"{base}-{suffix}" if suffix else base


# ── XML parse ─────────────────────────────────────────────────────────────

def parse_hosts(xml_path: str) -> list[dict]:
    tree = ET.parse(xml_path)
    hosts: list[dict] = []
    for h in tree.findall(".//host"):
        if h.find("status").get("state") != "up":
            continue
        ip = h.find("address").get("addr")
        hn_el = h.find(".//hostname")
        hostname = hn_el.get("name", "") if hn_el is not None else ""
        services = []
        for port in h.findall(".//port"):
            if port.find("state").get("state") != "open":
                continue
            svc = port.find("service")
            if svc is None:
                continue
            services.append({
                "port":    int(port.get("portid")),
                "name":    svc.get("name", ""),
                "product": svc.get("product", ""),
                "version": svc.get("version", ""),
            })
        hosts.append({"ip": ip, "hostname": hostname, "services": services})
    return hosts


# ── Container planning ────────────────────────────────────────────────────

def plan(host: dict) -> list[dict]:
    """
    Return ordered list of container specs.
    Element 0 is the anchor (owns the static IP).
    Rest are sidecars (network_mode: service:<anchor>).
    """
    # canonicalize: https→http, imap/pop3→smtp, etc.
    canonical: dict[str, str] = {}   # canonical_name → original_name
    for s in host["services"]:
        name = s["name"]
        canon = DEDUP.get(name, name)
        if canon not in canonical:
            canonical[canon] = name

    # always include ssh
    canonical.setdefault("ssh", "ssh")

    # rank by priority
    ranked = sorted(
        canonical.keys(),
        key=lambda n: ANCHORS.get(n, {"priority": 1})["priority"],
        reverse=True,
    )

    containers = []
    for i, canon in enumerate(ranked):
        cfg = ANCHORS.get(canon, ANCHORS["ssh"])
        containers.append({
            "svc":       canon,
            "image":     cfg["image"],
            "env":       cfg["env"],
            "cmd":       cfg["cmd"],
            "is_anchor": i == 0,
        })
    return containers


# ── YAML emit ─────────────────────────────────────────────────────────────

def emit_service(lines: list[str], host: dict, c: dict, anchor_key: str,
                 build_prefix: str = "./") -> None:
    ip = host["ip"]
    key = anchor_key if c["is_anchor"] else f"{anchor_key}-{c['svc']}"
    cname = f"lab-{key}"
    image = c["image"]

    lines.append(f"  # {'[anchor]' if c['is_anchor'] else '[sidecar]'} {ip}  {c['svc']}")
    lines.append(f"  {key}:")

    if image in CUSTOM_BUILD:
        ctx = build_prefix + CUSTOM_BUILD[image].lstrip("./")
        lines.append(f"    build:")
        lines.append(f"      context: {ctx}")
    else:
        lines.append(f"    image: {image}")

    lines.append(f"    container_name: {cname}")

    if c["is_anchor"]:
        hostname = host["hostname"] or ip.replace(".", "-")
        lines.append(f"    hostname: {hostname}")
        lines.append(f"    networks:")
        lines.append(f"      pentest_lab:")
        lines.append(f"        ipv4_address: {lab_ip(ip)}")
    else:
        lines.append(f"    network_mode: \"service:{anchor_key}\"")
        lines.append(f"    depends_on:")
        lines.append(f"      - {anchor_key}")

    if c["env"]:
        lines.append(f"    environment:")
        for k, v in c["env"].items():
            lines.append(f"      {k}: \"{v}\"")

    if c["cmd"]:
        lines.append(f"    command: {c['cmd']}")

    lines.append(f"    restart: unless-stopped")
    lines.append("")


def _network_block() -> list[str]:
    return [
        "networks:",
        "  pentest_lab:",
        "    driver: bridge",
        "    ipam:",
        "      driver: default",
        "      config:",
        "        - subnet: 172.30.0.0/16",
    ]


def _scanner_block(build_prefix: str = "./") -> list[str]:
    ctx = build_prefix + "scanner"
    # results volume: one level above where the compose file lives
    results_vol = build_prefix + "results"
    return [
        "  # ── scanner / attacker ─────────────────────────────────────────────",
        "  scanner:",
        "    build:",
        f"      context: {ctx}",
        "    container_name: lab-scanner",
        "    hostname: attacker.local",
        "    networks:",
        "      pentest_lab:",
        "        ipv4_address: 172.30.0.200",
        "    volumes:",
        f"      - {results_vol}:/results",
        "    stdin_open: true",
        "    tty: true",
        "    restart: unless-stopped",
    ]


def generate(hosts: list[dict], batch_num: int = 0, total_batches: int = 0,
             build_prefix: str = "./") -> str:
    """Produce a complete docker-compose YAML for the given host list.

    build_prefix: path prefix for custom image build contexts, e.g. "../" for
    compose files stored one level deeper than lab/.
    """
    if batch_num:
        title = f"# Batch {batch_num:02d}/{total_batches:02d} -- Hosts: {len(hosts)}"
        ips = " ".join(lab_ip(h["ip"]) for h in hosts)
        scan_comment = (
            f"# Scan:  docker exec lab-scanner nmap -sV -O -p {NMAP_PORTS} -T4 "
            f"{ips} -oX /results/batch_{batch_num:02d}.xml"
        )
    else:
        title = f"# Hosts: {len(hosts)}"
        scan_comment = (
            "# Scan:  docker exec lab-scanner nmap -sV -O "
            "--top-ports 1000 172.30.0.0/16 -oX /results/scan.xml"
        )

    lines: list[str] = [
        "version: \"3.9\"",
        "",
        "# Auto-generated by lab/generate_lab.py — do not edit manually",
        title,
        scan_comment,
        "",
    ]
    lines += _network_block()
    lines += ["", "services:", ""]

    total_containers = 0
    for host in hosts:
        containers = plan(host)
        anchor_key = svc_name(host["ip"])
        for c in containers:
            emit_service(lines, host, c, anchor_key, build_prefix=build_prefix)
            total_containers += 1

    lines += _scanner_block(build_prefix=build_prefix)

    header = f"# Containers: {total_containers + 1}  (incl. scanner)\n"
    return header + "\n".join(lines)


# ── Batch helpers ─────────────────────────────────────────────────────────

def _chunk(lst: list, n: int) -> list[list]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def generate_batches(hosts: list[dict], batch_size: int, out_dir: Path) -> int:
    """
    Write one docker-compose file per batch into out_dir.
    Returns number of batches created.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    batches = _chunk(hosts, batch_size)
    n = len(batches)

    for i, batch in enumerate(batches, 1):
        # batches/ is one level inside lab/, so build contexts need "../"
        yaml_text = generate(batch, batch_num=i, total_batches=n, build_prefix="../")
        p = out_dir / f"batch_{i:02d}.yml"
        p.write_text(yaml_text, encoding="utf-8")

    # Shell helper script — runs every batch in sequence and scans each one
    _write_run_script(batches, out_dir, n)
    # PowerShell version for Windows
    _write_run_ps1(batches, out_dir, n)

    return n


def _write_run_script(batches: list[list[dict]], out_dir: Path, n: int) -> None:
    lines = [
        "#!/usr/bin/env bash",
        "# run_all_batches.sh — bring up each batch, scan it, tear it down",
        "# Run from the project root: bash lab/batches/run_all_batches.sh",
        "set -euo pipefail",
        "",
        'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
        'RESULTS_DIR="$SCRIPT_DIR/../results"',
        "mkdir -p \"$RESULTS_DIR\"",
        "",
    ]
    for i, batch in enumerate(batches, 1):
        ips = " ".join(lab_ip(h["ip"]) for h in batch)
        xml_out = f"/results/batch_{i:02d}.xml"
        yml = f"$SCRIPT_DIR/batch_{i:02d}.yml"
        lines += [
            f'echo "━━━━━━ Batch {i:02d}/{n}: {len(batch)} hosts ━━━━━━"',
            f"docker compose -f {yml} up -d --build",
            f'echo "  [*] Waiting for services..."',
            f"sleep 15",
            f'echo "  [*] Scanning..."',
            f"docker exec lab-scanner nmap -sV -O -p {NMAP_PORTS} -T4 {ips} -oX {xml_out} || true",
            f'echo "  [+] Results → results/batch_{i:02d}.xml"',
            f"docker compose -f {yml} down",
            "",
        ]
    lines += [
        'echo "━━━━━━ All batches done ━━━━━━"',
        'echo "XML files in: $RESULTS_DIR"',
    ]
    (out_dir / "run_all_batches.sh").write_text("\n".join(lines), encoding="utf-8")


def _write_run_ps1(batches: list[list[dict]], out_dir: Path, n: int) -> None:
    lines = [
        "# run_all_batches.ps1 — Windows PowerShell version",
        "# Run from the project root: .\\lab\\batches\\run_all_batches.ps1",
        '$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path',
        '$ResultsDir = "$ScriptDir\\..\\results"',
        'New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null',
        "",
    ]
    for i, batch in enumerate(batches, 1):
        ips = " ".join(lab_ip(h["ip"]) for h in batch)
        xml_out = f"/results/batch_{i:02d}.xml"
        yml = f'$ScriptDir\\batch_{i:02d}.yml'
        lines += [
            f'Write-Host "━━━━━━ Batch {i:02d}/{n}: {len(batch)} hosts ━━━━━━"',
            f"docker compose -f {yml} up -d --build",
            f'Write-Host "  [*] Waiting for services..."',
            f"Start-Sleep -Seconds 15",
            f'Write-Host "  [*] Scanning..."',
            f"docker exec lab-scanner nmap -sV -O -p {NMAP_PORTS} -T4 {ips} -oX {xml_out}",
            f'Write-Host "  [+] Results saved to results/batch_{i:02d}.xml"',
            f"docker compose -f {yml} down",
            "",
        ]
    lines += ['Write-Host "━━━━━━ All batches done ━━━━━━"']
    (out_dir / "run_all_batches.ps1").write_text("\n".join(lines), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input",      default="../data/sample_nmap_scan.xml",
                    help="nmap XML source (relative to this script)")
    ap.add_argument("--output",     default="docker-compose.full.yml",
                    help="Output file for single-file mode")
    ap.add_argument("--batch-size", type=int, default=0, metavar="N",
                    help="Split into batches of N hosts each (creates lab/batches/)")
    args = ap.parse_args()

    here = Path(__file__).parent
    xml_path = (here / args.input).resolve()

    if not xml_path.exists():
        print(f"[!] XML not found: {xml_path}", file=sys.stderr)
        sys.exit(1)

    hosts = parse_hosts(str(xml_path))
    print(f"[*] Hosts parsed: {len(hosts)}")

    if args.batch_size:
        # ── Batch mode ───────────────────────────────────────────────────
        out_dir = here / "batches"
        n = generate_batches(hosts, args.batch_size, out_dir)
        batches = _chunk(hosts, args.batch_size)
        print(f"[+] {n} batch files -> {out_dir}/")
        print(f"    batch_01.yml … batch_{n:02d}.yml  ({args.batch_size} hosts each)")
        print(f"    run_all_batches.sh  (bash)")
        print(f"    run_all_batches.ps1 (PowerShell)")
        print()
        print("Run all batches sequentially:")
        print("  bash lab/batches/run_all_batches.sh")
        print()
        print("Or run a single batch manually:")
        print("  docker compose -f lab/batches/batch_01.yml up -d --build")
        print("  docker exec lab-scanner nmap -sV -T4 \\")
        ips_ex = " ".join(lab_ip(h["ip"]) for h in batches[0])
        print(f"    {ips_ex} -oX /results/batch_01.xml")
        print("  docker compose -f lab/batches/batch_01.yml down")
    else:
        # ── Single-file mode ─────────────────────────────────────────────
        out_path = (here / args.output).resolve()
        containers = sum(len(plan(h)) for h in hosts)
        print(f"[*] Containers: {containers + 1}  (incl. scanner)")
        compose_yaml = generate(hosts)
        out_path.write_text(compose_yaml, encoding="utf-8")
        print(f"[+] Written: {out_path}")
        print()
        print("Start:")
        print(f"  docker compose -f lab/docker-compose.full.yml up -d --build")
        print(f"  docker exec lab-scanner nmap -sV -O --top-ports 1000 172.30.0.0/16 \\")
        print(f"         -oX /results/full_scan.xml")
        print("Stop:")
        print(f"  docker compose -f lab/docker-compose.full.yml down")


if __name__ == "__main__":
    main()
