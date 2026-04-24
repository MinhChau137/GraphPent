# 🔧 PHASE 1.0: Nuclei Parser Implementation Guide

**Scope**: Add Nuclei vulnerability scanning integration to CVE knowledge management system  
**Duration**: 6-8 weeks  
**Resources**: 2-3 FTE  
**Status**: Ready for implementation  

---

## 📋 Overview

### What We're Building
A Nuclei output parser that:
1. Reads Nuclei JSON/YAML scan results
2. Extracts structured vulnerability data
3. Correlates with existing CVE/CWE knowledge
4. Stores findings in Neo4j with label separation
5. Integrates with existing retrieval system

### What We're NOT Building (Phase 1)
- ❌ Attack execution loop
- ❌ Nmap, Nikto, Metasploit integration (defer to Phase 2)
- ❌ Real-time scanning
- ❌ Multi-target orchestration

### Why Nuclei First?
- ✅ Single tool (simpler than parser factory)
- ✅ Popular in security community
- ✅ Well-structured output format
- ✅ Good foundation for Phase 2 tool additions

---

## 🏗️ Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    User Input                           │
│            "Run Nuclei scan on target.com"             │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│                  Nuclei CLI/API                         │
│         (user runs or API triggers)                     │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│              Nuclei Raw Output (JSON)                   │
│     {                                                   │
│       "template-id": "http-missing-headers",           │
│       "type": "http",                                  │
│       "severity": "high",                              │
│       "cve-id": "CVE-2021-12345",                     │
│       "cwe-id": "CWE-693",                             │
│       ...                                              │
│     }                                                   │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│          ⭐ NEW: Nuclei Parser Module                   │
│  app/adapters/nuclei_parser/                           │
│  ├─ base.py (AbstractParser)                           │
│  ├─ models.py (Finding, Template, Correlation)        │
│  ├─ nuclei_parser.py (Main logic)                      │
│  └─ formatter.py (JSON → Entity/Relationship)          │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│        Structured Entities & Relationships             │
│                                                         │
│  Finding {                                              │
│    id, template_id, severity, cve_id, cwe_id,         │
│    url, timestamp, ...                                  │
│  }                                                       │
│                                                         │
│  Relationship {                                         │
│    Finding → CVE (correlation)                         │
│    Finding → CWE (classification)                      │
│  }                                                       │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│           ⭐ ENHANCED: Neo4j Storage                    │
│                                                         │
│  :DiscoveredVulnerability (NEW label)                  │
│  ├─ template_id, severity, cve_id, cwe_id             │
│  └─ timestamp, url, matched_at                         │
│                                                         │
│  :CVE (EXISTING)                                        │
│  ├─ id, description, score                             │
│                                                         │
│  Relationships:                                         │
│  ├─ Finding -[:CORRELATES_TO]→ CVE (NEW)              │
│  └─ Finding -[:CLASSIFIED_AS]→ CWE (NEW)              │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│        ⭐ ENHANCED: Hybrid Search                       │
│                                                         │
│  Query: "SQL injection vulnerabilities on my app"      │
│                                                         │
│  Results: {                                             │
│    knowledge_base: [...CVE/CWE from existing],        │
│    discovered_findings: [...new Nuclei findings],     │
│    combined_score: reranked                            │
│  }                                                       │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│            User-Facing Reports                         │
│  ✅ Nuclei findings with CVE context                   │
│  ✅ Correlated with knowledge base                     │
│  ✅ Risk assessment & remediation                      │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 File Structure

### New Files to Create

```
app/adapters/nuclei_parser/
├── __init__.py
├── base.py                    # AbstractParser
├── models.py                  # Finding, Template, Correlation data models
├── nuclei_parser.py           # Main Nuclei parser logic
├── formatter.py               # Convert JSON → Entity format
└── validator.py               # Validate Nuclei output format

app/adapters/
├── nuclei_parser_client.py    # Main client for parser
└── nuclei_integration.py      # Service integration layer

app/services/
└── nuclei_integration_service.py  # NEW: Handle parser + graph updates

app/api/v1/routers/
└── nuclei.py                  # NEW: API endpoints for Nuclei

tests/
├── test_nuclei_parser.py      # Parser unit tests
└── test_nuclei_integration.py # Integration tests
```

### Modified Files

