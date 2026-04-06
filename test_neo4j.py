#!/usr/bin/env python3
"""Test Neo4j Cypher queries directly."""

import asyncio
import json
from neo4j import AsyncGraphDatabase
from app.config.settings import settings

async def test_neo4j():
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    # Test data from extraction_result.json
    entities = [
        {
            "id": "6f4dab11-7a5e-4b9c-a456-e0f2d3f7bcf8",
            "type": "Project",
            "name": "graphrag-pentest",
            "properties": {},
            "provenance": {
                "source_chunk_id": None,
                "document_id": None,
                "extraction_timestamp": "2026-04-04T13:15:10.814877",
                "confidence": 0.85,
                "llm_model": "llama3.1:8b",
                "tool_origin": "graphrag-extraction",
                "sensitivity": "lab-internal"
            }
        },
        {
            "id": "1daa95af-9f44-43eb-bc6f-5f1d4d4e2e14",
            "type": "Directory",
            "name": "graphrag-pentest",
            "properties": {},
            "provenance": {
                "source_chunk_id": None,
                "document_id": None,
                "extraction_timestamp": "2026-04-04T13:15:10.814893",
                "confidence": 0.85,
                "llm_model": "llama3.1:8b",
                "tool_origin": "graphrag-extraction",
                "sensitivity": "lab-internal"
            }
        }
    ]

    relations = [
        {
            "id": "b3c7d8ea-0f11-45a9-a56d-9fdd6f2c5c25",
            "type": "DEPENDS_ON",
            "source_id": "1daa95af-9f44-43eb-bc6f-5f1d4d4e2e14",
            "target_id": "6f4dab11-7a5e-4b9c-a456-e0f2d3f7bcf8",
            "properties": {},
            "provenance": {
                "source_chunk_id": None,
                "document_id": None,
                "extraction_timestamp": "2026-04-04T13:15:10.814903",
                "confidence": 0.85,
                "llm_model": "llama3.1:8b",
                "tool_origin": "graphrag-extraction",
                "sensitivity": "lab-internal"
            }
        }
    ]

    async with driver.session() as session:
        try:
            # Test entity upsert
            print("Testing entity upsert...")
            for entity in entities:
                label = entity["type"]
                props = {
                    "id": entity["id"],
                    "name": entity["name"],
                    **entity["properties"],
                    "provenance": entity["provenance"],
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
                RETURN n.name as name, n.id as id
                """

                print(f"Running Cypher for entity {entity['name']} (type: {label}):")
                print(cypher)
                result = await session.run(cypher, name=entity["name"], props=props)
                record = await result.single()
                print(f"Result: {record}")

            # Test relation upsert
            print("\nTesting relation upsert...")
            for rel in relations:
                rel_props = {
                    **rel["properties"],
                    "provenance": rel["provenance"],
                }

                cypher = f"""
                MATCH (source) WHERE source.id = $source_id
                MATCH (target) WHERE target.id = $target_id
                MERGE (source)-[r:{rel["type"]}]->(target)
                ON CREATE SET
                    r += $props,
                    r.created_at = datetime()
                ON MATCH SET
                    r += $props,
                    r.updated_at = datetime()
                RETURN type(r) as rel_type
                """

                print(f"Running Cypher for relation {rel['type']}:")
                print(cypher)
                result = await session.run(cypher,
                                         source_id=rel["source_id"],
                                         target_id=rel["target_id"],
                                         props=rel_props)
                record = await result.single()
                print(f"Result: {record}")

            print("All tests passed!")

        except Exception as e:
            print(f"Error: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()

    await driver.close()

if __name__ == "__main__":
    asyncio.run(test_neo4j())