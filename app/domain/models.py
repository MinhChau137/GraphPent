"""
Domain Models - Entity Types & Relationships for Security Knowledge Graph

Based on extracted data:
- Entity Types: Weakness, Mitigation, AffectedPlatform, Vulnerability, CWE, Reference
- Relation Types: MITIGATED_BY, AFFECTS, RELATED_TO, HAS_WEAKNESS, IMPLEMENTS, etc.
"""

from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Set
from datetime import datetime


# ============================================================================
# ENTITY TYPE DEFINITIONS (From current dataset)
# ============================================================================

class EntityType(str, Enum):
    """All security entity types in the knowledge graph."""
    
    # CWE/Weakness related
    WEAKNESS = "Weakness"                    # CWE weaknesses (e.g., SQL Injection, XSS)
    CWE = "CWE"                             # CWE reference (same as Weakness, alternative)
    CWE_CATEGORY = "CWECategory"            # CWE category/class
    CWE_VIEW = "CWEView"                    # CWE view/perspective
    
    # Mitigation/Remediation
    MITIGATION = "Mitigation"                # Security countermeasure (e.g., Input validation)
    MITIGATION_STRATEGY = "MitigationStrategy"
    REMEDIATION = "Remediation"              # Specific fix/patch
    
    # Impact/Consequence
    CONSEQUENCE = "Consequence"              # Security impact (e.g., Data Exposure)
    IMPACT = "Impact"                       # Effect of vulnerability
    
    # Affected Scope
    AFFECTED_PLATFORM = "AffectedPlatform"   # Platform/OS/Framework (e.g., Java, PHP)
    AFFECTED_PRODUCT = "AffectedProduct"     # Specific product
    AFFECTED_COMPONENT = "AffectedComponent" # Software component
    
    # Vulnerability related
    VULNERABILITY = "Vulnerability"         # CVE vulnerability instance
    CVE = "CVE"                             # CVE reference
    
    # Reference/Source
    REFERENCE = "Reference"                 # External reference/documentation
    STANDARD = "Standard"                   # Security standard (e.g., OWASP)
    
    # Attack related
    ATTACK_VECTOR = "AttackVector"          # How attack is delivered
    ATTACK_PATTERN = "AttackPattern"        # CAPEC attack pattern
    
    # Detection/Monitoring
    DETECTION_METHOD = "DetectionMethod"    # How to detect the issue
    TEST_CASE = "TestCase"                 # Test case for the vulnerability
    

# ============================================================================
# RELATIONSHIP TYPE DEFINITIONS
# ============================================================================

class RelationType(str, Enum):
    """All relationship types in the security knowledge graph."""
    
    # Mitigation relationships
    MITIGATED_BY = "MITIGATED_BY"                  # Weakness --[MITIGATED_BY]--> Mitigation
    HAS_MITIGATION = "HAS_MITIGATION"              # Same as above, alternative direction
    IMPLEMENTS_MITIGATION = "IMPLEMENTS_MITIGATION"
    
    # Consequence/Impact relationships
    HAS_CONSEQUENCE = "HAS_CONSEQUENCE"            # Weakness --[HAS_CONSEQUENCE]--> Consequence
    CAUSES_IMPACT = "CAUSES_IMPACT"                # Vulnerability --[CAUSES_IMPACT]--> Impact
    
    # Affected relationships
    AFFECTS = "AFFECTS"                           # Weakness --[AFFECTS]--> Platform
    IMPACTS = "IMPACTS"                           # CVE --[IMPACTS]--> Product
    TARGETS = "TARGETS"                           # Attack --[TARGETS]--> Component
    
    # Related/Similar relationships
    RELATED_TO = "RELATED_TO"                      # Weakness --[RELATED_TO]--> Weakness (similar)
    CHILD_OF = "CHILD_OF"                         # CWE --[CHILD_OF]--> Parent CWE
    PARENT_OF = "PARENT_OF"                       # Parent --[PARENT_OF]--> Child
    VARIANT_OF = "VARIANT_OF"                     # Variant --[VARIANT_OF]--> Base weakness
    PREDECESSOR_OF = "PREDECESSOR_OF"            # Older version --[PREDECESSOR_OF]--> Newer
    
    # Mapping relationships
    MAPPED_TO = "MAPPED_TO"                       # CVE --[MAPPED_TO]--> CWE
    REFERENCES = "REFERENCES"                     # Entity --[REFERENCES]--> Reference
    IMPLEMENTS = "IMPLEMENTS"                     # Product --[IMPLEMENTS]--> Standard
    
    # Detection relationships
    DETECTABLE_BY = "DETECTABLE_BY"              # Weakness --[DETECTABLE_BY]--> Method
    TESTED_BY = "TESTED_BY"                      # Vulnerability --[TESTED_BY]--> TestCase
    
    # Attack chain relationships
    PRECEDES = "PRECEDES"                        # Step1 --[PRECEDES]--> Step2
    ENABLES = "ENABLES"                          # Weakness1 --[ENABLES]--> Weakness2
    REQUIRES = "REQUIRES"                        # Attack --[REQUIRES]--> Capability


