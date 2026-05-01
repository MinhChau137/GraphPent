"""Graph router - Phase 6: Neo4j Operations + Hybrid Search."""

import logging
from fastapi import APIRouter, HTTPException, status, Depends

from app.services.graph_service import GraphService, get_graph_service
from app.domain.schemas.extraction import ExtractionResult
from app.domain.schemas.graph import (
    HybridSearchRequest,
    HybridSearchResponse,
    GraphStatistics,
    GraphSchemaResponse,
    FindingKnowledgeLinkRequest,
    FindingKnowledgeLinkResponse,
    GraphQueryRequest,
    GraphQueryResponse,
    GraphHealthCheck,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/graph", tags=["Graph Operations"])


# ==================== Core Graph Operations ====================


@router.post("/upsert", status_code=status.HTTP_201_CREATED)
async def upsert_from_extraction(
    extraction_result: ExtractionResult,
    graph_service: GraphService = Depends(get_graph_service),
):
    """Upsert entities & relations từ extraction result.
    
    **Requires**: `graph:write` permission
    
    Takes extracted entities and relationships and stores them in Neo4j with
    automatic deduplication and relationship normalization.
    
    Example:
    ```json
    {
      "entities": [
        {"id": "uuid", "type": "CVE", "name": "CVE-2024-1234", "properties": {...}}
      ],
      "relations": [
        {"id": "uuid", "type": "RELATES_TO", "source_id": "source", "target_id": "target"}
      ]
    }
    ```
    """
    try:
        result = await graph_service.process_extraction_result(extraction_result)
        logger.info(f"Graph upsert: {result}")
        return result
    except Exception as e:
        logger.error(f"Graph upsert failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upsert to graph"
        )


# ==================== Hybrid Search ====================


@router.post("/search", response_model=HybridSearchResponse)
async def hybrid_search(
    search_request: HybridSearchRequest,
    graph_service: GraphService = Depends(get_graph_service),
):
    """Perform hybrid search across knowledge base and findings.
    
    **Requires**: `search:advanced` permission
    
    Searches both CVE/CWE knowledge base and discovered vulnerabilities from scans.
    Results can be filtered by severity, CVE/CWE IDs, hosts, and date range.
    
    Example:
    ```json
    {
      "query": "SQL Injection",
      "severity": "CRITICAL",
      "search_scope": "mixed",
      "limit": 20
    }
    ```
    """
    try:
        result = await graph_service.hybrid_search(search_request)
        logger.info(
            f"Hybrid search: query={search_request.query}, results={result.total_results}, "
            f"time={result.execution_time_ms}ms"
        )
        return result
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Hybrid search failed"
        )


# ==================== Graph Statistics ====================


@router.get("/statistics", response_model=GraphStatistics)
async def get_statistics(
    graph_service: GraphService = Depends(get_graph_service),
):
    """Get comprehensive graph statistics.
    
    **Requires**: `graph:read` permission
    
    Returns node counts by label, relationship counts by type, and overall metrics.
    """
    try:
        stats = await graph_service.get_statistics()
        logger.info(
            f"Graph statistics: nodes={stats.total_nodes}, "
            f"relationships={stats.total_relationships}"
        )
        return stats
    except Exception as e:
        logger.error(f"Get statistics failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get graph statistics"
        )


# ==================== Graph Schema ====================


@router.get("/schema", response_model=GraphSchemaResponse)
async def get_schema(
    graph_service: GraphService = Depends(get_graph_service),
):
    """Get graph schema information.
    
    **Requires**: `graph:read` permission
    
    Returns all node labels, relationship types, constraints, and indexes.
    """
    try:
        schema = await graph_service.get_schema()
        logger.info(
            f"Graph schema: labels={schema.total_labels}, "
            f"relationship_types={schema.total_relationship_types}"
        )
        return schema
    except Exception as e:
        logger.error(f"Get schema failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get graph schema"
        )


# ==================== Finding-Knowledge Links ====================


@router.post("/findings/{finding_id}/link-knowledge", response_model=FindingKnowledgeLinkResponse)
async def link_finding_to_knowledge(
    finding_id: str,
    link_request: FindingKnowledgeLinkRequest,
    graph_service: GraphService = Depends(get_graph_service),
):
    """Link a finding to knowledge base (CVE/CWE).
    
    **Requires**: `graph:write` permission
    
    Creates CORRELATES_TO relationships between findings and CVEs,
    and CLASSIFIED_AS relationships between findings and CWEs.
    
    Example:
    ```json
    {
      "finding_id": "uuid",
      "cve_ids": ["CVE-2024-1234", "CVE-2024-5678"],
      "cwe_ids": ["CWE-79", "CWE-89"]
    }
    ```
    """
    try:
        link_request.finding_id = finding_id
        result = await graph_service.link_finding_to_knowledge(link_request)
        logger.info(
            f"Finding linked: finding_id={finding_id}, "
            f"cves={result.linked_cves}, cwes={result.linked_cwes}"
        )
        return result
    except Exception as e:
        logger.error(f"Link finding failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to link finding to knowledge"
        )


# ==================== Custom Cypher Queries ====================


@router.post("/query", response_model=GraphQueryResponse)
async def execute_cypher_query(
    query_request: GraphQueryRequest,
    graph_service: GraphService = Depends(get_graph_service),
):
    """Execute custom Cypher query against the graph.
    
    **Requires**: `graph:admin` permission
    
    Allows executing arbitrary Cypher queries for advanced graph operations.
    Parameters are properly escaped to prevent injection.
    
    Example:
    ```json
    {
      "query": "MATCH (n:CVE) WHERE n.score > $min_score RETURN n LIMIT $limit",
      "parameters": {"min_score": 7.5, "limit": 100}
    }
    ```
    """
    try:
        result = await graph_service.execute_query(query_request)
        logger.info(
            f"Cypher query executed: results={result.result_count}, "
            f"time={result.execution_time_ms}ms"
        )
        return result
    except Exception as e:
        logger.error(f"Execute query failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute Cypher query"
        )


# ==================== Health Check ====================


@router.get("/health", response_model=GraphHealthCheck)
async def graph_health_check(
    graph_service: GraphService = Depends(get_graph_service),
):
    """Check graph system health.
    
    Returns Neo4j connection status, node/relationship counts, and response time.
    """
    try:
        health = await graph_service.health_check()
        logger.info(f"Graph health check: status={health.status}")
        return health
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph service unavailable"
        )