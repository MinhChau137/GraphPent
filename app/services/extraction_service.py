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
        from app.config.settings import settings
        self._entity_threshold = getattr(settings, "ENTITY_CONFIDENCE_THRESHOLD", 0.85)
        self._relation_threshold = getattr(settings, "RELATION_CONFIDENCE_THRESHOLD", 0.75)

    def validate_entities(self, entities: list) -> list:
        """Validate entities: meaningful names + confidence >= 0.85 (STRICT).
        
        Entity validation ensures graph node quality:
        - Confidence >= 0.85 (HIGH threshold)
        - Meaningful names (not generic IDs or 'unknown-entity')
        - Sufficient properties
        """
        validated = []
        for entity in entities:
            name = entity.get("name", "").strip()
            entity_id = entity.get("id", "").strip()
            
            # STEP 0: REJECT unknown-entity names immediately (PRIORITY FIX)
            if name.lower() == "unknown-entity" or not name or len(name) < 2:
                logger.debug(f"❌ Entity {entity_id}: invalid/unknown name '{name}'")
                continue
            
            # STEP 1: Check confidence threshold (STRICT)
            provenance = entity.get("provenance", {})
            confidence = provenance.get("confidence", 0.85)
            if confidence < self._entity_threshold:
                logger.debug(f"❌ Entity {entity_id}: confidence={confidence:.2f} < {self._entity_threshold}")
                continue  # Skip low-confidence entities
            
            # STEP 2: Validate meaningful names (existing logic)
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

    def filter_relations_by_confidence(self, relations: list, entity_ids: set) -> list:
        """Filter relations with strict criteria to prevent orphaned edges (PRIORITY 2 FIX).
        
        Relation validation:
        - Confidence >= 0.75 (LOWERED from 0.85 for better coverage)
        - REQUIRE SOURCE entity to be local (strict: no floating edges)
        - TARGET can be external (enables cross-chunk references)
        - Skip relations where target entity is unknown/placeholder
        
        Returns: List of validated relations (guaranteed valid source & target)
        """
        filtered = []
        rejected = []
        
        for relation in relations:
            relation_id = relation.get('id', 'unknown')
            source_id = relation.get("source_id", "")
            target_id = relation.get("target_id", "")
            rel_type = relation.get("type", "UNKNOWN")
            
            # VALIDATION 1: Check confidence
            provenance = relation.get("provenance", {})
            confidence = provenance.get("confidence", 0.75)
            
            if confidence < self._relation_threshold:
                rejected.append(f"Rel {relation_id}: confidence={confidence:.2f} < {self._relation_threshold}")
                continue
            
            # VALIDATION 2: Require valid, non-empty IDs (no unknown placeholders)
            if not source_id or not target_id or "unknown" in source_id.lower() or "unknown" in target_id.lower():
                rejected.append(f"Rel {relation_id}: invalid/unknown IDs (src={source_id}, tgt={target_id})")
                continue
            
            # VALIDATION 3: Strict source requirement - source MUST be local
            source_local = source_id in entity_ids
            target_local = target_id in entity_ids
            
            if source_local:
                # VALID: Source is local (in current chunk)
                filtered.append(relation)
                if target_local:
                    logger.debug(f"✅ Rel {relation_id} ({rel_type}): LOCAL [{source_id}→{target_id}] conf={confidence:.2f}")
                else:
                    logger.debug(f"✓ Rel {relation_id} ({rel_type}): CROSS-CHUNK [{source_id}→{target_id}] conf={confidence:.2f}")
            else:
                # REJECT: Source not local (prevents floating/orphaned edges)
                rejected.append(f"Rel {relation_id}: source not local")
        
        # Log filtering summary
        if rejected:
            if len(rejected) <= 3:
                for reason in rejected:
                    logger.debug(f"❌ {reason}")
            else:
                logger.debug(f"❌ Filtered {len(rejected)} relations (low confidence or no local anchor)")
        
        logger.debug(f"✓ Relation filtering: {len(filtered)} accepted, {len(rejected)} rejected")
        return filtered

    async def extract_from_chunk(self, chunk_id: int) -> ExtractionResult:
        """Extract entities & relations từ một chunk."""
        await audit_log("extraction_start", {"chunk_id": chunk_id})

        async with AsyncSessionLocal() as session:
            # Lấy chunk
            result = await session.execute(select(Chunk).where(Chunk.id == chunk_id))
            chunk = result.scalar_one_or_none()

            if not chunk:
                raise ValueError(f"Chunk {chunk_id} not found")

            # Detect data type (CWE or CVE)
            data_type = self.llm._detect_data_type(chunk.content)
            
            # Call appropriate extraction method
            if data_type == "cve":
                logger.info("Detected CVE data, using CVE extraction", chunk_id=chunk_id)
                extraction_result = await self.llm.extract_entities_and_relations_from_cve(chunk.content, chunk_id)
            else:
                logger.info("Using CWE extraction", chunk_id=chunk_id)
                extraction_result = await self.llm.extract_entities_and_relations(chunk.content, chunk_id)

            # Validate entities & filter by confidence
            if not extraction_result.error:
                validated_entity_dicts = self.validate_entities([entity.dict() for entity in extraction_result.entities])
                entity_ids = {e.get("id") for e in validated_entity_dicts}
                
                # Filter relations by confidence & entity existence
                filtered_relation_dicts = self.filter_relations_by_confidence(
                    [r.dict() if hasattr(r, 'dict') else r for r in extraction_result.relations],
                    entity_ids
                )
                
                # Convert back to objects
                from app.domain.schemas.extraction import Entity, Relation
                extraction_result.entities = [Entity(**e) for e in validated_entity_dicts]
                extraction_result.relations = [Relation(**r) for r in filtered_relation_dicts]
                
                logger.debug(f"After confidence filtering: {len(extraction_result.entities)} entities, {len(extraction_result.relations)} relations")

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
            result = await session.execute(select(Chunk.id).where(Chunk.document_id == document_id))
            chunk_ids = [row[0] for row in result.fetchall()]

        logger.info(f"Starting batch extraction for document {document_id} with {len(chunk_ids)} chunks")

        total_entities = 0
        total_relations = 0
        successful_chunks = 0

        for i, chunk_id in enumerate(chunk_ids):
            try:
                logger.info(f"Processing chunk {i+1}/{len(chunk_ids)}: {chunk_id}")
                chunk_result = await self.extract_from_chunk(chunk_id)

                if not chunk_result.error:
                    total_entities += len(chunk_result.entities)
                    total_relations += len(chunk_result.relations)
                    successful_chunks += 1
                else:
                    logger.error(f"Failed to extract chunk {chunk_id}: {chunk_result.error}")

            except Exception as e:
                logger.error(f"Exception extracting chunk {chunk_id}: {str(e)}")

        logger.info(
            f"Batch extraction completed: {successful_chunks}/{len(chunk_ids)} chunks, "
            f"{total_entities} entities, {total_relations} relations"
        )
        return {
            "document_id": document_id,
            "total_chunks": len(chunk_ids),
            "successful_chunks": successful_chunks,
            "total_entities": total_entities,
            "total_relations": total_relations,
        }