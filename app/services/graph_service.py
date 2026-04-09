"""Graph Service - Phase 6: Entity Resolution + Upsert."""

from typing import List
from app.adapters.neo4j_client import Neo4jAdapter
from app.domain.schemas.extraction import ExtractionResult, Entity, Relation
from app.core.logger import logger
from app.core.security import audit_log

class GraphService:
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

    async def close(self):
        await self.neo4j.close()