```
app/config/settings.py         # Add Nuclei config flags
app/adapters/neo4j_client.py   # Add new queries for findings
app/services/retriever_service.py  # Enhance hybrid search
app/adapters/weaviate_client.py    # (NO change - keep as is)
docker-compose.yml             # (NO change - keep as is)
```

---

## 🔑 Data Models

### 1. Finding (Nuclei result)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict

class Finding(BaseModel):
    """Represents a single Nuclei finding"""
    
    # Core fields from Nuclei output
    template_id: str              # e.g., "http-missing-headers"
    template_name: str            # e.g., "Missing HTTP Headers"
    type: str                     # e.g., "http", "dns", "ssl"
    severity: str                 # "critical", "high", "medium", "low", "info"
    
    # Vulnerability linkage
    cve_id: Optional[str]         # e.g., "CVE-2021-12345"
    cwe_id: Optional[str]         # e.g., "CWE-693"
    cvss_score: Optional[float]   # 0.0-10.0
    
    # Target info
    host: str                     # e.g., "target.com"
    url: str                      # Full URL where finding occurred
    port: Optional[int]           # Port number
    
    # Finding details
    matched_at: datetime          # When template matched
    extracted_values: Dict = {}   # Template-specific extracted data
    
    # Metadata
    scan_id: str                  # Unique scan identifier
    template_author: Optional[str]
    reference: Optional[str]      # Link to advisory/docs
    tags: List[str] = []          # e.g., ["owasp", "cwe"]

class Template(BaseModel):
    """Nuclei template metadata"""
    id: str
    name: str
    description: str
    severity: str
    author: str
    reference: Optional[str]

class Correlation(BaseModel):
    """Link between Finding and CVE/CWE"""
    finding_id: str
    cve_id: Optional[str]
    cwe_id: Optional[str]
    confidence: float             # 0.0-1.0 (how confident is the link?)
    relationship: str             # "CORRELATES_TO", "IMPLEMENTS", "RELATES_TO"
```

---

## 💻 Implementation Guide

### Step 1: Create Base Parser Interface

**File**: `app/adapters/nuclei_parser/base.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from .models import Finding, Correlation

class AbstractParser(ABC):
    """Base class for security tool parsers"""
    
    @abstractmethod
    async def parse(self, raw_output: str) -> List[Finding]:
        """
        Parse raw tool output into Finding objects
        
        Args:
            raw_output: Raw JSON/YAML from tool
            
        Returns:
            List of Finding objects
        """
        pass
    
    @abstractmethod
    async def validate_format(self, raw_output: str) -> bool:
        """Validate output format before parsing"""
        pass
```

### Step 2: Create Nuclei Parser

**File**: `app/adapters/nuclei_parser/nuclei_parser.py`

```python
import json
import yaml
from typing import List, Dict, Any, Optional
from datetime import datetime
from .base import AbstractParser
from .models import Finding, Correlation

