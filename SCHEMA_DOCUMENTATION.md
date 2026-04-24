# 📊 Security Knowledge Graph Schema

**Date:** 2026-04-23  
**Status:** Production Ready ✅

## 📋 Overview

This document defines the complete domain model for the security knowledge graph, including:
- **Entity Types** (10 types)
- **Relationship Types** (12 types)
- **Neo4j Node Schemas**
- **Validation Rules**
- **Query Patterns**

---

## 🏗️ Entity Types (Classes)

### 1. **Weakness** (`EntityType.WEAKNESS`)
Security vulnerability pattern or flaw (CWE)

**Properties:**
- `id`: Unique identifier (e.g., "cwe-89")
- `name`: Descriptive name (e.g., "SQL Injection")
- `cwe_id`: CWE reference
- `severity`: Low, Medium, High, Critical
- `abstraction_level`: Pillar, Class, Base, Variant
- `status`: Draft, Incomplete, Active, Obsolete
- `confidence`: ≥ 0.85 (strict)

**Current Count:** 13 entities

**Example Neo4j Node:**
```
(:Weakness {
  id: "cwe-89",
  name: "SQL Injection",
  severity: "High",
  confidence: 0.95,
  created_at: 2026-04-23T07:43:09.483Z
})
```

---

### 2. **Mitigation** (`EntityType.MITIGATION`)
Security countermeasure or defense strategy

**Properties:**
- `id`: Unique identifier (e.g., "mit-input-validation")
- `name`: Mitigation name (e.g., "Input Validation")
- `effectiveness`: High, Medium, Low
- `effort`: Low, Medium, High
- `applicable_weaknesses`: List of CWE IDs it mitigates
- `confidence`: ≥ 0.85 (strict)

**Current Count:** 4 entities

**Example Neo4j Node:**
```
(:Mitigation {
  id: "mit-param-1",
  name: "Parameterized Queries",
  effectiveness: "High",
  effort: "Medium",
  confidence: 0.92
})
```

---

### 3. **AffectedPlatform** (`EntityType.AFFECTED_PLATFORM`)
Technology/Platform/Framework that can be affected by weaknesses

**Properties:**
- `id`: Platform identifier (e.g., "platform-java")
- `name`: Display name (e.g., "Java")
- `platform_type`: OS, Language, Framework, Database, Runtime
- `version_range`: Version constraints (optional)
- `confidence`: ≥ 0.85 (strict)

**Current Count:** 3 entities

**Example Neo4j Node:**
```
(:AffectedPlatform {
  id: "platform-java",
  name: "Java",
  platform_type: "Language",
  confidence: 0.88
})
```

---

### 4. **Vulnerability** (`EntityType.VULNERABILITY`)
Specific CVE vulnerability instance

**Properties:**
- `id`: CVE identifier (e.g., "cve-2024-001")
- `name`: Vulnerability description
- `cve_id`: Official CVE number
- `cvss_score`: CVSS v3.1 score (0.0-10.0)
- `cvss_vector`: CVSS vector string
- `published_date`: Publication date
- `confidence`: ≥ 0.85

---

### 5. **Consequence** (`EntityType.CONSEQUENCE`)
Security impact or consequence of a weakness

**Properties:**
- `id`: Consequence identifier
- `name`: Impact description (e.g., "Data Exposure")
- `consequence_type`: Confidentiality, Integrity, Availability, Accountability
- `scope`: Scope of impact

---

### 6. **Reference** (`EntityType.REFERENCE`)
External documentation or reference

**Properties:**
- `reference_url`: URL to documentation
- `source_type`: CVE, CWE, CAPEC, OWASP, External

---

### 7-10. **Additional Entity Types** (Extensible)
- `CWECategory`: CWE category/hierarchy level
- `AttackVector`: Attack delivery method
- `DetectionMethod`: How to detect the issue
- `TestCase`: Test case for validation

---

## 🔗 Relationship Types

### Current Relationships in Graph

