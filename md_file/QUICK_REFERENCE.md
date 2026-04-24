# 🚀 Quick Reference - Security Knowledge Graph

## Entity Types at a Glance

```
CURRENT (In Database Now):
├─ Weakness (13)           ← CWE weaknesses
├─ Mitigation (4)          ← Security fixes
└─ AffectedPlatform (3)    ← Platforms/frameworks

EXTENSIBLE (Ready to use):
├─ Vulnerability (CVE)
├─ Consequence (Impact)
├─ Reference (Documentation)
├─ CWECategory (Hierarchy)
└─ AttackVector/DetectionMethod/TestCase
```

---

## Relationship Types at a Glance

```
CURRENT (In Database Now):
├─ MITIGATED_BY (9)  [conf ≥ 0.85] ← Weakness → Mitigation
├─ AFFECTS (5)       [conf ≥ 0.75] ← Weakness → Platform
└─ RELATED_TO (6)    [conf ≥ 0.75] ← Weakness → Weakness

AVAILABLE (Ready to query):
├─ HAS_CONSEQUENCE
├─ MAPPED_TO (CVE → CWE)
├─ REFERENCES
├─ CHILD_OF/PARENT_OF (hierarchy)
├─ VARIANT_OF
└─ DETECTABLE_BY/TESTED_BY (validation)
```

---

## Python Code Examples

### Create Entity

```python
from app.domain.models import Weakness, Mitigation

# Create weakness
weakness = Weakness(
    id="cwe-89",
    name="SQL Injection",
    severity="High",
    confidence=0.95,
    properties={"cwe_id": "CWE-89"}
)

# Create mitigation
mitigation = Mitigation(
    id="mit-001",
    name="Parameterized Queries",
    effectiveness="High",
    confidence=0.92
)
```

### Query Graph

```python
from app.domain.graph_operations import GraphQueryBuilder

# Find mitigations for a weakness
query = GraphQueryBuilder.find_mitigations_for_weakness("cwe-89")
# Returns Cypher query ready for Neo4j

# Find impact chain
chain_query = GraphQueryBuilder.find_impact_chain("cwe-89", depth=3)

# Get attack surface
surface = GraphQueryBuilder.get_attack_surface("platform-java")
```

### Analyze Graph

```python
from app.domain.graph_operations import GraphAnalyzer, RelationshipValidator

# Calculate metrics
density = GraphAnalyzer.calculate_graph_density(entity_count=21, relation_count=20)
connectivity = GraphAnalyzer.calculate_connectivity_ratio(total=21, connected=21)

# Find isolated nodes
isolated = GraphAnalyzer.find_isolated_nodes(nodes, relationships)

# Validate relationship
is_valid, msg = RelationshipValidator.validate_relation_confidence("MITIGATED_BY", 0.92)
```

---

## Neo4j Cypher Cheat Sheet

### Find High-Risk Weaknesses
```cypher
MATCH (w:Weakness)
WHERE w.severity = 'High' AND w.confidence >= 0.85
RETURN w.id, w.name, w.severity
ORDER BY w.confidence DESC
```

### Get Mitigations for Weakness
```cypher
MATCH (w:Weakness {id: 'cwe-89'})-[r:MITIGATED_BY]->(m:Mitigation)
WHERE r.confidence >= 0.85
RETURN m.id, m.name, m.effectiveness, r.confidence
ORDER BY r.confidence DESC
```

### Find Unmitigated Weaknesses
```cypher
MATCH (w:Weakness)
WHERE NOT EXISTS((w)-[:MITIGATED_BY]->())
RETURN w.id, w.name, w.severity
```

### Find Most Vulnerable Platform
```cypher
MATCH (p:AffectedPlatform)<-[r:AFFECTS]-(w:Weakness)
WHERE r.confidence >= 0.75
RETURN p.id, p.name, COUNT(w) as risk_count
ORDER BY risk_count DESC
LIMIT 1
```

### Find Related Weaknesses (Attack Chains)
```cypher
MATCH path = (w1:Weakness {id: 'cwe-89'})-[r:RELATED_TO*1..3]->(w2:Weakness)
RETURN w2.id, w2.name, length(path) as distance
ORDER BY distance
LIMIT 10
```

