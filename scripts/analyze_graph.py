"""Analyze Neo4j graph structure and quality."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from neo4j import AsyncGraphDatabase
from app.config.settings import settings

async def analyze_graph():
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    
    async def query(q):
        async with driver.session() as session:
            result = await session.run(q)
            return [rec async for rec in result]
    
    print("\n" + "="*70)
    print("📊 NEO4J GRAPH ANALYSIS")
    print("="*70)
    
    # 1. Node statistics
    print("\n1️⃣ NODE STATISTICS:")
    print("-" * 70)
    records = await query("MATCH (n) RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC")
    total_nodes = 0
    for record in records:
        node_type = record.get("type", "Unknown")
        count = record.get("count", 0)
        total_nodes += count
        print(f"   {node_type:<20} {count:>6} nodes")
    print(f"   {'TOTAL':<20} {total_nodes:>6} nodes")
    
    # 2. Relationship statistics
    print("\n2️⃣ RELATIONSHIP STATISTICS:")
    print("-" * 70)
    records = await query("MATCH ()-[r]-() RETURN type(r) as rel_type, count(r) as count ORDER BY count DESC")
    total_rels = 0
    for record in records:
        rel_type = record.get("rel_type", "Unknown")
        count = record.get("count", 0)
        total_rels += count
        print(f"   {rel_type:<20} {count:>6} relations")
    print(f"   {'TOTAL':<20} {total_rels:>6} relations")
    
    # 3. Graph connectivity
    print("\n3️⃣ CONNECTIVITY METRICS:")
    print("-" * 70)
    records = await query("MATCH (n) WHERE NOT (n)--() RETURN count(n) as orphaned")
    orphaned = records[0].get("orphaned", 0) if records else 0
    print(f"   Orphaned nodes:      {orphaned:>6} (isolated, no relations)")
    print(f"   Connected nodes:     {total_nodes - orphaned:>6} (part of graph)")
    
    connectivity = 0
    if total_nodes > 0:
        connectivity = 100 * (total_nodes - orphaned) / total_nodes
        print(f"   Connectivity ratio:  {connectivity:>6.1f}% (goal: >80%)")
    
    # 4. Relation density
    print("\n4️⃣ GRAPH DENSITY:")
    print("-" * 70)
    if total_nodes > 1:
        max_edges = total_nodes * (total_nodes - 1) / 2
        density = total_rels / max_edges if max_edges > 0 else 0
        print(f"   Total relations:     {total_rels:>6}")
        print(f"   Max possible edges:  {int(max_edges):>6}")
        print(f"   Density:             {density*100:>6.2f}% (actual/theoretical)")
    
    avg_degree = (2 * total_rels / total_nodes) if total_nodes > 0 else 0
    print(f"   Avg node degree:     {avg_degree:>6.2f} (relations per node)")
    
    # 5. Cross-chunk relations
    print("\n5️⃣ CROSS-CHUNK RELATIONSHIP VALIDATION:")
    print("-" * 70)
    records = await query("""
    MATCH (a)-[r]->(b) 
    RETURN 
        count(CASE WHEN a.chunk_id = b.chunk_id THEN 1 END) as same_chunk,
        count(CASE WHEN a.chunk_id <> b.chunk_id OR a.chunk_id IS NULL OR b.chunk_id IS NULL THEN 1 END) as cross_chunk
    """)
    same = 0
    cross = 0
    if records:
        same = records[0].get("same_chunk", 0)
        cross = records[0].get("cross_chunk", 0)
        print(f"   Same-chunk relations: {same:>6}")
        print(f"   Cross-chunk relations:{cross:>6}")
        if total_rels > 0:
            cross_pct = 100 * cross / total_rels
            print(f"   Cross-chunk ratio:   {cross_pct:>6.1f}%")
    
    # 6. Sample of extracted relationships
    print("\n6️⃣ SAMPLE RELATIONSHIPS (First 15):")
    print("-" * 70)
    records = await query("""
    MATCH (a)-[r]->(b)
    RETURN 
        a.id as source, 
        a.name as source_name,
        type(r) as rel_type,
        b.id as target,
        b.name as target_name,
        r.confidence as confidence
    LIMIT 15
    """)
    for i, record in enumerate(records, 1):
        src_name = (record.get("source_name", "?") or "?")[:20]
        rel = record.get("rel_type", "?")
        tgt_name = (record.get("target_name", "?") or "?")[:20]
        conf = record.get("confidence", 0) or 0
        print(f"   {i:2}. {src_name:<20} --[{rel:12}]--> {tgt_name:<20} (conf={conf:.2f})")
    
    # 7. Entity type distribution
    print("\n7️⃣ ENTITY TYPE DISTRIBUTION:")
    print("-" * 70)
    records = await query("""
    MATCH (n)
    WHERE n.type IS NOT NULL
    RETURN n.type as entity_type, count(n) as count
    ORDER BY count DESC
    """)
    for record in records:
        etype = record.get("entity_type", "Unknown")
        count = record.get("count", 0)
        print(f"   {etype:<25} {count:>6} entities")
    
    # 8. Quality check
    print("\n8️⃣ DATA QUALITY CHECK:")
    print("-" * 70)
    records = await query("""
    MATCH (n)
    WHERE n.name IS NULL OR n.name = '' OR n.id IS NULL OR n.id = ''
    RETURN count(n) as invalid_nodes
    """)
    invalid = records[0].get("invalid_nodes", 0) if records else 0
    print(f"   Nodes with missing name/id: {invalid:>3}")
    
    records = await query("""
    MATCH ()-[r]->()
    WHERE r.confidence IS NULL
    RETURN count(r) as rels_no_conf
    """)
    no_conf = records[0].get("rels_no_conf", 0) if records else 0
    print(f"   Relations without confidence: {no_conf:>3}")
    
    # 9. Confidence statistics
    print("\n9️⃣ RELATION CONFIDENCE STATISTICS:")
    print("-" * 70)
    records = await query("MATCH ()-[r]->() RETURN avg(r.confidence) as avg_conf, min(r.confidence) as min_conf, max(r.confidence) as max_conf")
    if records:
        avg_conf = records[0].get("avg_conf", 0) or 0
        min_conf = records[0].get("min_conf", 0) or 0
        max_conf = records[0].get("max_conf", 0) or 0
        print(f"   Average confidence:  {avg_conf:.2f} (target: >0.80) {'✅' if avg_conf > 0.80 else '⚠️'}")
        print(f"   Min confidence:      {min_conf:.2f} (target: >0.75) {'✅' if min_conf > 0.75 else '⚠️'}")
        print(f"   Max confidence:      {max_conf:.2f}")
    
    # 10. Scoring
    print("\n🔟 OVERALL GRAPH QUALITY SCORE:")
    print("-" * 70)
    
    scores = []
    
    # Score 1: Connectivity
    conn_score = min(100, int(connectivity)) if total_nodes > 0 else 0
    scores.append(("Connectivity (target >80%)", conn_score))
    
    # Score 2: Node validity
    validity_score = max(0, 100 - (invalid * 100 / total_nodes)) if total_nodes > 0 else 100
    scores.append(("Data validity", int(validity_score)))
    
    # Score 3: Cross-chunk ratio
    if total_rels > 0:
        cross_score = min(100, int((cross / total_rels) * 50))
        scores.append(("Cross-chunk coverage", cross_score))
    
    print()
    avg_score = sum(s[1] for s in scores) / len(scores) if scores else 0
    for metric, score in scores:
        bar = "█" * (score // 5) + "░" * ((100 - score) // 5)
        print(f"   {metric:<30} {score:>3}% {bar}")
    
    print(f"\n   📈 OVERALL SCORE:           {avg_score:>3.0f}% ", end="")
    if avg_score >= 80:
        print("✅ EXCELLENT")
    elif avg_score >= 60:
        print("🟢 GOOD")
    elif avg_score >= 40:
        print("🟡 FAIR")
    else:
        print("🔴 POOR")
    
    print("\n" + "="*70)
    await driver.close()

asyncio.run(analyze_graph())
