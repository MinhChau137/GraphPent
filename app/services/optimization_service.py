"""Optimization Service - Parameter tuning & benchmarking for Phases 10-13."""

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.adapters.neo4j_client import Neo4jAdapter
from app.config.settings import settings
from app.core.logger import logger
from app.core.security import audit_log
from app.services.gnn_service import GNNService
from app.services.kg_completion_service import KGCompletionService
from app.services.retriever_service import HybridRetrieverService

# ── Redis key for persisting results ───────────────────────────────────────
_RESULTS_KEY = "optimization:last_results"
_TESTSET_KEY = "optimization:test_set"


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _get_redis():
    try:
        import redis as _redis
        return _redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        return None


def _save_to_redis(key: str, data: Any, ttl: int = 86400) -> None:
    r = _get_redis()
    if r:
        try:
            r.set(key, json.dumps(data, default=str), ex=ttl)
        except Exception:
            pass


def _load_from_redis(key: str) -> Optional[Any]:
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _precision_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """Precision@k: fraction of top-k results that are relevant."""
    if not relevant_ids or k == 0:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & set(relevant_ids)) / k


def _spearman(ranking_a: List[str], ranking_b: List[str]) -> float:
    """Spearman rank correlation between two orderings of the same ids."""
    n = len(ranking_a)
    if n == 0:
        return 0.0
    rank_a = {v: i for i, v in enumerate(ranking_a)}
    rank_b = {v: i for i, v in enumerate(ranking_b)}
    ids = set(ranking_a) & set(ranking_b)
    if not ids:
        return 0.0
    d_sq = sum((rank_a[i] - rank_b[i]) ** 2 for i in ids)
    n_common = len(ids)
    return 1 - (6 * d_sq) / (n_common * (n_common ** 2 - 1)) if n_common > 1 else 0.0


# ══════════════════════════════════════════════════════════════════════════════
# OptimizationService
# ══════════════════════════════════════════════════════════════════════════════

