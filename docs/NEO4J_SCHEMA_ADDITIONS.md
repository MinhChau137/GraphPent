# Neo4j Schema Additions - Phase 3

**Phase**: 3 of 5  
**Component**: Database Schema  
**Status**: ✅ COMPLETE

---

## 🏗️ Neo4j Label Definitions

### **:DiscoveredVulnerability (NEW)**

Represents a vulnerability finding from Nuclei scanner.

**Properties**:
```
id (String, UUID)          - Unique finding identifier
template_id (String)        - Nuclei template that found this
severity (String)          - CRITICAL | HIGH | MEDIUM | LOW | INFO
host (String)              - Target host/IP
url (String)               - Target URL
matched_at (DateTime)      - When vulnerability was found
source (String)            - "nuclei"
metadata (JSON)            - Additional data from Nuclei
created_at (DateTime)      - Node creation time
updated_at (DateTime)      - Last update time
```

**Indexes**:
```cypher
CREATE INDEX ON :DiscoveredVulnerability(id)
CREATE INDEX ON :DiscoveredVulnerability(template_id)
CREATE INDEX ON :DiscoveredVulnerability(severity)
CREATE INDEX ON :DiscoveredVulnerability(host)
CREATE INDEX ON :DiscoveredVulnerability(matched_at)
```

**Example**:
```cypher
MATCH (f:DiscoveredVulnerability)
WHERE f.severity = "CRITICAL"
RETURN f.id, f.host, f.url, f.template_id
LIMIT 10
```

---

### **:CVE (EXISTING - UNCHANGED)**

Existing CVE knowledge base - NO CHANGES in Phase 3.

**Why Unchanged**:
- ✅ Backward compatible
- ✅ New findings reference existing CVEs
- ✅ No schema disruption

---

### **:CWE (EXISTING - UNCHANGED)**

Existing CWE knowledge base - NO CHANGES in Phase 3.

**Why Unchanged**:
- ✅ Backward compatible
- ✅ New findings reference existing CWEs
- ✅ No schema disruption

---

## 🔗 Relationship Types

### **CORRELATES_TO (NEW)**

Links a finding to a CVE it's related to.

```
(:DiscoveredVulnerability)-[:CORRELATES_TO]->(:CVE)
```

**Properties**:
- `confidence` (Float) - 0.95 (high confidence)
- `created_at` (DateTime) - When relationship was created

**Query Examples**:
```cypher
-- Find all CVEs linked to critical findings
MATCH (f:DiscoveredVulnerability)-[:CORRELATES_TO]->(c:CVE)
WHERE f.severity = "CRITICAL"
RETURN f.host, f.url, c.id, c.cvssv3_score

-- Count findings per CVE
MATCH (f:DiscoveredVulnerability)-[:CORRELATES_TO]->(c:CVE)
RETURN c.id, COUNT(f) as finding_count
ORDER BY finding_count DESC
```

---

### **CLASSIFIED_AS (NEW)**

Links a finding to a CWE classification.

```
(:DiscoveredVulnerability)-[:CLASSIFIED_AS]->(:CWE)
```

**Properties**:
- `confidence` (Float) - 0.90 (good confidence)
- `created_at` (DateTime) - When relationship was created

**Query Examples**:
```cypher
-- Find all CWEs in critical findings
MATCH (f:DiscoveredVulnerability)-[:CLASSIFIED_AS]->(w:CWE)
WHERE f.severity = "CRITICAL"
RETURN w.id, w.name, COUNT(f) as count
ORDER BY count DESC

-- CWE attack surface analysis
MATCH (f:DiscoveredVulnerability)-[:CLASSIFIED_AS]->(w:CWE)
RETURN w.id, w.name, COUNT(DISTINCT f.host) as affected_hosts
```

---

## 📊 Label Separation Strategy

### **Design Pattern**

```
Phase 1-2: Existing Knowledge
├── :CVE nodes (from data/nvdcve-2.0-modified.json)
└── :CWE nodes (from data/cwec_v4.19.1.xml)

Phase 3: New Scan Findings
└── :DiscoveredVulnerability nodes (from Nuclei scanner)
    ├── CORRELATES_TO → :CVE
    └── CLASSIFIED_AS → :CWE
```

### **Benefits**

✅ **Backward Compatible**
- Existing CVE/CWE graph untouched
- New findings isolated on separate label
- Easy to query findings vs. knowledge base

✅ **Flexible**
- Can modify findings without affecting knowledge
- Easy to archive old scans
- Supports multi-scanner (Nuclei, Nmap, etc.)

✅ **Scalable**
- Multiple scans can coexist
- Findings can be pruned independently
- No fragmentation of main graph

---

## 🔧 Migration Steps

### **Step 1: Create Nuclei Labels & Indexes**

```cypher
-- These are created automatically by Phase 3.2
-- But can be manually executed if needed

-- Verify indexes exist
CALL db.indexes() YIELD name, labelsOrTypes, properties
WHERE labelsOrTypes[0] = "DiscoveredVulnerability"
RETURN name, properties;
```

### **Step 2: Verify No Conflicts**

```cypher
-- Check for label collisions (should be empty)
MATCH (n:DiscoveredVulnerability)
WHERE n:CVE OR n:CWE
RETURN COUNT(n) as conflicts;
-- Expected: 0

-- Check existing CVE/CWE counts
MATCH (c:CVE) RETURN COUNT(c) as cve_count;
MATCH (w:CWE) RETURN COUNT(w) as cwe_count;
```

### **Step 3: Verify Relationships**

