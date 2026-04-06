"""Neo4j Adapter - FINAL FIX Phase 6 (hỗ trợ mọi label + provenance)."""

from neo4j import AsyncGraphDatabase, AsyncDriver
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Dict
from app.config.settings import settings
from app.core.logger import logger
from app.domain.schemas.extraction import Entity, Relation

class Neo4jAdapter:
    def __init__(self):
        self.driver: AsyncDriver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    async def close(self):
        await self.driver.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def upsert_entities_and_relations(self, entities: List[Entity], relations: List[Relation]) -> Dict:
        async with self.driver.session() as session:
            result = await session.execute_write(self._upsert_tx, entities, relations)
            return result

    async def _upsert_tx(self, tx, entities: List[Entity], relations: List[Relation]):
        stats = {"entities_upserted": 0, "relations_created": 0}

        # 1. Entities (hỗ trợ mọi label động)
        for entity in entities:
            label = entity.type
            props = {
                "id": entity.id,
                "name": entity.name,
            }

            cypher = f"""
            MERGE (n:{label} {{name: $name}})
            ON CREATE SET 
                n.id = $props.id,
                n += $props,
                n.created_at = datetime()
            ON MATCH SET 
                n += $props,
                n.updated_at = datetime()
            RETURN n.name as name
            """

            await tx.run(cypher, name=entity.name, props=props)
            stats["entities_upserted"] += 1

        # 2. Relations
        for rel in relations:
            rel_props = {
            }

            cypher = f"""
            MATCH (source) WHERE source.id = $source_id
            OPTIONAL MATCH (target) WHERE target.id = $target_id
            WITH source, target
            WHERE target IS NOT NULL
            MERGE (source)-[r:{rel.type}]->(target)
            ON CREATE SET 
                r += $props,
                r.created_at = datetime()
            ON MATCH SET 
                r += $props,
                r.updated_at = datetime()
            RETURN type(r) as rel_type
            """

            result = await tx.run(cypher, 
                        source_id=rel.source_id, 
                        target_id=rel.target_id, 
                        props=rel_props)
            record = await result.single()
            if record:
                stats["relations_created"] += 1

        logger.info("Neo4j upsert completed", **stats)
        return stats