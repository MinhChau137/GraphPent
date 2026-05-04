"""GNN / Risk Service - Phase 12: Neo4j GDS risk scoring + attack-path reasoning."""

from typing import Dict, List, Optional

from app.adapters.neo4j_client import Neo4jAdapter
from app.core.logger import logger
from app.core.security import audit_log

def _weights():
    """Read GNN weights from settings at call-time (supports live reload in tests)."""
    from app.config.settings import settings
    return (
        getattr(settings, "GNN_W_PAGERANK",    0.25),
        getattr(settings, "GNN_W_SEVERITY",    0.60),
        getattr(settings, "GNN_W_BETWEENNESS", 0.15),
    )

_SEV_SCORE = {"critical": 1.0, "high": 0.75, "medium": 0.50, "low": 0.25, "unknown": 0.10}


class GNNService:
    """
    Phase 12 — Structural risk scoring and attack-path inference.

    Uses Neo4j GDS (PageRank + Betweenness Centrality) when available,
    with a degree-based fallback for environments without GDS.
    Exposes risk-ranked node lists and Cypher-based attack-path finding.
    """

    def __init__(self):
        self.neo4j = Neo4jAdapter()

    # ---------------------------------------------------------------- public

    async def compute_risk_scores(self) -> Dict:
        """
        Run PageRank + Betweenness Centrality on the full graph,
        then write a blended `risk_score` property to each node.

        Returns stats about how many nodes were updated.
        """
        logger.info("GNN: computing risk scores")

        pr_result = await self.neo4j.compute_pagerank_scores()
        bc_result = await self.neo4j.compute_betweenness_scores()

        # Blend: final_risk = weighted combination of pagerank + severity + betweenness
        blend_result = await self._write_blended_scores()

        stats = {
            "pagerank": pr_result,
            "betweenness": bc_result,
            "blended": blend_result,
        }
        logger.info("GNN: risk scoring done", stats=stats)
        await audit_log("gnn_risk_scoring", stats)
        return stats

    async def get_high_risk_nodes(self, limit: int = 20) -> List[Dict]:
        """Return top-N nodes by blended risk_score."""
        nodes = await self.neo4j.get_high_risk_nodes(limit=limit)
        # Annotate with human-readable risk tier
        for node in nodes:
            score = float(node.get("risk_score", 0))
            node["risk_tier"] = self._score_to_tier(score)
        return nodes

    async def find_attack_paths(
        self,
        source_id: str,
        target_label: str = "CVE",
        max_hops: int = 4,
    ) -> List[Dict]:
        """Find shortest paths from source_id to nodes of target_label type.

        Returns a list of path dicts, each with node_names, rel_types, hops,
        target info, and a path_risk score.
        """
        paths = await self.neo4j.find_attack_paths(
            source_id=source_id,
            target_label=target_label,
            max_hops=max_hops,
        )
        # Add a composite path_risk = target_risk / hops (shorter paths to risky targets score highest)
        for path in paths:
            hops = max(path.get("hops", 1), 1)
            target_risk = float(path.get("target_risk", 0.1))
            path["path_risk"] = round(target_risk / hops, 4)

        paths.sort(key=lambda p: p["path_risk"], reverse=True)
        await audit_log("attack_path_query", {"source": source_id, "paths_found": len(paths)})
        return paths

    async def get_risk_summary(self) -> Dict:
        """High-level risk snapshot: severity counts + top-5 risks."""
        summary = await self.neo4j.get_risk_summary()
        top_nodes = await self.neo4j.get_high_risk_nodes(limit=5)
        summary["top_risks"] = [
            {
                "id": n.get("id"),
                "label": n.get("label"),
                "name": n.get("name"),
                "risk_score": n.get("risk_score"),
                "risk_tier": self._score_to_tier(float(n.get("risk_score") or 0)),
            }
            for n in top_nodes
        ]
        return summary

    async def get_prioritized_targets(self, limit: int = 10) -> List[Dict]:
        """
        Return Host nodes sorted by their blended risk_score.
        Used by planner_node (Phase 13) to select the next scan target.
        """
        try:
            async with self.neo4j.driver.session() as session:
                result = await session.execute_read(self._get_prioritized_hosts_tx, limit)
                return result
        except Exception as exc:
            logger.warning("get_prioritized_targets failed", error=str(exc))
            return []

    # ---------------------------------------------------------------- private

    async def _write_blended_scores(self) -> Dict:
        """Compute blended risk_score from pagerank + severity + betweenness."""
        try:
            async with self.neo4j.driver.session() as session:
                result = await session.execute_write(self._write_blended_scores_tx)
                return result
        except Exception as exc:
            logger.warning("Blended score write failed", error=str(exc))
            return {"nodes_updated": 0, "error": str(exc)}

    async def _write_blended_scores_tx(self, tx) -> Dict:
        w_pr, w_sev, w_bc = _weights()
        # Use cvss_score/10 when available (granular: 9.8→0.98),
        # fallback to categorical severity string mapping.
        cypher = """
        MATCH (n)
        WITH n,
             coalesce(n.pagerank_score, 0.0)    AS pr,
             coalesce(n.betweenness_score, 0.0) AS bc,
             CASE
               WHEN n.cvss_score IS NOT NULL
                 THEN n.cvss_score / 10.0
               ELSE CASE toLower(coalesce(n.severity, 'unknown'))
                 WHEN 'critical' THEN 1.00
                 WHEN 'high'     THEN 0.75
                 WHEN 'medium'   THEN 0.50
                 WHEN 'low'      THEN 0.25
                 ELSE 0.10
               END
             END AS sev
        SET n.risk_score = round(
              $w_pr * pr + $w_sev * sev + $w_bc * bc,
              4
            )
        RETURN count(n) AS updated
        """
        result = await tx.run(
            cypher,
            w_pr=w_pr,
            w_sev=w_sev,
            w_bc=w_bc,
        )
        record = await result.single()
        updated = record["updated"] if record else 0
        logger.info("Blended risk_score written", nodes=updated)
        return {"nodes_updated": updated}

    async def _get_prioritized_hosts_tx(self, tx, limit: int) -> List[Dict]:
        cypher = """
        MATCH (h:Host)
        OPTIONAL MATCH (h)-[:HAS_PORT]->(p:Port)
        OPTIONAL MATCH (h)-[:EXPOSES]->(s:Service)
        WITH h,
             count(DISTINCT p) AS open_ports,
             count(DISTINCT s) AS services,
             coalesce(h.risk_score, 0.0) AS risk_score
        RETURN h.id AS id,
               coalesce(h.name, h.id) AS name,
               open_ports, services, risk_score,
               properties(h) AS props
        ORDER BY risk_score DESC, open_ports DESC
        LIMIT $limit
        """
        result = await tx.run(cypher, limit=limit)
        records = await result.fetch(limit)
        rows = []
        for r in records:
            d = dict(r)
            d["risk_tier"] = self._score_to_tier(float(d.get("risk_score", 0)))
            rows.append(d)
        return rows

    @staticmethod
    def _score_to_tier(score: float) -> str:
        if score >= 0.75:
            return "CRITICAL"
        if score >= 0.50:
            return "HIGH"
        if score >= 0.25:
            return "MEDIUM"
        return "LOW"
