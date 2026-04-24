"""
Graph Operations - Utilities for querying and analyzing the security knowledge graph
"""

from typing import List, Dict, Optional, Set, Tuple
from app.domain.models import (
    EntityType, RelationType, Weakness, Mitigation, AffectedPlatform,
    Vulnerability, BaseEntity, BaseRelationship
)
from app.domain.graph_schema import CYPHER_QUERIES, VALIDATION_RULES


class GraphQueryBuilder:
    """Helper for building Neo4j Cypher queries."""
    
    @staticmethod
    def find_weaknesses_by_severity(severity: str, min_confidence: float = 0.85) -> str:
        """Find weaknesses by severity level."""
        return f"""
        MATCH (w:Weakness)
        WHERE w.severity = '{severity}' AND w.confidence >= {min_confidence}
        RETURN w.id, w.name, w.severity, w.confidence
        ORDER BY w.confidence DESC
        """
    
    @staticmethod
    def find_mitigations_for_weakness(weakness_id: str) -> str:
        """Find all mitigations for a specific weakness."""
        return f"""
        MATCH (w:Weakness {{id: '{weakness_id}'}})-[r:MITIGATED_BY]->(m:Mitigation)
        RETURN m.id, m.name, r.confidence, m.effectiveness, m.effort
        ORDER BY r.confidence DESC
        """
    
    @staticmethod
    def find_impact_chain(start_weakness_id: str, depth: int = 3) -> str:
        """Find chain of impact from a weakness."""
        return f"""
        MATCH (start:Weakness {{id: '{start_weakness_id}'}})
        MATCH path = (start)-[r:RELATED_TO|AFFECTS*1..{depth}]-(target)
        RETURN 
            start.name as origin,
            target.name as affected,
            length(path) as distance,
            [rel in relationships(path) | {{type: type(rel), confidence: rel.confidence}}] as chain
        ORDER BY distance
        """
    
    @staticmethod
    def get_attack_surface(platform_id: str) -> str:
        """Get all vulnerabilities affecting a platform."""
        return f"""
        MATCH (w:Weakness)-[r:AFFECTS]->(:AffectedPlatform {{id: '{platform_id}'}})
        OPTIONAL MATCH (w)-[m:MITIGATED_BY]->(mit:Mitigation)
        RETURN 
            w.id, w.name, w.severity,
            COUNT(DISTINCT mit.id) as mitigation_count,
            COLLECT(DISTINCT mit.name) as mitigations,
            AVG(r.confidence) as avg_confidence
        ORDER BY w.severity DESC, avg_confidence DESC
        """
    
    @staticmethod
    def find_related_vulnerabilities(vuln_id: str, limit: int = 10) -> str:
        """Find similar/related vulnerabilities."""
        return f"""
        MATCH (v1:Vulnerability {{id: '{vuln_id}'}})-[r:RELATED_TO]->(v2:Vulnerability)
        RETURN v2.id, v2.name, v2.cvss_score, r.confidence
        ORDER BY r.confidence DESC
        LIMIT {limit}
        """


class GraphAnalyzer:
    """Analyze graph structure and quality."""
    
    @staticmethod
    def calculate_coverage_percentage(entities_total: int, entities_mitigated: int) -> float:
        """Calculate what percentage of entities have mitigations."""
        if entities_total == 0:
            return 0.0
        return (entities_mitigated / entities_total) * 100
    
    @staticmethod
    def calculate_connectivity_ratio(total_nodes: int, connected_nodes: int) -> float:
        """Calculate what percentage of nodes are connected to the graph."""
        if total_nodes == 0:
            return 0.0
        return (connected_nodes / total_nodes)
    
    @staticmethod
    def find_isolated_nodes(nodes: List[BaseEntity], relationships: List[BaseRelationship]) -> List[str]:
        """Find nodes with no incoming or outgoing relationships."""
        node_ids = {n.id for n in nodes}
        connected_ids = set()
        
        for rel in relationships:
            connected_ids.add(rel.source_id)
            connected_ids.add(rel.target_id)
        
        isolated = node_ids - connected_ids
        return list(isolated)
    
    @staticmethod
    def find_high_confidence_paths(relationships: List[BaseRelationship], min_confidence: float = 0.85) -> List[List[BaseRelationship]]:
        """Find paths where all relationships have high confidence."""
        high_confidence_rels = [r for r in relationships if r.metadata.confidence >= min_confidence]
        return [list(high_confidence_rels)]  # Simplified - returns all high-confidence rels
    
    @staticmethod
    def calculate_graph_density(entity_count: int, relation_count: int) -> float:
        """Calculate graph density (actual vs possible edges)."""
        if entity_count <= 1:
            return 0.0
        max_edges = entity_count * (entity_count - 1)
        return (relation_count / max_edges) * 100 if max_edges > 0 else 0.0
    
    @staticmethod
    def get_centrality_scores(nodes: List[BaseEntity], relationships: List[BaseRelationship]) -> Dict[str, float]:
        """Calculate degree centrality for each node."""
        centrality = {}
        
        for node in nodes:
            in_degree = sum(1 for r in relationships if r.target_id == node.id)
            out_degree = sum(1 for r in relationships if r.source_id == node.id)
            centrality[node.id] = in_degree + out_degree
        
        return centrality