# ============================================================================
# ENTITY SCHEMA CLASSES
# ============================================================================

class BaseEntity(BaseModel):
    """Base class for all security entities."""
    
    id: str
    type: EntityType
    name: str
    description: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = False


class Weakness(BaseEntity):
    """CWE Weakness entity."""
    
    type: EntityType = EntityType.WEAKNESS
    cwe_id: Optional[str] = None          # e.g., "CWE-89"
    abstraction_level: Optional[str] = None  # Pillar, Class, Base, Variant
    status: Optional[str] = None           # Draft, Incomplete, Active, Obsolete
    severity: Optional[str] = None         # Low, Medium, High, Critical
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "cwe-89",
                "type": "Weakness",
                "name": "SQL Injection",
                "cwe_id": "CWE-89",
                "severity": "High",
                "confidence": 0.95
            }
        }


class Mitigation(BaseEntity):
    """Security Mitigation/Countermeasure entity."""
    
    type: EntityType = EntityType.MITIGATION
    applicable_weaknesses: List[str] = Field(default_factory=list)  # CWE IDs it mitigates
    effectiveness: Optional[str] = None   # High, Medium, Low
    effort: Optional[str] = None          # Low, Medium, High
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "mit-001",
                "type": "Mitigation",
                "name": "Input Validation",
                "effectiveness": "High",
                "effort": "Medium"
            }
        }


class AffectedPlatform(BaseEntity):
    """Platform/Technology that can be affected by vulnerabilities."""
    
    type: EntityType = EntityType.AFFECTED_PLATFORM
    platform_type: Optional[str] = None   # OS, Language, Framework, Database
    version_range: Optional[str] = None   # Version constraints
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "platform-java-11",
                "type": "AffectedPlatform",
                "name": "Java 11+",
                "platform_type": "Language"
            }
        }


class Vulnerability(BaseEntity):
    """CVE Vulnerability instance (specific occurrence)."""
    
    type: EntityType = EntityType.VULNERABILITY
    cve_id: Optional[str] = None
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    published_date: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "cve-2024-001",
                "type": "Vulnerability",
                "name": "Remote Code Execution in LibXML",
                "cve_id": "CVE-2024-001",
                "cvss_score": 9.8
            }
        }


class Consequence(BaseEntity):
    """Security impact/consequence of a weakness."""
    
    type: EntityType = EntityType.CONSEQUENCE
    consequence_type: Optional[str] = None  # Confidentiality, Integrity, Availability
    scope: Optional[str] = None             # Scope of impact
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "cons-001",
                "type": "Consequence",
                "name": "Data Exposure",
                "consequence_type": "Confidentiality"
            }
        }


class Reference(BaseEntity):
    """External reference/documentation."""
    
    type: EntityType = EntityType.REFERENCE
    reference_url: Optional[str] = None
    source_type: Optional[str] = None  # CVE, CWE, CAPEC, External
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "ref-001",
                "type": "Reference",
                "name": "OWASP Top 10 - A03:2021 Injection",
                "reference_url": "https://owasp.org/..."
            }
        }