class NucleiParser(AbstractParser):
    """Parse Nuclei vulnerability scanner output"""
    
    async def parse(self, raw_output: str) -> List[Finding]:
        """Parse Nuclei JSON/YAML output"""
        findings = []
        
        try:
            # Handle both JSON and YAML
            if raw_output.strip().startswith('{'):
                # Line-delimited JSON
                for line in raw_output.strip().split('\n'):
                    if line.strip():
                        data = json.loads(line)
                        finding = self._convert_nuclei_to_finding(data)
                        if finding:
                            findings.append(finding)
            else:
                # YAML format (less common for Nuclei)
                data = yaml.safe_load(raw_output)
                if isinstance(data, dict):
                    finding = self._convert_nuclei_to_finding(data)
                    if finding:
                        findings.append(finding)
                elif isinstance(data, list):
                    for item in data:
                        finding = self._convert_nuclei_to_finding(item)
                        if finding:
                            findings.append(finding)
            
            return findings
        
        except Exception as e:
            print(f"Error parsing Nuclei output: {e}")
            return []
    
    def _convert_nuclei_to_finding(self, nuclei_result: Dict[str, Any]) -> Optional[Finding]:
        """Convert single Nuclei JSON result to Finding object"""
        
        try:
            # Extract core fields
            template_id = nuclei_result.get('template-id', '')
            if not template_id:
                return None  # Skip invalid entries
            
            finding = Finding(
                # Template info
                template_id=template_id,
                template_name=nuclei_result.get('template', template_id),
                type=nuclei_result.get('type', 'http'),
                severity=nuclei_result.get('severity', 'info').lower(),
                
                # CVE/CWE linkage
                cve_id=nuclei_result.get('cve-id'),
                cwe_id=nuclei_result.get('cwe-id'),
                cvss_score=self._parse_cvss(nuclei_result.get('cvss-score')),
                
                # Target
                host=nuclei_result.get('host', nuclei_result.get('url', '')),
                url=nuclei_result.get('url', ''),
                port=nuclei_result.get('port'),
                
                # Timestamp
                matched_at=datetime.fromisoformat(
                    nuclei_result.get('timestamp', datetime.now().isoformat())
                ),
                
                # Metadata
                scan_id=nuclei_result.get('scan-id', 'unknown'),
                template_author=nuclei_result.get('author'),
                reference=nuclei_result.get('reference'),
                tags=nuclei_result.get('tags', []),
                
                # Extra fields
                extracted_values=nuclei_result.get('extracted-values', {})
            )
            
            return finding
        
        except Exception as e:
            print(f"Error converting Nuclei result: {e}")
            return None
    
    def _parse_cvss(self, cvss_value) -> Optional[float]:
        """Parse CVSS score"""
        try:
            if isinstance(cvss_value, (int, float)):
                return float(cvss_value)
            elif isinstance(cvss_value, str):
                return float(cvss_value)
        except:
            pass
        return None
    
    async def validate_format(self, raw_output: str) -> bool:
        """Validate Nuclei output format"""
        try:
            # Check if it's line-delimited JSON
            lines = raw_output.strip().split('\n')
            for line in lines[:3]:  # Check first 3 lines
                if line.strip():
                    data = json.loads(line)
                    if 'template-id' in data:
                        return True
            return False
        except:
            return False
```

### Step 3: Create Neo4j Integration

**File**: `app/adapters/neo4j_client.py` (ADD these methods):

```python
async def upsert_nuclei_finding(self, finding: Finding) -> str:
    """Store Nuclei finding in Neo4j"""
    
    query = """
    MERGE (f:DiscoveredVulnerability {
        template_id: $template_id,
        host: $host,
        url: $url,
        scan_id: $scan_id
    })
    ON CREATE SET
        f.severity = $severity,
        f.cve_id = $cve_id,
        f.cwe_id = $cwe_id,
        f.template_name = $template_name,
        f.cvss_score = $cvss_score,
        f.created_at = datetime()
    ON MATCH SET
        f.last_seen = datetime()
    RETURN f.template_id
    """
    
    result = await self.driver.execute_query(
        query,
        {
            "template_id": finding.template_id,
            "host": finding.host,
            "url": finding.url,
            "scan_id": finding.scan_id,
            "severity": finding.severity,
            "cve_id": finding.cve_id,
            "cwe_id": finding.cwe_id,
            "template_name": finding.template_name,
            "cvss_score": finding.cvss_score,
        }
    )
    
    # Link to existing CVE if present
    if finding.cve_id:
        await self._correlate_with_cve(finding.template_id, finding.cve_id)
    
    return finding.template_id

async def _correlate_with_cve(self, finding_id: str, cve_id: str):
    """Create relationship: Finding → CVE"""
    
    query = """
    MATCH (f:DiscoveredVulnerability {template_id: $finding_id})
    MATCH (c:CVE {id: $cve_id})
    MERGE (f)-[:CORRELATES_TO]->(c)
    """
    
    await self.driver.execute_query(
        query,
        {"finding_id": finding_id, "cve_id": cve_id}
    )

async def get_findings_by_severity(self, severity: str, limit: int = 10):
    """Query findings by severity"""
    
    query = """
    MATCH (f:DiscoveredVulnerability {severity: $severity})
    OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
    RETURN f, c
    LIMIT $limit
    """
    
    return await self.driver.execute_query(
        query,
        {"severity": severity.lower(), "limit": limit}
    )

async def get_findings_for_host(self, host: str):
    """Query all findings for a specific host"""
    
    query = """
    MATCH (f:DiscoveredVulnerability {host: $host})
    OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
    RETURN f, c
    ORDER BY f.severity DESC
    """
    
    return await self.driver.execute_query(query, {"host": host})
```

### Step 4: Create Integration Service

**File**: `app/services/nuclei_integration_service.py`

```python
from typing import List
from app.adapters.nuclei_parser_client import NucleiParserClient
from app.adapters.neo4j_client import Neo4jAdapter
from app.domain.schemas.pentest import NucleiScan

