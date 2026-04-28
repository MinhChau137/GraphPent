# 🚀 Phase 1.0 Implementation Quick Start

**Mục đích**: Bắt đầu Nuclei integration Phase 1.0 trong 1 tuần  
**Deadline**: Week 1 MVP  
**Status**: Ready to implement  

---

## 📋 Pre-Implementation Checklist

### **Team & Resources**
- [ ] Assign 2-3 FTE developers
- [ ] 1 person for testing/validation
- [ ] 1 person for documentation
- [ ] Setup project management (Jira/GitHub Issues)
- [ ] Schedule daily standup

### **Environment Setup**
- [ ] Python venv active (already done ✅)
- [ ] Docker & Docker Compose running (already done ✅)
- [ ] PostgreSQL, Neo4j, Weaviate accessible (verify)
- [ ] Ollama running with llama3.2:3b (verify)
- [ ] DVWA Docker container available (setup)

### **Version Pinning**
- [ ] FastAPI 0.115.0+ ✅
- [ ] Neo4j 5.20+ ✅
- [ ] PostgreSQL 16+ ✅
- [ ] Nuclei latest (install during setup)

---

## ✅ Week 1: Rapid Prototyping

### **Day 1-2: Design & Setup (4-6 hours)**

#### **Task 1.1: Nuclei Parser Module Structure**
```bash
# Create directory structure
mkdir -p app/adapters/nuclei_parser
mkdir -p app/services/nuclei_services
mkdir -p app/api/v1/routers/tools
mkdir -p tests/unit/nuclei
mkdir -p tests/integration/nuclei
```

#### **Task 1.2: Install Nuclei**
```bash
# On your test machine (or Docker)
# Download Nuclei
wget https://github.com/projectdiscovery/nuclei/releases/download/v2.9.17/nuclei_2.9.17_linux_amd64.zip
unzip nuclei_*.zip
chmod +x nuclei
# Or use: go install github.com/projectdiscovery/nuclei/v2/cmd/nuclei@latest
```

#### **Task 1.3: Get Sample Nuclei Output**
```bash
# Run Nuclei on test target to capture real output
./nuclei -u http://testphp.vulnweb.com -t /path/to/templates -json > sample_nuclei_output.json

# Save to fixtures
cp sample_nuclei_output.json tests/fixtures/nuclei_sample.json
```

---

### **Day 2-3: Core Parser Implementation (8-10 hours)**

#### **Task 1.4: Create Data Models**
```python
# app/adapters/nuclei_parser/models.py

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class SeverityEnum(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class NucleiTemplate(BaseModel):
    name: str
    type: str
    severity: SeverityEnum
    cve_id: Optional[str] = None
    cwe_id: Optional[str] = None

class NucleiMatched(BaseModel):
    template_id: str
    template_url: Optional[str]
    host: str
    matched_at: str
    severity: SeverityEnum
    cve_id: Optional[List[str]] = []
    cwe_id: Optional[List[str]] = []
    description: Optional[str]
    matcher_name: Optional[str]
    extracted_results: Optional[dict]

class NucleiRawOutput(BaseModel):
    """Map Nuclei JSON output"""
    template_id: str
    type: str
    host: str
    matched_at: str
    severity: SeverityEnum
    cve_id: Optional[str]
    cwe_id: Optional[str]

class Finding(BaseModel):
    """Normalized Finding entity"""
    id: str
    template_id: str
    severity: SeverityEnum
    host: str
    url: str
    cve_ids: List[str] = []
    cwe_ids: List[str] = []
    matched_at: datetime
    description: Optional[str]
    metadata: dict = {}
```

#### **Task 1.5: Create Parser Base Class**
```python
# app/adapters/nuclei_parser/base.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from .models import Finding

class AbstractParser(ABC):
    """Base parser for tool outputs (future: multi-tool support)"""
    
    @abstractmethod
    async def parse(self, output: Dict[str, Any]) -> List[Finding]:
        """Parse raw tool output into Finding entities"""
        pass
    
    @abstractmethod
    async def validate(self, output: Dict[str, Any]) -> bool:
        """Validate tool output format"""
        pass
```

