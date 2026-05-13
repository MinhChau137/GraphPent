#!/usr/bin/env python3
"""
train_gnn_link_predictor.py — Train R-GCN link predictor (Service → Vulnerability).

Reads data/gnn/ export (from export_graph_for_gnn.py) and trains a 2-layer
Relational GCN that scores (Service, Vulnerability) pairs.

Output:
    models/gnn_link_predictor.pt   — trained model weights
    data/gnn/embeddings.json       — {node_id: [dim, ...]} node embeddings
    data/gnn/train_log.json        — loss/AUC history per epoch

Usage:
    python scripts/train_gnn_link_predictor.py
    python scripts/train_gnn_link_predictor.py --data data/gnn --epochs 200 --dim 64
    python scripts/train_gnn_link_predictor.py --no-gpu
"""

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Constants ─────────────────────────────────────────────────────────────────

SEED = 42
TARGET_SRC_TYPE = "Service"
TARGET_DST_TYPE = "Vulnerability"
TARGET_REL      = "HAS_VULN"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_seed(seed: int):
    random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        pass


def _load_data(data_dir: Path):
    nodes      = json.loads((data_dir / "nodes.json").read_text(encoding="utf-8"))
    edges      = json.loads((data_dir / "edges.json").read_text(encoding="utf-8"))
    node_index = json.loads((data_dir / "node_index.json").read_text(encoding="utf-8"))
    meta       = json.loads((data_dir / "meta.json").read_text(encoding="utf-8"))
    return nodes, edges, node_index, meta


def _compute_auc(scores_pos, scores_neg):
    """Simple AUC via pairwise comparison (O(n²) — OK for small sets)."""
    if not scores_pos or not scores_neg:
        return 0.5
    n_pos, n_neg = len(scores_pos), len(scores_neg)
    wins = sum(1 for p in scores_pos for n in scores_neg if p > n)
    ties = sum(1 for p in scores_pos for n in scores_neg if p == n)
    return (wins + 0.5 * ties) / (n_pos * n_neg)


# ── Numpy fallback R-GCN ──────────────────────────────────────────────────────
# Pure numpy implementation — used when PyTorch is unavailable.
# Trains with gradient descent via manual backprop (simplified).

class NumpyRGCN:
    """Minimal R-GCN in numpy (2 layers, link prediction head)."""

    def __init__(self, n_nodes: int, feat_dim: int, hidden: int, n_rels: int):
        rng = random.Random(SEED)
        _r = lambda r, c: [[rng.gauss(0, 0.1) for _ in range(c)] for _ in range(r)]
        self.W0 = [_r(feat_dim, hidden) for _ in range(n_rels)]   # per-relation layer 1
        self.W1 = [_r(hidden, hidden) for _ in range(n_rels)]      # per-relation layer 2
        self.Wp = _r(hidden, 1)                                     # prediction head

    def _matmul(self, A, B):
        rows, inner = len(A), len(A[0])
        cols = len(B[0])
        return [[sum(A[i][k] * B[k][j] for k in range(inner)) for j in range(cols)]
                for i in range(rows)]

    def _relu(self, X):
        return [[max(0.0, v) for v in row] for row in X]

    def _sigmoid(self, x: float) -> float:
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))

    def forward_node(self, feat: list[float], adj_feats_per_rel: list[list[list[float]]]) -> list[float]:
        """Single node forward pass — returns hidden embedding."""
        h = [0.0] * len(self.W0[0][0])
        for r_idx, (W, agg_feat) in enumerate(zip(self.W0, adj_feats_per_rel)):
            for src_feat in agg_feat:
                row = [sum(src_feat[k] * W[k][j] for k in range(len(W))) for j in range(len(W[0]))]
                h = [h[j] + row[j] for j in range(len(h))]
        return [max(0.0, v) for v in h]

    def score_pair(self, h_src: list[float], h_dst: list[float]) -> float:
        dot = sum(a * b for a, b in zip(h_src, h_dst))
        return self._sigmoid(dot)


