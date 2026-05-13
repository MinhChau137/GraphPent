#!/usr/bin/env python3
"""
infer_gnn_edges.py — Score all (Service, Vulnerability) pairs with trained GNN
and write top-scoring HAS_VULN edges (source="gnn") to Neo4j.

Also writes gnn_embedding property to each node in Neo4j so gnn_service.py
can load embeddings for risk scoring.

Usage:
    python scripts/infer_gnn_edges.py
    python scripts/infer_gnn_edges.py --data data/gnn --model models/gnn_link_predictor.pt
    python scripts/infer_gnn_edges.py --top 500 --min-score 0.55 --dry-run
"""

import argparse
import json
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

TARGET_SRC = "Service"
TARGET_DST = "Vulnerability"
TARGET_REL = "HAS_VULN"


# ── Score pairs ───────────────────────────────────────────────────────────────

def _dot_sigmoid(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, dot))))


def score_pairs(embeddings: dict, svc_ids: list[str], vuln_ids: list[str],
                existing_pairs: set, top_k: int, min_score: float) -> list[dict]:
    """Score all (svc, vuln) pairs not already in existing_pairs."""
    candidates = []
    for svc_id in svc_ids:
        if svc_id not in embeddings:
            continue
        h_s = embeddings[svc_id]
        for vuln_id in vuln_ids:
            if (svc_id, vuln_id) in existing_pairs:
                continue
            if vuln_id not in embeddings:
                continue
            score = _dot_sigmoid(h_s, embeddings[vuln_id])
            if score >= min_score:
                candidates.append({"src": svc_id, "dst": vuln_id, "score": score})

    candidates.sort(key=lambda x: -x["score"])
    return candidates[:top_k]


def _try_torch_score(data_dir: Path, model_path: Path, nodes, edges, node_index,
                     svc_ids, vuln_ids, existing_pairs, top_k, min_score) -> list[dict] | None:
    try:
        import torch
    except ImportError:
        return None

    if not model_path.exists():
        print(f"[WARN] Model not found: {model_path} — using embeddings.json")
        return None

    # We need the same model architecture from training
    # Re-derive relation types from edges
    rel_types = list({e["rel_type"] for e in edges})
    rel_map   = {r: i for i, r in enumerate(rel_types)}
    n_rels    = len(rel_types)
    n_nodes   = len(nodes)
    feat_dim  = 10
    idx_to_id = {v: k for k, v in node_index.items()}
    node_map  = {n["id"]: n for n in nodes}

    feat_rows = [node_map[idx_to_id[i]]["features"] for i in range(n_nodes)]
    X = torch.tensor(feat_rows, dtype=torch.float32)

    adj_src = [[] for _ in range(n_rels)]
    adj_dst = [[] for _ in range(n_rels)]
    for e in edges:
        r = rel_map[e["rel_type"]]
        adj_src[r].append(e["src_idx"])
        adj_dst[r].append(e["dst_idx"])

    adjs = []
    for r in range(n_rels):
        if not adj_src[r]:
            adjs.append((None, None, None))
            continue
        src_t = torch.tensor(adj_src[r], dtype=torch.long)
        dst_t = torch.tensor(adj_dst[r], dtype=torch.long)
        deg   = torch.zeros(n_nodes)
        deg.scatter_add_(0, dst_t, torch.ones(len(dst_t)))
        deg_inv = 1.0 / (deg + 1e-8)
        adjs.append((src_t, dst_t, deg_inv))

    # Load checkpoint to infer hidden dim
    state = torch.load(model_path, map_location="cpu")
    # Detect hidden from first W0 weight shape
    hidden = None
    for k, v in state.items():
        if "W0" in k and "weight" in k:
            hidden = v.shape[0]
            break
    if hidden is None:
        print("[WARN] Could not detect hidden dim from checkpoint")
        return None

    import torch.nn as nn
    import torch.nn.functional as F

    class RGCN(nn.Module):
        def __init__(self):
            super().__init__()
            self.W0 = nn.ModuleList([nn.Linear(feat_dim, hidden, bias=False) for _ in range(n_rels)])
            self.W1 = nn.ModuleList([nn.Linear(hidden, hidden, bias=False) for _ in range(n_rels)])
            self.W0_self = nn.Linear(feat_dim, hidden, bias=False)
            self.W1_self = nn.Linear(hidden, hidden, bias=False)

        def forward(self, x):
            h = self.W0_self(x)
            for r, (src_t, dst_t, deg_inv) in enumerate(adjs):
                if src_t is None:
                    continue
                msg = self.W0[r](x[src_t])
                agg = torch.zeros(n_nodes, hidden)
                agg.scatter_add_(0, dst_t.unsqueeze(1).expand_as(msg), msg)
                h = h + agg * deg_inv.unsqueeze(1)
            h = F.relu(h)
            h2 = self.W1_self(h)
            for r, (src_t, dst_t, deg_inv) in enumerate(adjs):
                if src_t is None:
                    continue
                msg = self.W1[r](h[src_t])
                agg = torch.zeros(n_nodes, hidden)
                agg.scatter_add_(0, dst_t.unsqueeze(1).expand_as(msg), msg)
                h2 = h2 + agg * deg_inv.unsqueeze(1)
            return F.relu(h2)

    model = RGCN()
    model.load_state_dict(state)
    model.eval()

    with torch.no_grad():
        H = model(X)

    emb_dict = {idx_to_id[i]: H[i].tolist() for i in range(n_nodes)}
    print(f"[GNN] Scored {n_nodes:,} nodes with PyTorch model (hidden={hidden})")
    return emb_dict, score_pairs(emb_dict, svc_ids, vuln_ids, existing_pairs, top_k, min_score)