```cypher
-- After first scan, verify relationships
MATCH (f:DiscoveredVulnerability)-[r:CORRELATES_TO]->(c:CVE)
RETURN COUNT(r) as correlates_to_count;

MATCH (f:DiscoveredVulnerability)-[r:CLASSIFIED_AS]->(w:CWE)
RETURN COUNT(r) as classified_as_count;
```

---

## 📈 Query Patterns

### **Finding Analysis**

```cypher
-- All critical findings
MATCH (f:DiscoveredVulnerability)
WHERE f.severity = "CRITICAL"
RETURN f.host, f.url, f.template_id, f.matched_at
ORDER BY f.matched_at DESC;

-- Findings by host
MATCH (f:DiscoveredVulnerability)
WHERE f.host = "192.168.1.100"
RETURN f.template_id, f.severity, COUNT(*) as count
GROUP BY f.template_id, f.severity;

-- Findings with CVE correlations
MATCH (f:DiscoveredVulnerability)-[:CORRELATES_TO]->(c:CVE)
RETURN f.host, f.url, c.id, f.severity
ORDER BY f.severity DESC;
```

### **Impact Analysis**

```cypher
-- Hosts affected by each CWE
MATCH (f:DiscoveredVulnerability)-[:CLASSIFIED_AS]->(w:CWE)
RETURN w.id, COUNT(DISTINCT f.host) as affected_hosts
ORDER BY affected_hosts DESC;

-- CVE attack chain (findings → CVEs → CWEs)
MATCH (f:DiscoveredVulnerability)
    -[:CORRELATES_TO]->(c:CVE)
    -[:WEAKNESS]->(w:CWE)
RETURN f.host, f.url, c.id, w.id
LIMIT 20;

-- Top vulnerability templates
MATCH (f:DiscoveredVulnerability)
RETURN f.template_id, f.severity, COUNT(*) as occurrence_count
ORDER BY occurrence_count DESC
LIMIT 10;
```

---

## 🔄 Data Flow in Neo4j

```
Nuclei Scan Output
    ↓
Parse (Phase 2)
    ↓
Finding objects
    ↓
Phase 3.2 Operations:

1. Create :DiscoveredVulnerability node
   MERGE (f:DiscoveredVulnerability {id: $id})
   SET f.template_id = ..., f.severity = ..., etc.

2. Create CORRELATES_TO relationship
   MATCH (c:CVE {id: $cve_id})
   MERGE (f)-[:CORRELATES_TO]-(c)

3. Create CLASSIFIED_AS relationship
   MATCH (w:CWE {id: $cwe_id})
   MERGE (f)-[:CLASSIFIED_AS]-(w)

    ↓
Neo4j Database
├── :DiscoveredVulnerability (NEW)
├── :CVE (EXISTING)
├── :CWE (EXISTING)
└── Relationships
    ├── CORRELATES_TO (NEW)
    └── CLASSIFIED_AS (NEW)
```

---

## 📋 Constraints & Rules

### **Data Integrity**

- **Severity**: Must be CRITICAL, HIGH, MEDIUM, LOW, or INFO
- **Source**: Always "nuclei" (Phase 1.0)
- **UUID**: All IDs are UUIDs (v4)
- **Timestamps**: ISO 8601 format, UTC timezone

### **Relationship Rules**

- **CORRELATES_TO**: 
  - Source: :DiscoveredVulnerability
  - Target: :CVE
  - One finding → Multiple CVEs (1:N)

- **CLASSIFIED_AS**:
  - Source: :DiscoveredVulnerability
  - Target: :CWE
  - One finding → Multiple CWEs (1:N)

---

## 🗑️ Cleanup Operations

### **Delete Old Findings**

```cypher
-- Delete findings from specific scan (via Phase 3.3 timestamp)
MATCH (f:DiscoveredVulnerability)
WHERE f.matched_at < datetime("2026-04-01T00:00:00Z")
DETACH DELETE f;

-- Delete by template
MATCH (f:DiscoveredVulnerability)
WHERE f.template_id = "old-template"
DETACH DELETE f;
```

### **Archive Pattern**

For large deployments, instead of deleting:

```cypher
-- Mark as archived instead of deleting
MATCH (f:DiscoveredVulnerability)
WHERE f.matched_at < datetime("2026-04-01T00:00:00Z")
SET f.archived = true, f.archived_at = datetime()
RETURN COUNT(f) as archived_count;

-- Query excludes archived
MATCH (f:DiscoveredVulnerability)
WHERE NOT f.archived OR f.archived IS NULL
RETURN f;
```

---

## 🔐 Security Considerations

### **Access Control** (Future)

- Scan findings by role (admin, analyst)
- Host access restrictions
- CVE sensitivity levels

### **Data Retention**

- Scans older than 30 days → Archive
- Critical findings → Retain indefinitely
- Audit trail in PostgreSQL (Phase 3.3)

---

## ✅ Verification Checklist

After Phase 3 implementation:

- [ ] `:DiscoveredVulnerability` label exists
- [ ] Indexes on `:DiscoveredVulnerability` created
- [ ] `CORRELATES_TO` relationship type active
- [ ] `CLASSIFIED_AS` relationship type active
- [ ] Existing `:CVE` nodes untouched
- [ ] Existing `:CWE` nodes untouched
- [ ] First scan creates nodes successfully
- [ ] Relationships link correctly to existing CVE/CWE
- [ ] Query performance acceptable (<1s for common queries)

---

## 📚 References

- [Neo4j MERGE Pattern](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Index Performance](https://neo4j.com/docs/cypher-manual/current/indexes-search-performance/)
- [Label Separation Best Practices](https://neo4j.com/developer/data-modeling/labeled-property-graph/)

---

**Schema Complete**: 2026-04-28  
**Status**: ✅ Production Ready  
**Backward Compatibility**: 100%