### Mitigation Impact Analysis
```cypher
MATCH (m:Mitigation)-[r:MITIGATED_BY*1..]->(w:Weakness)
WHERE r.confidence >= 0.85
RETURN m.id, m.name, COUNT(DISTINCT w.id) as weakness_count
ORDER BY weakness_count DESC
```

---

## Validation Rules Quick Check

| Rule | Min Value | Type |
|------|-----------|------|
| Entity confidence | 0.85 | STRICT |
| MITIGATED_BY confidence | 0.85 | STRICT |
| AFFECTS confidence | 0.75 | MEDIUM |
| RELATED_TO confidence | 0.75 | MEDIUM |
| HAS_CONSEQUENCE confidence | 0.80 | HIGH |

---

## Quality Metrics

```
Current State (10-chunk test):
✅ Unknown-entity nodes: 0 (filtered)
✅ Entity confidence: >0.85 (all valid)
✅ Relation confidence: >0.75 (all valid)
✅ Connectivity: 100%
✅ Orphaned nodes: 0

Target State:
✅ Min entity confidence: 0.85
✅ Min relation confidence: 0.75
✅ Max orphaned: <10%
✅ Connectivity: >80%
✅ Graph density: >5%
```

---

## Import Paths

```python
# Domain models
from app.domain.models import (
    EntityType, RelationType,
    Weakness, Mitigation, AffectedPlatform,
    Vulnerability, Consequence, Reference
)

# Graph schema
from app.domain.graph_schema import (
    NODE_SCHEMAS, RELATIONSHIP_SCHEMAS,
    CYPHER_QUERIES, VALIDATION_RULES
)

# Operations
from app.domain.graph_operations import (
    GraphQueryBuilder,
    GraphAnalyzer,
    RelationshipValidator,
    GraphRecommendations
)
```

---

## Common Patterns

### Pattern 1: Find & Fix Unmitigated Weaknesses
```python
# Query unmitigated
unmitigated = [
    w.id for w in weaknesses
    if not any(r.source_id == w.id and r.type == "MITIGATED_BY" for r in relationships)
]

# Recommend mitigations
for weak_id in unmitigated:
    recommendations = GraphRecommendations.get_high_priority_mitigations([...], [...])
```

### Pattern 2: Assess Platform Risk
```python
# Get all weaknesses affecting platform
vulnerable_weaknesses = [
    r.source_id for r in relationships
    if r.type == "AFFECTS" and r.target_id == "platform-java" and r.confidence >= 0.75
]

# Check mitigation coverage
unmitigated = [
    w for w in weaknesses
    if w.id in vulnerable_weaknesses and not any(...)
]
```

### Pattern 3: Find Attack Chains
```python
# Get related weaknesses (possible attack progression)
# Use RELATED_TO relationships with high confidence
chains = [
    (w1.name, w2.name) for r in relationships
    if r.type == "RELATED_TO" and r.confidence >= 0.75
]
```

---

## Troubleshooting

### Q: Unknown entities appearing?
**A:** Check entity validation in `extraction_service.py`:
```python
if name.lower() == "unknown-entity" or not name:
    logger.debug(f"❌ Entity {entity_id}: invalid/unknown name")
    continue  # Skip
```

### Q: Low confidence relationships?
**A:** Check relation filtering:
```python
if confidence < 0.75:
    rejected.append(f"Rel {rel_id}: confidence too low")
    continue
```

### Q: Orphaned nodes?
**A:** Ensure source-local requirement:
```python
if not source_local:  # Source must exist in current chunk
    rejected.append(f"Rel {rel_id}: source not local")
    continue
```

---

## Resources

📖 **Full Documentation:** [SCHEMA_DOCUMENTATION.md](SCHEMA_DOCUMENTATION.md)
💻 **Code Files:**
- [app/domain/models.py](app/domain/models.py)
- [app/domain/graph_schema.py](app/domain/graph_schema.py)
- [app/domain/graph_operations.py](app/domain/graph_operations.py)

📊 **Execution Guide:** [EXECUTION_GUIDE_VI.md](EXECUTION_GUIDE_VI.md)
🔧 **Fixes Summary:** [FIXES_SUMMARY_VI.md](FIXES_SUMMARY_VI.md)

---

**Last Updated:** 2026-04-23 | **Version:** 1.0
