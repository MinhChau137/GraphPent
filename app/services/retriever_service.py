"""Hybrid Retriever Service - Phase 7."""

from typing import List, Dict, Any
from app.adapters.weaviate_client import WeaviateAdapter
from app.adapters.neo4j_client import Neo4jAdapter
from app.core.logger import logger
from app.core.security import audit_log
from tenacity import retry, stop_after_attempt, wait_exponential

class MockWeaviateAdapter:
    """Mock adapter for when Weaviate is unavailable."""
    async def vector_search(self, query: str, limit: int = 10) -> List[Dict]:
        logger.warning("Weaviate is not available - returning empty vector results")
        return []

class HybridRetrieverService:
    def __init__(self):
        self._weaviate = None
        self._neo4j = None

    @property
    def weaviate(self):
        if self._weaviate is None:
            try:
                from app.adapters.weaviate_client import WeaviateAdapter
                self._weaviate = WeaviateAdapter()
            except Exception as e:
                logger.error(f"Failed to initialize WeaviateAdapter: {e}")
                # Return a mock adapter that raises errors
                self._weaviate = MockWeaviateAdapter()
        return self._weaviate

    @property
    def neo4j(self):
        if self._neo4j is None:
            from app.adapters.neo4j_client import Neo4jAdapter
            self._neo4j = Neo4jAdapter()
        return self._neo4j

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def hybrid_retrieve(self, query: str, limit: int = 15, alpha: float = 0.7) -> List[Dict]:
        """Hybrid retrieval + fusion rerank."""
        await audit_log("hybrid_retrieve_start", {"query": query[:100], "limit": limit})

        # 1. Vector retrieval (with fallback)
        vector_results = []
        try:
            vector_results = await self.weaviate.vector_search(query, limit=limit)
        except Exception as e:
            logger.warning(f"Weaviate vector search failed, falling back to graph-only: {e}")
            # Continue with graph-only retrieval

        # 2. Graph traversal (simple keyword + relation expansion)
        graph_results = await self._graph_traversal(query, limit=limit)

        # 3. Fusion + rerank
        fused = self._fusion_rerank(vector_results, graph_results, alpha=alpha)

        logger.info("Hybrid retrieval completed", 
                   vector_count=len(vector_results),
                   graph_count=len(graph_results),
                   fused_count=len(fused))

        await audit_log("hybrid_retrieve_success", {"results": len(fused)})
        return fused[:limit]

    async def _graph_traversal(self, query: str, limit: int) -> List[Dict]:
        """Graph traversal using fulltext index or fallback to CONTAINS."""
        logger.info(f"Starting graph traversal for query: {query}")
        try:
            async with self.neo4j.driver.session() as session:
                # Try fulltext index first
                try:
                    cypher = """
                    CALL db.index.fulltext.queryNodes("nodeSearch", $query) 
                    YIELD node, score
                    RETURN node.id as id, node.name as name, labels(node)[0] as type, 
                           node.provenance as provenance, score as relevance_score
                    ORDER BY score DESC
                    LIMIT $limit
                    """
                    result = await session.run(cypher, {"query": query, "limit": limit})
                    records = await result.data()
                    if records:
                        logger.info(f"Fulltext search found {len(records)} records")
                        results = [{
                            "id": r["id"],
                            "content": f"{r['type']}: {r['name']}",
                            "metadata": {"type": r["type"], "provenance": r.get("provenance")},
                            "graph_score": r.get("relevance_score", 0.8)
                        } for r in records]
                        return results
                except Exception as e:
                    logger.warning(f"Fulltext search failed, falling back to CONTAINS: {e}")
                
                # Fallback to CONTAINS search
                cypher = """
                MATCH (n)
                WHERE ANY(word IN split(toLower($query), ' ') 
                      WHERE toLower(n.name) CONTAINS word OR toLower(n.id) CONTAINS word)
                RETURN n.id as id, n.name as name, labels(n)[0] as type, 
                       n.provenance as provenance
                ORDER BY size([word IN split(toLower($query), ' ') 
                              WHERE toLower(n.name) CONTAINS word]) DESC
                LIMIT $limit
                """
                result = await session.run(cypher, {"query": query, "limit": limit})
                records = await result.data()
                logger.info(f"CONTAINS search found {len(records)} records")
                results = [{
                    "id": r["id"],
                    "content": f"{r['type']}: {r['name']}",
                    "metadata": {"type": r["type"], "provenance": r.get("provenance")},
                    "graph_score": 0.8
                } for r in records]
                return results
        except Exception as e:
            logger.error(f"Graph traversal failed: {e}")
            raise

    def _fusion_rerank(self, vector_results: List[Dict], graph_results: List[Dict], alpha: float = 0.7) -> List[Dict]:
        """Simple fusion of vector and graph results."""
        # For now, just combine and deduplicate by ID
        seen_ids = set()
        fused = []
        
        # Add vector results first (higher priority)
        for result in vector_results:
            if result["id"] not in seen_ids:
                result["final_score"] = result.get("vector_score", 0.5) * alpha
                fused.append(result)
                seen_ids.add(result["id"])
        
        # Add graph results
        for result in graph_results:
            if result["id"] not in seen_ids:
                result["final_score"] = result.get("graph_score", 0.5) * (1 - alpha)
                fused.append(result)
                seen_ids.add(result["id"])
        
        # Sort by final score
        fused.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        return fused

    def _fusion_rerank(self, vector_results: List[Dict], graph_results: List[Dict], alpha: float = 0.7) -> List[Dict]:
        """Improved fusion rerank: vector_score * alpha + graph_score * (1-alpha) + semantic boost."""
        combined = {}

        # Vector results
        for v in vector_results:
            key = v["id"]
            combined[key] = {
                **v,
                "graph_score": 0.0,
                "vector_score": v.get("vector_score", 0.0),
                "final_score": v.get("vector_score", 0.0) * alpha
            }

        # Graph results
        for g in graph_results:
            key = g["id"]
            if key in combined:
                combined[key]["graph_score"] = g.get("graph_score", 0.5)
                combined[key]["final_score"] = (
                    combined[key]["vector_score"] * alpha +
                    g["graph_score"] * (1 - alpha)
                )
                # Boost if both vector and graph match
                combined[key]["final_score"] += 0.1
            else:
                combined[key] = {
                    **g, 
                    "vector_score": 0.0, 
                    "final_score": g.get("graph_score", 0.5) * (1 - alpha)
                }

        # Sort by final_score descending
        sorted_results = sorted(combined.values(), key=lambda x: x["final_score"], reverse=True)
        return sorted_results