| Type | Count | Description | Min Confidence |
|------|-------|-------------|-----------------|
| `MITIGATED_BY` | 9 | Weakness mitigated by mitigation | 0.85 |
| `RELATED_TO` | 6 | Entity related to another | 0.75 |
| `AFFECTS` | 5 | Weakness affects platform | 0.75 |

---

### All Supported Relationship Types

#### 1. **MITIGATED_BY**
Weakness is mitigated by a mitigation strategy

```
(Weakness)-[MITIGATED_BY {confidence, source_chunk_id}]->(Mitigation)
```

**Threshold:** 0.85 (strict - must be highly confident)  
**Example:**
```
(:Weakness {name: "SQL Injection"})-[MITIGATED_BY {confidence: 0.92}]->(:Mitigation {name: "Parameterized Queries"})
```

---

#### 2. **AFFECTS**
Weakness or vulnerability affects a platform/product

```
(Weakness|Vulnerability)-[AFFECTS {confidence}]->(AffectedPlatform|Product)
```

**Threshold:** 0.75  
**Example:**
```
(:Weakness {name: "SQL Injection"})-[AFFECTS {confidence: 0.88}]->(:AffectedPlatform {name: "Java"})
```

---

#### 3. **RELATED_TO**
Entity is related to another entity (similar, variant, predecessor)

```
(Weakness|Vulnerability|Mitigation)-[RELATED_TO {confidence, relation_reason}]->(Weakness|Vulnerability|Mitigation)
```

**Threshold:** 0.75  
**Example:**
```
(:Weakness {name: "Comparison Using Wrong Factors"})-[RELATED_TO {confidence: 0.75}]->(:Weakness {name: "Data Corruption"})
```

---

#### 4. **HAS_CONSEQUENCE**
Weakness has a security consequence

```
(Weakness|Vulnerability)-[HAS_CONSEQUENCE {confidence}]->(Consequence)
```

**Threshold:** 0.80

---

#### 5. **MAPPED_TO**
CVE maps to CWE weakness

```
(Vulnerability)-[MAPPED_TO {confidence}]->(Weakness)
```

**Threshold:** 0.90 (very strict)

---

#### 6-12. **Other Relationship Types**
- `CHILD_OF / PARENT_OF`: Hierarchy relationships
- `VARIANT_OF`: Variant/specialized version
- `DETECTABLE_BY`: How to detect
- `TESTED_BY`: Test case
- `REFERENCES`: External reference
- `IMPLEMENTS`: Implements standard

---

## 🗃️ Neo4j Schema Definition

### Node Labels & Indexes

```cypher
// Weakness nodes
CREATE INDEX idx_weakness_id FOR (w:Weakness) ON (w.id);
CREATE INDEX idx_weakness_cwe FOR (w:Weakness) ON (w.cwe_id);
CREATE CONSTRAINT unique_weakness_id FOR (w:Weakness) REQUIRE w.id IS UNIQUE;

// Mitigation nodes
CREATE INDEX idx_mitigation_id FOR (m:Mitigation) ON (m.id);
CREATE CONSTRAINT unique_mitigation_id FOR (m:Mitigation) REQUIRE m.id IS UNIQUE;

// Platform nodes
CREATE INDEX idx_platform_id FOR (p:AffectedPlatform) ON (p.id);

// Full-text search
CALL db.index.fulltext.createNodeIndex(
    "entities",
    ["Weakness", "Mitigation", "AffectedPlatform"],
    ["name", "id", "description"]
);
```

---

## ✅ Validation Rules

### Confidence Thresholds

| Entity Type | Min Confidence | Reason |
|------------|----------------|--------|
| All Entities | 0.85 | High confidence in extraction |
| MITIGATED_BY | 0.85 | Direct mitigation relationship |
| AFFECTS | 0.75 | Platform impact confidence |
| RELATED_TO | 0.75 | Similarity confidence |
| HAS_CONSEQUENCE | 0.80 | Impact certainty |
| MAPPED_TO | 0.90 | CVE-CWE mapping (strict) |

---

### Relationship Validation

