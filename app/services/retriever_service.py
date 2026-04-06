"""Hybrid Retriever Service - Phase 7."""

from typing import List, Dict, Any
from app.adapters.weaviate_client import WeaviateAdapter
from app.adapters.neo4j_client import Neo4jAdapter
from app.core.logger import logger
from app.core.security import audit_log
from tenacity import retry, stop_after_attempt, wait_exponential

class HybridRetrieverService:
    def __init__(self):
        self.weaviate = WeaviateAdapter()
        self.neo4j = Neo4jAdapter()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def hybrid_retrieve(self, query: str, limit: int = 15, alpha: float = 0.7) -> List[Dict]:
        """Hybrid retrieval + fusion rerank."""
        await audit_log("hybrid_retrieve_start", {"query": query[:100], "limit": limit})

        # 1. Vector retrieval
        vector_results = await self.weaviate.vector_search(query, limit=limit)

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
        """Graph traversal đơn giản (tìm entity gần query)."""
        async with self.neo4j.driver.session() as session:
            cypher = """
            CALL db.index.fulltext.queryNodes("entityNameIndex", $query, {limit: $limit})
            YIELD node, score
            RETURN node.id as id, node.name as name, labels(node)[0] as type, 
                   score as graph_score, node.provenance as provenance
            """
            result = await session.run(cypher, query=query, limit=limit)
            records = await result.data()
            return [{
                "id": r["id"],
                "content": f"{r['type']}: {r['name']}",
                "metadata": {"type": r["type"], "provenance": r.get("provenance")},
                "graph_score": float(r["graph_score"])
            } for r in records]

    def _fusion_rerank(self, vector_results: List[Dict], graph_results: List[Dict], alpha: float = 0.7) -> List[Dict]:
        """Fusion rerank: vector_score * alpha + graph_score * (1-alpha) + freshness."""
        combined = {}

        # Vector results
        for v in vector_results:
            key = v["id"]
            combined[key] = {
                **v,
                "graph_score": 0.0,
                "final_score": v.get("vector_score", 0.0) * alpha
            }

        # Graph results
        for g in graph_results:
            key = g["id"]
            if key in combined:
                combined[key]["graph_score"] = g["graph_score"]
                combined[key]["final_score"] = (
                    combined[key].get("vector_score", 0.0) * alpha +
                    g["graph_score"] * (1 - alpha)
                )
            else:
                combined[key] = {**g, "vector_score": 0.0, "final_score": g["graph_score"] * (1 - alpha)}

        # Sort by final_score
        sorted_results = sorted(combined.values(), key=lambda x: x["final_score"], reverse=True)
        return sorted_results