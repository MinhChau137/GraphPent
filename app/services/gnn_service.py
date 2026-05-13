"""GNN / Risk Service — confidence-weighted, context-aware risk scoring.

Risk model (3 passes):
  Pass 1 — vuln_exposure_score per Service:
      vuln_exposure = 1 - exp(-Σ(edge_confidence × cvss/10 × exploit_factor) / 3)
      exploit_factor = 1.15 when a TTP is mapped to the CVE's CWE, else 1.0
      Writes: s.vuln_exposure_score

  Pass 2 — vuln_exposure_score per Host:
      host_exposure = min(max(service.vuln_exposure) × web_factor, 1.0)
      web_factor = 1.15 when host exposes any web port (80/443/8080/…)
      Writes: h.vuln_exposure_score

  Pass 3 — blended risk_score on all nodes:
      risk = w_pr × pagerank + w_sev × effective_sev + w_bc × betweenness
      effective_sev priority: vuln_exposure_score > cvss/10 > gnn_proximity > severity_string
      Writes: n.risk_score

Attack path scoring:
  path_risk = path_confidence × target_risk / sqrt(hops)
  path_confidence = Π(edge.confidence) along the path
"""

import math
from typing import Dict, List, Optional

from app.adapters.neo4j_client import Neo4jAdapter
from app.core.logger import logger
from app.core.security import audit_log


def _weights():
    from app.config.settings import settings
    return (
        getattr(settings, "GNN_W_PAGERANK",    0.10),
        getattr(settings, "GNN_W_SEVERITY",    0.80),
        getattr(settings, "GNN_W_BETWEENNESS", 0.10),
    )


def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a))
    nb   = math.sqrt(sum(y * y for y in b))
    denom = na * nb
    return dot / denom if denom > 1e-9 else 0.0


_WEB_PORTS = [80, 443, 8080, 8443, 8888, 3000, 9090, 4443]


