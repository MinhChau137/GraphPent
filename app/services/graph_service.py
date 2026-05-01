"""Graph Service - Phase 6: Entity Resolution + Upsert + Hybrid Search."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from functools import lru_cache

from app.adapters.neo4j_client import Neo4jAdapter
from app.domain.schemas.extraction import ExtractionResult, Entity, Relation
from app.domain.schemas.graph import (
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResult,
    GraphStatistics,
    GraphSchemaResponse,
    GraphSchema,
    FindingKnowledgeLinkRequest,
    FindingKnowledgeLinkResponse,
    FindingKnowledgeLink,
    GraphQueryRequest,
    GraphQueryResponse,
    GraphHealthCheck,
)
from app.core.logger import logger
from app.core.security import audit_log


class GraphService:
    """Service for graph operations including hybrid search and statistics."""

    def __init__(self):
        self.neo4j = Neo4jAdapter()

    async def process_extraction_result(self, extraction_result: ExtractionResult) -> dict:
        """Xử lý kết quả extraction → upsert vào Neo4j với dedup."""
        if extraction_result.error:
            logger.warning("Skipping graph upsert due to extraction error", error=extraction_result.error)
            return {"status": "skipped", "reason": "extraction_error"}

        try:
            stats = await self.neo4j.upsert_entities_and_relations(
                extraction_result.entities,
                extraction_result.relations
            )

            await audit_log("graph_upsert_success", {
                "entities": stats["entities_upserted"],
                "relations": stats["relations_created"],
                "chunk_id": extraction_result.chunk_id
            })

            return {
                "status": "success",
                "entities_upserted": stats["entities_upserted"],
                "relations_upserted": stats["relations_created"]
            }

        except Exception as e:
            logger.error("Graph upsert failed", error=str(e), error_type=type(e).__name__)
            await audit_log("graph_upsert_failed", {"error": str(e), "error_type": type(e).__name__, "chunk_id": extraction_result.chunk_id})
            return {"status": "failed", "error": str(e)}

    # ==================== Phase 6: Hybrid Search ====================

    async def hybrid_search(self, search_request: HybridSearchRequest) -> HybridSearchResponse:
        """Perform hybrid search across knowledge base and findings.
        
        Args:
            search_request: Search request with query, filters, and scope
            
        Returns:
            Hybrid search response with mixed results
        """
        try:
            start_time = datetime.utcnow()

            # Execute hybrid search
            search_result = await self.neo4j.hybrid_search(
                query=search_request.query,
                limit=search_request.limit,
                offset=search_request.offset,
                scope=search_request.search_scope
            )

            # Convert results to HybridSearchResult objects
            hybrid_results = []
            knowledge_count = 0
            findings_count = 0

            for idx, result in enumerate(search_result.get("results", [])):
                source = result.get("source", "unknown")
                if source == "knowledge":
                    knowledge_count += 1
                else:
                    findings_count += 1

                hybrid_result = HybridSearchResult(
                    result_id=f"result-{idx}",
                    node={
                        "id": result.get("id"),
                        "labels": result.get("labels", []),
                        "properties": result.get("properties", {}),
                    },
                    node_type=source,
                    relevance_score=0.85,  # Default relevance score
                    related_findings=[],
                    related_knowledge=[],
                    relationships=[]
                )
                hybrid_results.append(hybrid_result)

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            response = HybridSearchResponse(
                query=search_request.query,
                total_results=len(hybrid_results),
                results=hybrid_results,
                knowledge_count=knowledge_count,
                findings_count=findings_count,
                execution_time_ms=execution_time,
                limit=search_request.limit,
                offset=search_request.offset,
                has_more=len(hybrid_results) >= search_request.limit
            )

            logger.info(
                f"Hybrid search completed: query={search_request.query}, results={len(hybrid_results)}",
                extra={"execution_time_ms": execution_time}
            )

            return response

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            raise

    # ==================== Phase 6: Graph Statistics ====================

    async def get_statistics(self) -> GraphStatistics:
        """Get comprehensive graph statistics.
        
        Returns:
            Graph statistics including node and relationship counts
        """
        try:
            stats_dict = await self.neo4j.get_graph_statistics()

            return GraphStatistics(
                total_nodes=stats_dict.get("total_nodes", 0),
                total_relationships=stats_dict.get("total_relationships", 0),
                by_label=stats_dict.get("by_label", {}),
                by_relationship_type=stats_dict.get("by_relationship_type", {}),
                cve_count=stats_dict.get("cve_count", 0),
                cwe_count=stats_dict.get("cwe_count", 0),
                discovered_vulnerability_count=stats_dict.get("discovered_vulnerability_count", 0),
                average_relationships_per_node=(
                    stats_dict.get("total_relationships", 0) / stats_dict.get("total_nodes", 1)
                    if stats_dict.get("total_nodes", 0) > 0
                    else 0
                ),
                created_at=datetime.utcnow()
            )

        except Exception as e:
            logger.error(f"Get statistics failed: {e}")
            raise

    # ==================== Phase 6: Graph Schema ====================

    async def get_schema(self) -> GraphSchemaResponse:
        """Get graph schema information.
        
        Returns:
            Graph schema response with labels, relationships, and constraints
        """
        try:
            schema_dict = await self.neo4j.get_schema_info()
            stats = await self.neo4j.get_graph_statistics()

            # Build schema entries
            schemas = []
            by_label = stats.get("by_label", {})

            for label in schema_dict.get("labels", []):
                count = by_label.get(label, 0)
                schemas.append(
                    GraphSchema(
                        label=label,
                        properties={},  # Would need more detailed schema query
                        relationships_out=schema_dict.get("relationship_types", []),
                        relationships_in=schema_dict.get("relationship_types", []),
                        count=count
                    )
                )

            return GraphSchemaResponse(
                schemas=schemas,
                total_labels=len(schema_dict.get("labels", [])),
                total_relationship_types=len(schema_dict.get("relationship_types", [])),
                indexes=[]
            )

        except Exception as e:
            logger.error(f"Get schema failed: {e}")
            raise

    # ==================== Phase 6: Finding-Knowledge Links ====================

    async def link_finding_to_knowledge(
        self,
        link_request: FindingKnowledgeLinkRequest
    ) -> FindingKnowledgeLinkResponse:
        """Link a finding to knowledge base (CVE/CWE).
        
        Args:
            link_request: Request with finding ID and optional CVE/CWE IDs
            
        Returns:
            Response with link results
        """
        try:
            linked_cves = 0
            linked_cwes = 0
            new_relationships = 0

            # Link to CVEs
            if link_request.cve_ids:
                for cve_id in link_request.cve_ids:
                    result = await self.neo4j.create_finding_cve_relationship(
                        link_request.finding_id,
                        cve_id
                    )
                    if result.get("success"):
                        linked_cves += 1
                        new_relationships += 1

            # Link to CWEs
            if link_request.cwe_ids:
                for cwe_id in link_request.cwe_ids:
                    result = await self.neo4j.create_finding_cwe_relationship(
                        link_request.finding_id,
                        cwe_id
                    )
                    if result.get("success"):
                        linked_cwes += 1
                        new_relationships += 1

            logger.info(
                f"Finding linked to knowledge: finding_id={link_request.finding_id}, "
                f"cves={linked_cves}, cwes={linked_cwes}"
            )

            return FindingKnowledgeLinkResponse(
                finding_id=link_request.finding_id,
                linked_cves=linked_cves,
                linked_cwes=linked_cwes,
                new_relationships=new_relationships,
                links=[
                    FindingKnowledgeLink(
                        finding_id=link_request.finding_id,
                        finding_severity="UNKNOWN",
                        linked_cves=link_request.cve_ids or [],
                        linked_cwes=link_request.cwe_ids or [],
                        confidence_scores={
                            "cve": 0.95,
                            "cwe": 0.90
                        }
                    )
                ]
            )

        except Exception as e:
            logger.error(f"Link finding to knowledge failed: {e}")
            raise

    # ==================== Phase 6: Custom Cypher Queries ====================

    async def execute_query(self, query_request: GraphQueryRequest) -> GraphQueryResponse:
        """Execute custom Cypher query.
        
        Args:
            query_request: Query request with Cypher query and parameters
            
        Returns:
            Query response with results
        """
        try:
            start_time = datetime.utcnow()

            result_dict = await self.neo4j.execute_cypher_query(
                query_request.query,
                query_request.parameters
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return GraphQueryResponse(
                query=query_request.query,
                execution_time_ms=execution_time,
                result_count=result_dict.get("total", 0),
                results=result_dict.get("results", []),
                columns=result_dict.get("columns", [])
            )

        except Exception as e:
            logger.error(f"Execute query failed: {e}")
            raise

    # ==================== Phase 6: Health Check ====================

    async def health_check(self) -> GraphHealthCheck:
        """Check graph system health.
        
        Returns:
            Health check status
        """
        try:
            start_time = datetime.utcnow()

            # Test connection and get stats
            stats = await self.neo4j.get_graph_statistics()
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            status = "healthy" if stats.get("total_nodes", 0) > 0 else "degraded"

            return GraphHealthCheck(
                status=status,
                neo4j_connection=True,
                node_count=stats.get("total_nodes", 0),
                relationship_count=stats.get("total_relationships", 0),
                indexes_active=0,  # Would need more detailed query
                last_update=datetime.utcnow(),
                response_time_ms=response_time
            )

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return GraphHealthCheck(
                status="offline",
                neo4j_connection=False,
                node_count=0,
                relationship_count=0,
                indexes_active=0,
                last_update=None,
                response_time_ms=0
            )

    async def close(self):
        await self.neo4j.close()


@lru_cache(maxsize=1)
async def get_graph_service() -> GraphService:
    """Get or create graph service singleton."""
    return GraphService()