class OptimizationService:
    """
    Central benchmark engine.  Three independent experiments can be run
    individually or together via run_all():

      1. benchmark_alpha()     — find best RRF alpha
      2. benchmark_gnn_weights() — find best GNN weight combination
      3. benchmark_kg_completion() — measure KG completion precision/recall

    Each experiment generates a test set from existing graph data
    (no external labeled data required) and stores results in Redis.
    """

    def __init__(self):
        self.neo4j = Neo4jAdapter()
        self.retriever = HybridRetrieverService()
        self.gnn = GNNService()
        self.kg = KGCompletionService()

    # ──────────────────────────────────────────────────────── Test-set builder

    async def generate_test_set(self, n_queries: int = 30, holdout_n: int = 20) -> Dict:
        """
        Build a synthetic evaluation dataset from existing graph data.

        Two outputs:
          retrieval_queries  — [{query, relevant_ids}]  for alpha benchmark
          holdout_relations  — [{source_id, target_id, rel_type}]  for KG benchmark

        Everything is persisted in Redis so other benchmarks can reuse it.
        """
        logger.info("Generating test set", n_queries=n_queries, holdout_n=holdout_n)

        retrieval_queries = await self._build_retrieval_queries(n_queries)
        holdout_relations = await self._sample_holdout_relations(holdout_n)

        test_set = {
            "generated_at": datetime.utcnow().isoformat(),
            "retrieval_queries": retrieval_queries,
            "holdout_relations": holdout_relations,
        }
        _save_to_redis(_TESTSET_KEY, test_set)

        logger.info("Test set saved", queries=len(retrieval_queries), holdout=len(holdout_relations))
        await audit_log("generate_test_set", {
            "queries": len(retrieval_queries),
            "holdout": len(holdout_relations),
        })
        return {
            "retrieval_queries": len(retrieval_queries),
            "holdout_relations": len(holdout_relations),
            "persisted": True,
        }

    # ──────────────────────────────────────────────────────── Alpha benchmark

    async def benchmark_alpha(
        self,
        alpha_range: Optional[List[float]] = None,
        k: int = 5,
        test_queries: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Try each alpha value in alpha_range, measure Precision@k.

        Args:
            alpha_range : list of floats to try, default [0.0,0.2,0.4,0.6,0.7,0.8,1.0]
            k           : Precision@k cutoff
            test_queries: list of {query, relevant_ids}. If None, loads from Redis or auto-generates.

        Returns dict with per-alpha results + recommended_alpha.
        """
        if alpha_range is None:
            alpha_range = [0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 1.0]

        if test_queries is None:
            cached = _load_from_redis(_TESTSET_KEY)
            test_queries = (cached or {}).get("retrieval_queries") or []
        if not test_queries:
            auto = await self._build_retrieval_queries(20)
            test_queries = auto

        logger.info("Benchmarking alpha", alphas=alpha_range, queries=len(test_queries))

        rows: List[Dict] = []
        for alpha in alpha_range:
            precisions = []
            latencies = []
            for tq in test_queries:
                query = tq["query"]
                relevant = tq["relevant_ids"]
                t0 = time.perf_counter()
                try:
                    results = await self.retriever.hybrid_retrieve(
                        query=query, alpha=alpha, limit=k * 2, use_cache=False
                    )
                    retrieved_ids = [r["id"] for r in results]
                    p = _precision_at_k(retrieved_ids, relevant, k)
                except Exception as exc:
                    logger.warning(f"Alpha {alpha} query failed: {exc}")
                    p = 0.0
                    retrieved_ids = []
                elapsed = (time.perf_counter() - t0) * 1000
                precisions.append(p)
                latencies.append(elapsed)

            avg_p = sum(precisions) / len(precisions) if precisions else 0.0
            avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
            rows.append({
                "alpha": alpha,
                f"precision_at_{k}": round(avg_p, 4),
                "avg_latency_ms": round(avg_lat, 1),
            })
            logger.info(f"  alpha={alpha}  P@{k}={avg_p:.4f}  lat={avg_lat:.1f}ms")

        best = max(rows, key=lambda r: r[f"precision_at_{k}"])
        result = {
            "experiment": "alpha_benchmark",
            "metric": f"precision_at_{k}",
            "k": k,
            "rows": rows,
            "recommended_alpha": best["alpha"],
            "best_score": best[f"precision_at_{k}"],
            "current_alpha": getattr(settings, "RRF_ALPHA", 0.7),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._persist_result("alpha", result)
        await audit_log("benchmark_alpha", {"recommended": best["alpha"], "score": best[f"precision_at_{k}"]})
        return result

    # ──────────────────────────────────────────────── GNN weights benchmark

    async def benchmark_gnn_weights(
        self,
        scenarios: Optional[List[Dict]] = None,
        ground_truth_ids: Optional[List[str]] = None,
    ) -> Dict:
        """
        Try different GNN weight combinations, measure Spearman rank correlation
        against a ground-truth ordering (severity-based proxy if none provided).

        Each scenario: {"name": str, "w_pr": float, "w_sev": float, "w_bc": float}
        """
        if scenarios is None:
            scenarios = [
                {"name": "severity_first",  "w_pr": 0.20, "w_sev": 0.60, "w_bc": 0.20},
                {"name": "topology_first",  "w_pr": 0.50, "w_sev": 0.20, "w_bc": 0.30},
                {"name": "balanced",        "w_pr": 0.50, "w_sev": 0.30, "w_bc": 0.20},
                {"name": "pagerank_heavy",  "w_pr": 0.70, "w_sev": 0.20, "w_bc": 0.10},
            ]

        logger.info("Benchmarking GNN weights", scenarios=len(scenarios))

        # Ground truth: severity-based ordering (critical→high→medium→low)
        gt_order = await self._severity_ground_truth(limit=50)
        gt_ids = [n["id"] for n in gt_order]

        rows: List[Dict] = []
        for sc in scenarios:
            name = sc["name"]
            w_pr, w_sev, w_bc = sc["w_pr"], sc["w_sev"], sc["w_bc"]

            # Temporarily write blended scores with these weights
            scored = await self._compute_temp_scores(gt_ids, w_pr, w_sev, w_bc)
            scored.sort(key=lambda x: x["score"], reverse=True)
            scored_ids = [x["id"] for x in scored]

            rho = _spearman(scored_ids, gt_ids)
            rows.append({
                "scenario": name,
                "w_pr": w_pr, "w_sev": w_sev, "w_bc": w_bc,
                "spearman_rho": round(rho, 4),
            })
            logger.info(f"  {name}: rho={rho:.4f}")

        best = max(rows, key=lambda r: r["spearman_rho"])
        result = {
            "experiment": "gnn_weights_benchmark",
            "metric": "spearman_rank_correlation",
            "rows": rows,
            "recommended": {
                "scenario": best["scenario"],
                "w_pr": best["w_pr"],
                "w_sev": best["w_sev"],
                "w_bc": best["w_bc"],
            },
            "best_spearman": best["spearman_rho"],
            "current_weights": {
                "w_pr": getattr(settings, "GNN_W_PAGERANK", 0.50),
                "w_sev": getattr(settings, "GNN_W_SEVERITY", 0.30),
                "w_bc": getattr(settings, "GNN_W_BETWEENNESS", 0.20),
            },
            "note": "Ground truth = severity-based ordering (critical>high>medium>low)",
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._persist_result("gnn_weights", result)
        await audit_log("benchmark_gnn_weights", {"recommended_scenario": best["scenario"]})
        return result

    # ─────────────────────────────────────────── KG completion benchmark

    async def benchmark_kg_completion(
        self,
        holdout_relations: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Measure KG completion precision/recall by trying to predict
        a held-out set of known relations.

        If holdout_relations is None, loads from Redis test set or auto-samples.
        Each holdout item: {source_id, target_id, rel_type}
        """
        if holdout_relations is None:
            cached = _load_from_redis(_TESTSET_KEY)
            holdout_relations = (cached or {}).get("holdout_relations") or []
        if not holdout_relations:
            holdout_relations = await self._sample_holdout_relations(20)

        logger.info("Benchmarking KG completion", holdout_n=len(holdout_relations))

        # Get entity pool
        candidate_pool = await self.neo4j.get_entity_sample_for_completion(limit=60)
        true_positives = 0
        false_positives = 0
        false_negatives = 0

        # For each held-out relation, ask KG service to predict it
        for hr in holdout_relations[:20]:
            source_id = hr.get("source_id", "")
            target_id = hr.get("target_id", "")
            expected_rel = str(hr.get("rel_type", "")).upper()

            # Build entity row for source
            entity_row = await self._get_entity_row(source_id)
            if not entity_row:
                false_negatives += 1
                continue

            # Run prediction
            try:
                preds = await self.kg._predict_relations(entity_row, candidate_pool)
                predicted_targets = {p["target_id"] for p in preds}
                predicted_for_target = [p for p in preds if p["target_id"] == target_id]

                if target_id in predicted_targets:
                    true_positives += 1
                else:
                    false_negatives += 1

                # False positives: predictions not in holdout
                for p in preds:
                    if p["target_id"] != target_id:
                        false_positives += 0.1  # partial credit (simplified)
            except Exception as exc:
                logger.warning(f"KG prediction error for {source_id}: {exc}")
                false_negatives += 1

        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        result = {
            "experiment": "kg_completion_benchmark",
            "holdout_size": len(holdout_relations),
            "true_positives": true_positives,
            "false_negatives": false_negatives,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "current_min_confidence": getattr(settings, "KG_MIN_CONFIDENCE", 0.65),
            "interpretation": self._interpret_kg_result(precision, recall),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._persist_result("kg_completion", result)
        await audit_log("benchmark_kg_completion", {"precision": precision, "recall": recall, "f1": f1})
        return result

    # ─────────────────────────────────────────────────── Run all

    async def run_all(self) -> Dict:
        """Generate test set, then run all three benchmarks sequentially."""
        logger.info("Running full optimization benchmark suite")
        t0 = time.perf_counter()

        ts_result = await self.generate_test_set()
        alpha_result = await self.benchmark_alpha()
        gnn_result = await self.benchmark_gnn_weights()
        kg_result = await self.benchmark_kg_completion()

        elapsed = round((time.perf_counter() - t0), 1)
        summary = {
            "run_at": datetime.utcnow().isoformat(),
            "elapsed_seconds": elapsed,
            "test_set": ts_result,
            "alpha": {
                "recommended": alpha_result["recommended_alpha"],
                "score": alpha_result["best_score"],
            },
            "gnn_weights": {
                "recommended_scenario": gnn_result["recommended"]["scenario"],
                "w_pr": gnn_result["recommended"]["w_pr"],
                "w_sev": gnn_result["recommended"]["w_sev"],
                "w_bc": gnn_result["recommended"]["w_bc"],
                "spearman": gnn_result["best_spearman"],
            },
            "kg_completion": {
                "precision": kg_result["precision"],
                "recall": kg_result["recall"],
                "f1": kg_result["f1"],
            },
            "action_items": self._build_action_items(alpha_result, gnn_result, kg_result),
        }
        _save_to_redis(_RESULTS_KEY, summary)
        await audit_log("run_all_benchmarks", {"elapsed": elapsed})
        return summary

    def get_last_results(self) -> Optional[Dict]:
        return _load_from_redis(_RESULTS_KEY)

    # ─────────────────────────────────────── Private helpers

    async def _build_retrieval_queries(self, n: int) -> List[Dict]:
        """Generate {query, relevant_ids} pairs from entity names in graph."""
        try:
            async with self.neo4j.driver.session() as session:
                cypher = """
                MATCH (n)
                WHERE n.name IS NOT NULL AND size(n.name) > 3
                      AND NOT n:DiscoveredVulnerability
                RETURN n.id AS id, n.name AS name, labels(n)[0] AS label
                ORDER BY rand()
                LIMIT $n
                """
                result = await session.run(cypher, n=n)
                records = await result.fetch(n)

            queries = []
            for r in records:
                entity_id = r["id"]
                name = r["name"]
                # Query = entity name; relevant = [entity_id] + neighbors
                neighbors = await self.neo4j.get_entity_neighbors(entity_id, hops=1)
                relevant_ids = [entity_id] + [nb["id"] for nb in neighbors[:3]]
                queries.append({"query": name, "relevant_ids": relevant_ids})
            return queries
        except Exception as exc:
            logger.warning("Could not build retrieval queries", error=str(exc))
            return []

    async def _sample_holdout_relations(self, n: int) -> List[Dict]:
        """Sample n existing relations to use as held-out test cases."""
        try:
            async with self.neo4j.driver.session() as session:
                cypher = """
                MATCH (s)-[r]->(t)
                WHERE s.id IS NOT NULL AND t.id IS NOT NULL
                      AND NOT r.inferred
                RETURN s.id AS source_id, t.id AS target_id, type(r) AS rel_type
                ORDER BY rand()
                LIMIT $n
                """
                result = await session.run(cypher, n=n)
                records = await result.fetch(n)
            return [dict(r) for r in records]
        except Exception as exc:
            logger.warning("Could not sample holdout relations", error=str(exc))
            return []

    async def _severity_ground_truth(self, limit: int) -> List[Dict]:
        """Return entities ordered by severity as proxy ground truth for GNN."""
        try:
            async with self.neo4j.driver.session() as session:
                cypher = """
                MATCH (n)
                WHERE n.severity IS NOT NULL OR n.cvss_score IS NOT NULL
                RETURN n.id AS id,
                       coalesce(n.severity, 'unknown') AS severity,
                       coalesce(n.cvss_score, 0.0) AS cvss
                ORDER BY
                  CASE n.severity
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                    WHEN 'medium'   THEN 2 WHEN 'low'  THEN 3 ELSE 4
                  END, n.cvss_score DESC
                LIMIT $limit
                """
                result = await session.run(cypher, limit=limit)
                records = await result.fetch(limit)
            return [dict(r) for r in records]
        except Exception as exc:
            logger.warning("Could not build severity ground truth", error=str(exc))
            return []

    async def _compute_temp_scores(
        self, ids: List[str], w_pr: float, w_sev: float, w_bc: float
    ) -> List[Dict]:
        """Compute blended scores for a set of node IDs without writing to graph."""
        try:
            async with self.neo4j.driver.session() as session:
                cypher = """
                UNWIND $ids AS nid
                MATCH (n {id: nid})
                RETURN n.id AS id,
                       coalesce(n.pagerank_score, 0.0) AS pr,
                       coalesce(n.betweenness_score, 0.0) AS bc,
                       CASE coalesce(n.severity, 'unknown')
                         WHEN 'critical' THEN 1.0 WHEN 'high' THEN 0.75
                         WHEN 'medium'   THEN 0.50 WHEN 'low'  THEN 0.25
                         ELSE 0.10
                       END AS sev
                """
                result = await session.run(cypher, ids=ids)
                records = await result.fetch(len(ids))

            scored = []
            for r in records:
                s = w_pr * r["pr"] + w_sev * r["sev"] + w_bc * r["bc"]
                scored.append({"id": r["id"], "score": s})
            return scored
        except Exception as exc:
            logger.warning("Temp score computation failed", error=str(exc))
            return []

    async def _get_entity_row(self, entity_id: str) -> Optional[Dict]:
        try:
            async with self.neo4j.driver.session() as session:
                cypher = "MATCH (n {id: $id}) RETURN n.id AS id, labels(n) AS labels, properties(n) AS props LIMIT 1"
                result = await session.run(cypher, id=entity_id)
                record = await result.single()
                return dict(record) if record else None
        except Exception:
            return None

    @staticmethod
    def _interpret_kg_result(precision: float, recall: float) -> str:
        if precision >= 0.7 and recall >= 0.5:
            return "Good — KG completion is reliable. Keep KG_MIN_CONFIDENCE as-is."
        if precision < 0.5:
            return "Too many false positives — raise KG_MIN_CONFIDENCE (try 0.70-0.75)."
        if recall < 0.3:
            return "Too many misses — lower KG_MIN_CONFIDENCE (try 0.55-0.60) or raise KG_MAX_DEGREE."
        return "Acceptable — minor tuning may help. Check individual predictions."

    @staticmethod
    def _build_action_items(alpha_res: Dict, gnn_res: Dict, kg_res: Dict) -> List[str]:
        actions = []
        cur_alpha = getattr(settings, "RRF_ALPHA", 0.7)
        rec_alpha = alpha_res.get("recommended_alpha", cur_alpha)
        if abs(rec_alpha - cur_alpha) >= 0.1:
            actions.append(
                f"Set RRF_ALPHA={rec_alpha} in .env "
                f"(current={cur_alpha}, score gain: {alpha_res.get('best_score', 0):.3f})"
            )

        rec = gnn_res.get("recommended", {})
        cur_w = (
            getattr(settings, "GNN_W_PAGERANK", 0.5),
            getattr(settings, "GNN_W_SEVERITY", 0.3),
            getattr(settings, "GNN_W_BETWEENNESS", 0.2),
        )
        new_w = (rec.get("w_pr"), rec.get("w_sev"), rec.get("w_bc"))
        if new_w != cur_w and gnn_res.get("best_spearman", 0) > 0.3:
            actions.append(
                f"Set GNN_W_PAGERANK={new_w[0]}, GNN_W_SEVERITY={new_w[1]}, "
                f"GNN_W_BETWEENNESS={new_w[2]} (scenario: {rec.get('scenario')})"
            )

        kg_interp = kg_res.get("interpretation", "")
        if "raise" in kg_interp.lower():
            actions.append("Raise KG_MIN_CONFIDENCE (e.g. to 0.72) — too many false positives.")
        elif "lower" in kg_interp.lower():
            actions.append("Lower KG_MIN_CONFIDENCE (e.g. to 0.58) — missing too many relations.")

        if not actions:
            actions.append("Current parameters are near-optimal. No immediate changes needed.")
        return actions

    def _persist_result(self, key: str, data: Dict) -> None:
        existing = _load_from_redis(_RESULTS_KEY) or {}
        existing[key] = data
        _save_to_redis(_RESULTS_KEY, existing)