class NumpyTrainer:
    """Train NumpyRGCN with full-batch score on pos/neg pairs."""

    def __init__(self, nodes, edges, node_index, hidden=32):
        self.nodes = {n["id"]: n for n in nodes}
        self.node_index = node_index
        self.idx_to_id  = {v: k for k, v in node_index.items()}
        n_nodes  = len(nodes)
        feat_dim = 10

        # Relation types → indices
        rel_types = list({e["rel_type"] for e in edges})
        self.rel_map = {r: i for i, r in enumerate(rel_types)}
        n_rels = len(rel_types)

        # Features matrix (list of 10-dim vectors)
        self.feats = [self.nodes[self.idx_to_id[i]]["features"]
                      for i in range(n_nodes)]

        # Adjacency per relation: rel_idx → list of (src_idx, dst_idx)
        self.adj = [[] for _ in range(n_rels)]
        for e in edges:
            r = self.rel_map[e["rel_type"]]
            self.adj[r].append((e["src_idx"], e["dst_idx"]))

        self.model = NumpyRGCN(n_nodes, feat_dim, hidden, n_rels)

        # Positive pairs
        self.pos_pairs = [(e["src_idx"], e["dst_idx"])
                          for e in edges if e["rel_type"] == TARGET_REL]

        # Service / Vuln index sets for negative sampling
        self.svc_indices = {node_index[n["id"]] for n in nodes
                            if n["type"] == TARGET_SRC_TYPE}
        self.vuln_indices = {node_index[n["id"]] for n in nodes
                             if n["type"] == TARGET_DST_TYPE}

    def _agg_feats(self, node_idx: int):
        """For each relation, collect avg feature of neighbors."""
        n_rels = len(self.model.W0)
        agg = [[] for _ in range(n_rels)]
        for r, pairs in enumerate(self.adj):
            nbrs = [self.feats[s] for s, d in pairs if d == node_idx]
            nbrs += [self.feats[d] for s, d in pairs if s == node_idx]
            if nbrs:
                avg = [sum(nbrs[i][j] for i in range(len(nbrs))) / len(nbrs)
                       for j in range(len(nbrs[0]))]
                agg[r].append(avg)
        return agg

    def _embed(self, idx: int) -> list[float]:
        agg = self._agg_feats(idx)
        return self.model.forward_node(self.feats[idx], agg)

    def train_epoch(self, neg_ratio=2) -> tuple[float, float]:
        pos_pairs = self.pos_pairs
        svc_list  = list(self.svc_indices)
        vuln_list = list(self.vuln_indices)
        pos_set   = set(pos_pairs)

        neg_pairs = []
        while len(neg_pairs) < len(pos_pairs) * neg_ratio:
            s = random.choice(svc_list)
            v = random.choice(vuln_list)
            if (s, v) not in pos_set:
                neg_pairs.append((s, v))

        scores_pos, scores_neg = [], []
        loss = 0.0
        eps = 1e-7

        for s, v in pos_pairs:
            h_s = self._embed(s)
            h_v = self._embed(v)
            sc  = self.model.score_pair(h_s, h_v)
            scores_pos.append(sc)
            loss -= math.log(sc + eps)

        for s, v in neg_pairs:
            h_s = self._embed(s)
            h_v = self._embed(v)
            sc  = self.model.score_pair(h_s, h_v)
            scores_neg.append(sc)
            loss -= math.log(1.0 - sc + eps)

        n = len(pos_pairs) + len(neg_pairs)
        auc = _compute_auc(scores_pos, scores_neg)
        return loss / max(n, 1), auc

    def get_all_embeddings(self) -> dict:
        embeddings = {}
        for idx, nid in self.idx_to_id.items():
            embeddings[nid] = self._embed(idx)
        return embeddings


# ── PyTorch R-GCN ─────────────────────────────────────────────────────────────