class RelationshipValidator:
    """Validate relationships conform to schema rules."""
    
    @staticmethod
    def validate_relation_confidence(rel_type: str, confidence: float) -> Tuple[bool, str]:
        """Check if relationship confidence meets minimum threshold."""
        if rel_type not in VALIDATION_RULES:
            return False, f"Unknown relationship type: {rel_type}"
        
        min_conf = VALIDATION_RULES[rel_type]["minimum_confidence"]
        if confidence < min_conf:
            return False, f"Confidence {confidence} below minimum {min_conf} for {rel_type}"
        
        return True, "Valid"
    
    @staticmethod
    def validate_relation_types(source_type: str, rel_type: str, target_type: str) -> Tuple[bool, str]:
        """Check if source/target types are allowed for relationship."""
        if rel_type not in VALIDATION_RULES:
            return False, f"Unknown relationship type: {rel_type}"
        
        rules = VALIDATION_RULES[rel_type]
        
        if source_type not in rules["allowed_source_types"]:
            return False, f"Source type {source_type} not allowed for {rel_type}"
        
        if target_type not in rules["allowed_target_types"]:
            return False, f"Target type {target_type} not allowed for {rel_type}"
        
        return True, "Valid"


class GraphRecommendations:
    """Generate recommendations based on graph analysis."""
    
    @staticmethod
    def get_high_priority_mitigations(weaknesses: List[Weakness], relationships: List[BaseRelationship]) -> List[Tuple[str, int, float]]:
        """Get mitigations affecting most critical weaknesses.
        
        Returns: List of (mitigation_id, affected_count, avg_confidence)
        """
        mitigation_stats: Dict[str, Tuple[int, List[float]]] = {}
        
        for rel in relationships:
            if rel.type == RelationType.MITIGATED_BY:
                if rel.target_id not in mitigation_stats:
                    mitigation_stats[rel.target_id] = (0, [])
                
                count, confidences = mitigation_stats[rel.target_id]
                mitigation_stats[rel.target_id] = (count + 1, confidences + [rel.metadata.confidence])
        
        # Calculate averages and sort by impact
        results = []
        for mit_id, (count, confidences) in mitigation_stats.items():
            avg_conf = sum(confidences) / len(confidences) if confidences else 0
            results.append((mit_id, count, avg_conf))
        
        return sorted(results, key=lambda x: (-x[1], -x[2]))  # Sort by count desc, then confidence desc
    
    @staticmethod
    def get_unmitigated_weaknesses(weaknesses: List[Weakness], relationships: List[BaseRelationship]) -> List[str]:
        """Get weaknesses that have no mitigations."""
        mitigated_ids = {
            rel.source_id for rel in relationships 
            if rel.type == RelationType.MITIGATED_BY
        }
        
        return [w.id for w in weaknesses if w.id not in mitigated_ids]
    
    @staticmethod
    def get_vulnerable_platforms(relationships: List[BaseRelationship], min_count: int = 2) -> List[Tuple[str, int]]:
        """Get platforms affected by multiple weaknesses."""
        platform_counts: Dict[str, int] = {}
        
        for rel in relationships:
            if rel.type == RelationType.AFFECTS:
                platform_counts[rel.target_id] = platform_counts.get(rel.target_id, 0) + 1
        
        return sorted(
            [(p_id, count) for p_id, count in platform_counts.items() if count >= min_count],
            key=lambda x: -x[1]
        )


# ============================================================================
# EXAMPLE USAGE & QUICK QUERIES
# ============================================================================

def print_schema_summary():
    """Print summary of entity and relationship types."""
    from app.domain.graph_schema import SCHEMA_SUMMARY
    print(SCHEMA_SUMMARY)


def get_sample_queries() -> Dict[str, str]:
    """Get dictionary of pre-built Cypher queries."""
    return CYPHER_QUERIES


# Sample query examples
EXAMPLE_QUERIES = {
    "high_severity": "MATCH (w:Weakness) WHERE w.severity='High' RETURN w.name, w.id LIMIT 10",
    "unmitigated": "MATCH (w:Weakness) WHERE NOT EXISTS((w)-[:MITIGATED_BY]->()) RETURN w.name, w.id",
    "vulnerable_platforms": "MATCH (p:AffectedPlatform)<-[r:AFFECTS]-(w:Weakness) RETURN p.name, COUNT(w) as risk_count ORDER BY risk_count DESC",
    "mitigation_effective": "MATCH (m:Mitigation)-[r:MITIGATED_BY]->(w:Weakness) WHERE r.confidence >= 0.85 RETURN m.name, COUNT(w) as weakness_count",
}