# ============================================================================
# RELATIONSHIP SCHEMA CLASSES
# ============================================================================

class RelationshipMetadata(BaseModel):
    """Metadata for relationships."""
    
    confidence: float = Field(ge=0.0, le=1.0, default=0.75)
    source_chunk_id: Optional[int] = None
    extraction_method: str = "llm-extraction"  # How the relation was discovered
    evidence: Optional[str] = None             # Supporting evidence/quote


class BaseRelationship(BaseModel):
    """Base class for relationships."""
    
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    type: RelationType
    source_id: str
    target_id: str
    metadata: RelationshipMetadata = Field(default_factory=RelationshipMetadata)
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = False


class MitigationRelation(BaseRelationship):
    """Weakness is mitigated by a mitigation strategy."""
    type: RelationType = RelationType.MITIGATED_BY
    # source_id: Weakness ID
    # target_id: Mitigation ID


class AffectsRelation(BaseRelationship):
    """Entity affects a platform/product."""
    type: RelationType = RelationType.AFFECTS
    # source_id: Weakness/Vulnerability ID
    # target_id: Platform/Product ID


class RelatedToRelation(BaseRelationship):
    """Entity is related to another entity."""
    type: RelationType = RelationType.RELATED_TO
    relation_reason: Optional[str] = None  # Why they're related


class ConsequenceRelation(BaseRelationship):
    """Entity has a consequence."""
    type: RelationType = RelationType.HAS_CONSEQUENCE
    # source_id: Weakness ID
    # target_id: Consequence ID


class MapsToRelation(BaseRelationship):
    """CVE maps to CWE."""
    type: RelationType = RelationType.MAPPED_TO
    # source_id: CVE ID
    # target_id: CWE ID


# ============================================================================
# KNOWLEDGE GRAPH SCHEMA
# ============================================================================

class KnowledgeGraph(BaseModel):
    """Complete security knowledge graph."""
    
    entities: List[BaseEntity] = Field(default_factory=list)
    relationships: List[BaseRelationship] = Field(default_factory=list)
    
    # Statistics
    entity_count: int = 0
    relationship_count: int = 0
    
    def get_entities_by_type(self, entity_type: EntityType) -> List[BaseEntity]:
        """Get all entities of a specific type."""
        return [e for e in self.entities if e.type == entity_type]
    
    def get_relations_by_type(self, rel_type: RelationType) -> List[BaseRelationship]:
        """Get all relationships of a specific type."""
        return [r for r in self.relationships if r.type == rel_type]
    
    def get_entity_relations(self, entity_id: str) -> List[BaseRelationship]:
        """Get all relationships connected to an entity."""
        return [
            r for r in self.relationships 
            if r.source_id == entity_id or r.target_id == entity_id
        ]
    
    def get_related_entities(self, entity_id: str) -> Set[str]:
        """Get all entity IDs related to this entity."""
        related = set()
        for rel in self.get_entity_relations(entity_id):
            if rel.source_id == entity_id:
                related.add(rel.target_id)
            else:
                related.add(rel.source_id)
        return related


# ============================================================================
# RELATION MAPPING (Current Dataset Statistics)
# ============================================================================

RELATION_TYPE_STATS = {
    "MITIGATED_BY": {"count": 9, "description": "Weakness mitigated by mitigation"},
    "RELATED_TO": {"count": 6, "description": "Entity related to another entity"},
    "AFFECTS": {"count": 5, "description": "Weakness/CVE affects platform/product"},
}

ENTITY_TYPE_STATS = {
    "Weakness": {"count": 13, "description": "CWE weaknesses"},
    "Mitigation": {"count": 4, "description": "Security mitigations"},
    "AffectedPlatform": {"count": 3, "description": "Platforms/technologies"},
}

# Sample confidence thresholds
CONFIDENCE_THRESHOLDS = {
    "MITIGATED_BY": 0.85,  # Strict - direct mitigation
    "AFFECTS": 0.75,       # Medium - platform impact
    "RELATED_TO": 0.75,    # Medium - similarity
    "HAS_CONSEQUENCE": 0.80, # High - impact certainty
}
