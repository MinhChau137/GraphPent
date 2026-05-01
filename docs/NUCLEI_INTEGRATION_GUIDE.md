# Nuclei Integration Guide - Phase 3

**Phase**: 3 of 5  
**Date**: April 28, 2026  
**Status**: ✅ COMPLETE

---

## 📖 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Service Components](#service-components)
3. [Database Schema](#database-schema)
4. [Usage Examples](#usage-examples)
5. [API Reference](#api-reference)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## 🏗️ Architecture Overview

### **Three-Layer Architecture**

```
Layer 1: Parser (Phase 2)
└── NucleiParser
    ├── JSONL parsing
    ├── Finding normalization
    └── Severity mapping

Layer 2: Integration Service (Phase 3.1)
└── NucleiIntegrationService
    ├── Orchestration
    ├── Pipeline execution
    └── Error handling

Layer 3: Storage (Phase 3.2, 3.3)
├── Neo4j (NucleiStorageManager)
│   ├── :DiscoveredVulnerability nodes
│   ├── CORRELATES_TO relationships
│   └── CLASSIFIED_AS relationships
└── PostgreSQL (NucleiPostgresService)
    ├── nuclei_scans table
    └── nuclei_findings table
```

### **Data Flow**

```
Nuclei JSON Output
    ↓
NucleiParser.normalize()
    ↓
Finding[] (validated, normalized)
    ↓
NucleiIntegrationService.process_nuclei_output()
    ├─ NucleiStorageManager.bulk_create_findings()
    │   └─ Neo4jAdapter.create_discovered_vulnerability()
    ├─ NucleiStorageManager.create_finding_relationships()
    │   ├─ create_finding_cve_relationship()
    │   └─ create_finding_cwe_relationship()
    └─ NucleiPostgresService.bulk_create_findings()
        └─ nuclei_findings table
    ↓
Result: {
  scan_id, findings_count, findings_stored,
  cve_relationships, cwe_relationships, status
}
```

---

## 🔧 Service Components

### **1. NucleiIntegrationService**

Main orchestration service.

**Initialization**:
```python
from app.services.nuclei_services import NucleiIntegrationService
from app.adapters.neo4j_client import Neo4jAdapter

neo4j = Neo4jAdapter()
service = NucleiIntegrationService(neo4j)
```

**Key Methods**:
```python
# Process findings
result = await service.process_nuclei_output(
    nuclei_output=nuclei_json,
    target_url="http://target.com"
)

# Query findings
critical = await service.get_critical_findings()
by_host = await service.get_findings_by_host("192.168.1.1")
by_template = await service.get_findings_by_template("sql-injection")
by_severity = await service.get_findings_by_severity("CRITICAL")

# Get specific finding
finding = await service.get_finding(finding_id)

# Delete findings
result = await service.delete_findings_by_template("template-id")
```

---

### **2. NucleiStorageManager**

Neo4j operations manager.

**Responsibilities**:
- Create `:DiscoveredVulnerability` nodes
- Create relationships (CORRELATES_TO, CLASSIFIED_AS)
- Query findings from Neo4j
- Delete findings by criteria

**Internal Methods**:
```python
# Create nodes
await storage.create_finding_node(finding)
await storage.bulk_create_findings(findings)

# Create relationships
await storage.create_cve_relationship(finding_id, cve_id)
await storage.create_cwe_relationship(finding_id, cwe_id)
await storage.create_finding_relationships(finding)

# Query
findings = await storage.query_findings_by_severity("CRITICAL")
findings = await storage.query_findings_by_host("192.168.1.1")
findings = await storage.query_findings_by_template("template-id")
finding = await storage.get_finding_by_id(finding_id)

# Delete
result = await storage.delete_findings_by_template(template_id)
```

---

### **3. NucleiPostgresService**

PostgreSQL scan tracking service.

**Responsibilities**:
- Create scan records
- Update scan status
- Store finding metadata
- Query scan history

**Methods**:
```python
# Create scan
scan_id = await postgres.create_scan(
    target_url="http://target.com",
    scan_type="full"
)

# Update status
await postgres.update_scan_status(
    scan_id=scan_id,
    status="completed",
    findings_count=5
)

# Get scan details
scan = await postgres.get_scan(scan_id)

# Store findings
await postgres.create_finding(
    scan_id=scan_id,
    finding_id=finding_id,
    template_id="sql-injection",
    severity="CRITICAL",
    ...
)

# Query history
scans = await postgres.get_scan_history(limit=20)
findings = await postgres.get_scan_findings(scan_id)
```

---

## 💾 Database Schema

### **PostgreSQL Tables**

#### **nuclei_scans**
```sql
Column              | Type
--------------------|------------------
id                  | VARCHAR(36) PRIMARY KEY
target_url          | VARCHAR(1024)
status              | VARCHAR(50) -- pending, running, completed, failed
findings_count      | INTEGER
scan_type           | VARCHAR(50) -- full, web, api
raw_output_path     | VARCHAR(1024)
neo4j_status        | VARCHAR(50)
neo4j_error         | TEXT
error_message       | TEXT
metadata            | JSONB
started_at          | TIMESTAMP
completed_at        | TIMESTAMP
created_at          | TIMESTAMP (DEFAULT now())
updated_at          | TIMESTAMP (DEFAULT now())
```

#### **nuclei_findings**
```sql
Column              | Type
--------------------|------------------
id                  | VARCHAR(36) PRIMARY KEY
scan_id             | VARCHAR(36) FK → nuclei_scans
finding_id          | VARCHAR(36)
template_id         | VARCHAR(256)
severity            | VARCHAR(50)
host                | VARCHAR(256)
url                 | VARCHAR(2048)
matched_at          | TIMESTAMP
source              | VARCHAR(50) DEFAULT 'nuclei'
cve_ids             | JSONB
cwe_ids             | JSONB
metadata            | JSONB
neo4j_id            | VARCHAR(36)
created_at          | TIMESTAMP (DEFAULT now())
updated_at          | TIMESTAMP (DEFAULT now())
```

### **Indexes**
- `idx_nuclei_scans_target_url`
- `idx_nuclei_scans_status`
- `idx_nuclei_scans_created_at`
- `idx_nuclei_findings_scan_id`
- `idx_nuclei_findings_template_id`
- `idx_nuclei_findings_severity`
- `idx_nuclei_findings_host`

---

## 💡 Usage Examples

### **Example 1: Process Nuclei Output**

```python
import asyncio
from app.services.nuclei_services import NucleiIntegrationService
from app.adapters.neo4j_client import Neo4jAdapter

async def scan_and_store():
    # Initialize
    neo4j = Neo4jAdapter()
    service = NucleiIntegrationService(neo4j)
    
    # Nuclei output (JSONL format)
    nuclei_output = """
{"template-id":"http-missing-headers","severity":"high","host":"192.168.1.100","url":"http://192.168.1.100/","matched-at":"2026-04-28T08:00:00Z","cve-id":"CVE-2021-12345","cwe-id":"CWE-693"}
{"template-id":"sql-injection","severity":"critical","host":"192.168.1.101","url":"http://192.168.1.101/api/search","matched-at":"2026-04-28T08:05:00Z","cve-id":"CVE-2024-1234","cwe-id":"CWE-89"}
"""
    
    # Process
    result = await service.process_nuclei_output(
        nuclei_output=nuclei_output,
        target_url="http://192.168.1.0/24"
    )
    
    print(f"Scan ID: {result['scan_id']}")
    print(f"Findings: {result['findings_count']}")
    print(f"Stored: {result['findings_stored']}")
    print(f"CVE Relationships: {result['cve_relationships']}")
    
    await neo4j.close()

asyncio.run(scan_and_store())
```

### **Example 2: Query Critical Findings**

```python
async def get_critical_findings():
    neo4j = Neo4jAdapter()
    service = NucleiIntegrationService(neo4j)
    
    # Get critical findings
    critical = await service.get_critical_findings()
    
    for finding in critical:
        print(f"Host: {finding['host']}")
        print(f"URL: {finding['url']}")
        print(f"Template: {finding['template_id']}")
        print(f"CVEs: {', '.join(finding.get('cve_ids', []))}")
        print("---")
    
    await neo4j.close()

asyncio.run(get_critical_findings())
```

### **Example 3: Analyze by Host**

```python
async def analyze_host(host: str):
    neo4j = Neo4jAdapter()
    service = NucleiIntegrationService(neo4j)
    
    # Get findings for host
    findings = await service.get_findings_by_host(host)
    
    # Summarize by severity
    by_severity = {}
    for f in findings:
        severity = f['severity']
        by_severity[severity] = by_severity.get(severity, 0) + 1
    
    print(f"Host: {host}")
    print(f"Total Findings: {len(findings)}")
    for severity, count in by_severity.items():
        print(f"  {severity}: {count}")
    
    await neo4j.close()

asyncio.run(analyze_host("192.168.1.100"))
```

---

## 📡 API Reference

### **NucleiIntegrationService**

#### `process_nuclei_output(nuclei_output, scan_id, target_url)`

**Description**: Process Nuclei output end-to-end

**Parameters**:
- `nuclei_output` (str|dict|list): Nuclei output (JSONL, dict, or list)
- `scan_id` (str, optional): Custom scan ID (generates UUID if not provided)
- `target_url` (str, optional): Target URL for scan

**Returns**: Dictionary
```python
{
    "scan_id": "uuid-xxx",
    "findings_count": 3,
    "findings_stored": 3,
    "findings_failed": 0,
    "cve_relationships": 3,
    "cwe_relationships": 4,
    "status": "completed",
    "parser_warnings": 0,
    "relationship_errors": 0
}
```

**Example**:
```python
result = await service.process_nuclei_output(
    nuclei_output=nuclei_json,
    target_url="http://example.com"
)
assert result["status"] == "completed"
```

---

#### `get_findings_by_severity(severity)`

**Description**: Query findings by severity level

**Parameters**:
- `severity` (str): CRITICAL, HIGH, MEDIUM, LOW, or INFO

**Returns**: List[Dict]
```python
[
    {
        "id": "uuid",
        "template_id": "sql-injection",
        "severity": "CRITICAL",
        "host": "192.168.1.100",
        "url": "http://192.168.1.100/api",
        "matched_at": "2026-04-28T08:05:00Z",
        "cve_ids": ["CVE-2024-1234"],
        "cwe_ids": ["CWE-89"]
    }
]
```

---

#### `get_findings_by_host(host)`

**Description**: Query findings by target host

**Parameters**:
- `host` (str): Target host/IP

**Returns**: List[Dict] (same structure as above)

---

#### `get_findings_by_template(template_id)`

**Description**: Query findings by Nuclei template ID

**Parameters**:
- `template_id` (str): Template identifier

**Returns**: List[Dict]

---

#### `get_critical_findings()`, `get_high_findings()`

**Description**: Convenience methods for common queries

**Returns**: List[Dict]

---

#### `get_finding(finding_id)`

**Description**: Get specific finding by UUID

**Parameters**:
- `finding_id` (str): Finding UUID

**Returns**: Dict or None

---

#### `delete_findings_by_template(template_id)`

**Description**: Delete all findings for a template

**Parameters**:
- `template_id` (str): Template to delete

**Returns**: Dictionary with deletion count

---

### **NucleiPostgresService**

#### `create_scan(target_url, scan_type, metadata)`

Creates a new scan record.

**Returns**: Scan ID (UUID string)

---

#### `get_scan(scan_id)`

Gets scan details.

**Returns**: Dict or None

---

#### `get_scan_history(limit, status_filter)`

Gets recent scans.

**Returns**: List[Dict]

---

#### `get_scan_findings(scan_id, limit)`

Gets findings for a scan.

**Returns**: List[Dict]

---

## ⚠️ Error Handling

### **Common Errors**

#### **Parser Errors**

```python
# Invalid JSON
result = await service.process_nuclei_output("{invalid json")
# → result["findings_count"] == 0

# Malformed severity
result = await service.process_nuclei_output({
    "template-id": "test",
    "severity": "INVALID",  # ← Will be logged as warning
    "host": "192.168.1.1"
})
# → Finding skipped, logged in result["parser_warnings"]
```

#### **Neo4j Errors**

```python
try:
    result = await service.process_nuclei_output(output)
    if result["status"] == "failed":
        print(f"Error: {result['error']}")
except Exception as e:
    logger.error(f"Processing failed: {e}")
```

#### **PostgreSQL Errors**

```python
# Connection errors are caught and logged
# Service will retry automatically (retry decorator)
# If all retries fail, error is logged and processing continues
```

### **Retry Logic**

All Neo4j operations have retry logic:
- **Attempts**: 3
- **Strategy**: Exponential backoff (2s, 4s, 8s)
- **Fallback**: Log error and return failure

---

## 🎯 Best Practices

### **1. Use Async/Await**

```python
# ✅ Good
async def process_scans():
    results = []
    for nuclei_output in outputs:
        result = await service.process_nuclei_output(nuclei_output)
        results.append(result)
    return results

# ❌ Bad - synchronous usage
result = service.process_nuclei_output(nuclei_output)  # Won't work
```

### **2. Handle Partial Failures**

```python
result = await service.process_nuclei_output(output)

if result["findings_failed"] > 0:
    logger.warning(f"Some findings failed: {result}")

# Still process successfully stored findings
for finding_id in successful_findings:
    ...
```

### **3. Batch Queries**

```python
# ✅ Better
all_findings = await service.get_findings_by_severity("CRITICAL")

# ❌ Avoid repeated queries
for i in range(100):
    findings = await service.get_findings_by_severity("CRITICAL")
```

### **4. Check Service State**

```python
# Initialize once, reuse
neo4j = Neo4jAdapter()
service = NucleiIntegrationService(neo4j)

# Multiple operations
result1 = await service.process_nuclei_output(output1)
result2 = await service.process_nuclei_output(output2)

# Close when done
await neo4j.close()
```

### **5. Monitor Error Rates**

```python
results = []
for output in outputs:
    result = await service.process_nuclei_output(output)
    results.append(result)

# Calculate success rate
total_findings = sum(r["findings_count"] for r in results)
total_stored = sum(r["findings_stored"] for r in results)
success_rate = (total_stored / total_findings * 100) if total_findings > 0 else 0

logger.info(f"Success rate: {success_rate:.2f}%")
```

---

## 🔧 Troubleshooting

### **Issue: No findings stored**

**Cause**: Neo4j connection failure

**Solution**:
```bash
# Check Neo4j is running
docker exec neo4j cypher-shell "MATCH (n) RETURN COUNT(n)"

# Check settings
echo $NEO4J_URI
echo $NEO4J_USER
```

### **Issue: Wrong CVE/CWE links**

**Cause**: Missing CVE/CWE nodes in database

**Solution**:
```cypher
-- Check if CVE exists
MATCH (c:CVE {id: "CVE-2024-1234"})
RETURN c;

-- If missing, check data loading
MATCH (c:CVE) RETURN COUNT(c) as cve_count;
```

### **Issue: Slow queries**

**Cause**: Missing indexes

**Solution**:
```cypher
-- Verify indexes
CALL db.indexes() YIELD name, labelsOrTypes
WHERE labelsOrTypes[0] = "DiscoveredVulnerability"
RETURN name;

-- If missing, create manually
CREATE INDEX idx_finding_severity 
ON :DiscoveredVulnerability(severity);
```

### **Issue: Duplicate findings**

**Cause**: Re-running same scan

**Solution**: MERGE handles deduplication automatically
```cypher
-- Or query for duplicates
MATCH (f:DiscoveredVulnerability {id: "uuid"})
RETURN COUNT(f);  -- Should be 1
```

---

## 📋 Migration Checklist

Before going to production:

- [ ] PostgreSQL tables created
- [ ] Indexes created
- [ ] Neo4j `:DiscoveredVulnerability` label active
- [ ] Relationships CORRELATES_TO, CLASSIFIED_AS defined
- [ ] NucleiPostgresService initialized
- [ ] First scan completes successfully
- [ ] Findings visible in Neo4j
- [ ] PostgreSQL records created
- [ ] Queries work correctly
- [ ] Error handling tested
- [ ] Performance acceptable (<1s per finding)

---

**Documentation Complete**: 2026-04-28  
**Status**: ✅ Production Ready  
**Version**: 1.0