class GNNService:
    """Contextual risk scoring with confidence propagation."""

    def __init__(self):
        self.neo4j = Neo4jAdapter()

    # ═══════════════════════════════════════════════════════════════ public API

    async def compute_risk_scores(self) -> Dict:
        """
        Full risk scoring pipeline:
          1. PageRank + Betweenness (graph centrality)
          2. GNN proximity (optional, if embeddings exist)
          3. Confidence-weighted vuln_exposure_score (Service + Host)
          4. Blended risk_score on all nodes
        """
        logger.info("Risk: starting full scoring pipeline")

        pr_result  = await self.neo4j.compute_pagerank_scores()
        bc_result  = await self.neo4j.compute_betweenness_scores()
        prox_result = await self.compute_gnn_proximity_scores()

        # Confidence-weighted pass: core of the new model
        svc_result  = await self.compute_vuln_exposure_scores()
        host_result = await self.compute_host_exposure_scores()

        blend_result = await self._write_blended_scores()

        stats = {
            "pagerank":        pr_result,
            "betweenness":     bc_result,
            "gnn_proximity":   prox_result,
            "svc_exposure":    svc_result,
            "host_exposure":   host_result,
            "blended":         blend_result,
        }
        logger.info("Risk: pipeline done", **{k: v.get("nodes_updated", "?") for k, v in stats.items() if isinstance(v, dict)})
        await audit_log("gnn_risk_scoring", stats)
        return stats

    async def compute_vuln_exposure_scores(self) -> Dict:
        """
        Pass 1: For each Service, compute vuln_exposure_score from its HAS_VULN edges.

        vuln_exposure_score = 1 - exp( -Σ(conf × cvss/10 × exploit_factor) / 3 )

        This is a saturating function: adding more weak CVEs raises score slowly;
        one critical high-confidence CVE raises it quickly.
        exploit_factor = 1.15 when any TTP is mapped to the CVE's CWE.
        """
        try:
            async with self.neo4j.driver.session() as session:
                return await session.execute_write(self._vuln_exposure_tx)
        except Exception as exc:
            logger.warning("vuln_exposure_scores failed", error=str(exc))
            return {"nodes_updated": 0, "error": str(exc)}

    async def compute_host_exposure_scores(self) -> Dict:
        """
        Pass 2: For each Host, propagate from its services and apply web_exposure_factor.

        host_exposure_score = min( max(service.vuln_exposure) × web_factor, 1.0 )
        web_factor = 1.15 when host has any web port open (80/443/8080/…)
        """
        try:
            async with self.neo4j.driver.session() as session:
                return await session.execute_write(self._host_exposure_tx)
        except Exception as exc:
            logger.warning("host_exposure_scores failed", error=str(exc))
            return {"nodes_updated": 0, "error": str(exc)}

    async def compute_gnn_proximity_scores(self) -> Dict:
        """
        Optional: for Service nodes with gnn_embedding, compute cosine proximity
        to Vulnerability embeddings → gnn_vuln_proximity.
        No-op if embeddings are absent.
        """
        try:
            async with self.neo4j.driver.session() as session:
                return await session.execute_write(self._compute_proximity_tx)
        except Exception as exc:
            logger.warning("GNN proximity failed", error=str(exc))
            return {"nodes_updated": 0, "skipped": True, "error": str(exc)}

    async def get_high_risk_nodes(self, limit: int = 20) -> List[Dict]:
        nodes = await self.neo4j.get_high_risk_nodes(limit=limit)
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
        """
        Find shortest paths from source_id to nodes of target_label.
        path_risk = path_confidence × target_risk / sqrt(hops)
        path_confidence = Π(edge.confidence) — penalises paths through
        low-confidence inferred edges.
        """
        paths = await self.neo4j.find_attack_paths(
            source_id=source_id,
            target_label=target_label,
            max_hops=max_hops,
        )
        for path in paths:
            hops        = max(float(path.get("hops", 1)), 1.0)
            target_risk = float(path.get("target_risk", 0.1))
            path_conf   = float(path.get("path_confidence", 1.0))
            # Penalise long paths via sqrt (less aggressive than /hops)
            path["path_risk"] = round(path_conf * target_risk / math.sqrt(hops), 4)
            path["path_confidence"] = round(path_conf, 4)

        paths.sort(key=lambda p: p["path_risk"], reverse=True)
        await audit_log("attack_path_query", {"source": source_id, "paths_found": len(paths)})
        return paths

    async def get_risk_summary(self) -> Dict:
        summary   = await self.neo4j.get_risk_summary()
        top_nodes = await self.neo4j.get_high_risk_nodes(limit=5)
        summary["top_risks"] = [
            {
                "id":         n.get("id"),
                "label":      n.get("label"),
                "name":       n.get("name"),
                "risk_score": n.get("risk_score"),
                "risk_tier":  self._score_to_tier(float(n.get("risk_score") or 0)),
            }
            for n in top_nodes
        ]
        return summary

    async def get_prioritized_targets(self, limit: int = 10) -> List[Dict]:
        try:
            async with self.neo4j.driver.session() as session:
                result = await session.execute_read(self._get_prioritized_hosts_tx, limit)
                return result
        except Exception as exc:
            logger.warning("get_prioritized_targets failed", error=str(exc))
            return []

    # ═══════════════════════════════════════════════════════════════ pass 1: service

    async def _vuln_exposure_tx(self, tx) -> Dict:
        """
        Compute confidence-weighted vuln_exposure_score for every Service node.

        Formula:
          raw = Σ over HAS_VULN edges of:
                  edge.confidence × vuln.cvss_score/10 × exploit_factor
          vuln_exposure_score = 1 - exp(-raw / 3.0)   ∈ (0, 1)

        exploit_factor = 1.15 when ∃ TTP mapped to any CWE of this Vulnerability.

        Services with no HAS_VULN edges get score = 0.0.
        """
        # Zero-out services with no vulnerability links
        await tx.run("""
            MATCH (s:Service)
            WHERE NOT (s)-[:HAS_VULN]->()
            SET s.vuln_exposure_score = 0.0
        """)

        result = await tx.run("""
            MATCH (s:Service)-[r:HAS_VULN]->(v:Vulnerability)
            OPTIONAL MATCH (v)-[:HAS_WEAKNESS]->(:CWE)<-[:MAPPED_TO]-(:TTP)
            WITH s, r, v,
                 coalesce(r.confidence, 0.65)          AS edge_conf,
                 coalesce(v.cvss_score, 5.0) / 10.0    AS cvss_norm,
                 CASE WHEN count(*) > 0 THEN 1.15 ELSE 1.0 END AS exploit_factor
            WITH s,
                 sum(edge_conf * cvss_norm * exploit_factor) AS raw_score
            SET s.vuln_exposure_score = round(
                    1.0 - exp(-raw_score / 3.0),
                    4)
            RETURN count(s) AS updated
        """)
        rec = await result.single()
        updated = int(rec["updated"]) if rec else 0
        logger.info("vuln_exposure_score written", service_nodes=updated)
        return {"nodes_updated": updated}

    # ═══════════════════════════════════════════════════════════════ pass 2: host

    async def _host_exposure_tx(self, tx) -> Dict:
        """
        Propagate vuln_exposure_score from Services to Hosts with web_factor boost.

        web_factor = 1.15 when the host has at least one web port open.
        Capped at 1.0 to stay in probability range.
        """
        result = await tx.run(
            """
            MATCH (h:Host)-[:EXPOSES]->(s:Service)
            WITH h,
                 max(coalesce(s.vuln_exposure_score, 0.0)) AS max_svc_exposure
            OPTIONAL MATCH (h)-[:HAS_PORT]->(p:Port)
            WHERE p.port IN $web_ports
            WITH h, max_svc_exposure,
                 CASE WHEN count(p) > 0 THEN 1.15 ELSE 1.0 END AS web_factor
            SET h.vuln_exposure_score = round(
                    min(max_svc_exposure * web_factor, 1.0),
                    4)
            RETURN count(h) AS updated
            """,
            web_ports=_WEB_PORTS,
        )
        rec = await result.single()
        updated = int(rec["updated"]) if rec else 0
        logger.info("host vuln_exposure_score written", host_nodes=updated)
        return {"nodes_updated": updated}

    # ═══════════════════════════════════════════════════════════════ pass 3: blend

    async def _write_blended_scores(self) -> Dict:
        try:
            async with self.neo4j.driver.session() as session:
                result = await session.execute_write(self._write_blended_scores_tx)
                return result
        except Exception as exc:
            logger.warning("Blended score write failed", error=str(exc))
            return {"nodes_updated": 0, "error": str(exc)}

    async def _write_blended_scores_tx(self, tx) -> Dict:
        w_pr, w_sev, w_bc = _weights()
        """
        effective_sev priority (descending):
          1. vuln_exposure_score  — confidence-weighted path from node to CVEs
          2. cvss_score / 10      — direct CVSS for Vulnerability nodes
          3. gnn_vuln_proximity   — embedding-based proximity to vulnerability space
          4. severity string      — categorical fallback (critical/high/medium/low)
        """
        result = await tx.run(
            """
            MATCH (n)
            WITH n,
                 coalesce(n.pagerank_score,    0.0) AS pr,
                 coalesce(n.betweenness_score, 0.0) AS bc,
                 CASE
                   WHEN n.vuln_exposure_score IS NOT NULL
                     THEN n.vuln_exposure_score
                   WHEN n.cvss_score IS NOT NULL
                     THEN n.cvss_score / 10.0
                   WHEN n.gnn_vuln_proximity IS NOT NULL
                     THEN n.gnn_vuln_proximity
                   ELSE CASE toLower(coalesce(n.severity, 'unknown'))
                     WHEN 'critical' THEN 1.00
                     WHEN 'high'     THEN 0.75
                     WHEN 'medium'   THEN 0.50
                     WHEN 'low'      THEN 0.25
                     ELSE 0.10
                   END
                 END AS eff_sev
            SET n.risk_score = round($w_pr * pr + $w_sev * eff_sev + $w_bc * bc, 4)
            RETURN count(n) AS updated
            """,
            w_pr=w_pr, w_sev=w_sev, w_bc=w_bc,
        )
        rec = await result.single()
        updated = int(rec["updated"]) if rec else 0
        logger.info("Blended risk_score written", nodes=updated)
        return {"nodes_updated": updated}

    # ═══════════════════════════════════════════════════════════════ GNN proximity

    async def _compute_proximity_tx(self, tx) -> Dict:
        check = await tx.run(
            "MATCH (n) WHERE n.gnn_embedding IS NOT NULL RETURN count(n) AS n LIMIT 1"
        )
        rec = await check.single()
        if not rec or rec["n"] == 0:
            return {"nodes_updated": 0, "skipped": True, "reason": "no gnn_embedding"}

        vuln_res  = await tx.run(
            "MATCH (v:Vulnerability) WHERE v.gnn_embedding IS NOT NULL "
            "RETURN v.id AS id, v.gnn_embedding AS emb, "
            "coalesce(v.cvss_score, 5.0) / 10.0 AS severity"
        )
        vuln_recs = await vuln_res.fetch(5000)
        if not vuln_recs:
            return {"nodes_updated": 0, "skipped": True, "reason": "no vuln embeddings"}

        vuln_embs = [(r["emb"], float(r["severity"])) for r in vuln_recs]

        svc_res  = await tx.run(
            "MATCH (s:Service) WHERE s.gnn_embedding IS NOT NULL "
            "RETURN s.id AS id, s.gnn_embedding AS emb"
        )
        svc_recs = await svc_res.fetch(5000)

        updated = 0
        BATCH   = 100
        rows    = []

        for rec in svc_recs:
            emb  = rec["emb"]
            best = max((_cosine(emb, v_emb) * sev for v_emb, sev in vuln_embs), default=0.0)
            rows.append({"id": rec["id"], "prox": round(min(best, 1.0), 4)})
            if len(rows) >= BATCH:
                await tx.run(
                    "UNWIND $rows AS r MATCH (s:Service {id: r.id}) "
                    "SET s.gnn_vuln_proximity = r.prox",
                    rows=rows,
                )
                updated += len(rows)
                rows = []

        if rows:
            await tx.run(
                "UNWIND $rows AS r MATCH (s:Service {id: r.id}) "
                "SET s.gnn_vuln_proximity = r.prox",
                rows=rows,
            )
            updated += len(rows)

        logger.info("GNN proximity written", service_nodes=updated)
        return {"nodes_updated": updated}

    # ═══════════════════════════════════════════════════════════════ helpers

    async def _get_prioritized_hosts_tx(self, tx, limit: int) -> List[Dict]:
        result = await tx.run(
            """
            MATCH (h:Host)
            OPTIONAL MATCH (h)-[:HAS_PORT]->(p:Port)
            OPTIONAL MATCH (h)-[:EXPOSES]->(s:Service)
            WITH h,
                 count(DISTINCT p) AS open_ports,
                 count(DISTINCT s) AS services,
                 coalesce(h.risk_score, 0.0)          AS risk_score,
                 coalesce(h.vuln_exposure_score, 0.0) AS exposure_score
            RETURN h.id AS id,
                   coalesce(h.name, h.id) AS name,
                   open_ports, services, risk_score, exposure_score,
                   properties(h) AS props
            ORDER BY risk_score DESC, exposure_score DESC, open_ports DESC
            LIMIT $limit
            """,
            limit=limit,
        )
        records = await result.fetch(limit)
        rows = []
        for r in records:
            d = dict(r)
            d["risk_tier"] = self._score_to_tier(float(d.get("risk_score", 0)))
            rows.append(d)
        return rows

    @staticmethod
    def _score_to_tier(score: float) -> str:
        if score >= 0.75: return "CRITICAL"
        if score >= 0.50: return "HIGH"
        if score >= 0.25: return "MEDIUM"
        return "LOW"