class NucleiIntegrationService:
    """Handle Nuclei scanning and integration"""
    
    def __init__(
        self, 
        parser_client: NucleiParserClient,
        graph_client: Neo4jAdapter
    ):
        self.parser = parser_client
        self.graph = graph_client
    
    async def process_nuclei_output(self, raw_output: str, scan_id: str):
        """
        Process Nuclei scan output end-to-end:
        1. Parse output
        2. Correlate with CVE
        3. Store in Neo4j
        """
        
        # Parse
        findings = await self.parser.parse(raw_output)
        
        if not findings:
            return {"status": "error", "message": "No findings parsed"}
        
        # Store in graph
        stored_count = 0
        for finding in findings:
            try:
                await self.graph.upsert_nuclei_finding(finding)
                stored_count += 1
            except Exception as e:
                print(f"Error storing finding: {e}")
                continue
        
        return {
            "status": "success",
            "parsed": len(findings),
            "stored": stored_count,
            "scan_id": scan_id
        }
    
    async def get_findings_summary(self, host: str):
        """Get summary of findings for host"""
        
        findings = await self.graph.get_findings_for_host(host)
        
        severity_count = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        
        for finding in findings:
            severity = finding.get("f", {}).get("severity", "info").lower()
            if severity in severity_count:
                severity_count[severity] += 1
        
        return {
            "host": host,
            "total_findings": sum(severity_count.values()),
            "by_severity": severity_count
        }
```

### Step 5: Create API Endpoint

**File**: `app/api/v1/routers/nuclei.py`

```python
from fastapi import APIRouter, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse
from app.services.nuclei_integration_service import NucleiIntegrationService

router = APIRouter(prefix="/api/v1/nuclei", tags=["nuclei"])

@router.post("/process")
async def process_nuclei_output(
    raw_output: str,
    scan_id: str,
    service: NucleiIntegrationService = Depends()
):
    """
    Process Nuclei scan output
    
    Example:
    ```
    POST /api/v1/nuclei/process
    Content-Type: application/json
    
    {
        "raw_output": "... Nuclei JSON output ...",
        "scan_id": "scan_20260420_001"
    }
    ```
    """
    
    result = await service.process_nuclei_output(raw_output, scan_id)
    return JSONResponse(result)

@router.post("/upload")
async def upload_nuclei_output(
    file: UploadFile,
    scan_id: str,
    service: NucleiIntegrationService = Depends()
):
    """Upload Nuclei output file"""
    
    content = await file.read()
    raw_output = content.decode('utf-8')
    
    result = await service.process_nuclei_output(raw_output, scan_id)
    return JSONResponse(result)

@router.get("/findings/{host}")
async def get_host_findings(
    host: str,
    service: NucleiIntegrationService = Depends()
):
    """Get all findings for a host"""
    
    summary = await service.get_findings_summary(host)
    return JSONResponse(summary)
```

---

## 🧪 Testing Strategy

### Unit Tests

**File**: `tests/test_nuclei_parser.py`

```python
import pytest
from app.adapters.nuclei_parser.nuclei_parser import NucleiParser

@pytest.mark.asyncio
async def test_parse_nuclei_output():
    """Test basic Nuclei JSON parsing"""
    
    nuclei_output = '''{"template-id": "http-missing-headers", "severity": "high", "host": "example.com", "cve-id": "CVE-2021-12345"}'''
    
    parser = NucleiParser()
    findings = await parser.parse(nuclei_output)
    
    assert len(findings) == 1
    assert findings[0].template_id == "http-missing-headers"
    assert findings[0].severity == "high"
    assert findings[0].cve_id == "CVE-2021-12345"

@pytest.mark.asyncio
async def test_parse_multiple_findings():
    """Test parsing line-delimited JSON"""
    
    nuclei_output = '''{"template-id": "http-missing-headers", "severity": "high"}
{"template-id": "ssl-weak-cipher", "severity": "critical"}'''
    
    parser = NucleiParser()
    findings = await parser.parse(nuclei_output)
    
    assert len(findings) == 2

@pytest.mark.asyncio
async def test_validate_format():
    """Test format validation"""
    
    valid_output = '''{"template-id": "test"}'''
    invalid_output = "This is not JSON"
    
    parser = NucleiParser()
    assert await parser.validate_format(valid_output) == True
    assert await parser.validate_format(invalid_output) == False