#### **Task 1.6: Implement Nuclei Parser**
```python
# app/adapters/nuclei_parser/nuclei_parser.py

import json
from datetime import datetime
from typing import List, Dict, Any
from uuid import uuid4
from .base import AbstractParser
from .models import Finding, NucleiRawOutput, SeverityEnum

class NucleiParser(AbstractParser):
    """Parse Nuclei JSON output into Finding entities"""
    
    async def parse(self, nuclei_output: str | Dict) -> List[Finding]:
        """
        Parse Nuclei output. Supports:
        1. JSON string (one finding per line)
        2. Dict (single finding)
        3. List (multiple findings)
        """
        findings = []
        
        if isinstance(nuclei_output, str):
            # JSONL format (one JSON per line)
            for line in nuclei_output.strip().split('\n'):
                if line.strip():
                    try:
                        raw = json.loads(line)
                        finding = self._convert_raw_to_finding(raw)
                        findings.append(finding)
                    except json.JSONDecodeError:
                        # Log and skip malformed lines
                        pass
        
        elif isinstance(nuclei_output, dict):
            # Single finding
            finding = self._convert_raw_to_finding(nuclei_output)
            findings.append(finding)
        
        elif isinstance(nuclei_output, list):
            # List of findings
            for raw in nuclei_output:
                finding = self._convert_raw_to_finding(raw)
                findings.append(finding)
        
        return findings
    
    def _convert_raw_to_finding(self, raw: dict) -> Finding:
        """Convert raw Nuclei output to Finding model"""
        # Handle severity mapping
        severity_str = raw.get('severity', 'info').lower()
        try:
            severity = SeverityEnum(severity_str)
        except ValueError:
            severity = SeverityEnum.INFO
        
        # Extract CVE/CWE (may be comma-separated or array)
        cve_ids = self._parse_ids(raw.get('cve-id', ''))
        cwe_ids = self._parse_ids(raw.get('cwe-id', ''))
        
        # Build URL
        host = raw.get('host', '')
        matched_at = raw.get('matched-at', host)
        
        # Create Finding
        finding = Finding(
            id=str(uuid4()),
            template_id=raw.get('template-id', 'unknown'),
            severity=severity,
            host=host,
            url=matched_at or host,
            cve_ids=cve_ids,
            cwe_ids=cwe_ids,
            matched_at=self._parse_timestamp(raw.get('timestamp', '')),
            description=raw.get('info', {}).get('description', ''),
            metadata={
                'type': raw.get('type'),
                'template_url': raw.get('template-url'),
                'matcher_name': raw.get('matcher-name'),
                'extracted_results': raw.get('extracted-results', {})
            }
        )
        return finding
    
    @staticmethod
    def _parse_ids(value: str) -> List[str]:
        """Parse ID string (may be comma/space separated)"""
        if not value:
            return []
        if isinstance(value, list):
            return value
        # Handle comma/space separated
        ids = [id.strip() for id in str(value).replace(',', ' ').split()]
        return [id for id in ids if id]
    
    @staticmethod
    def _parse_timestamp(timestamp_str: str) -> datetime:
        """Parse Nuclei timestamp"""
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except:
            return datetime.utcnow()
    
    async def validate(self, output: Dict[str, Any]) -> bool:
        """Validate Nuclei output format"""
        required_fields = ['template-id', 'host', 'severity']
        return all(field in output for field in required_fields)
```

---

### **Day 3-4: Graph Integration (6-8 hours)**

#### **Task 1.7: Neo4j Adapter Enhancement**
```python
# app/adapters/neo4j_client.py (extend existing)

class Neo4jClient:
    # ... existing methods ...
    
    async def create_discovered_vulnerability(self, finding: Finding) -> str:
        """Create :DiscoveredVulnerability node in Neo4j"""
        query = """
        CREATE (dv:DiscoveredVulnerability {
            id: $id,
            template_id: $template_id,
            severity: $severity,
            host: $host,
            url: $url,
            matched_at: $matched_at,
            description: $description,
            created_at: datetime()
        })
        RETURN dv.id
        """
        params = {
            'id': finding.id,
            'template_id': finding.template_id,
            'severity': finding.severity.value,
            'host': finding.host,
            'url': finding.url,
            'matched_at': finding.matched_at.isoformat(),
            'description': finding.description
        }
        result = await self.session.run(query, params)
        return finding.id
    
    async def create_finding_cve_relationship(self, finding_id: str, cve_id: str):
        """Create CORRELATES_TO relationship"""
        query = """
        MATCH (dv:DiscoveredVulnerability {id: $finding_id})
        MATCH (cve:CVE {id: $cve_id})
        CREATE (dv)-[:CORRELATES_TO {
            created_at: datetime(),
            source: "nuclei"
        }]->(cve)
        """
        await self.session.run(query, {
            'finding_id': finding_id,
            'cve_id': cve_id
        })
    
    async def create_finding_cwe_relationship(self, finding_id: str, cwe_id: str):
        """Create CLASSIFIED_AS relationship"""
        query = """
        MATCH (dv:DiscoveredVulnerability {id: $finding_id})
        MATCH (cwe:CWE {id: $cwe_id})
        CREATE (dv)-[:CLASSIFIED_AS {
            created_at: datetime(),
            source: "nuclei"
        }]->(cwe)
        """
        await self.session.run(query, {
            'finding_id': finding_id,
            'cwe_id': cwe_id
        })
```

