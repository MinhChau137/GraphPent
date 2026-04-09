"""Weaviate Adapter - Vector retrieval cho Phase 7."""

import weaviate
from weaviate.classes.query import MetadataQuery
from typing import List, Dict
from app.config.settings import settings
from app.core.logger import logger
import asyncio

class WeaviateAdapter:
    def __init__(self):
        try:
            self.client = weaviate.connect_to_local(
                host="weaviate",
                port=8080,
                grpc_port=50051
            )
            self._ensure_collection()
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            self.client = None

    def _ensure_collection(self):
        """Ensure docs_chunks collection exists."""
        try:
            if not self.client.collections.exists("docs_chunks"):
                self.client.collections.create(
                    name="docs_chunks",
                    vectorizer_config=None,  # Manual vectors
                    properties=[
                        {"name": "content", "dataType": ["text"]},
                        {"name": "metadata", "dataType": ["object"]},
                        {"name": "chunk_id", "dataType": ["int"]},
                    ]
                )
                logger.info("Created docs_chunks collection")
        except Exception as e:
            logger.warning("Could not ensure collection", error=str(e))

    def close(self):
        if self.client:
            self.client.close()

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using Ollama."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": settings.EMBEDDING_MODEL, "prompt": text}
            )
            response.raise_for_status()
            return response.json()["embedding"]

    async def upsert_chunk(self, chunk_id: int, content: str, metadata: Dict = None) -> str:
        """Upsert chunk vào Weaviate với embedding."""
        if not self.client:
            logger.warning("Weaviate client not available, skipping upsert")
            return str(chunk_id)
            
        try:
            collection = self.client.collections.get("docs_chunks")
            
            # Generate embedding
            embedding = await self.generate_embedding(content)
            
            # Prepare data
            data = {
                "content": content,
                "metadata": metadata or {},
                "chunk_id": chunk_id
            }
            
            # Upsert
            result = collection.data.insert(
                properties=data,
                vector=embedding,
                uuid=str(chunk_id)
            )
            
            logger.info("Chunk upserted to Weaviate", chunk_id=chunk_id, uuid=result)
            return result
            
        except Exception as e:
            logger.error("Failed to upsert chunk to Weaviate", chunk_id=chunk_id, error=str(e))
            raise

    async def vector_search(self, query: str, limit: int = 10) -> List[Dict]:
        """Vector search trên collection docs_chunks."""
        if not self.client:
            logger.warning("Weaviate client not available")
            return []
            
        try:
            collection = self.client.collections.get("docs_chunks")
            
            # Generate query embedding
            query_embedding = await self.generate_embedding(query)
            
            response = collection.query.near_vector(
                near_vector=query_embedding,
                limit=limit,
                return_metadata=MetadataQuery(distance=True, certainty=True)
            )

            results = []
            for obj in response.objects:
                results.append({
                    "id": str(obj.properties.get("chunk_id", obj.uuid)),
                    "content": obj.properties.get("content"),
                    "metadata": obj.properties.get("metadata", {}),
                    "vector_score": 1 - (obj.metadata.distance or 0.0)
                })
            logger.info("Vector search completed", results_count=len(results))
            return results
            
        except Exception as e:
            logger.error("Vector search failed", error=str(e))
            return []