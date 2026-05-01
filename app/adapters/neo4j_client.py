"""Neo4j Adapter - FINAL FIX Phase 6 (hỗ trợ mọi label + provenance) + Phase 3 (Nuclei findings)."""

from neo4j import AsyncGraphDatabase, AsyncDriver
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Dict, Optional
from app.config.settings import settings
from app.core.logger import logger
from app.domain.schemas.extraction import Entity, Relation

class Neo4jAdapter:
    def __init__(self):
        self.driver: AsyncDriver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    async def close(self):
        await self.driver.close()

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