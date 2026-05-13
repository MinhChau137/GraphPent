#!/usr/bin/env python3
"""
ingest_attack_ttp.py — Ingest MITRE ATT&CK Enterprise techniques vào Neo4j.

Tạo TTP nodes + cạnh TTP -[USES_TECHNIQUE]-> TTP (tactic → technique)
và TTP -[MAPPED_TO]-> CWE khi có mapping data.

Usage:
    # Download tự động từ MITRE GitHub (cần internet):
    python scripts/ingest_attack_ttp.py

    # Dùng file local đã tải về:
    python scripts/ingest_attack_ttp.py --file data/enterprise-attack.json

    # Chỉ xem, không ghi:
    python scripts/ingest_attack_ttp.py --dry-run

Download file thủ công:
    curl -L https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json \
         -o data/enterprise-attack.json
"""

import argparse
import json
import os
import sys
import urllib.request
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

ATTACK_URL = (
    "https://raw.githubusercontent.com/mitre/cti/master/"
    "enterprise-attack/enterprise-attack.json"
)
DEFAULT_FILE = Path(__file__).parent.parent / "data" / "enterprise-attack.json"

# ── CWE mapping (subset — technique_id → [CWE-IDs]) ─────────────────────────
# Source: MITRE CWE–ATT&CK mappings (selected high-value entries)
_TTP_CWE_MAP = {
    "T1190": ["CWE-20", "CWE-89", "CWE-79", "CWE-78"],   # Exploit Public-Facing App
    "T1059": ["CWE-78", "CWE-77", "CWE-116"],             # Command Scripting
    "T1059.001": ["CWE-78"],                               # PowerShell
    "T1059.003": ["CWE-78"],                               # Windows CMD
    "T1203": ["CWE-20", "CWE-119", "CWE-416"],            # Exploitation for Client Execution
    "T1078": ["CWE-287", "CWE-522", "CWE-798"],           # Valid Accounts
    "T1110": ["CWE-307", "CWE-521"],                       # Brute Force
    "T1110.001": ["CWE-521"],                              # Password Guessing
    "T1133": ["CWE-287"],                                  # External Remote Services
    "T1021": ["CWE-287"],                                  # Remote Services
    "T1021.001": ["CWE-287"],                              # RDP
    "T1021.004": ["CWE-287"],                              # SSH
    "T1068": ["CWE-269", "CWE-250"],                       # Exploitation for Privilege Escalation
    "T1055": ["CWE-119", "CWE-416"],                       # Process Injection
    "T1134": ["CWE-269"],                                  # Access Token Manipulation
    "T1003": ["CWE-522", "CWE-256"],                       # OS Credential Dumping
    "T1552": ["CWE-312", "CWE-522"],                       # Unsecured Credentials
    "T1083": ["CWE-732"],                                  # File and Directory Discovery
    "T1071": ["CWE-319"],                                  # App Layer Protocol (C2)
    "T1041": ["CWE-319"],                                  # Exfiltration Over C2 Channel
    "T1486": ["CWE-400"],                                  # Data Encrypted for Impact
    "T1562": ["CWE-693"],                                  # Impair Defenses
    "T1562.001": ["CWE-693"],                              # Disable/Modify Tools
    "T1036": ["CWE-116"],                                  # Masquerading
    "T1218": ["CWE-829"],                                  # System Binary Proxy Execution
    "T1105": ["CWE-829"],                                  # Ingress Tool Transfer
    "T1574": ["CWE-426", "CWE-427"],                       # Hijack Execution Flow
    "T1548": ["CWE-269", "CWE-284"],                       # Abuse Elevation Control
}


# ── Parser ────────────────────────────────────────────────────────────────────

def _load_stix(filepath: Optional[Path]) -> dict:
    if filepath and filepath.exists():
        print(f"[READ] {filepath}")
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return json.load(f)

    print(f"[DOWNLOAD] {ATTACK_URL}")
    print("  (Nếu không có internet, tải thủ công và dùng --file)")
    try:
        req = urllib.request.urlopen(ATTACK_URL, timeout=30)
        data = json.loads(req.read().decode("utf-8"))
        # Cache locally
        DEFAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_FILE.write_text(json.dumps(data), encoding="utf-8")
        print(f"  Cached: {DEFAULT_FILE}")
        return data
    except Exception as e:
        print(f"[ERR] Download failed: {e}")
        print("  Tải thủ công:")
        print(f"  curl -L \"{ATTACK_URL}\" -o data/enterprise-attack.json")
        sys.exit(1)