**MITIGATED_BY** relationship:
- Source: Weakness, Vulnerability
- Target: Mitigation
- Min Confidence: 0.85
- Validation: Must have both source AND target as valid nodes

**AFFECTS** relationship:
- Source: Weakness, Vulnerability
- Target: AffectedPlatform
- Min Confidence: 0.75
- Validation: Platform must exist in database

**RELATED_TO** relationship:
- Source: Any of (Weakness, Vulnerability, Mitigation)
- Target: Any of (Weakness, Vulnerability, Mitigation)
- Min Confidence: 0.75
- Validation: Cannot relate entity to itself

---

## 📊 Current Graph Statistics

```
Total Nodes: 21
  - Weakness: 13
  - Mitigation: 4
  - AffectedPlatform: 3

Total Relationships: 20
  - MITIGATED_BY: 9 (45%)
  - RELATED_TO: 6 (30%)
  - AFFECTS: 5 (25%)

Connectivity: 100% of nodes connected
Graph Density: ~4.5% (20 edges / 420 possible)
Avg Degree: 1.9 relations per node
```

---

## 🔍 Key Queries

### Find High-Severity Weaknesses
```cypher
MATCH (w:Weakness)
WHERE w.severity = 'High' AND w.confidence >= 0.85
RETURN w.id, w.name, w.severity
ORDER BY w.confidence DESC
```

### Get Mitigations for Weakness
```cypher
MATCH (w:Weakness {id: 'cwe-89'})-[r:MITIGATED_BY]->(m:Mitigation)
RETURN m.id, m.name, r.confidence
ORDER BY r.confidence DESC
```

### Find Affected Platforms
```cypher
MATCH (w:Weakness)-[r:AFFECTS]->(p:AffectedPlatform)
WHERE r.confidence >= 0.75
RETURN p.id, p.name, COUNT(DISTINCT w.id) as weakness_count
ORDER BY weakness_count DESC
```

### Find Attack Chains
```cypher
MATCH path = (w1:Weakness)-[r:RELATED_TO*2..4]->(w2:Weakness)
WHERE ALL(rel IN relationships(path) WHERE rel.confidence >= 0.75)
RETURN w1.name, w2.name, length(path) as chain_length
LIMIT 10
```

---

## 🛡️ Quality Metrics

### Target Standards

| Metric | Target | Current |
|--------|--------|---------|
| Entity Confidence | ≥ 0.85 | ✅ 100% |
| Relation Confidence | ≥ 0.75 | ✅ 100% |
| Connectivity | >80% | ✅ 100% |
| Orphaned Nodes | <10% | ✅ 0% |
| Graph Density | >5% | ⚠️ 4.5% |

---

## 🚀 Usage Examples

### Import & Query

```python
from app.domain.models import Weakness, Mitigation, EntityType, RelationType
from app.domain.graph_schema import CYPHER_QUERIES
from app.domain.graph_operations import GraphAnalyzer, GraphQueryBuilder

# Create entity
weakness = Weakness(
    id="cwe-89",
    name="SQL Injection",
    severity="High",
    confidence=0.95
)

# Build query
query = GraphQueryBuilder.find_mitigations_for_weakness("cwe-89")

# Analyze graph
analyzer = GraphAnalyzer()
connectivity = analyzer.calculate_connectivity_ratio(total=21, connected=21)
```

---

## 📚 Files

| File | Purpose |
|------|---------|
| [models.py](app/domain/models.py) | Pydantic domain classes for all entities & relationships |
| [graph_schema.py](app/domain/graph_schema.py) | Neo4j schema definitions, queries, validation rules |
| [graph_operations.py](app/domain/graph_operations.py) | Query builders, analyzers, validators, recommendations |

---

## 📝 Next Steps

1. **Extend entity types** as new security concepts emerge
2. **Add more relationships** (PARENT_OF, VARIANT_OF, etc.) from CWE hierarchy
3. **Build reasoning engine** using relationship chains
4. **Add knowledge base** with external CVE/CWE mappings
5. **Create recommendation API** using graph analytics

---

**Last Updated:** 2026-04-23  
**Version:** 1.0 - Production Release
