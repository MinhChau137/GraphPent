#!/usr/bin/env python3
"""
Check actual Neo4j graph structure vs schema
"""

import time
import sys
from neo4j import GraphDatabase
from typing import Dict, List

# Connection settings
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "password123"

def connect_neo4j(uri=URI, user=USER, pwd=PASSWORD):
    """Connect to Neo4j"""
    try:
        driver = GraphDatabase.driver(uri, auth=(user, pwd))
        # Test connection
        with driver.session() as session:
            result = session.run("RETURN 1")
            result.consume()
        print(f"✅ Connected to {uri}")
        return driver
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

def check_constraints(driver):
    """Get all constraints"""
    with driver.session() as session:
        result = session.run("""
            SHOW CONSTRAINTS
            YIELD name, properties, entityType, labelsOrTypes
            RETURN name, properties, entityType, labelsOrTypes
            ORDER BY name
        """)
        constraints = result.data()
    return constraints

def check_node_counts(driver):
    """Get node counts by label"""
    with driver.session() as session:
        result = session.run("""
            CALL db.labels() YIELD label
            CALL {
                WITH label
                MATCH (n) WHERE any(lbl IN labels(n) WHERE lbl = label)
                RETURN count(n) as count
            }
            RETURN label, count ORDER BY count DESC
        """)
        labels = result.data()
    return labels

def check_relationship_types(driver):
    """Get relationship counts by type"""
    with driver.session() as session:
        result = session.run("""
            CALL db.relationshipTypes() YIELD relationshipType
            CALL {
                WITH relationshipType
                MATCH ()-[r]->() WHERE type(r) = relationshipType
                RETURN count(r) as count
            }
            RETURN relationshipType as type, count ORDER BY count DESC
        """)
        rels = result.data()
    return rels

def check_node_samples(driver, label: str, limit=3):
    """Get sample nodes of a label"""
    with driver.session() as session:
        result = session.run(f"""
            MATCH (n:{label})
            RETURN n LIMIT {limit}
        """)
        nodes = [record["n"] for record in result]
    return nodes

def format_node(node):
    """Format node for display"""
    return {
        "id": node.get("id", "N/A"),
        "name": node.get("name", "N/A"),
        "labels": list(node.labels),
        "properties": dict(node)
    }

def main():
    print("=" * 80)
    print("NEO4J GRAPH STRUCTURE CHECK")
    print("=" * 80)
    
    # Connect
    driver = connect_neo4j()
    if not driver:
        print("\n⏳ Waiting for Neo4j to be ready...")
        for i in range(10):
            time.sleep(2)
            driver = connect_neo4j()
            if driver:
                break
        if not driver:
            print("❌ Failed to connect after retries")
            sys.exit(1)
    
    try:
        # 1. Constraints
        print("\n" + "=" * 80)
        print("1. CONSTRAINTS")
        print("=" * 80)
        constraints = check_constraints(driver)
        if constraints:
            for c in constraints:
                print(f"  • {c['name']}: {c['entityType']} {c['labelsOrTypes']} {c['properties']}")
            print(f"\nTotal: {len(constraints)} constraints")
        else:
            print("  No constraints found")
        
        # 2. Node Counts
        print("\n" + "=" * 80)
        print("2. NODE COUNTS BY LABEL")
        print("=" * 80)
        nodes = check_node_counts(driver)
        if nodes:
            for item in nodes:
                print(f"  • {item['label']:20} : {item['count']:6} nodes")
            total = sum(n['count'] for n in nodes)
            print(f"\nTotal: {total} nodes")
        else:
            print("  No nodes found")
        
        # 3. Relationship Types
        print("\n" + "=" * 80)
        print("3. RELATIONSHIP TYPES")
        print("=" * 80)
        rels = check_relationship_types(driver)
        if rels:
            for rel in rels:
                print(f"  • {rel['type']:20} : {rel['count']:6} relationships")
            total = sum(r['count'] for r in rels)
            print(f"\nTotal: {total} relationships")
        else:
            print("  ⚠️  No relationships found!")
        
        # 4. Sample nodes
        print("\n" + "=" * 80)
        print("4. SAMPLE NODES")
        print("=" * 80)
        if nodes:
            for item in nodes[:5]:  # Show first 5 labels
                label = item['label']
                print(f"\n  {label} (sample):")
                samples = check_node_samples(driver, label, limit=1)
                for sample in samples:
                    props = dict(sample)
                    print(f"    id: {props.get('id', 'N/A')}")
                    print(f"    name: {props.get('name', 'N/A')}")
                    for k, v in list(props.items())[:5]:
                        if k not in ['id', 'name']:
                            print(f"    {k}: {v}")
        
        # 5. Comparison with Schema
        print("\n" + "=" * 80)
        print("5. SCHEMA COMPARISON")
        print("=" * 80)
        
        schema_nodes = {
            "Vulnerability", "AffectedProduct", "CWE", "Mitigation",
            "Reference", "Weakness", "AffectedPlatform", "Consequence"
        }
        
        actual_labels = {n['label'] for n in nodes}
        
        print("\n  Expected nodes (Schema):")
        for node in sorted(schema_nodes):
            status = "✅" if node in actual_labels else "❌"
            count = next((n['count'] for n in nodes if n['label'] == node), 0)
            print(f"    {status} {node:20} ({count} nodes)")
        
        print("\n  Unexpected nodes (Not in Schema):")
        unexpected = actual_labels - schema_nodes
        if unexpected:
            for node in sorted(unexpected):
                count = next((n['count'] for n in nodes if n['label'] == node), 0)
                print(f"    ⚠️  {node:20} ({count} nodes)")
        else:
            print("    None")
        
        print("\n  Expected relationships (Schema):")
        schema_rels = {
            "IMPACTS", "HAS_WEAKNESS", "RESOLVED_BY", "VERSION_OF",
            "MITIGATED_BY", "AFFECTS", "HAS_CONSEQUENCE", "RELATED_TO"
        }
        
        actual_rels = {r['type'] for r in rels}
        
        for rel in sorted(schema_rels):
            status = "✅" if rel in actual_rels else "❌"
            count = next((r['count'] for r in rels if r['type'] == rel), 0)
            print(f"    {status} {rel:20} ({count} relationships)")
        
    finally:
        driver.close()
        print("\n" + "=" * 80)
        print("✅ Check completed")
        print("=" * 80)

if __name__ == "__main__":
    main()
