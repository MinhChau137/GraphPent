"""Extraction service - Phase 5."""

import re
from sqlalchemy import select, update
from app.adapters.llm_client import LLMClient
from app.adapters.postgres import Chunk, AsyncSessionLocal
from app.domain.schemas.extraction import ExtractionResult
from app.services.graph_service import GraphService
from app.core.logger import logger
from app.core.security import audit_log

class ExtractionService:
    def __init__(self):
        self.llm = LLMClient()
        self.graph_service = GraphService()

    def validate_entities(self, entities: list) -> list:
        """Validate entities have meaningful names, not just CWE IDs."""
        validated = []
        for entity in entities:
            name = entity.get("name", "").strip()
            entity_id = entity.get("id", "").strip()
            
            # Check if name is meaningful (not just CWE ID or empty)
            if not name or name.lower() == entity_id.lower() or re.match(r'^cwe-\d+$', name.lower()):
                # Try to create a meaningful name from ID or properties
                if entity.get("type") == "VulnerabilityType":
                    # For vulnerability types, create descriptive names
                    if "sql" in entity_id.lower() or "injection" in name.lower():
                        entity["name"] = "SQL Injection Vulnerability"
                    elif "xss" in entity_id.lower() or "cross-site" in name.lower():
                        entity["name"] = "Cross-Site Scripting (XSS) Vulnerability"
                    elif "buffer" in entity_id.lower() or "overflow" in name.lower():
                        entity["name"] = "Buffer Overflow Vulnerability"
                    else:
                        entity["name"] = f"{name} Vulnerability" if name else f"Unknown Vulnerability ({entity_id})"
                elif entity.get("type") == "Weakness":
                    # For weaknesses, keep CWE ID but add descriptive name if possible
                    if not name or name == entity_id:
                        entity["name"] = f"CWE Weakness {entity_id.split('-')[-1]}" if entity_id.startswith("cwe-") else name
                else:
                    # For other types, ensure name is not empty
                    if not name:
                        entity["name"] = f"Unknown {entity.get('type', 'Entity')} ({entity_id})"
            
            validated.append(entity)
        return validated

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

            # Validate entities for meaningful names
            if not extraction_result.error:
                extraction_result.entities = self.validate_entities([entity.dict() for entity in extraction_result.entities])
                # Convert back to Entity objects
                from app.domain.schemas.extraction import Entity
                extraction_result.entities = [Entity(**e) for e in extraction_result.entities]

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
                
                # Store in graph database
                try:
                    graph_stats = await self.graph_service.process_extraction_result(extraction_result)
                    logger.info("Graph upsert completed", chunk_id=chunk_id, **graph_stats)
                except Exception as e:
                    logger.error("Graph upsert failed", chunk_id=chunk_id, error=str(e))
                    raise
                
                logger.info("Extraction completed", chunk_id=chunk_id, entities=len(extraction_result.entities))

            return extraction_result

    async def extract_all_chunks(self, document_id: int) -> dict:
        """Extract entities & relations từ tất cả chunks của một document."""
        from sqlalchemy import select
        from app.adapters.postgres import Chunk, AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            # Lấy tất cả chunk IDs của document
            result = await session.execute(select(Chunk.id).where(Chunk.document_id == document_id))
            chunk_ids = [row[0] for row in result.fetchall()]
        
        logger.info(f"Starting batch extraction for document {document_id} with {len(chunk_ids)} chunks")
        
        total_entities = 0
        total_relations = 0
        successful_chunks = 0
        
        for i, chunk_id in enumerate(chunk_ids):
            try:
                logger.info(f"Processing chunk {i+1}/{len(chunk_ids)}: {chunk_id}")
                result = await self.extract_from_chunk(chunk_id)
                
                if not result.error:
                    total_entities += len(result.entities)
                    total_relations += len(result.relations)
                    successful_chunks += 1
                else:
                    logger.error(f"Failed to extract chunk {chunk_id}: {result.error}")
                    
            except Exception as e:
                logger.error(f"Exception extracting chunk {chunk_id}: {str(e)}")
        
        logger.info(f"Batch extraction completed: {successful_chunks}/{len(chunk_ids)} chunks successful, {total_entities} entities, {total_relations} relations")
        return {
            "document_id": document_id,
            "total_chunks": len(chunk_ids),
            "successful_chunks": successful_chunks,
            "total_entities": total_entities,
            "total_relations": total_relations
        }

    async def extract_all_chunks(self, document_id: int) -> dict:
        """Extract entities & relations từ tất cả chunks của một document."""
        from sqlalchemy import select
        from app.adapters.postgres import Chunk, AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            # Lấy tất cả chunk IDs của document
            result = await session.execute(select(Chunk.id).where(Chunk.document_id == document_id))
            chunk_ids = [row[0] for row in result.fetchall()]
        
        logger.info(f"Starting batch extraction for document {document_id} with {len(chunk_ids)} chunks")
        
        total_entities = 0
        total_relations = 0
        successful_chunks = 0
        
        for i, chunk_id in enumerate(chunk_ids):
            try:
                logger.info(f"Processing chunk {i+1}/{len(chunk_ids)}: {chunk_id}")
                result = await self.extract_from_chunk(chunk_id)
                
                if not result.error:
                    total_entities += len(result.entities)
                    total_relations += len(result.relations)
                    successful_chunks += 1
                else:
                    logger.error(f"Failed to extract chunk {chunk_id}: {result.error}")
                    
            except Exception as e:
                logger.error(f"Exception extracting chunk {chunk_id}: {str(e)}")
        
        logger.info(f"Batch extraction completed: {successful_chunks}/{len(chunk_ids)} chunks successful, {total_entities} entities, {total_relations} relations")
        return {
            "document_id": document_id,
            "total_chunks": len(chunk_ids),
            "successful_chunks": successful_chunks,
            "total_entities": total_entities,
            "total_relations": total_relations
        }