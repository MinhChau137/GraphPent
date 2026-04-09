#!/usr/bin/env python3
"""
Create fulltext index in Neo4j for faster text search
"""

from app.adapters.neo4j_client import Neo4jAdapter
import asyncio

async def create_fulltext_index():
    neo4j = Neo4jAdapter()
    async with neo4j.driver.session() as session:
        # Drop existing index if exists
        try:
            await session.run("DROP INDEX nodeSearch IF EXISTS")
            print("Dropped existing index")
        except:
            pass
        
        # Create fulltext index on node names and IDs
        cypher = """
        CREATE FULLTEXT INDEX nodeSearch
        FOR (n)
        ON EACH [n.name, n.id]
        """
        await session.run(cypher)
        print("Fulltext index created successfully")

        # Test the index
        test_cypher = """
        CALL db.index.fulltext.queryNodes("nodeSearch", "vulnerability") 
        YIELD node, score 
        RETURN node.id, node.name, score 
        LIMIT 5
        """
        result = await session.run(test_cypher)
        records = await result.data()
        print(f"Test query returned {len(records)} results")
        for r in records:
            print(f"  {r['node.id']}: {r['node.name']} (score: {r['score']:.2f})")

if __name__ == "__main__":
    asyncio.run(create_fulltext_index())