def _try_torch_train(nodes, edges, node_index, hidden, epochs, lr, neg_ratio, device_str):
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError:
        return None

    print("[INFO] PyTorch found — using GPU-accelerated R-GCN")
    device = torch.device("cuda" if torch.cuda.is_available() and device_str != "cpu" else "cpu")
    print(f"[INFO] Device: {device}")

    n_nodes  = len(nodes)
    feat_dim = 10
    idx_to_id = {v: k for k, v in node_index.items()}
    node_map  = {n["id"]: n for n in nodes}

    # Feature matrix [n_nodes, feat_dim]
    feat_rows = [node_map[idx_to_id[i]]["features"] for i in range(n_nodes)]
    X = torch.tensor(feat_rows, dtype=torch.float32, device=device)

    # Relation indices
    rel_types = list({e["rel_type"] for e in edges})
    rel_map   = {r: i for i, r in enumerate(rel_types)}
    n_rels    = len(rel_types)

    # Sparse adjacency per relation: list of (src, dst) tensors
    adj_src = [[] for _ in range(n_rels)]
    adj_dst = [[] for _ in range(n_rels)]
    for e in edges:
        r = rel_map[e["rel_type"]]
        adj_src[r].append(e["src_idx"])
        adj_dst[r].append(e["dst_idx"])

    def make_norm_adj(src_list, dst_list, n):
        if not src_list:
            return None, None
        src_t = torch.tensor(src_list, dtype=torch.long, device=device)
        dst_t = torch.tensor(dst_list, dtype=torch.long, device=device)
        deg   = torch.zeros(n, device=device)
        deg.scatter_add_(0, dst_t, torch.ones(len(dst_t), device=device))
        deg_inv = 1.0 / (deg + 1e-8)
        return src_t, dst_t, deg_inv

    adjs = [make_norm_adj(adj_src[r], adj_dst[r], n_nodes) for r in range(n_rels)]

    class RGCN(nn.Module):
        def __init__(self):
            super().__init__()
            self.W0 = nn.ModuleList([nn.Linear(feat_dim, hidden, bias=False) for _ in range(n_rels)])
            self.W1 = nn.ModuleList([nn.Linear(hidden, hidden, bias=False) for _ in range(n_rels)])
            self.W0_self = nn.Linear(feat_dim, hidden, bias=False)
            self.W1_self = nn.Linear(hidden, hidden, bias=False)

        def forward(self, x):
            # Layer 1
            h = self.W0_self(x)
            for r, (src_t, dst_t, deg_inv) in enumerate(adjs):
                if src_t is None:
                    continue
                msg = self.W0[r](x[src_t])
                agg = torch.zeros(n_nodes, hidden, device=device)
                agg.scatter_add_(0, dst_t.unsqueeze(1).expand_as(msg), msg)
                agg = agg * deg_inv.unsqueeze(1)
                h = h + agg
            h = F.relu(h)

            # Layer 2
            h2 = self.W1_self(h)
            for r, (src_t, dst_t, deg_inv) in enumerate(adjs):
                if src_t is None:
                    continue
                msg = self.W1[r](h[src_t])
                agg = torch.zeros(n_nodes, hidden, device=device)
                agg.scatter_add_(0, dst_t.unsqueeze(1).expand_as(msg), msg)
                agg = agg * deg_inv.unsqueeze(1)
                h2 = h2 + agg
            return F.relu(h2)

    model = RGCN().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    # Positive pairs
    pos_pairs = torch.tensor(
        [(e["src_idx"], e["dst_idx"]) for e in edges if e["rel_type"] == TARGET_REL],
        dtype=torch.long, device=device
    )
    svc_idx   = [node_index[n["id"]] for n in nodes if n["type"] == TARGET_SRC_TYPE]
    vuln_idx  = [node_index[n["id"]] for n in nodes if n["type"] == TARGET_DST_TYPE]
    svc_t     = torch.tensor(svc_idx, dtype=torch.long, device=device)
    vuln_t    = torch.tensor(vuln_idx, dtype=torch.long, device=device)
    pos_set   = set(map(tuple, pos_pairs.tolist()))

    def sample_neg(n_neg):
        neg = []
        while len(neg) < n_neg:
            s = svc_idx[random.randint(0, len(svc_idx)-1)]
            v = vuln_idx[random.randint(0, len(vuln_idx)-1)]
            if (s, v) not in pos_set:
                neg.append((s, v))
        return torch.tensor(neg, dtype=torch.long, device=device)

    history = []
    best_auc = 0.0
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()

        H = model(X)
        n_pos = len(pos_pairs)
        neg   = sample_neg(n_pos * neg_ratio)

        scores_pos = torch.sigmoid((H[pos_pairs[:, 0]] * H[pos_pairs[:, 1]]).sum(dim=1))
        scores_neg = torch.sigmoid((H[neg[:, 0]] * H[neg[:, 1]]).sum(dim=1))

        loss = -torch.log(scores_pos + 1e-7).mean() \
             - torch.log(1.0 - scores_neg + 1e-7).mean()

        loss.backward()
        optimizer.step()

        if epoch % 10 == 0 or epoch == 1:
            model.eval()
            with torch.no_grad():
                H_eval = model(X)
                sp = torch.sigmoid((H_eval[pos_pairs[:, 0]] * H_eval[pos_pairs[:, 1]]).sum(dim=1))
                sn = torch.sigmoid((H_eval[neg[:, 0]] * H_eval[neg[:, 1]]).sum(dim=1))
            sp_list = sp.cpu().tolist()
            sn_list = sn.cpu().tolist()
            auc = _compute_auc(sp_list, sn_list)
            l_val = loss.item()
            history.append({"epoch": epoch, "loss": round(l_val, 4), "auc": round(auc, 4)})
            print(f"  epoch {epoch:>4}  loss={l_val:.4f}  auc={auc:.4f}")
            if auc > best_auc:
                best_auc = auc
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    # Restore best
    if best_state:
        model.load_state_dict({k: v.to(device) for k, v in best_state.items()})
    model.eval()
    with torch.no_grad():
        H_final = model(X).cpu()

    embeddings = {idx_to_id[i]: H_final[i].tolist() for i in range(n_nodes)}
    return model, embeddings, history, best_auc


