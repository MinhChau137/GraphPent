"""Neo4j Adapter - FINAL FIX Phase 6 (hỗ trợ mọi label + provenance) + Phase 3 (Nuclei findings)."""

from neo4j import AsyncGraphDatabase, AsyncDriver
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Dict, Optional
from app.config.settings import settings
from app.core.logger import logger
from app.domain.schemas.extraction import Entity, Relation

# Module-level shared driver — created once, reused by all Neo4jAdapter instances.
_shared_driver: Optional[AsyncDriver] = None


def _get_shared_driver() -> AsyncDriver:
    global _shared_driver
    if _shared_driver is None:
        _shared_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _shared_driver


async def close_neo4j_driver() -> None:
    """Call once on application shutdown to release the shared driver."""
    global _shared_driver
    if _shared_driver is not None:
        await _shared_driver.close()
        _shared_driver = None


class Neo4jAdapter:
    def __init__(self):
        self.driver: AsyncDriver = _get_shared_driver()

    async def close(self):
        # Individual adapters no longer own the driver; use close_neo4j_driver()
        # at app shutdown instead of calling this directly.
        pass

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def upsert_entities_and_relations(self, entities: List[Entity], relations: List[Relation]) -> Dict:
        async with self.driver.session() as session:
            result = await session.execute_write(self._upsert_tx, entities, relations)
            return result

    async def _upsert_tx(self, tx, entities: List[Entity], relations: List[Relation]):
        stats = {"entities_upserted": 0, "relations_created": 0}

        # 1. Entities (hỗ trợ mọi label động)
        for entity in entities:
            label = entity.type
            props = {
                "id": entity.id,
                "name": entity.name,
            }
            # Merge entity.properties (cvss_score, severity, cve_id, etc.)
            # Filter to Neo4j-compatible scalar types only
            for k, v in (entity.properties or {}).items():
                if isinstance(v, (str, int, float, bool)) and v is not None:
                    props[k] = v

            cypher = f"""
            MERGE (n:{label} {{id: $id}})
            ON CREATE SET
                n.name = $name,
                n += $props,
                n.created_at = datetime()
            ON MATCH SET
                n.name = $name,
                n += $props,
                n.updated_at = datetime()
            RETURN n.id as id
            """

            await tx.run(cypher, id=entity.id, name=entity.name, props=props)
            stats["entities_upserted"] += 1

        # 2. Relations (PRIORITY 1 FIX: Store confidence + normalize casing)
        for rel in relations:
            # Store confidence and other provenance in relation properties
            rel_props = {
                "confidence": rel.provenance.confidence if rel.provenance else 0.75,
                "source_chunk_id": rel.provenance.source_chunk_id if rel.provenance else None,
            }
            rel_props.update(rel.properties)

            # Normalize relation type to UPPERCASE (PRIORITY 3 FIX)
            rel_type_normalized = rel.type.upper()

            cypher = f"""
            MATCH (source) WHERE source.id = $source_id
            MATCH (target) WHERE target.id = $target_id
            MERGE (source)-[r:{rel_type_normalized}]->(target)
            ON CREATE SET 
                r += $props,
                r.created_at = datetime()
            ON MATCH SET 
                r += $props,
                r.updated_at = datetime()
            RETURN type(r) as rel_type
            """

            result = await tx.run(cypher, 
                        source_id=rel.source_id, 
                        target_id=rel.target_id, 
                        props=rel_props)
            record = await result.single()
            if record:
                stats["relations_created"] += 1

        logger.info("Neo4j upsert completed", **stats)
        return stats

    # ==================== Phase 3: Nuclei Findings Methods ====================

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def create_discovered_vulnerability(self, finding: Dict) -> Dict:
        """Create a :DiscoveredVulnerability node.
        
        Args:
            finding: Dictionary with finding data:
            {
                "id": str (UUID),
                "template_id": str,
                "severity": str,
                "host": str,
                "url": str,
                "matched_at": str (ISO 8601),
                "source": str,
                "metadata": dict
            }
            
        Returns:
            Dictionary with result {id, success, error}
        """
        async with self.driver.session() as session:
            result = await session.execute_write(
                self._create_discovered_vulnerability_tx,
                finding
            )
            return result

    async def _create_discovered_vulnerability_tx(self, tx, finding: Dict):
        """Transaction for creating DiscoveredVulnerability node."""
        try:
            cypher = """
            MERGE (f:DiscoveredVulnerability {id: $finding_id})
            ON CREATE SET 
                f.template_id = $template_id,
                f.severity = $severity,
                f.host = $host,
                f.url = $url,
                f.matched_at = $matched_at,
                f.source = $source,
                f.created_at = datetime(),
                f.metadata = $metadata
            ON MATCH SET
                f.updated_at = datetime()
            RETURN f.id as id, f.template_id as template_id, f.severity as severity
            """
            
            result = await tx.run(
                cypher,
                finding_id=finding["id"],
                template_id=finding.get("template_id"),
                severity=finding.get("severity"),
                host=finding.get("host"),
                url=finding.get("url"),
                matched_at=finding.get("matched_at"),
                source=finding.get("source", "nuclei"),
                metadata=finding.get("metadata", {})
            )
            record = await result.single()
            
            logger.info(
                f"Created DiscoveredVulnerability: {finding['id']}",
                extra={"template_id": finding.get("template_id"), "severity": finding.get("severity")}
            )
            
            return {"id": finding["id"], "success": True, "error": None}
            
        except Exception as e:
            logger.error(f"Failed to create finding: {e}", extra={"finding_id": finding.get("id")})
            return {"id": finding.get("id"), "success": False, "error": str(e)}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def create_finding_cve_relationship(self, finding_id: str, cve_id: str) -> Dict:
        """Create CORRELATES_TO relationship between Finding and CVE.
        
        Args:
            finding_id: UUID of DiscoveredVulnerability
            cve_id: CVE identifier (e.g., "CVE-2024-1234")
            
        Returns:
            Dictionary with result
        """
        async with self.driver.session() as session:
            result = await session.execute_write(
                self._create_finding_cve_relationship_tx,
                finding_id,
                cve_id
            )
            return result

    async def _create_finding_cve_relationship_tx(self, tx, finding_id: str, cve_id: str):
        """Transaction for creating CORRELATES_TO relationship."""
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {id: $finding_id})
            MERGE (c:CVE {id: $cve_id})
            MERGE (f)-[r:CORRELATES_TO]->(c)
            ON CREATE SET 
                r.created_at = datetime(),
                r.confidence = 0.95
            RETURN f.id as finding_id, c.id as cve_id, type(r) as rel_type
            """
            
            result = await tx.run(cypher, finding_id=finding_id, cve_id=cve_id)
            record = await result.single()
            
            logger.info(
                f"Created CORRELATES_TO: {finding_id} -> {cve_id}",
                extra={"finding_id": finding_id, "cve_id": cve_id}
            )
            
            return {"finding_id": finding_id, "cve_id": cve_id, "success": True, "error": None}
            
        except Exception as e:
            logger.error(
                f"Failed to create CVE relationship: {e}",
                extra={"finding_id": finding_id, "cve_id": cve_id}
            )
            return {"finding_id": finding_id, "cve_id": cve_id, "success": False, "error": str(e)}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def create_finding_cwe_relationship(self, finding_id: str, cwe_id: str) -> Dict:
        """Create CLASSIFIED_AS relationship between Finding and CWE.
        
        Args:
            finding_id: UUID of DiscoveredVulnerability
            cwe_id: CWE identifier (e.g., "CWE-89")
            
        Returns:
            Dictionary with result
        """
        async with self.driver.session() as session:
            result = await session.execute_write(
                self._create_finding_cwe_relationship_tx,
                finding_id,
                cwe_id
            )
            return result

    async def _create_finding_cwe_relationship_tx(self, tx, finding_id: str, cwe_id: str):
        """Transaction for creating CLASSIFIED_AS relationship."""
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {id: $finding_id})
            MERGE (w:CWE {id: $cwe_id})
            MERGE (f)-[r:CLASSIFIED_AS]->(w)
            ON CREATE SET 
                r.created_at = datetime(),
                r.confidence = 0.90
            RETURN f.id as finding_id, w.id as cwe_id, type(r) as rel_type
            """
            
            result = await tx.run(cypher, finding_id=finding_id, cwe_id=cwe_id)
            record = await result.single()
            
            logger.info(
                f"Created CLASSIFIED_AS: {finding_id} -> {cwe_id}",
                extra={"finding_id": finding_id, "cwe_id": cwe_id}
            )
            
            return {"finding_id": finding_id, "cwe_id": cwe_id, "success": True, "error": None}
            
        except Exception as e:
            logger.error(
                f"Failed to create CWE relationship: {e}",
                extra={"finding_id": finding_id, "cwe_id": cwe_id}
            )
            return {"finding_id": finding_id, "cwe_id": cwe_id, "success": False, "error": str(e)}

    async def query_findings_by_severity(self, severity: str) -> List[Dict]:
        """Query findings by severity level.
        
        Args:
            severity: CRITICAL, HIGH, MEDIUM, LOW, or INFO
            
        Returns:
            List of finding dictionaries
        """
        async with self.driver.session() as session:
            result = await session.execute_read(
                self._query_findings_by_severity_tx,
                severity
            )
            return result

    async def _query_findings_by_severity_tx(self, tx, severity: str):
        """Transaction for querying by severity."""
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {severity: $severity})
            OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
            OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
            RETURN f.id as id, f.template_id as template_id, f.severity as severity,
                   f.host as host, f.url as url, f.matched_at as matched_at,
                   collect(c.id) as cve_ids, collect(w.id) as cwe_ids
            ORDER BY f.matched_at DESC
            """
            
            result = await tx.run(cypher, severity=severity)
            records = await result.fetch(1000)  # Limit to 1000 results
            
            return [dict(record) for record in records]
            
        except Exception as e:
            logger.error(f"Query by severity failed: {e}")
            return []

    async def query_findings_by_host(self, host: str) -> List[Dict]:
        """Query findings by host.
        
        Args:
            host: Host/IP address
            
        Returns:
            List of finding dictionaries
        """
        async with self.driver.session() as session:
            result = await session.execute_read(
                self._query_findings_by_host_tx,
                host
            )
            return result

    async def _query_findings_by_host_tx(self, tx, host: str):
        """Transaction for querying by host."""
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {host: $host})
            OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
            OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
            RETURN f.id as id, f.template_id as template_id, f.severity as severity,
                   f.host as host, f.url as url, f.matched_at as matched_at,
                   collect(c.id) as cve_ids, collect(w.id) as cwe_ids
            ORDER BY f.matched_at DESC
            """
            
            result = await tx.run(cypher, host=host)
            records = await result.fetch(1000)
            
            return [dict(record) for record in records]
            
        except Exception as e:
            logger.error(f"Query by host failed: {e}")
            return []

    async def query_findings_by_template(self, template_id: str) -> List[Dict]:
        """Query findings by template ID.
        
        Args:
            template_id: Nuclei template identifier
            
        Returns:
            List of finding dictionaries
        """
        async with self.driver.session() as session:
            result = await session.execute_read(
                self._query_findings_by_template_tx,
                template_id
            )
            return result

    async def _query_findings_by_template_tx(self, tx, template_id: str):
        """Transaction for querying by template."""
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {template_id: $template_id})
            OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
            OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
            RETURN f.id as id, f.template_id as template_id, f.severity as severity,
                   f.host as host, f.url as url, f.matched_at as matched_at,
                   collect(c.id) as cve_ids, collect(w.id) as cwe_ids
            """
            
            result = await tx.run(cypher, template_id=template_id)
            records = await result.fetch(1000)
            
            return [dict(record) for record in records]
            
        except Exception as e:
            logger.error(f"Query by template failed: {e}")
            return []

    async def get_finding_by_id(self, finding_id: str) -> Optional[Dict]:
        """Get a specific finding by ID.
        
        Args:
            finding_id: UUID of the finding
            
        Returns:
            Finding dictionary or None
        """
        async with self.driver.session() as session:
            result = await session.execute_read(
                self._get_finding_by_id_tx,
                finding_id
            )
            return result

    async def _get_finding_by_id_tx(self, tx, finding_id: str):
        """Transaction for getting finding by ID."""
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {id: $finding_id})
            OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
            OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
            RETURN f.id as id, f.template_id as template_id, f.severity as severity,
                   f.host as host, f.url as url, f.matched_at as matched_at,
                   f.source as source, f.metadata as metadata,
                   collect(c.id) as cve_ids, collect(w.id) as cwe_ids
            """
            
            result = await tx.run(cypher, finding_id=finding_id)
            record = await result.single()
            
            return dict(record) if record else None
            
        except Exception as e:
            logger.error(f"Get finding by ID failed: {e}")
            return None

    async def delete_findings_by_template(self, template_id: str) -> Dict:
        """Delete all findings for a specific template.
        
        Args:
            template_id: Nuclei template identifier
            
        Returns:
            Dictionary with deletion statistics
        """
        async with self.driver.session() as session:
            result = await session.execute_write(
                self._delete_findings_by_template_tx,
                template_id
            )
            return result

    async def _delete_findings_by_template_tx(self, tx, template_id: str):
        """Transaction for deleting findings by template."""
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {template_id: $template_id})
            DETACH DELETE f
            RETURN count(f) as deleted_count
            """
            
            result = await tx.run(cypher, template_id=template_id)
            summary = await result.consume()
            
            # Count deleted nodes from summary
            deleted_count = summary.counters.nodes_deleted if summary.counters else 0
            
            logger.info(
                f"Deleted findings by template: {template_id}",
                extra={"deleted_count": deleted_count}
            )
            
            return {
                "template_id": template_id,
                "deleted_count": deleted_count,
                "success": True,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Delete findings failed: {e}")
            return {
                "template_id": template_id,
                "deleted_count": 0,
                "success": False,
                "error": str(e)
            }

    # ==================== Phase 6: Hybrid Search & Statistics ====================

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def hybrid_search(self, query: str, limit: int = 20, offset: int = 0, scope: str = "mixed") -> Dict:
        """Perform hybrid search across knowledge base and findings.
        
        Args:
            query: Search query string
            limit: Maximum results to return
            offset: Pagination offset
            scope: Search scope (mixed, knowledge_only, findings_only)
            
        Returns:
            Dictionary with search results
        """
        async with self.driver.session() as session:
            result = await session.execute_read(
                self._hybrid_search_tx,
                query,
                limit,
                offset,
                scope
            )
            return result

    async def _hybrid_search_tx(self, tx, query: str, limit: int, offset: int, scope: str):
        """Transaction for hybrid search."""
        try:
            results = []
            query_lower = query.lower()

            if scope in ["mixed", "knowledge_only"]:
                # Search knowledge base (CVE, CWE)
                cypher_knowledge = """
                MATCH (n)
                WHERE (labels(n) IN [['CVE'], ['CWE']] OR any(label IN labels(n) WHERE label IN ['CVE', 'CWE']))
                AND (toLower(n.id) CONTAINS $query OR toLower(toString(n.name)) CONTAINS $query 
                     OR toLower(toString(n.description)) CONTAINS $query)
                RETURN n.id as id, labels(n) as labels, properties(n) as properties, 'knowledge' as source
                SKIP $offset LIMIT $limit
                """
                result_knowledge = await tx.run(cypher_knowledge, query=query_lower, offset=offset, limit=limit)
                records_knowledge = await result_knowledge.fetch(limit)
                results.extend([dict(record) for record in records_knowledge])

            if scope in ["mixed", "findings_only"]:
                # Search findings
                cypher_findings = """
                MATCH (f:DiscoveredVulnerability)
                WHERE toLower(f.url) CONTAINS $query OR toLower(f.host) CONTAINS $query 
                      OR toLower(f.template_id) CONTAINS $query
                OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
                OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
                RETURN f.id as id, labels(f) as labels, properties(f) as properties, 'finding' as source
                SKIP $offset LIMIT $limit
                """
                result_findings = await tx.run(cypher_findings, query=query_lower, offset=offset, limit=limit)
                records_findings = await result_findings.fetch(limit)
                results.extend([dict(record) for record in records_findings])

            logger.info(f"Hybrid search completed: query={query}, results={len(results)}")
            return {"query": query, "results": results[:limit], "total": len(results)}

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return {"query": query, "results": [], "error": str(e), "total": 0}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_graph_statistics(self) -> Dict:
        """Get comprehensive graph statistics.
        
        Returns:
            Dictionary with graph statistics
        """
        async with self.driver.session() as session:
            result = await session.execute_read(self._get_statistics_tx)
            return result

    async def _get_statistics_tx(self, tx):
        """Transaction for getting statistics."""
        try:
            stats = {
                "total_nodes": 0,
                "total_relationships": 0,
                "by_label": {},
                "by_relationship_type": {},
                "cve_count": 0,
                "cwe_count": 0,
                "discovered_vulnerability_count": 0
            }

            # Node counts by label
            cypher_nodes = """
            MATCH (n) RETURN labels(n) as labels, count(n) as count
            """
            result_nodes = await tx.run(cypher_nodes)
            records_nodes = await result_nodes.fetch(100)

            for record in records_nodes:
                labels = record["labels"]
                count = record["count"]
                stats["total_nodes"] += count

                if labels:
                    label_str = "|".join(labels)
                    stats["by_label"][label_str] = count

                    if "CVE" in labels:
                        stats["cve_count"] += count
                    if "CWE" in labels:
                        stats["cwe_count"] += count
                    if "DiscoveredVulnerability" in labels:
                        stats["discovered_vulnerability_count"] += count

            # Relationship counts
            cypher_rels = """
            MATCH ()-[r]->() RETURN type(r) as rel_type, count(r) as count
            """
            result_rels = await tx.run(cypher_rels)
            records_rels = await result_rels.fetch(100)

            for record in records_rels:
                rel_type = record["rel_type"]
                count = record["count"]
                stats["total_relationships"] += count
                stats["by_relationship_type"][rel_type] = count

            logger.info(f"Graph statistics: {stats['total_nodes']} nodes, {stats['total_relationships']} relationships")
            return stats

        except Exception as e:
            logger.error(f"Get statistics failed: {e}")
            return {"error": str(e)}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_schema_info(self) -> Dict:
        """Get graph schema information.
        
        Returns:
            Dictionary with schema information
        """
        async with self.driver.session() as session:
            result = await session.execute_read(self._get_schema_info_tx)
            return result

    async def _get_schema_info_tx(self, tx):
        """Transaction for getting schema info."""
        try:
            schema_info = {
                "labels": [],
                "relationship_types": [],
                "constraints": [],
                "indexes": []
            }

            # Get labels
            cypher_labels = """
            CALL db.labels() YIELD label RETURN collect(label) as labels
            """
            result_labels = await tx.run(cypher_labels)
            record_labels = await result_labels.single()
            if record_labels:
                schema_info["labels"] = record_labels["labels"]

            # Get relationship types
            cypher_rels = """
            CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) as types
            """
            result_rels = await tx.run(cypher_rels)
            record_rels = await result_rels.single()
            if record_rels:
                schema_info["relationship_types"] = record_rels["types"]

            logger.info(f"Schema info retrieved: {len(schema_info['labels'])} labels, {len(schema_info['relationship_types'])} relationship types")
            return schema_info

        except Exception as e:
            logger.error(f"Get schema info failed: {e}")
            return {"error": str(e)}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def execute_cypher_query(self, query: str, parameters: Dict = None) -> Dict:
        """Execute custom Cypher query.
        
        Args:
            query: Cypher query string
            parameters: Query parameters dictionary
            
        Returns:
            Dictionary with query results
        """
        if parameters is None:
            parameters = {}

        async with self.driver.session() as session:
            result = await session.execute_read(
                self._execute_cypher_query_tx,
                query,
                parameters
            )
            return result

    async def _execute_cypher_query_tx(self, tx, query: str, parameters: Dict):
        """Transaction for executing Cypher query."""
        try:
            result = await tx.run(query, **parameters)
            records = await result.fetch(1000)

            columns = []
            if records:
                columns = list(records[0].keys())

            logger.info(f"Cypher query executed: {len(records)} results")
            return {
                "query": query,
                "columns": columns,
                "results": [dict(record) for record in records],
                "total": len(records)
            }

        except Exception as e:
            logger.error(f"Execute Cypher query failed: {e}")
            return {"query": query, "error": str(e), "results": []}

    # ==================== Phase 11: KG Completion helpers ====================

    async def get_low_degree_entities(self, max_degree: int = 2, limit: int = 30) -> List[Dict]:
        """Return entities that have few relationships (candidates for KG completion)."""
        async with self.driver.session() as session:
            result = await session.execute_read(
                self._get_low_degree_entities_tx, max_degree, limit
            )
            return result

    async def _get_low_degree_entities_tx(self, tx, max_degree: int, limit: int) -> List[Dict]:
        cypher = """
        MATCH (n)
        WHERE NOT n:DiscoveredVulnerability
        WITH n, size([(n)--() | 1]) AS degree
        WHERE degree <= $max_degree
        RETURN n.id AS id, labels(n) AS labels, properties(n) AS props, degree
        ORDER BY degree ASC
        LIMIT $limit
        """
        result = await tx.run(cypher, max_degree=max_degree, limit=limit)
        records = await result.fetch(limit)
        return [dict(r) for r in records]

    async def get_entity_neighbors(self, entity_id: str, hops: int = 1) -> List[Dict]:
        """Return neighbors of an entity for KG completion context."""
        async with self.driver.session() as session:
            result = await session.execute_read(
                self._get_entity_neighbors_tx, entity_id, hops
            )
            return result

    async def _get_entity_neighbors_tx(self, tx, entity_id: str, hops: int) -> List[Dict]:
        cypher = f"""
        MATCH (n {{id: $entity_id}})-[r*1..{hops}]-(neighbor)
        RETURN DISTINCT neighbor.id AS id, labels(neighbor) AS labels,
               properties(neighbor) AS props,
               type(last(r)) AS last_rel_type
        LIMIT 20
        """
        result = await tx.run(cypher, entity_id=entity_id)
        records = await result.fetch(20)
        return [dict(r) for r in records]

    async def upsert_inferred_relation(
        self, source_id: str, target_id: str, rel_type: str, confidence: float
    ) -> Dict:
        """Store an LLM-predicted relation with inferred=True flag."""
        async with self.driver.session() as session:
            result = await session.execute_write(
                self._upsert_inferred_relation_tx, source_id, target_id, rel_type, confidence
            )
            return result

    async def _upsert_inferred_relation_tx(
        self, tx, source_id: str, target_id: str, rel_type: str, confidence: float
    ) -> Dict:
        rel_type_upper = rel_type.upper().replace(" ", "_")
        cypher = f"""
        MATCH (s) WHERE s.id = $source_id
        MATCH (t) WHERE t.id = $target_id
        MERGE (s)-[r:{rel_type_upper}]->(t)
        ON CREATE SET r.confidence = $confidence, r.inferred = true, r.created_at = datetime()
        ON MATCH SET  r.confidence = CASE WHEN r.inferred THEN $confidence ELSE r.confidence END,
                      r.updated_at = datetime()
        RETURN type(r) AS rel_type, r.inferred AS inferred
        """
        result = await tx.run(cypher, source_id=source_id, target_id=target_id, confidence=confidence)
        record = await result.single()
        return {"source_id": source_id, "target_id": target_id,
                "rel_type": rel_type_upper, "success": record is not None}

    async def get_entity_sample_for_completion(self, limit: int = 50) -> List[Dict]:
        """Sample entities as candidates for relation prediction context."""
        async with self.driver.session() as session:
            result = await session.execute_read(self._get_entity_sample_tx, limit)
            return result

    async def _get_entity_sample_tx(self, tx, limit: int) -> List[Dict]:
        cypher = """
        MATCH (n)
        WHERE n.id IS NOT NULL AND n.name IS NOT NULL
        RETURN n.id AS id, labels(n)[0] AS label, n.name AS name
        ORDER BY rand()
        LIMIT $limit
        """
        result = await tx.run(cypher, limit=limit)
        records = await result.fetch(limit)
        return [dict(r) for r in records]

    # ==================== Phase 12: GNN / Risk scoring via GDS ====================

    async def compute_pagerank_scores(self, project_name: str = "pentest-graph") -> Dict:
        """
        Run PageRank via Neo4j GDS. Falls back to degree-based scoring if GDS unavailable.
        GDS and fallback use separate sessions so a failed GDS transaction does not
        contaminate the fallback write.
        """
        try:
            async with self.driver.session() as session:
                result = await session.execute_write(self._compute_pagerank_gds_tx, project_name)
                return result
        except Exception as gds_error:
            logger.warning("GDS PageRank failed, using degree fallback", error=str(gds_error))

        # Fresh session for fallback — previous failed tx is fully discarded
        async with self.driver.session() as session:
            result = await session.execute_write(self._compute_pagerank_fallback_tx)
            return result

    async def _compute_pagerank_gds_tx(self, tx, project_name: str) -> Dict:
        """GDS PageRank — raises on failure so caller opens a fresh session for fallback."""
        await tx.run(f"""
            CALL gds.graph.project.cypher(
                '{project_name}',
                'MATCH (n) WHERE n.id IS NOT NULL RETURN id(n) AS id',
                'MATCH (s)-[r]->(t) WHERE s.id IS NOT NULL AND t.id IS NOT NULL
                 RETURN id(s) AS source, id(t) AS target'
            ) YIELD graphName
        """)
        result = await tx.run(f"""
            CALL gds.pageRank.write('{project_name}', {{
                writeProperty: 'pagerank_score',
                maxIterations: 20,
                dampingFactor: 0.85
            }}) YIELD nodePropertiesWritten, ranIterations
            RETURN nodePropertiesWritten, ranIterations
        """)
        record = await result.single()
        await tx.run(f"CALL gds.graph.drop('{project_name}', false) YIELD graphName")
        written = record["nodePropertiesWritten"] if record else 0
        logger.info("GDS PageRank completed", nodes_updated=written)
        return {"method": "gds_pagerank", "nodes_updated": written}

    async def _compute_pagerank_fallback_tx(self, tx) -> Dict:
        """Degree-based fallback: normalize to (0,1) via d/(d+10).
        d=5→0.33, d=10→0.50, d=50→0.83, d=100→0.91 — always bounded.
        """
        result = await tx.run("""
            MATCH (n)
            WITH n, size([(n)--() | 1]) AS degree
            SET n.pagerank_score = toFloat(degree) / (toFloat(degree) + 10.0)
            RETURN count(n) AS updated
        """)
        rec = await result.single()
        updated = rec["updated"] if rec else 0
        logger.info("Degree fallback pagerank written", nodes=updated)
        return {"method": "degree_fallback", "nodes_updated": updated}

    async def compute_betweenness_scores(self, project_name: str = "pentest-graph-bc") -> Dict:
        """Betweenness centrality — identifies bottleneck/pivot nodes.
        Skipped silently when GDS is not installed.
        """
        try:
            async with self.driver.session() as session:
                return await session.execute_write(self._compute_betweenness_gds_tx, project_name)
        except Exception as exc:
            logger.warning("GDS betweenness failed, skipping", error=str(exc))
            return {"method": "skipped", "nodes_updated": 0}

    async def _compute_betweenness_gds_tx(self, tx, project_name: str) -> Dict:
        """GDS Betweenness Centrality — raises on failure so caller can skip gracefully."""
        await tx.run(f"""
            CALL gds.graph.project.cypher(
                '{project_name}',
                'MATCH (n) WHERE n.id IS NOT NULL RETURN id(n) AS id',
                'MATCH (s)-[r]->(t) RETURN id(s) AS source, id(t) AS target'
            ) YIELD graphName
        """)
        result = await tx.run(f"""
            CALL gds.betweenness.write('{project_name}', {{writeProperty: 'betweenness_score'}})
            YIELD nodePropertiesWritten
            RETURN nodePropertiesWritten
        """)
        record = await result.single()
        await tx.run(f"CALL gds.graph.drop('{project_name}', false) YIELD graphName")
        written = record["nodePropertiesWritten"] if record else 0
        return {"method": "gds_betweenness", "nodes_updated": written}

    async def get_high_risk_nodes(self, limit: int = 20) -> List[Dict]:
        """Return top-N nodes ranked by blended risk_score (Phase 12).
        Falls back to pagerank_score if compute_risk_scores has not been called yet.
        """
        async with self.driver.session() as session:
            result = await session.execute_read(self._get_high_risk_nodes_tx, limit)
            return result

    async def _get_high_risk_nodes_tx(self, tx, limit: int) -> List[Dict]:
        cypher = """
        MATCH (n)
        WHERE n.pagerank_score IS NOT NULL
        WITH n,
             coalesce(n.risk_score, n.pagerank_score) AS effective_risk
        RETURN n.id AS id, labels(n)[0] AS label, n.name AS name,
               effective_risk AS risk_score,
               coalesce(n.betweenness_score, 0.0) AS betweenness,
               coalesce(n.severity, 'unknown') AS severity,
               n.cvss_score AS cvss_score
        ORDER BY effective_risk DESC
        LIMIT $limit
        """
        result = await tx.run(cypher, limit=limit)
        records = await result.fetch(limit)
        return [dict(r) for r in records]

    async def find_attack_paths(
        self,
        source_id: str,
        target_label: str = "CVE",
        max_hops: int = 4,
    ) -> List[Dict]:
        """Find shortest paths from a source node to nodes with a given label."""
        async with self.driver.session() as session:
            result = await session.execute_read(
                self._find_attack_paths_tx, source_id, target_label, max_hops
            )
            return result

    async def _find_attack_paths_tx(
        self, tx, source_id: str, target_label: str, max_hops: int
    ) -> List[Dict]:
        cypher = f"""
        MATCH path = (src {{id: $source_id}})-[*1..{max_hops}]->(tgt:{target_label})
        WITH path, tgt,
             [node IN nodes(path) | coalesce(node.name, node.id)] AS node_names,
             [rel  IN relationships(path) | type(rel)] AS rel_types,
             length(path) AS hops
        ORDER BY hops ASC
        LIMIT 10
        RETURN node_names, rel_types, hops,
               tgt.id AS target_id, tgt.name AS target_name,
               coalesce(tgt.risk_score, tgt.cvss_score, tgt.pagerank_score, 0.1) AS target_risk
        """
        result = await tx.run(cypher, source_id=source_id)
        records = await result.fetch(10)
        return [dict(r) for r in records]

    async def get_risk_summary(self) -> Dict:
        """Overall risk picture: counts by severity + top-risk nodes."""
        async with self.driver.session() as session:
            return await session.execute_read(self._risk_summary_tx)

    async def _risk_summary_tx(self, tx) -> Dict:
        cypher = """
        MATCH (n)
        WITH
          count(CASE WHEN n.severity = 'critical' THEN 1 END) AS critical,
          count(CASE WHEN n.severity = 'high'     THEN 1 END) AS high,
          count(CASE WHEN n.severity = 'medium'   THEN 1 END) AS medium,
          count(CASE WHEN n.severity = 'low'      THEN 1 END) AS low,
          count(CASE WHEN n.pagerank_score IS NOT NULL THEN 1 END) AS nodes_scored
        RETURN critical, high, medium, low, nodes_scored
        """
        result = await tx.run(cypher)
        record = await result.single()
        return dict(record) if record else {}