def parse_stix(bundle: dict) -> tuple[list[dict], list[dict]]:
    """Parse STIX bundle → (ttp_nodes, relations)."""
    objects = bundle.get("objects", [])
    ttps = []
    relations = []

    # Build tactic lookup: x-mitre-tactic id → shortname
    tactic_map = {}
    for obj in objects:
        if obj.get("type") == "x-mitre-tactic":
            ext = obj.get("x_mitre_shortname", "")
            tactic_map[obj.get("id", "")] = ext

    for obj in objects:
        if obj.get("type") != "attack-pattern":
            continue
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue

        ext_refs = obj.get("external_references", [])
        technique_id = next(
            (r["external_id"] for r in ext_refs
             if r.get("source_name") == "mitre-attack"),
            None,
        )
        if not technique_id:
            continue

        name        = obj.get("name", "")
        description = (obj.get("description") or "")[:500]
        platforms   = obj.get("x_mitre_platforms", [])
        tactics     = [
            p.get("phase_name", "")
            for p in obj.get("kill_chain_phases", [])
            if p.get("kill_chain_name") == "mitre-attack"
        ]
        is_sub      = "." in technique_id
        parent_id   = technique_id.split(".")[0] if is_sub else None

        node_id = f"ttp-{technique_id.lower()}"
        ttps.append({
            "id":           node_id,
            "name":         f"{technique_id}: {name}",
            "technique_id": technique_id,
            "tactic":       tactics[0] if tactics else "",
            "tactics":      tactics,
            "platforms":    platforms,
            "description":  description,
            "is_subtechnique": is_sub,
        })

        # Sub-technique → parent relation
        if is_sub and parent_id:
            relations.append({
                "type": "CHILD_OF",
                "src":  node_id,
                "dst":  f"ttp-{parent_id.lower()}",
            })

        # TTP → CWE mapping
        for cwe_id in _TTP_CWE_MAP.get(technique_id, []):
            relations.append({
                "type": "MAPPED_TO",
                "src":  node_id,
                "dst":  f"cwe-{cwe_id.lower()}",
                "confidence": 0.85,
                "source": "mitre_mapping",
            })

    print(f"  Techniques: {len(ttps):,}  |  Relations: {len(relations):,}")
    return ttps, relations


# ── Neo4j writer ──────────────────────────────────────────────────────────────

_CREATE_INDEXES = [
    "CREATE INDEX ttp_id IF NOT EXISTS FOR (n:TTP) ON (n.id)",
    "CREATE INDEX ttp_technique IF NOT EXISTS FOR (n:TTP) ON (n.technique_id)",
]

_MERGE_TTP = """
UNWIND $rows AS row
MERGE (t:TTP {id: row.id})
SET
    t.name           = row.name,
    t.technique_id   = row.technique_id,
    t.tactic         = row.tactic,
    t.tactics        = row.tactics,
    t.platforms      = row.platforms,
    t.description    = row.description,
    t.is_subtechnique = row.is_subtechnique,
    t.updated_at     = datetime()
"""

_MERGE_CHILD_OF = """
UNWIND $rows AS row
MATCH (child:TTP {id: row.src})
MATCH (parent:TTP {id: row.dst})
MERGE (child)-[r:CHILD_OF]->(parent)
"""

_MERGE_MAPPED_TO = """
UNWIND $rows AS row
MATCH (t:TTP {id: row.src})
MATCH (c:CWE {id: row.dst})
MERGE (t)-[r:MAPPED_TO]->(c)
SET r.confidence = row.confidence,
    r.source     = row.source
"""


def ingest(ttps: list[dict], relations: list[dict], dry_run: bool):
    if dry_run:
        print("\n[DRY RUN] Sample TTP nodes:")
        for t in ttps[:5]:
            print(f"  [{t['technique_id']}] {t['name'][:60]}  tactic={t['tactic']}")
        print(f"\n[DRY RUN] Sample relations:")
        for r in relations[:5]:
            print(f"  {r['src']} -[{r['type']}]-> {r['dst']}")
        return

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"[OK] Connected: {NEO4J_URI}\n")

    with driver.session() as s:
        for idx in _CREATE_INDEXES:
            s.run(idx)

        # Merge TTP nodes in batches
        BATCH = 200
        ok = 0
        for i in range(0, len(ttps), BATCH):
            batch = ttps[i:i+BATCH]
            s.run(_MERGE_TTP, rows=batch)
            ok += len(batch)
        print(f"[MERGE] TTP nodes: {ok:,}")

        # CHILD_OF (sub-technique → parent)
        child_rels = [r for r in relations if r["type"] == "CHILD_OF"]
        if child_rels:
            s.run(_MERGE_CHILD_OF, rows=child_rels)
            print(f"[MERGE] CHILD_OF edges: {len(child_rels):,}")

        # MAPPED_TO (TTP → CWE) — only if CWE nodes exist
        cwe_count = s.run("MATCH (c:CWE) RETURN count(c) AS n").single()["n"]
        mapped_rels = [r for r in relations if r["type"] == "MAPPED_TO"]
        if mapped_rels and cwe_count > 0:
            s.run(_MERGE_MAPPED_TO, rows=mapped_rels)
            print(f"[MERGE] MAPPED_TO edges: {len(mapped_rels):,}")
        elif mapped_rels:
            print(f"[SKIP] MAPPED_TO: {len(mapped_rels)} pending (no CWE nodes yet)")
            print("       Chay lai sau khi ingest CWE data.")

    driver.close()
    print("\n[DONE]")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=None,
                        help="Path to enterprise-attack.json (optional, auto-download if absent)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    filepath = Path(args.file) if args.file else None
    bundle   = _load_stix(filepath)
    ttps, relations = parse_stix(bundle)
    ingest(ttps, relations, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
