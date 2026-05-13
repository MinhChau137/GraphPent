"""
CSNT-style KG Completion Service — L4.

4 components that complement the LLM-based KGCompletionService:

  C — Confidence   : multi-factor scoring per edge (source × structural × decay)
  S — Structural   : graph-topology link prediction (common neighbors, path scan)
  N — Neural       : GNN embedding cosine similarity for candidate ranking
  T — Template     : security domain rules (product sharing, TTP chains, bridges)

  + Anomaly detection: flag statistically suspicious triples.

All computation is Cypher-based (no ML runtime required).
Neural component uses pre-computed gnn_embedding node properties when available.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.adapters.neo4j_client import Neo4jAdapter
from app.core.logger import logger
from app.core.security import audit_log


# ── Source confidence table ───────────────────────────────────────────────────

_SRC_CONF = {
    "nvd":               1.00,
    "cpe_exact":         0.90,
    "cpe_product":       0.80,
    "same_version_rule": 0.80,
    "ttp_cwe_chain":     0.75,
    "host_service_bridge": 0.70,
    "structural_cn":     0.65,
    "llm_inferred":      0.65,
    "gnn":               0.60,   # overridden by actual score at write time
    "structural_path":   0.60,
}


@dataclass
class PredictedEdge:
    src: str
    dst: str
    rel_type: str
    confidence: float
    method: str
    rationale: str = ""


@dataclass
class ScoredTriple:
    src: str
    dst: str
    rel_type: str
    old_confidence: Optional[float]
    new_confidence: float
    changed: bool


@dataclass
class AnomalyFlag:
    entity_id: str
    anomaly_type: str
    detail: str
    severity: str   # high / medium / low


@dataclass
class CompletionResult:
    # Structural + Template + Neural
    predicted_edges: List[PredictedEdge] = field(default_factory=list)
    edges_written: int = 0
    # Triple scoring
    triples_scored: int = 0
    confidence_updated: int = 0
    # Anomalies
    anomalies: List[AnomalyFlag] = field(default_factory=list)
    # Summary
    summary: Dict = field(default_factory=dict)


def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a))
    nb   = math.sqrt(sum(y * y for y in b))
    denom = na * nb
    return dot / denom if denom > 1e-9 else 0.0


class CSNTKGCompletion:
    """
    CSNT-style Knowledge Graph Completion.

    Usage:
        service = CSNTKGCompletion()
        result  = await service.run_completion_pass(min_confidence=0.60)
    """

    def __init__(self):
        self.neo4j = Neo4jAdapter()

    # ═══════════════════════════════════════════════════════════════ public API

    async def run_completion_pass(
        self,
        min_confidence: float = 0.60,
        max_edges_per_rule: int = 500,
        run_neural: bool = True,
        run_anomaly: bool = True,
    ) -> CompletionResult:
        """
        Full CSNT completion pass.  Returns CompletionResult with all sub-results.
        """
        result = CompletionResult()

        # ── T: Template rules ─────────────────────────────────────────────────
        logger.info("CSNT-L4: Template link prediction")
        template_edges = await self._template_link_prediction(max_edges_per_rule)
        result.predicted_edges.extend(template_edges)

        # ── S: Structural link prediction ─────────────────────────────────────
        logger.info("CSNT-L4: Structural link prediction")
        structural_edges = await self._structural_link_prediction(
            max_edges_per_rule, min_confidence
        )
        result.predicted_edges.extend(structural_edges)

        # ── N: Neural link prediction ─────────────────────────────────────────
        if run_neural:
            logger.info("CSNT-L4: Neural link prediction (GNN embeddings)")
            neural_edges = await self._neural_link_prediction(
                max_edges_per_rule, min_confidence
            )
            result.predicted_edges.extend(neural_edges)

        # Deduplicate by (src, dst, rel_type), keep highest confidence
        result.predicted_edges = _dedup_edges(result.predicted_edges)

        # Write predicted edges to Neo4j
        result.edges_written = await self._write_predicted_edges(
            result.predicted_edges, min_confidence
        )

        # ── C: Triple scoring + confidence propagation ────────────────────────
        logger.info("CSNT-L4: Confidence estimation & triple scoring")
        scored, updated = await self._score_and_propagate_confidence()
        result.triples_scored = scored
        result.confidence_updated = updated

        # ── Anomaly detection ─────────────────────────────────────────────────
        if run_anomaly:
            logger.info("CSNT-L4: Anomaly detection")
            result.anomalies = await self._detect_anomalies()

        result.summary = {
            "template_edges": len(template_edges),
            "structural_edges": len(structural_edges),
            "neural_edges": len(neural_edges) if run_neural else 0,
            "total_predicted": len(result.predicted_edges),
            "edges_written": result.edges_written,
            "triples_scored": result.triples_scored,
            "confidence_updated": result.confidence_updated,
            "anomalies_flagged": len(result.anomalies),
        }

        logger.info("CSNT-L4: completion pass done", **result.summary)
        await audit_log("csnt_kg_completion", result.summary)
        return result

    async def score_triples(self) -> Dict:
        """Score all edges without running prediction. Lightweight re-scoring pass."""
        scored, updated = await self._score_and_propagate_confidence()
        return {"triples_scored": scored, "confidence_updated": updated}

    async def detect_anomalies(self) -> List[AnomalyFlag]:
        """Run anomaly detection only (non-destructive)."""
        return await self._detect_anomalies()

    # ═══════════════════════════════════════════════════════════ T: Template rules

    async def _template_link_prediction(self, limit: int) -> List[PredictedEdge]:
        edges: List[PredictedEdge] = []

        # Rule 1 — Same product+version → share CVEs
        edges.extend(await self._rule_same_version_cve(limit))

        # Rule 2 — TTP→CWE→CVE→Service → TTP TARGETS Service
        edges.extend(await self._rule_ttp_cwe_chain(limit))

        # Rule 3 — Host→Service→CVE bridge → Host HAS_VULN CVE
        edges.extend(await self._rule_host_service_bridge(limit))

        # Rule 4 — TTP platform match → Application TARGETED_BY TTP
        edges.extend(await self._rule_ttp_platform_app(limit))

        return edges

    async def _rule_same_version_cve(self, limit: int) -> List[PredictedEdge]:
        """Services with identical product+version must share the same CVEs."""
        cypher = """
        MATCH (s1:Service)-[:HAS_VULN]->(v:Vulnerability)
        MATCH (s2:Service)
        WHERE s2.product = s1.product
          AND s2.version IS NOT NULL AND s1.version IS NOT NULL
          AND s2.version = s1.version
          AND s2.id <> s1.id
          AND NOT (s2)-[:HAS_VULN]->(v)
        RETURN s2.id AS src, v.id AS dst, 0.80 AS score
        LIMIT $limit
        """
        return await self._fetch_edges(cypher, limit, "HAS_VULN", "same_version_rule")

    async def _rule_ttp_cwe_chain(self, limit: int) -> List[PredictedEdge]:
        """TTP -[MAPPED_TO]-> CWE -[HAS_WEAKNESS]- CVE -[HAS_VULN]- Service → TTP TARGETS Service."""
        cypher = """
        MATCH (t:TTP)-[:MAPPED_TO]->(c:CWE)<-[:HAS_WEAKNESS]-(v:Vulnerability)
              <-[:HAS_VULN]-(s:Service)
        WHERE NOT (t)-[:TARGETS]->(s)
        WITH t.id AS src, s.id AS dst,
             count(DISTINCT v) AS chain_count
        RETURN src, dst,
               CASE WHEN chain_count >= 3 THEN 0.82
                    WHEN chain_count = 2  THEN 0.77
                    ELSE 0.73
               END AS score
        LIMIT $limit
        """
        return await self._fetch_edges(cypher, limit, "TARGETS", "ttp_cwe_chain")

    async def _rule_host_service_bridge(self, limit: int) -> List[PredictedEdge]:
        """Host -[EXPOSES]-> Service -[HAS_VULN]-> CVE  ⟹  Host -[HAS_VULN]-> CVE."""
        cypher = """
        MATCH (h:Host)-[:EXPOSES]->(s:Service)-[:HAS_VULN]->(v:Vulnerability)
        WHERE NOT (h)-[:HAS_VULN]->(v)
        WITH h.id AS src, v.id AS dst,
             max(coalesce(v.cvss_score, 5.0)) AS max_cvss
        RETURN src, dst,
               CASE WHEN max_cvss >= 9.0 THEN 0.80
                    WHEN max_cvss >= 7.0 THEN 0.72
                    ELSE 0.65
               END AS score
        LIMIT $limit
        """
        return await self._fetch_edges(cypher, limit, "HAS_VULN", "host_service_bridge")

    async def _rule_ttp_platform_app(self, limit: int) -> List[PredictedEdge]:
        """TTP with 'Linux'/'Windows' platform → TARGETS Applications running on those hosts."""
        cypher = """
        MATCH (t:TTP)
        WHERE t.platforms IS NOT NULL
        MATCH (h:Host)-[:RUNS]->(a:Application)
        WHERE (ANY(p IN t.platforms WHERE toLower(p) IN ['linux','unix'])
               AND toLower(h.os) CONTAINS 'linux')
           OR (ANY(p IN t.platforms WHERE toLower(p) IN ['windows'])
               AND toLower(h.os) CONTAINS 'windows')
        MATCH (t)-[:MAPPED_TO]->(c:CWE)<-[:HAS_WEAKNESS]-(v:Vulnerability)
              <-[:HAS_VULN]-(s:Service)-[:RUNS]->(a)
        WHERE NOT (t)-[:TARGETS]->(a)
        WITH t.id AS src, a.id AS dst, count(DISTINCT v) AS support
        WHERE support >= 1
        RETURN src, dst, 0.70 AS score
        LIMIT $limit
        """
        return await self._fetch_edges(cypher, limit, "TARGETS", "ttp_platform_app")

    # ═══════════════════════════════════════════════════════════ S: Structural

    async def _structural_link_prediction(
        self, limit: int, min_conf: float
    ) -> List[PredictedEdge]:
        edges: List[PredictedEdge] = []

        # Common neighbors via Application node
        edges.extend(await self._struct_cn_via_app(limit))

        # Path scan: Service ─[*2]─ Vulnerability not yet linked
        edges.extend(await self._struct_path_scan(limit))

        return [e for e in edges if e.confidence >= min_conf]

    async def _struct_cn_via_app(self, limit: int) -> List[PredictedEdge]:
        """
        Common neighbor: Service -[:RUNS]-> App, App product overlaps with Vuln.cpe_products.
        Uses cpe_products (list of strings) for matching — avoids parsing JSON in cpe_affected.
        """
        cypher = """
        MATCH (s:Service)-[:RUNS]->(a:Application)
        MATCH (v:Vulnerability)
        WHERE a.product IS NOT NULL
          AND v.cpe_products IS NOT NULL
          AND size(v.cpe_products) > 0
          AND ANY(vp IN v.cpe_products
                  WHERE toLower(a.product) CONTAINS toLower(vp)
                     OR toLower(vp) CONTAINS toLower(a.product))
          AND NOT (s)-[:HAS_VULN]->(v)
        WITH s.id AS src, v.id AS dst,
             count(DISTINCT a) AS cn
        RETURN src, dst,
               CASE WHEN cn >= 3 THEN 0.75
                    WHEN cn = 2  THEN 0.68
                    ELSE 0.62
               END AS score
        LIMIT $limit
        """
        return await self._fetch_edges(cypher, limit, "HAS_VULN", "structural_cn")

    async def _struct_path_scan(self, limit: int) -> List[PredictedEdge]:
        """
        CWE-based path scan: if Service already has CVE1 with CWE-X,
        and CVE2 also has CWE-X, then Service may also be affected by CVE2.
        """
        cypher = """
        MATCH (s:Service)-[:HAS_VULN]->(v1:Vulnerability)-[:HAS_WEAKNESS]->(c:CWE)
              <-[:HAS_WEAKNESS]-(v2:Vulnerability)
        WHERE v1 <> v2
          AND NOT (s)-[:HAS_VULN]->(v2)
        WITH s.id AS src, v2.id AS dst,
             count(DISTINCT c) AS shared_cwe
        WHERE shared_cwe >= 1
        RETURN src, dst,
               CASE WHEN shared_cwe >= 3 THEN 0.72
                    WHEN shared_cwe = 2  THEN 0.66
                    ELSE 0.60
               END AS score
        LIMIT $limit
        """
        return await self._fetch_edges(cypher, limit, "HAS_VULN", "structural_path")

    # ═══════════════════════════════════════════════════════════ N: Neural

    async def _neural_link_prediction(
        self, limit: int, min_conf: float
    ) -> List[PredictedEdge]:
        """Use pre-computed gnn_embedding to score (Service, Vulnerability) pairs."""
        try:
            async with self.neo4j.driver.session() as session:
                return await session.execute_read(
                    self._neural_score_tx, limit, min_conf
                )
        except Exception as exc:
            logger.warning("CSNT-N: neural scoring failed", error=str(exc))
            return []

    async def _neural_score_tx(self, tx, limit: int, min_conf: float) -> List[PredictedEdge]:
        # Check embeddings exist
        chk = await tx.run(
            "MATCH (n) WHERE n.gnn_embedding IS NOT NULL RETURN count(n) AS n LIMIT 1"
        )
        rec = await chk.single()
        if not rec or rec["n"] == 0:
            return []

        # Load service embeddings
        svc_res  = await tx.run(
            "MATCH (s:Service) WHERE s.gnn_embedding IS NOT NULL "
            "RETURN s.id AS id, s.gnn_embedding AS emb LIMIT 2000"
        )
        svc_recs = await svc_res.fetch(2000)

        # Load vuln embeddings with CVSS weight
        vuln_res = await tx.run(
            "MATCH (v:Vulnerability) WHERE v.gnn_embedding IS NOT NULL "
            "RETURN v.id AS id, v.gnn_embedding AS emb, "
            "coalesce(v.cvss_score, 5.0) / 10.0 AS severity LIMIT 5000"
        )
        vuln_recs = await vuln_res.fetch(5000)

        # Load existing HAS_VULN pairs to skip
        existing_res = await tx.run(
            "MATCH (s:Service)-[:HAS_VULN]->(v:Vulnerability) "
            "RETURN s.id AS s, v.id AS v LIMIT 100000"
        )
        existing_raw = await existing_res.fetch(100000)
        existing = {(r["s"], r["v"]) for r in existing_raw}

        edges: List[PredictedEdge] = []
        vuln_data = [(r["id"], r["emb"], float(r["severity"])) for r in vuln_recs]

        for svc_rec in svc_recs:
            svc_id  = svc_rec["id"]
            svc_emb = svc_rec["emb"]
            best_score = 0.0
            best_vid   = None

            for v_id, v_emb, v_sev in vuln_data:
                if (svc_id, v_id) in existing:
                    continue
                sim = _cosine(svc_emb, v_emb) * (0.5 + 0.5 * v_sev)
                if sim > best_score and sim >= min_conf:
                    best_score = sim
                    best_vid   = v_id

            if best_vid:
                edges.append(PredictedEdge(
                    src=svc_id, dst=best_vid,
                    rel_type="HAS_VULN",
                    confidence=round(best_score, 4),
                    method="gnn",
                    rationale="GNN embedding cosine similarity",
                ))

        # Sort and cap
        edges.sort(key=lambda e: -e.confidence)
        return edges[:limit]

    # ═══════════════════════════════════════════════════════ C: Confidence

    async def _score_and_propagate_confidence(self) -> tuple[int, int]:
        """
        (a) Fill missing confidence on inferred edges using structural heuristic.
        (b) Update confidence on all edges based on source × structural multiplier.
        Returns (triples_scored, nodes_updated).
        """
        try:
            async with self.neo4j.driver.session() as session:
                scored  = await session.execute_write(self._fill_missing_confidence_tx)
                updated = await session.execute_write(self._apply_structural_confidence_tx)
            return scored, updated
        except Exception as exc:
            logger.warning("CSNT-C: confidence propagation failed", error=str(exc))
            return 0, 0

    async def _fill_missing_confidence_tx(self, tx) -> int:
        """Fill NULL confidence on inferred edges with degree-based estimate."""
        result = await tx.run("""
        MATCH (a)-[r]->(b)
        WHERE r.inferred = true AND r.confidence IS NULL
        WITH a, r, b,
             size([(a)-[]-() | 1]) AS deg_a,
             size([(b)-[]-() | 1]) AS deg_b
        SET r.confidence = round(
            0.50
            + 0.10 * log(toFloat(deg_a) + 1.0)
            + 0.10 * log(toFloat(deg_b) + 1.0),
            3)
        RETURN count(r) AS updated
        """)
        rec = await result.single()
        return int(rec["updated"]) if rec else 0

    async def _apply_structural_confidence_tx(self, tx) -> int:
        """
        For HAS_VULN edges, boost confidence when:
        - Service has an Application with matching product (CPE proximity)
        - Service has other CVEs sharing a CWE with this CVE (CWE chain bonus)
        Write as r.structural_confidence; update r.confidence = max(r.confidence, struct_conf).
        """
        result = await tx.run("""
        MATCH (s:Service)-[r:HAS_VULN]->(v:Vulnerability)
        WITH s, r, v,
             size([(s)-[:RUNS]->(a:Application)
                   WHERE a.product IS NOT NULL | 1])           AS has_app,
             size([(s)-[:HAS_VULN]->(v2:Vulnerability)
                        -[:HAS_WEAKNESS]->(c:CWE)
                        <-[:HAS_WEAKNESS]-(v)
                   WHERE v2 <> v | 1])                          AS shared_cwe
        WITH r,
             coalesce(r.confidence, 0.65)
             * (1.0 + 0.08 * toFloat(CASE WHEN has_app  > 0 THEN 1 ELSE 0 END))
             * (1.0 + 0.08 * toFloat(CASE WHEN shared_cwe > 0 THEN 1 ELSE 0 END))
             AS struct_conf
        SET r.structural_confidence = round(struct_conf, 3),
            r.confidence = round(
                CASE WHEN struct_conf > coalesce(r.confidence, 0.0)
                     THEN struct_conf ELSE coalesce(r.confidence, 0.0) END,
                3)
        RETURN count(r) AS updated
        """)
        rec = await result.single()
        return int(rec["updated"]) if rec else 0

    # ═══════════════════════════════════════════════════════ Anomaly detection

    async def _detect_anomalies(self) -> List[AnomalyFlag]:
        flags: List[AnomalyFlag] = []

        flags.extend(await self._anomaly_vuln_count_outlier())
        flags.extend(await self._anomaly_orphaned_high_cvss())
        flags.extend(await self._anomaly_service_no_cve())
        flags.extend(await self._anomaly_low_confidence_inferred())

        return flags

    async def _anomaly_vuln_count_outlier(self) -> List[AnomalyFlag]:
        """
        Services with same product+version but very different CVE counts.
        Indicates either a missed link or a spurious link.
        """
        cypher = """
        MATCH (s:Service)
        WHERE s.product IS NOT NULL AND s.version IS NOT NULL
        OPTIONAL MATCH (s)-[:HAS_VULN]->(v:Vulnerability)
        WITH s.product AS prod, s.version AS ver, s.id AS svc_id,
             count(v) AS vuln_cnt
        WITH prod, ver,
             collect({id: svc_id, cnt: vuln_cnt}) AS svc_list,
             avg(toFloat(vuln_cnt)) AS avg_cnt
        WHERE size(svc_list) >= 2
        UNWIND svc_list AS row
        WITH row.id AS svc_id, toFloat(row.cnt) AS vuln_cnt, avg_cnt, prod, ver
        WHERE abs(vuln_cnt - avg_cnt) >= 5
        RETURN svc_id,
               'vuln_count_outlier' AS anomaly_type,
               prod + ' ' + ver + ': cnt=' + toString(toInteger(vuln_cnt))
               + ' avg=' + toString(round(avg_cnt, 1)) AS detail,
               CASE WHEN abs(vuln_cnt - avg_cnt) >= 10 THEN 'high'
                    ELSE 'medium' END AS severity
        LIMIT 50
        """
        return await self._fetch_anomalies(cypher)

    async def _anomaly_orphaned_high_cvss(self) -> List[AnomalyFlag]:
        """
        High-CVSS CVEs with no Service link — likely missing HAS_VULN edge.
        """
        cypher = """
        MATCH (v:Vulnerability)
        WHERE NOT (v)<-[:HAS_VULN]-()
          AND v.cvss_score >= 7.0
        RETURN v.id AS svc_id,
               'orphaned_high_cvss' AS anomaly_type,
               'CVSS=' + toString(v.cvss_score) + ' severity=' + coalesce(v.cvss_severity,'?') AS detail,
               CASE WHEN v.cvss_score >= 9.0 THEN 'high'
                    ELSE 'medium' END AS severity
        LIMIT 100
        """
        return await self._fetch_anomalies(cypher)

    async def _anomaly_service_no_cve(self) -> List[AnomalyFlag]:
        """
        Services with known product+version but zero CVE links.
        Flagged as low-severity — candidate for completion.
        """
        cypher = """
        MATCH (s:Service)
        WHERE s.product IS NOT NULL
          AND s.version IS NOT NULL
          AND s.version <> ''
          AND NOT (s)-[:HAS_VULN]->()
        RETURN s.id AS svc_id,
               'service_no_cve' AS anomaly_type,
               s.product + ' ' + s.version AS detail,
               'low' AS severity
        LIMIT 50
        """
        return await self._fetch_anomalies(cypher)

    async def _anomaly_low_confidence_inferred(self) -> List[AnomalyFlag]:
        """
        Inferred edges with confidence below 0.50 — candidates for removal.
        """
        cypher = """
        MATCH (a)-[r]->(b)
        WHERE r.inferred = true
          AND r.confidence < 0.50
        RETURN a.id AS svc_id,
               'low_confidence_inferred' AS anomaly_type,
               type(r) + '->' + b.id + ' conf=' + toString(round(r.confidence,3)) AS detail,
               'medium' AS severity
        LIMIT 50
        """
        return await self._fetch_anomalies(cypher)

    # ═══════════════════════════════════════════════════════ Write + helpers

    async def _write_predicted_edges(
        self, edges: List[PredictedEdge], min_conf: float
    ) -> int:
        """Merge predicted edges into Neo4j with inferred=True, source=method."""
        to_write = [e for e in edges if e.confidence >= min_conf]
        if not to_write:
            return 0

        rows = [
            {
                "src":       e.src,
                "dst":       e.dst,
                "rel_type":  e.rel_type,
                "confidence": e.confidence,
                "method":    e.method,
                "rationale": e.rationale,
            }
            for e in to_write
        ]

        try:
            async with self.neo4j.driver.session() as session:
                ok = await session.execute_write(self._merge_edges_tx, rows)
            return ok
        except Exception as exc:
            logger.warning("CSNT: edge write failed", error=str(exc))
            return 0

    async def _merge_edges_tx(self, tx, rows: List[Dict]) -> int:
        ok = 0
        BATCH = 100
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i+BATCH]
            # Dynamic rel_type requires APOC or unwind per type
            # Group by rel_type for safety
            by_type: Dict[str, List[Dict]] = {}
            for r in batch:
                by_type.setdefault(r["rel_type"], []).append(r)

            for rel_type, sub_batch in by_type.items():
                cypher = f"""
                UNWIND $rows AS row
                MATCH (a {{id: row.src}})
                MATCH (b {{id: row.dst}})
                MERGE (a)-[r:{rel_type}]->(b)
                ON CREATE SET
                    r.confidence       = row.confidence,
                    r.source           = row.method,
                    r.inferred         = true,
                    r.rationale        = row.rationale,
                    r.created_at       = datetime()
                ON MATCH SET
                    r.csnt_confidence  = row.confidence,
                    r.csnt_method      = row.method
                """
                await tx.run(cypher, rows=sub_batch)
                ok += len(sub_batch)
        return ok

    async def _fetch_edges(
        self, cypher: str, limit: int, rel_type: str, method: str
    ) -> List[PredictedEdge]:
        try:
            async with self.neo4j.driver.session() as session:
                result = await session.run(cypher, limit=limit)
                records = await result.fetch(limit)
            edges = []
            for r in records:
                edges.append(PredictedEdge(
                    src=r["src"],
                    dst=r["dst"],
                    rel_type=rel_type,
                    confidence=round(float(r["score"]), 4),
                    method=method,
                ))
            return edges
        except Exception as exc:
            logger.warning(f"CSNT-rule {method} failed", error=str(exc))
            return []

    async def _fetch_anomalies(self, cypher: str) -> List[AnomalyFlag]:
        try:
            async with self.neo4j.driver.session() as session:
                result = await session.run(cypher)
                records = await result.fetch(200)
            return [
                AnomalyFlag(
                    entity_id=r["svc_id"],
                    anomaly_type=r["anomaly_type"],
                    detail=r["detail"],
                    severity=r["severity"],
                )
                for r in records
            ]
        except Exception as exc:
            logger.warning("CSNT-anomaly query failed", error=str(exc))
            return []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dedup_edges(edges: List[PredictedEdge]) -> List[PredictedEdge]:
    """Keep highest-confidence edge for each (src, dst, rel_type) triple."""
    seen: Dict[tuple, PredictedEdge] = {}
    for e in edges:
        key = (e.src, e.dst, e.rel_type)
        if key not in seen or e.confidence > seen[key].confidence:
            seen[key] = e
    return list(seen.values())
