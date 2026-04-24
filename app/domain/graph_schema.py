"""
Graph Schema - Neo4j Node/Relationship Definitions & Query Patterns

Maps domain models to Neo4j structure
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


# ============================================================================
# NEO4J NODE DEFINITIONS
# ============================================================================

@dataclass
class NodeSchema:
    """Neo4j Node definition."""
    label: str
    description: str
    required_properties: List[str]
    optional_properties: List[str]
    indexes: List[str] = None
    
    def __post_init__(self):
        if self.indexes is None:
            self.indexes = ["id", "name"]


# Current nodes from extraction
NODE_SCHEMAS = {
    "Weakness": NodeSchema(
        label="Weakness",
        description="CWE Weakness (security flaw category)",
        required_properties=["id", "name"],
        optional_properties=["cwe_id", "severity", "abstraction_level", "status", "confidence"],
        indexes=["id", "name", "cwe_id"]
    ),
    
    "Mitigation": NodeSchema(
        label="Mitigation",
        description="Security Mitigation/Countermeasure",
        required_properties=["id", "name"],
        optional_properties=["effectiveness", "effort", "confidence"],
        indexes=["id", "name"]
    ),
    
    "AffectedPlatform": NodeSchema(
        label="AffectedPlatform",
        description="Platform/Technology/Framework that can be affected",
        required_properties=["id", "name"],
        optional_properties=["platform_type", "version_range", "confidence"],
        indexes=["id", "name"]
    ),
    
    "Vulnerability": NodeSchema(
        label="Vulnerability",
        description="CVE Vulnerability instance",
        required_properties=["id", "name"],
        optional_properties=["cve_id", "cvss_score", "cvss_vector", "published_date", "confidence"],
        indexes=["id", "name", "cve_id"]
    ),
    
    "Consequence": NodeSchema(
        label="Consequence",
        description="Security impact/consequence",
        required_properties=["id", "name"],
        optional_properties=["consequence_type", "scope", "confidence"],
        indexes=["id", "name"]
    ),
    
    "Reference": NodeSchema(
        label="Reference",
        description="External reference/documentation",
        required_properties=["id", "name"],
        optional_properties=["reference_url", "source_type", "confidence"],
        indexes=["id", "name", "reference_url"]
    ),
}


# ============================================================================
# NEO4J RELATIONSHIP DEFINITIONS
# ============================================================================

@dataclass
class RelationshipSchema:
    """Neo4j Relationship definition."""
    type: str
    description: str
    source_labels: List[str]
    target_labels: List[str]
    properties: List[str]
    cypher_template: str = None
    confidence_threshold: float = 0.75
    
    def __post_init__(self):
        if self.cypher_template is None:
            src = "|".join(self.source_labels)
            tgt = "|".join(self.target_labels)
            self.cypher_template = f"""
            MATCH (source:{src})
            MATCH (target:{tgt})
            WHERE source.id = $source_id AND target.id = $target_id
            MERGE (source)-[r:{self.type}]->(target)
            SET r.confidence = $confidence, r.source_chunk_id = $source_chunk_id
            """


RELATIONSHIP_SCHEMAS = {
    "MITIGATED_BY": RelationshipSchema(
        type="MITIGATED_BY",
        description="Weakness is mitigated by mitigation strategy",
        source_labels=["Weakness", "Vulnerability"],
        target_labels=["Mitigation"],
        properties=["confidence", "source_chunk_id"],
        confidence_threshold=0.85
    ),
    
    "AFFECTS": RelationshipSchema(
        type="AFFECTS",
        description="Weakness/Vulnerability affects platform/product",
        source_labels=["Weakness", "Vulnerability"],
        target_labels=["AffectedPlatform"],
        properties=["confidence", "source_chunk_id"],
        confidence_threshold=0.75
    ),
    
    "RELATED_TO": RelationshipSchema(
        type="RELATED_TO",
        description="Entity is related to another entity (similar, variant, etc.)",
        source_labels=["Weakness", "Vulnerability", "Mitigation"],
        target_labels=["Weakness", "Vulnerability", "Mitigation"],
        properties=["confidence", "source_chunk_id", "relation_reason"],
        confidence_threshold=0.75
    ),
    
    "HAS_CONSEQUENCE": RelationshipSchema(
        type="HAS_CONSEQUENCE",
        description="Weakness has a security consequence",
        source_labels=["Weakness", "Vulnerability"],
        target_labels=["Consequence"],
        properties=["confidence", "source_chunk_id"],
        confidence_threshold=0.80
    ),
    
    "MAPPED_TO": RelationshipSchema(
        type="MAPPED_TO",
        description="CVE vulnerability maps to CWE weakness",
        source_labels=["Vulnerability"],
        target_labels=["Weakness"],
        properties=["confidence", "source_chunk_id"],
        confidence_threshold=0.90
    ),
    
    "REFERENCES": RelationshipSchema(
        type="REFERENCES",
        description="Entity references documentation",
        source_labels=["Weakness", "Vulnerability", "Mitigation"],
        target_labels=["Reference"],
        properties=["confidence", "source_chunk_id"],
        confidence_threshold=0.75
    ),
}


# ============================================================================
# CYPHER QUERY TEMPLATES
# ============================================================================

CYPHER_QUERIES = {
    # Find weaknesses by severity
    "get_high_severity_weaknesses": """
    MATCH (w:Weakness)
    WHERE w.severity = 'High' OR w.severity = 'Critical'
    RETURN w.id, w.name, w.severity, w.confidence
    ORDER BY w.confidence DESC
    """,
    
    # Find all mitigations for a weakness
    "get_mitigations_for_weakness": """
    MATCH (w:Weakness {id: $weakness_id})-[r:MITIGATED_BY]->(m:Mitigation)
    RETURN m.id, m.name, r.confidence
    ORDER BY r.confidence DESC
    """,
    
    # Find all affected platforms
    "get_affected_platforms": """
    MATCH (w:Weakness)-[r:AFFECTS]->(p:AffectedPlatform)
    RETURN p.id, p.name, COUNT(*) as weakness_count
    ORDER BY weakness_count DESC
    """,
    
    # Find related weaknesses
    "get_related_weaknesses": """
    MATCH (w1:Weakness {id: $weakness_id})-[r:RELATED_TO]->(w2:Weakness)
    RETURN w2.id, w2.name, r.confidence
    ORDER BY r.confidence DESC
    LIMIT 10
    """,
    
    # Find mitigation effectiveness across weaknesses
    "get_mitigation_coverage": """
    MATCH (m:Mitigation)-[r:MITIGATED_BY*1..]->(w:Weakness)
    RETURN m.id, m.name, COUNT(DISTINCT w.id) as weakness_count, AVG(r.confidence) as avg_confidence
    ORDER BY weakness_count DESC
    """,
    
    # Find attack chains (related weaknesses that enable each other)
    "get_attack_chains": """
    MATCH path = (w1:Weakness)-[r:RELATED_TO*2..4]->(w2:Weakness)
    WHERE r.confidence >= 0.8
    RETURN 
        w1.name as start_weakness,
        w2.name as end_weakness,
        length(path) as chain_length,
        [rel in relationships(path) | rel.confidence] as confidences
    LIMIT 20
    """,
    
    # Get graph statistics
    "get_graph_stats": """
    RETURN
        COUNT(DISTINCT n:Weakness) as weakness_count,
        COUNT(DISTINCT n:Mitigation) as mitigation_count,
        COUNT(DISTINCT n:AffectedPlatform) as platform_count,
        COUNT(DISTINCT n:Consequence) as consequence_count,
        COUNT(r) as relationship_count
    """,
    
    # Find vulnerable platforms
    "get_vulnerable_platforms": """
    MATCH (p:AffectedPlatform)<-[r:AFFECTS]-(w:Weakness)
    WHERE r.confidence >= 0.75
    RETURN p.id, p.name, COUNT(DISTINCT w.id) as weakness_count, AVG(r.confidence) as avg_confidence
    ORDER BY weakness_count DESC
    """,
    
    # Find consequences of a weakness
    "get_consequences": """
    MATCH (w:Weakness {id: $weakness_id})-[r:HAS_CONSEQUENCE]->(c:Consequence)
    RETURN c.id, c.name, c.consequence_type, r.confidence
    ORDER BY r.confidence DESC
    """,
    
    # Find cascading risks (weak A affects platform P, weak B is related to A)
    "get_cascading_risks": """
    MATCH (w1:Weakness)-[r1:RELATED_TO]->(w2:Weakness)-[r2:AFFECTS]->(p:AffectedPlatform)
    WHERE r1.confidence >= 0.75 AND r2.confidence >= 0.75
    RETURN DISTINCT w1.name, w2.name, p.name, [r1.confidence, r2.confidence] as confidences
    LIMIT 20
    """,
}


# ============================================================================
# NEO4J INITIALIZATION SCRIPTS
# ============================================================================

NEO4J_SETUP_SCRIPTS = {
    "create_indexes": """
    // Create indexes for faster queries
    CREATE INDEX idx_weakness_id IF NOT EXISTS FOR (w:Weakness) ON (w.id);
    CREATE INDEX idx_mitigation_id IF NOT EXISTS FOR (m:Mitigation) ON (m.id);
    CREATE INDEX idx_platform_id IF NOT EXISTS FOR (p:AffectedPlatform) ON (p.id);
    CREATE INDEX idx_weakness_cwe IF NOT EXISTS FOR (w:Weakness) ON (w.cwe_id);
    CREATE CONSTRAINT unique_weakness_id IF NOT EXISTS FOR (w:Weakness) REQUIRE w.id IS UNIQUE;
    CREATE CONSTRAINT unique_mitigation_id IF NOT EXISTS FOR (m:Mitigation) REQUIRE m.id IS UNIQUE;
    """,
    
    "create_constraints": """
    // Create uniqueness constraints
    CREATE CONSTRAINT unique_id IF NOT EXISTS
    FOR (n) REQUIRE n.id IS UNIQUE;
    """,
    
    "add_full_text_index": """
    // Create full-text search index
    CALL db.index.fulltext.createNodeIndex(
        "entities",
        ["Weakness", "Mitigation", "AffectedPlatform"],
        ["name", "id", "description"]
    ) YIELD indexName
    RETURN indexName;
    """,
}


# ============================================================================
# RELATION TYPE VALIDATION RULES
# ============================================================================

VALIDATION_RULES = {
    "MITIGATED_BY": {
        "minimum_confidence": 0.85,
        "allowed_source_types": ["Weakness", "Vulnerability"],
        "allowed_target_types": ["Mitigation"],
        "description": "Mitigation must have high confidence"
    },
    "AFFECTS": {
        "minimum_confidence": 0.75,
        "allowed_source_types": ["Weakness", "Vulnerability"],
        "allowed_target_types": ["AffectedPlatform"],
        "description": "Platform impact must be reasonably confident"
    },
    "RELATED_TO": {
        "minimum_confidence": 0.75,
        "allowed_source_types": ["Weakness", "Vulnerability", "Mitigation"],
        "allowed_target_types": ["Weakness", "Vulnerability", "Mitigation"],
        "description": "Relation similarity should be reasonably confident"
    },
}


# ============================================================================
# DATA QUALITY METRICS
# ============================================================================

QUALITY_METRICS = {
    "min_entity_confidence": 0.85,
    "min_relation_confidence": 0.75,
    "max_orphaned_nodes_percentage": 0.10,  # Max 10% orphaned
    "min_connectivity_ratio": 0.80,  # Min 80% of nodes should be connected
    "max_duplicate_threshold": 0.95,  # Detect near-duplicates above this similarity
}


# ============================================================================
# SCHEMA VALIDATION HELPERS
# ============================================================================

def validate_node_properties(node_data: Dict, label: str) -> Tuple[bool, str]:
    """Validate node has required properties for its label."""
    if label not in NODE_SCHEMAS:
        return False, f"Unknown node label: {label}"
    
    schema = NODE_SCHEMAS[label]
    missing = [prop for prop in schema.required_properties if prop not in node_data]
    
    if missing:
        return False, f"Missing required properties for {label}: {missing}"
    
    return True, "Valid"


def validate_relationship(source_label: str, rel_type: str, target_label: str) -> Tuple[bool, str]:
    """Validate relationship is allowed between node types."""
    if rel_type not in RELATIONSHIP_SCHEMAS:
        return False, f"Unknown relationship type: {rel_type}"
    
    rel_schema = RELATIONSHIP_SCHEMAS[rel_type]
    
    if source_label not in rel_schema.source_labels:
        return False, f"{rel_type} source must be one of: {rel_schema.source_labels}"
    
    if target_label not in rel_schema.target_labels:
        return False, f"{rel_type} target must be one of: {rel_schema.target_labels}"
    
    return True, "Valid"


def get_recommended_confidence_threshold(rel_type: str) -> float:
    """Get recommended confidence threshold for relationship type."""
    if rel_type in RELATIONSHIP_SCHEMAS:
        return RELATIONSHIP_SCHEMAS[rel_type].confidence_threshold
    return 0.75  # Default


# ============================================================================
# SUMMARY
# ============================================================================

SCHEMA_SUMMARY = f"""
SECURITY KNOWLEDGE GRAPH SCHEMA

NODE TYPES ({len(NODE_SCHEMAS)}):
{chr(10).join(f"  - {label}: {schema.description}" for label, schema in NODE_SCHEMAS.items())}

RELATIONSHIP TYPES ({len(RELATIONSHIP_SCHEMAS)}):
{chr(10).join(f"  - {rel_type}: {schema.description}" for rel_type, schema in RELATIONSHIP_SCHEMAS.items())}

CONFIDENCE THRESHOLDS:
{chr(10).join(f"  - {rel_type}: {schema.confidence_threshold}" for rel_type, schema in RELATIONSHIP_SCHEMAS.items())}

QUALITY STANDARDS:
  - Min entity confidence: {QUALITY_METRICS['min_entity_confidence']}
  - Min relation confidence: {QUALITY_METRICS['min_relation_confidence']}
  - Max orphaned nodes: {QUALITY_METRICS['max_orphaned_nodes_percentage']*100}%
  - Min connectivity: {QUALITY_METRICS['min_connectivity_ratio']*100}%
"""
