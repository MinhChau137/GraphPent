"""Weaviate Adapter - Vector retrieval cho Phase 7."""

import weaviate
from weaviate.classes.query import MetadataQuery
from typing import List, Dict
from app.config.settings import settings
from app.core.logger import logger

class WeaviateAdapter:
    def __init__(self):
        self.client = weaviate.connect_to_weaviate(
            settings.WEAVIATE_URL,
            auth_credentials=weaviate.auth.AuthApiKey(settings.WEAVIATE_API_KEY) if settings.WEAVIATE_API_KEY else None,
        )

    def close(self):
        self.client.close()

    async def vector_search(self, query: str, limit: int = 10) -> List[Dict]:
        """Vector search trên collection docs_chunks."""
        collection = self.client.collections.get("docs_chunks")
        
        response = collection.query.near_text(
            query=query,
            limit=limit,
            return_metadata=MetadataQuery(distance=True, certainty=True)
        )

        results = []
        for obj in response.objects:
            results.append({
                "id": obj.uuid,
                "content": obj.properties.get("content"),
                "metadata": obj.properties.get("metadata", {}),
                "vector_score": 1 - (obj.metadata.distance or 0.0)  # convert distance -> score
            })
        logger.info("Vector search completed", results_count=len(results))
        return results