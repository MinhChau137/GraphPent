"""Graph operation schemas (Phase 6)."""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class NodeTypeEnum(str, Enum):
    """Neo4j node types."""
    CVE = "CVE"
    CWE = "CWE"
    WEAKNESS = "Weakness"
    DISCOVERED_VULNERABILITY = "DiscoveredVulnerability"
    FINDING = "Finding"
    ASSET = "Asset"
    HOST = "Host"


class SeverityEnum(str, Enum):
    """Vulnerability severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class HybridSearchRequest(BaseModel):
    """Hybrid search across knowledge + findings."""
    
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    severity: Optional[SeverityEnum] = None
    cve_filter: Optional[List[str]] = None
    cwe_filter: Optional[List[str]] = None
    host_filter: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    search_scope: str = Field(
        default="mixed",
        pattern="^(mixed|knowledge_only|findings_only)$",
        description="Search in knowledge base, findings, or both"
    )
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class GraphNode(BaseModel):
    """Graph node representation."""
    
    id: str = Field(..., description="Unique node ID")
    labels: List[str] = Field(..., description="Node labels (e.g., ['CVE', 'Vulnerability'])")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Node properties")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GraphRelationship(BaseModel):
    """Graph relationship representation."""
    
    id: str = Field(..., description="Relationship ID")
    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    type: str = Field(..., description="Relationship type")
    properties: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FindingNode(GraphNode):
    """DiscoveredVulnerability node."""
    
    template_id: str
    severity: SeverityEnum
    host: str
    url: str
    matched_at: datetime
    source: str = "nuclei"
    cve_ids: List[str] = Field(default_factory=list)
    cwe_ids: List[str] = Field(default_factory=list)


class KnowledgeNode(GraphNode):
    """CVE or CWE knowledge node."""
    
    node_type: NodeTypeEnum
    description: Optional[str] = None
    score: Optional[float] = None
    references: Optional[List[str]] = None


class HybridSearchResult(BaseModel):
    """Hybrid search result combining knowledge + findings."""
    
    result_id: str = Field(..., description="Unique result ID")
    node: GraphNode
    node_type: str = Field(description="Type of result (knowledge or finding)")
    relevance_score: float = Field(ge=0.0, le=1.0)
    related_findings: List[GraphNode] = Field(default_factory=list)
    related_knowledge: List[GraphNode] = Field(default_factory=list)
    relationships: List[GraphRelationship] = Field(default_factory=list)


class HybridSearchResponse(BaseModel):
    """Hybrid search response."""
    
    query: str
    total_results: int
    results: List[HybridSearchResult]
    knowledge_count: int = Field(description="Number of knowledge-based results")
    findings_count: int = Field(description="Number of finding-based results")
    execution_time_ms: float
    limit: int
    offset: int
    has_more: bool


class GraphStatistics(BaseModel):
    """Graph statistics."""
    
    total_nodes: int
    total_relationships: int
    by_label: Dict[str, int] = Field(description="Node count by label")
    by_relationship_type: Dict[str, int] = Field(description="Relationship count by type")
    cve_count: int
    cwe_count: int
    discovered_vulnerability_count: int
    average_relationships_per_node: float
    created_at: datetime


class GraphSchema(BaseModel):
    """Graph schema information."""
    
    label: str
    properties: Dict[str, str] = Field(description="Property names and types")
    relationships_out: List[str] = Field(description="Outgoing relationship types")
    relationships_in: List[str] = Field(description="Incoming relationship types")
    count: int = Field(description="Number of nodes with this label")


class GraphSchemaResponse(BaseModel):
    """Graph schema response."""
    
    schemas: List[GraphSchema]
    total_labels: int
    total_relationship_types: int
    indexes: List[Dict[str, Any]] = Field(default_factory=list)


class FindingKnowledgeLink(BaseModel):
    """Link between a finding and knowledge base."""
    
    finding_id: str
    finding_severity: SeverityEnum
    linked_cves: List[str] = Field(default_factory=list)
    linked_cwes: List[str] = Field(default_factory=list)
    confidence_scores: Dict[str, float] = Field(default_factory=dict)


class FindingKnowledgeLinkRequest(BaseModel):
    """Request to link findings to knowledge."""
    
    finding_id: str
    cve_ids: Optional[List[str]] = None
    cwe_ids: Optional[List[str]] = None
    auto_link: bool = Field(default=True, description="Auto-link based on similarity")


class FindingKnowledgeLinkResponse(BaseModel):
    """Response for linking findings to knowledge."""
    
    finding_id: str
    linked_cves: int
    linked_cwes: int
    new_relationships: int
    links: List[FindingKnowledgeLink]


class GraphQueryRequest(BaseModel):
    """Custom Cypher query request."""
    
    query: str = Field(..., min_length=10, description="Cypher query")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    limit: int = Field(default=100, ge=1, le=1000)


class GraphQueryResponse(BaseModel):
    """Graph query response."""
    
    query: str
    execution_time_ms: float
    result_count: int
    results: List[Dict[str, Any]]
    columns: List[str] = Field(description="Result column names")


class FindingSeverityDistribution(BaseModel):
    """Finding distribution by severity."""
    
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    
    @property
    def total(self) -> int:
        return self.critical + self.high + self.medium + self.low + self.info


class GraphHealthCheck(BaseModel):
    """Graph system health check."""
    
    status: str = Field(pattern="^(healthy|degraded|offline)$")
    neo4j_connection: bool
    node_count: int
    relationship_count: int
    indexes_active: int
    last_update: Optional[datetime] = None
    response_time_ms: float