```

### Integration Tests

**File**: `tests/test_nuclei_integration.py`

```python
@pytest.mark.asyncio
async def test_end_to_end_nuclei_processing(neo4j_client, nuclei_service):
    """Test full pipeline: parse → correlate → store"""
    
    nuclei_output = '''{"template-id": "sql-injection", "severity": "critical", "host": "target.com", "cve-id": "CVE-2021-99999"}'''
    
    result = await nuclei_service.process_nuclei_output(nuclei_output, "test_scan")
    
    assert result["status"] == "success"
    assert result["parsed"] == 1
    assert result["stored"] == 1
    
    # Verify in database
    findings = await neo4j_client.get_findings_for_host("target.com")
    assert len(findings) > 0
```

---

## 🚀 Implementation Timeline

### Week 1: Parser Development
- [ ] Day 1-2: Create data models + base parser
- [ ] Day 3-4: Implement Nuclei parser logic
- [ ] Day 5: Unit tests (>80% coverage)

### Week 2: Neo4j Integration + API
- [ ] Day 1-2: Neo4j adapter methods + queries
- [ ] Day 3: Integration service
- [ ] Day 4: API endpoints
- [ ] Day 5: Integration testing

### Week 3-4: Testing & Hardening
- [ ] DVWA testing (live Nuclei scans)
- [ ] HackTheBox scenarios
- [ ] Performance testing
- [ ] Feature flag setup

### Week 5-6: Deployment & Documentation
- [ ] Staging deployment
- [ ] Load testing
- [ ] Documentation
- [ ] Knowledge transfer

---

## ✅ Validation Checklist

### Code Quality
- [ ] Unit tests > 80% coverage
- [ ] Integration tests pass
- [ ] No linting errors
- [ ] Code review approved

### Functionality
- [ ] Parse valid Nuclei JSON output
- [ ] Handle invalid/malformed input gracefully
- [ ] Correlate findings with existing CVE/CWE
- [ ] Store in Neo4j correctly
- [ ] Retrieve and query findings

### Performance
- [ ] Parse 1000 findings < 10 sec
- [ ] Neo4j queries < 100ms
- [ ] API response < 500ms

### Testing
- [ ] DVWA: Run Nuclei scan → Parse → Verify
- [ ] HackTheBox: Same workflow
- [ ] Regression: Existing CVE queries unaffected

---

## 🔄 Feature Flags

### Configuration (settings.py)

```python
# Feature flags for Nuclei integration
NUCLEI_PARSER_ENABLED: bool = False          # Enable/disable parser
NUCLEI_AUTO_CORRELATE: bool = True          # Auto-correlate with CVE
NUCLEI_STORE_FINDINGS: bool = True           # Store in database
HYBRID_FINDINGS_SEARCH: bool = False         # Include findings in search
```

### Usage in Code

```python
if settings.NUCLEI_PARSER_ENABLED:
    findings = await nuclei_service.process_nuclei_output(...)
else:
    # Fallback to existing behavior
    return None
```

### Gradual Rollout

1. **Week 1**: Deploy with `NUCLEI_PARSER_ENABLED = False`
2. **Week 2**: Enable for 10% of requests (canary)
3. **Week 3**: Enable for 50% of requests
4. **Week 4**: 100% enabled

---

## 📊 Expected Metrics (Post-Phase 1)

### Functional
✅ Parse 95%+ of Nuclei outputs successfully  
✅ Correlate 80%+ with existing CVE/CWE  
✅ Zero data loss during migration  
✅ Backward compatibility maintained  

### Performance
✅ Parser latency: < 10ms per finding  
✅ Database writes: < 5ms per finding  
✅ Query performance: < 100ms (cold), < 50ms (warm)  

### Quality
✅ Test coverage: > 80%  
✅ Production bugs: 0 critical  
✅ User adoption: >80% by week 4

---

## 🔮 Future Enhancements (Phase 2.0)

- [ ] Add Nmap parser for network reconnaissance
- [ ] Add Nikto parser for web application scanning
- [ ] Add Metasploit parser for exploitation results
- [ ] Implement attack loop (cyclic workflow)
- [ ] Dynamic LLM decision-making
- [ ] Multi-target orchestration

---

**Status**: ✅ Ready for development  
**Questions?** Review EXECUTIVE_SUMMARY.md or DOCUMENTATION_INDEX.md