#### **Task 1.8: Integration Service**
```python
# app/services/nuclei_integration_service.py

from typing import List
from app.adapters.nuclei_parser.nuclei_parser import NucleiParser
from app.adapters.nuclei_parser.models import Finding
from app.adapters.neo4j_client import Neo4jClient
from app.models import database as db

class NucleiIntegrationService:
    def __init__(self, neo4j_client: Neo4jClient, parser: NucleiParser):
        self.neo4j = neo4j_client
        self.parser = parser
    
    async def process_nuclei_output(self, nuclei_json: str, scan_id: str) -> dict:
        """
        End-to-end processing:
        1. Parse Nuclei output
        2. Create entities
        3. Create relationships
        4. Update database
        """
        # Step 1: Parse
        findings = await self.parser.parse(nuclei_json)
        
        # Step 2: Normalize and store
        stored_findings = []
        for finding in findings:
            # Create in Neo4j
            await self.neo4j.create_discovered_vulnerability(finding)
            
            # Create CVE correlations
            for cve_id in finding.cve_ids:
                await self.neo4j.create_finding_cve_relationship(
                    finding.id, cve_id
                )
            
            # Create CWE classifications
            for cwe_id in finding.cwe_ids:
                await self.neo4j.create_finding_cwe_relationship(
                    finding.id, cwe_id
                )
            
            stored_findings.append(finding)
        
        # Step 3: Update PostgreSQL metadata
        await db.update_scan_status(
            scan_id,
            status='completed',
            findings_count=len(findings)
        )
        
        return {
            'scan_id': scan_id,
            'findings_count': len(findings),
            'stored_findings': len(stored_findings),
            'status': 'success'
        }
```

---

### **Day 4-5: API Endpoints (4-6 hours)**

#### **Task 1.9: API Routes**
```python
# app/api/v1/routers/nuclei.py

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4
from datetime import datetime

router = APIRouter(prefix="/nuclei", tags=["nuclei"])

class NucleiScanRequest(BaseModel):
    target_url: str
    templates: Optional[list] = None  # Specific templates
    timeout: Optional[int] = 300  # seconds

class NucleiScanResponse(BaseModel):
    scan_id: str
    status: str
    target_url: str
    started_at: datetime

@router.post("/scan")
async def start_nuclei_scan(
    request: NucleiScanRequest,
    background_tasks: BackgroundTasks
):
    """Start Nuclei scan on target"""
    # Validate target
    if request.target_url not in settings.ALLOWED_TARGETS:
        raise HTTPException(status_code=403, detail="Target not allowed")
    
    # Create scan record
    scan_id = str(uuid4())
    await db.create_nuclei_scan(
        scan_id=scan_id,
        target_url=request.target_url,
        status='pending'
    )
    
    # Add background task
    background_tasks.add_task(
        execute_nuclei_scan,
        scan_id, request.target_url, request.templates, request.timeout
    )
    
    return NucleiScanResponse(
        scan_id=scan_id,
        status='pending',
        target_url=request.target_url,
        started_at=datetime.utcnow()
    )

@router.get("/scan/{scan_id}")
async def get_scan_status(scan_id: str):
    """Check scan progress"""
    scan = await db.get_nuclei_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan

@router.get("/scan/{scan_id}/results")
async def get_scan_results(scan_id: str, limit: int = 100, offset: int = 0):
    """Get findings from scan"""
    findings = await db.get_nuclei_findings(scan_id, limit, offset)
    return {'findings': findings, 'count': len(findings)}

async def execute_nuclei_scan(scan_id: str, target: str, templates: list, timeout: int):
    """Background task: run Nuclei scan"""
    try:
        # Update status
        await db.update_nuclei_scan(scan_id, status='running')
        
        # Run Nuclei
        nuclei_service = NucleiExecutionService()
        output = await nuclei_service.run(target, templates, timeout)
        
        # Process results
        integration_service = NucleiIntegrationService(neo4j, parser)
        result = await integration_service.process_nuclei_output(output, scan_id)
        
        # Update status
        await db.update_nuclei_scan(
            scan_id,
            status='completed',
            findings_count=result['findings_count']
        )
    except Exception as e:
        await db.update_nuclei_scan(scan_id, status='failed', error=str(e))
```

---

### **Day 5: Testing & Validation (4-6 hours)**

