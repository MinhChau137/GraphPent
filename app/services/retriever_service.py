"""Hybrid Retriever Service - Phase 7 Complete."""

from typing import List, Dict, Any, Optional, Tuple
from app.adapters.weaviate_client import WeaviateAdapter
from app.adapters.neo4j_client import Neo4jAdapter
from app.core.logger import logger
from app.core.security import audit_log
from tenacity import retry, stop_after_attempt, wait_exponential
import json
import hashlib
from datetime import datetime, timedelta
import redis
from app.config.settings import settings

class MockWeaviateAdapter:
    """Mock adapter for when Weaviate is unavailable."""
    async def vector_search(self, query: str, limit: int = 10) -> List[Dict]:
        logger.warning("Weaviate is not available - returning empty vector results")
        return []

class HybridRetrieverService:
    """Phase 7: Hybrid retrieval with vector+graph fusion, caching, and analytics."""
    
    def __init__(self):
        self._weaviate = None
        self._neo4j = None
        self._redis_client = self._init_redis()

    def _init_redis(self) -> Optional[redis.Redis]:
        """Initialize Redis for caching (optional fallback)."""
        try:
            from redis import Redis
            client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
            client.ping()
            logger.info("Redis cache initialized")
            return client
        except Exception as e:
            logger.warning(f"Redis cache unavailable: {e}")
            return None

    @property
    def weaviate(self):
        if self._weaviate is None:
            try:
                from app.adapters.weaviate_client import WeaviateAdapter
                self._weaviate = WeaviateAdapter()
            except Exception as e:
                logger.error(f"Failed to initialize WeaviateAdapter: {e}")
                self._weaviate = MockWeaviateAdapter()
        return self._weaviate

    @property
    def neo4j(self):
        if self._neo4j is None:
            from app.adapters.neo4j_client import Neo4jAdapter
            self._neo4j = Neo4jAdapter()
        return self._neo4j

    def _get_cache_key(self, query: str, mode: str = "hybrid") -> str:
        """Generate cache key for query."""
        key_data = f"{query}:{mode}"
        hash_obj = hashlib.md5(key_data.encode())
        return f"retrieve:{hash_obj.hexdigest()}"

    async def _get_cached_results(self, cache_key: str) -> Optional[List[Dict]]:
        """Retrieve cached results (TTL: 1 hour)."""
        if not self._redis_client:
            return None
        try:
            cached = self._redis_client.get(cache_key)
            if cached:
                logger.info(f"Cache hit for {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")
        return None

    async def _cache_results(self, cache_key: str, results: List[Dict], ttl: int = 3600):
        """Cache results with TTL."""
        if not self._redis_client:
            return
        try:
            self._redis_client.setex(cache_key, ttl, json.dumps(results))
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def hybrid_retrieve(
        self,
        query: str,
        limit: int = 15,
        alpha: float = None,   # None → read from settings.RRF_ALPHA
        mode: str = "hybrid",
        use_cache: bool = True,
    ) -> List[Dict]:
        if alpha is None:
            alpha = getattr(settings, "RRF_ALPHA", 0.7)
        """
        Hybrid retrieval with 3 modes:
        - mode="hybrid" (alpha=0.7): vector 70% + graph 30%
        - mode="vector_only" (alpha=1.0): pure vector similarity
        - mode="graph_only" (alpha=0.0): pure graph traversal
        """
        await audit_log("retrieve_start", {
            "query": query[:100],
            "limit": limit,
            "alpha": alpha,
            "mode": mode
        })

        # Check cache
        cache_key = self._get_cache_key(query, mode)
        if use_cache:
            cached = await self._get_cached_results(cache_key)
            if cached:
                return cached[:limit]

        start_time = datetime.now()

        # 1. Vector retrieval (unless graph_only)
        vector_results = []
        if alpha > 0:
            try:
                vector_results = await self.weaviate.vector_search(query, limit=limit)
                logger.info(f"Vector search returned {len(vector_results)} results")
            except Exception as e:
                logger.warning(f"Vector search failed: {e}")

        # 2. Graph traversal (unless vector_only)
        graph_results = []
        if alpha < 1.0:
            try:
                graph_results = await self._graph_traversal(query, limit=limit)
                logger.info(f"Graph search returned {len(graph_results)} results")
            except Exception as e:
                logger.warning(f"Graph search failed: {e}")

        # 3. Fusion + rerank using RRF (Reciprocal Rank Fusion)
        fused = await self._fusion_rerank_rrf(vector_results, graph_results, alpha=alpha)

        # 4. Store analytics
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        await self._store_analytics({
            "query": query[:100],
            "mode": mode,
            "alpha": alpha,
            "vector_count": len(vector_results),
            "graph_count": len(graph_results),
            "result_count": len(fused),
            "latency_ms": elapsed_ms,
            "timestamp": datetime.now().isoformat()
        })

        logger.info("Hybrid retrieval completed", 
                   vector_count=len(vector_results),
                   graph_count=len(graph_results),
                   fused_count=len(fused),
                   latency_ms=f"{elapsed_ms:.1f}")

        # 5. Cache results
        final_results = fused[:limit]
        await self._cache_results(cache_key, final_results)

        await audit_log("retrieve_success", {"results": len(final_results), "latency_ms": elapsed_ms})
        return final_results

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

    async def _fusion_rerank_rrf(
        self,
        vector_results: List[Dict],
        graph_results: List[Dict],
        alpha: float = 0.7,
        k: float = None,   # None → read from settings.RRF_K
    ) -> List[Dict]:
        if k is None:
            k = float(getattr(settings, "RRF_K", 60.0))
        """
        RRF (Reciprocal Rank Fusion) algorithm for fusion.
        Formula: score = 1 / (k + rank)
        alpha controls the blend: alpha * vector_score + (1-alpha) * graph_score
        """
        combined = {}

        # Process vector results (rank from 0 to len-1)
        for idx, v_result in enumerate(vector_results):
            result_id = v_result["id"]
            vector_score = v_result.get("vector_score", 0.0)
            # RRF score for vector
            rrf_vector = 1.0 / (k + idx + 1)
            
            combined[result_id] = {
                **v_result,
                "vector_rank": idx,
                "vector_rrf": rrf_vector,
                "graph_rank": None,
                "graph_rrf": 0.0,
                "graph_score": 0.0,
                "vector_score": vector_score,
            }

        # Process graph results
        for idx, g_result in enumerate(graph_results):
            result_id = g_result["id"]
            graph_score = g_result.get("graph_score", 0.5)
            # RRF score for graph
            rrf_graph = 1.0 / (k + idx + 1)
            
            if result_id in combined:
                # Update existing entry
                combined[result_id]["graph_rank"] = idx
                combined[result_id]["graph_rrf"] = rrf_graph
                combined[result_id]["graph_score"] = graph_score
            else:
                # New entry
                combined[result_id] = {
                    **g_result,
                    "vector_rank": None,
                    "vector_rrf": 0.0,
                    "vector_score": 0.0,
                    "graph_rank": idx,
                    "graph_rrf": rrf_graph,
                    "graph_score": graph_score,
                }

        # Normalize graph_score to [0,1] so it's comparable with vector_score (cosine 0-1)
        max_graph = max((v["graph_score"] for v in combined.values()), default=1.0)
        max_graph = max(max_graph, 1e-9)
        for item in combined.values():
            item["graph_score_norm"] = item["graph_score"] / max_graph

        # Calculate final scores: pure RRF (rank-based, already normalized)
        for result_id, item in combined.items():
            # RRF fusion — only rank positions, no raw score bias
            final_rrf = (
                item["vector_rrf"] * alpha +
                item["graph_rrf"] * (1 - alpha)
            )
            # Normalized score fusion
            final_score = (
                item["vector_score"]      * alpha +
                item["graph_score_norm"]  * (1 - alpha)
            )
            # Final = average of rank-based RRF and normalized score blend
            item["final_score"] = (final_rrf + final_score) / 2.0
            item["final_rrf"] = final_rrf

        # Sort by final score
        sorted_results = sorted(combined.values(), key=lambda x: x["final_score"], reverse=True)
        return sorted_results

    async def _store_analytics(self, analytics: Dict):
        """Store retrieval analytics for dashboarding."""
        if not self._redis_client:
            return
        try:
            key = f"analytics:retrieve:{datetime.now().strftime('%Y-%m-%d')}"
            self._redis_client.lpush(key, json.dumps(analytics))
            self._redis_client.expire(key, 86400 * 30)  # 30 days retention
            logger.debug("Analytics stored", timestamp=analytics.get("timestamp"))
        except Exception as e:
            logger.warning(f"Analytics storage failed: {e}")

    async def get_retrieval_stats(self, hours: int = 24) -> Dict:
        """Get retrieval statistics for dashboard."""
        if not self._redis_client:
            return {"message": "Redis not available"}
        
        try:
            key_pattern = "analytics:retrieve:*"
            keys = self._redis_client.keys(key_pattern)
            
            stats = {
                "total_queries": 0,
                "avg_latency_ms": 0,
                "mode_distribution": {},
                "total_results_returned": 0,
                "cache_enabled": self._redis_client is not None
            }
            
            all_latencies = []
            
            for key in keys:
                data_list = self._redis_client.lrange(key, 0, -1)
                for data in data_list:
                    item = json.loads(data)
                    stats["total_queries"] += 1
                    stats["mode_distribution"][item.get("mode")] = \
                        stats["mode_distribution"].get(item.get("mode"), 0) + 1
                    stats["total_results_returned"] += item.get("result_count", 0)
                    all_latencies.append(item.get("latency_ms", 0))
            
            if all_latencies:
                stats["avg_latency_ms"] = sum(all_latencies) / len(all_latencies)
                stats["max_latency_ms"] = max(all_latencies)
                stats["min_latency_ms"] = min(all_latencies)
            
            return stats
        except Exception as e:
            logger.error(f"Stats retrieval failed: {e}")
            return {"error": str(e)}