# ── Neo4j writer ──────────────────────────────────────────────────────────────

_MERGE_GNN_VULN = """
UNWIND $rows AS row
MATCH (s:Service {id: row.src})
MATCH (v:Vulnerability {id: row.dst})
MERGE (s)-[r:HAS_VULN]->(v)
ON CREATE SET r.confidence = row.score,
              r.source     = 'gnn',
              r.created_at = datetime()
ON MATCH SET  r.gnn_score  = row.score,
              r.source     = CASE WHEN r.source IS NULL THEN 'gnn' ELSE r.source END
"""

_SET_EMBEDDING = """
UNWIND $rows AS row
MATCH (n {id: row.id})
SET n.gnn_embedding = row.emb
"""


def write_to_neo4j(new_edges: list[dict], embeddings: dict, dry_run: bool):
    if dry_run:
        print(f"\n[DRY RUN] Would write {len(new_edges)} HAS_VULN edges to Neo4j")
        for e in new_edges[:10]:
            print(f"  {e['src']} → {e['dst']}  score={e['score']:.4f}")
        if len(new_edges) > 10:
            print(f"  ... and {len(new_edges)-10} more")
        print(f"[DRY RUN] Would set gnn_embedding on {len(embeddings):,} nodes")
        return

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERR] pip install neo4j")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print(f"[OK] Connected: {NEO4J_URI}")

    with driver.session() as s:
        # Write GNN-predicted HAS_VULN edges
        if new_edges:
            BATCH = 200
            ok = 0
            for i in range(0, len(new_edges), BATCH):
                batch = new_edges[i:i+BATCH]
                s.run(_MERGE_GNN_VULN, rows=batch)
                ok += len(batch)
            print(f"[MERGE] GNN HAS_VULN edges: {ok:,}")

        # Write embeddings (batch — embeddings can be large)
        emb_rows = [{"id": nid, "emb": emb} for nid, emb in embeddings.items()]
        BATCH = 100
        for i in range(0, len(emb_rows), BATCH):
            s.run(_SET_EMBEDDING, rows=emb_rows[i:i+BATCH])
        print(f"[SET] gnn_embedding on {len(emb_rows):,} nodes")

    driver.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def infer(data_dir: Path, model_path: Path, top_k: int, min_score: float, dry_run: bool):
    print(f"[LOAD] {data_dir}/")
    nodes      = json.loads((data_dir / "nodes.json").read_text(encoding="utf-8"))
    edges      = json.loads((data_dir / "edges.json").read_text(encoding="utf-8"))
    node_index = json.loads((data_dir / "node_index.json").read_text(encoding="utf-8"))

    svc_ids   = [n["id"] for n in nodes if n["type"] == TARGET_SRC]
    vuln_ids  = [n["id"] for n in nodes if n["type"] == TARGET_DST]
    existing  = {(e["src"], e["dst"]) for e in edges if e["rel_type"] == TARGET_REL}
    print(f"  Service: {len(svc_ids):,}  Vulnerability: {len(vuln_ids):,}")
    print(f"  Existing HAS_VULN: {len(existing):,}")

    # Try loading from PyTorch model
    embeddings = None
    new_edges  = None
    torch_result = _try_torch_score(data_dir, model_path, nodes, edges, node_index,
                                    svc_ids, vuln_ids, existing, top_k, min_score)
    if torch_result is not None and isinstance(torch_result, tuple):
        embeddings, new_edges = torch_result
    else:
        # Fall back to pre-computed embeddings.json
        emb_path = data_dir / "embeddings.json"
        if not emb_path.exists():
            print(f"[ERR] No embeddings found at {emb_path}")
            print("      Chay train_gnn_link_predictor.py truoc.")
            sys.exit(1)
        embeddings = json.loads(emb_path.read_text(encoding="utf-8"))
        print(f"[LOAD] Embeddings from {emb_path} ({len(embeddings):,} nodes)")
        new_edges = score_pairs(embeddings, svc_ids, vuln_ids, existing, top_k, min_score)

    print(f"\n[SCORE] {len(new_edges):,} new edges above threshold {min_score}")
    if new_edges:
        top5 = new_edges[:5]
        print("  Top 5 predicted edges:")
        for e in top5:
            print(f"    {e['src'][:30]} → {e['dst'][:20]}  score={e['score']:.4f}")

    write_to_neo4j(new_edges, embeddings, dry_run)

    if not dry_run:
        print(f"\n[DONE] Graph updated. gnn_service.py will now use GNN embeddings.")
    else:
        print(f"\n[DONE] (dry run)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",      default="data/gnn")
    parser.add_argument("--model",     default="models/gnn_link_predictor.pt")
    parser.add_argument("--top",       type=int,   default=1000,
                        help="Max new HAS_VULN edges to create")
    parser.add_argument("--min-score", type=float, default=0.55,
                        help="Minimum sigmoid score to create edge")
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args()

    infer(
        data_dir  = Path(args.data),
        model_path= Path(args.model),
        top_k     = args.top,
        min_score = args.min_score,
        dry_run   = args.dry_run,
    )


if __name__ == "__main__":
    main()