#### **Task 1.10: Unit Tests**
```python
# tests/unit/nuclei/test_parser.py

import pytest
from app.adapters.nuclei_parser.nuclei_parser import NucleiParser
from app.adapters.nuclei_parser.models import SeverityEnum

@pytest.fixture
def parser():
    return NucleiParser()

@pytest.fixture
def sample_nuclei_output():
    return {
        "template-id": "http-missing-headers",
        "type": "http",
        "host": "example.com",
        "severity": "high",
        "cve-id": "CVE-2021-12345",
        "cwe-id": "CWE-693"
    }

@pytest.mark.asyncio
async def test_parse_single_finding(parser, sample_nuclei_output):
    findings = await parser.parse(sample_nuclei_output)
    assert len(findings) == 1
    assert findings[0].template_id == "http-missing-headers"
    assert findings[0].severity == SeverityEnum.HIGH

@pytest.mark.asyncio
async def test_parse_jsonl(parser, sample_nuclei_output):
    jsonl = "\n".join([json.dumps(sample_nuclei_output)] * 3)
    findings = await parser.parse(jsonl)
    assert len(findings) == 3
```

#### **Task 1.11: Integration Test**
```python
# tests/integration/nuclei/test_integration.py

@pytest.mark.asyncio
async def test_end_to_end_nuclei_processing():
    # Setup
    neo4j = Neo4jClient(...)
    parser = NucleiParser()
    service = NucleiIntegrationService(neo4j, parser)
    
    # Run
    result = await service.process_nuclei_output(sample_json, "test-scan-1")
    
    # Verify
    assert result['status'] == 'success'
    
    # Check Neo4j
    nodes = await neo4j.query("MATCH (dv:DiscoveredVulnerability) RETURN count(dv)")
    assert nodes > 0
```

---

## 📊 Daily Progress Checklist

### **Day 1 ✅**
- [ ] Directory structure created
- [ ] Nuclei installed & tested locally
- [ ] Sample output collected
- [ ] Fixture files prepared

### **Day 2 ✅**
- [ ] Data models completed
- [ ] Parser base class done
- [ ] Nuclei parser logic 80% complete
- [ ] Tests passing for parser

### **Day 3 ✅**
- [ ] Nuclei parser 100% complete
- [ ] Neo4j adapter extensions done
- [ ] Integration service 80% complete
- [ ] Neo4j schema migration ready

### **Day 4 ✅**
- [ ] Integration service 100% complete
- [ ] API endpoints designed & implemented
- [ ] API tests passing
- [ ] Background task implemented

### **Day 5 ✅**
- [ ] Full integration test passing
- [ ] DVWA test environment working
- [ ] End-to-end test successful
- [ ] All tests green

---

## 🎯 Week 1 Deliverables

By end of Week 1:
- ✅ Nuclei parser module (production-ready)
- ✅ Neo4j integration (label separation working)
- ✅ API endpoints (functional)
- ✅ Unit & integration tests (>90% coverage)
- ✅ Sample data in fixtures
- ✅ Documentation started

**Status**: Ready for Week 2 integration & enhancement

---

## 🔗 File Dependencies

```
app/adapters/nuclei_parser/
├── __init__.py
├── base.py (AbstractParser)
├── models.py (Finding, NucleiRawOutput)
├── nuclei_parser.py (NucleiParser impl)
└── validator.py (optional)

app/services/
└── nuclei_integration_service.py (uses parser + neo4j)

app/api/v1/routers/
└── nuclei.py (uses integration_service)

tests/
├── unit/nuclei/
│   ├── test_parser.py
│   └── test_models.py
└── integration/nuclei/
    └── test_integration.py
```

---

## 📌 Critical Implementation Notes

1. **Error Handling**: All parsing errors → logged, not crashed
2. **Type Safety**: Use Pydantic models, mypy validation
3. **Async/Await**: All I/O operations must be async
4. **Database Transactions**: Use atomic operations in Neo4j
5. **Idempotency**: Duplicate findings should be deduplicated
6. **Logging**: INFO level for all major steps, DEBUG for details

---

## 🚀 Go/No-Go Decision (End of Week 1)

**Go Decision Criteria**:
- ✅ All tests passing (unit + integration)
- ✅ Parser handles 99%+ of Nuclei outputs
- ✅ Neo4j relationships created correctly
- ✅ API endpoints responding correctly
- ✅ DVWA end-to-end test successful
- ✅ No critical bugs

**If GO**: Proceed to Week 2 (Workflow integration)  
**If NO-GO**: Debug issues, replan

---

**Phase 1.0 Week 1 Ready**: ✅  
**Expected Outcome**: MVP parser ready for integration  
**Risk Level**: LOW  

Next: [Week 2-8 Timeline in PHASE_1_NUCLEI_IMPLEMENTATION.md](../PHASE_1_NUCLEI_IMPLEMENTATION.md)
