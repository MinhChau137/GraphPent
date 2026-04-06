"""Extraction service - Phase 5."""

from sqlalchemy import select, update
from app.adapters.llm_client import LLMClient
from app.adapters.postgres import Chunk, AsyncSessionLocal
from app.domain.schemas.extraction import ExtractionResult
from app.core.logger import logger
from app.core.security import audit_log

class ExtractionService:
    def __init__(self):
        self.llm = LLMClient()

    async def extract_from_chunk(self, chunk_id: int) -> ExtractionResult:
        """Extract entities & relations từ một chunk."""
        await audit_log("extraction_start", {"chunk_id": chunk_id})

        async with AsyncSessionLocal() as session:
            # Lấy chunk
            result = await session.execute(select(Chunk).where(Chunk.id == chunk_id))
            chunk = result.scalar_one_or_none()

            if not chunk:
                raise ValueError(f"Chunk {chunk_id} not found")

            # Gọi LLM
            extraction_result = await self.llm.extract_entities_and_relations(chunk.content, chunk_id)

            # Lưu kết quả vào extraction_jobs (stub cho Phase sau)
            # TODO: Thêm bảng extraction_jobs và lưu entities_json

            if extraction_result.error:
                await audit_log("extraction_failed", {"chunk_id": chunk_id, "error": extraction_result.error})
                logger.error("Extraction failed", chunk_id=chunk_id, error=extraction_result.error)
            else:
                await audit_log("extraction_success", {
                    "chunk_id": chunk_id,
                    "entities": len(extraction_result.entities),
                    "relations": len(extraction_result.relations)
                })
                logger.info("LLM extraction successful", chunk_id=chunk_id, entities=len(extraction_result.entities), relations=len(extraction_result.relations))
                logger.info("Extraction completed", chunk_id=chunk_id, entities=len(extraction_result.entities))

            return extraction_result