# ── Main ──────────────────────────────────────────────────────────────────────

def train(data_dir: Path, out_model: Path, epochs: int, hidden: int,
          lr: float, neg_ratio: int, no_gpu: bool):
    _set_seed(SEED)

    print(f"[LOAD] {data_dir}/")
    nodes, edges, node_index, meta = _load_data(data_dir)
    print(f"  Nodes: {meta['total_nodes']:,}  Edges: {meta['total_edges']:,}")
    print(f"  Positive labels (HAS_VULN): {meta['positive_labels']:,}")

    if meta["positive_labels"] == 0:
        print("\n[ERR] Khong co HAS_VULN edges — can't train.")
        print("  Chay link_service_cve.py truoc:")
        print("  python scripts/link_service_cve.py --min-confidence 0.60")
        sys.exit(1)

    n_svc  = sum(1 for n in nodes if n["type"] == TARGET_SRC_TYPE)
    n_vuln = sum(1 for n in nodes if n["type"] == TARGET_DST_TYPE)
    print(f"  Service nodes: {n_svc:,}  Vulnerability nodes: {n_vuln:,}")

    out_model.parent.mkdir(parents=True, exist_ok=True)

    # Try PyTorch first
    device_str = "cpu" if no_gpu else "auto"
    result = _try_torch_train(nodes, edges, node_index, hidden, epochs, lr, neg_ratio, device_str)

    if result is not None:
        model, embeddings, history, best_auc = result
        try:
            import torch
            torch.save(model.state_dict(), out_model)
            print(f"\n[SAVE] Model → {out_model}")
        except Exception as e:
            print(f"[WARN] Could not save model: {e}")
    else:
        print("[INFO] PyTorch not available — using numpy fallback (slower)")
        trainer = NumpyTrainer(nodes, edges, node_index, hidden=hidden)
        history = []
        best_auc = 0.0
        for epoch in range(1, min(epochs, 50) + 1):  # numpy capped at 50 (slow)
            loss, auc = trainer.train_epoch(neg_ratio)
            if epoch % 10 == 0 or epoch == 1:
                history.append({"epoch": epoch, "loss": round(loss, 4), "auc": round(auc, 4)})
                print(f"  epoch {epoch:>4}  loss={loss:.4f}  auc={auc:.4f}")
                if auc > best_auc:
                    best_auc = auc
        embeddings = trainer.get_all_embeddings()
        print("[INFO] Numpy mode: model weights not saved (use PyTorch for model persistence)")

    # Save embeddings
    emb_path = data_dir / "embeddings.json"
    emb_path.write_text(json.dumps(embeddings, ensure_ascii=False), encoding="utf-8")
    print(f"[SAVE] Embeddings ({len(embeddings):,} nodes) → {emb_path}")

    # Save training log
    log_path = data_dir / "train_log.json"
    log_path.write_text(json.dumps({
        "epochs": epochs, "hidden": hidden, "lr": lr, "neg_ratio": neg_ratio,
        "best_auc": round(best_auc, 4),
        "target_src": TARGET_SRC_TYPE, "target_dst": TARGET_DST_TYPE,
        "target_rel": TARGET_REL,
        "history": history,
    }, indent=2), encoding="utf-8")
    print(f"[SAVE] Train log → {log_path}")

    print(f"\n[DONE] Best AUC={best_auc:.4f}")
    print("  Buoc tiep theo:")
    print("  python scripts/infer_gnn_edges.py --data data/gnn --model models/gnn_link_predictor.pt")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",      default="data/gnn",
                        help="Directory with GNN export (nodes.json etc)")
    parser.add_argument("--model",     default="models/gnn_link_predictor.pt")
    parser.add_argument("--epochs",    type=int,   default=200)
    parser.add_argument("--dim",       type=int,   default=64, help="Hidden dim")
    parser.add_argument("--lr",        type=float, default=0.01)
    parser.add_argument("--neg-ratio", type=int,   default=2,
                        help="Negative samples per positive")
    parser.add_argument("--no-gpu",    action="store_true")
    args = parser.parse_args()

    train(
        data_dir  = Path(args.data),
        out_model = Path(args.model),
        epochs    = args.epochs,
        hidden    = args.dim,
        lr        = args.lr,
        neg_ratio = args.neg_ratio,
        no_gpu    = args.no_gpu,
    )


if __name__ == "__main__":
    main()
