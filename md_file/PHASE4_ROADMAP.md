# 🚀 Phase 4 Roadmap: API Endpoints

**Phase**: 4 of 5 (Week 3 - Days 1-2)  
**Duration**: 2-3 days  
**Status**: READY TO START  
**Dependencies**: ✅ Phase 3 (Integration Service) - COMPLETE

---

## 🎯 Phase 4 Objectives

**What We're Building**:
1. FastAPI endpoints for Nuclei operations
2. Request/Response models
3. Integration with Phase 3 service
4. Swagger/OpenAPI documentation
5. Input validation & error handling

**What We're NOT Building**:
- ❌ Workflow integration (Phase 5)
- ❌ Feature flags (Phase 6)
- ❌ Testing deployment (Phase 7)

---

## 📋 Detailed Tasks (Phase 4)

### **Task 4.1: API Router Creation** (Day 1, 4 hours)

```python
# app/api/v1/routers/nuclei.py

Router endpoints:
- POST /nuclei/scan              - Trigger new scan
- GET  /nuclei/scan/{id}         - Get scan status
- GET  /nuclei/scan/{id}/results - Get findings
- GET  /nuclei/findings          - Query findings (filter by severity/host/template)
- GET  /nuclei/findings/{id}     - Get specific finding
- DELETE /nuclei/findings/{template_id}  - Delete findings
- GET  /nuclei/stats             - Statistics
```

**Key Features**:
- ✅ Input validation with Pydantic
- ✅ Error handling
- ✅ Response serialization
- ✅ OpenAPI documentation
- ✅ Auth/security (from Phase 1)

---

### **Task 4.2: Request/Response Models** (Day 1, 2 hours)

```python
# app/domain/schemas/nuclei.py

Models:
- NucleiScanRequest
- NucleiScanResponse
- FindingResponse
- FindingsQueryRequest
- FindingsQueryResponse
- NucleiStatsResponse
```

**Example Structure**:
```python
class NucleiScanRequest(BaseModel):
    target_url: str
    scan_type: str = "full"  # full, web, api
    templates: Optional[List[str]] = None
    metadata: Dict = {}

class FindingResponse(BaseModel):
    id: str
    template_id: str
    severity: str
    host: str
    url: str
    matched_at: datetime
    cve_ids: List[str]
    cwe_ids: List[str]
```

---

### **Task 4.3: Service Integration** (Day 2, 2 hours)

**Connect**:
- Phase 3 `NucleiIntegrationService`
- Request models → Processing
- Findings → Response models
- Error handling

**Handle**:
- Async operations
- Long-running scans
- Result pagination
- Query filters

---

### **Task 4.4: Error Handling & Validation** (Day 2, 2 hours)

**Implement**:
- Input validation (Pydantic)
- Error responses (400, 404, 500)
- Logging
- Rate limiting (optional)
- CORS support

**Error Scenarios**:
- Invalid target URL
- Missing scan ID
- Invalid filters
- Neo4j connection errors
- Parser errors

---

### **Task 4.5: API Documentation** (Day 2, 1 hour)

**Create**:
- `docs/API_ENDPOINTS.md`
  - Endpoint descriptions
  - Request/response examples
  - Error codes
  - Query parameters

- `docs/NUCLEI_API_GUIDE.md`
  - Getting started
  - Usage examples
  - Integration with Phase 5 (workflow)

---

## 📊 Work Breakdown (Phase 4)

| Task | Duration | Priority | Status |
|------|----------|----------|--------|
| 4.1: Router Creation | 4h | HIGH | ⏳ TODO |
| 4.2: Request/Response Models | 2h | HIGH | ⏳ TODO |
| 4.3: Service Integration | 2h | HIGH | ⏳ TODO |
| 4.4: Error Handling | 2h | MEDIUM | ⏳ TODO |
| 4.5: Documentation | 1h | MEDIUM | ⏳ TODO |
| **Total** | **11h** | — | — |

**Estimate**: 2 days for 1 developer (with Phase 3 ready)

---

## 📝 Code Templates

### **Router Template**

```python
# app/api/v1/routers/nuclei.py

from fastapi import APIRouter, HTTPException, Query, Path
from typing import List, Optional
from app.services.nuclei_services import NucleiIntegrationService
from app.domain.schemas.nuclei import (
    NucleiScanRequest,
    NucleiScanResponse,
    FindingResponse,
    FindingsQueryRequest
)
from app.adapters.neo4j_client import Neo4jAdapter

router = APIRouter(prefix="/nuclei", tags=["nuclei"])

# Initialize service
_neo4j = Neo4jAdapter()
_service = NucleiIntegrationService(_neo4j)


@router.post("/scan", response_model=NucleiScanResponse)
async def trigger_scan(request: NucleiScanRequest):
    """Trigger a new Nuclei scan.
    
    Args:
        request: Scan parameters (target_url, templates, etc.)
        
    Returns:
        Scan ID and initial status
    """
    try:
        result = await _service.process_nuclei_output(
            nuclei_output={},  # Would come from Nuclei CLI execution
            target_url=request.target_url
        )
        
        return NucleiScanResponse(
            scan_id=result["scan_id"],
            status="queued",
            target_url=request.target_url
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/{scan_id}", response_model=NucleiScanResponse)
async def get_scan_status(scan_id: str = Path(...)):
    """Get scan status by ID."""
    try:
        # TODO: Query from PostgreSQL (Phase 3.3)
        return NucleiScanResponse(
            scan_id=scan_id,
            status="completed",
            findings_count=0
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Scan not found: {scan_id}")


@router.get("/findings", response_model=List[FindingResponse])
async def query_findings(
    severity: Optional[str] = Query(None),
    host: Optional[str] = Query(None),
    template_id: Optional[str] = Query(None),
    limit: int = Query(100, le=1000)
):
    """Query findings with filters."""
    try:
        if severity:
            findings = await _service.get_findings_by_severity(severity)
        elif host:
            findings = await _service.get_findings_by_host(host)
        elif template_id:
            findings = await _service.get_findings_by_template(template_id)
        else:
            # Default: all critical findings
            findings = await _service.get_critical_findings()
        
        return findings[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### **Models Template**

```python
# app/domain/schemas/nuclei.py

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict
from datetime import datetime

class NucleiScanRequest(BaseModel):
    """Request to trigger a Nuclei scan."""
    target_url: str = Field(..., description="Target URL/IP to scan")
    scan_type: str = Field("full", description="Scan type: full, web, api")
    templates: Optional[List[str]] = None
    metadata: Dict = Field(default_factory=dict)
    
    @validator('target_url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Must be a valid URL')
        return v

class NucleiScanResponse(BaseModel):
    """Response from scan trigger."""
    scan_id: str
    status: str  # queued, running, completed, failed
    target_url: str
    findings_count: Optional[int] = None
    started_at: Optional[datetime] = None

class FindingResponse(BaseModel):
    """Finding from Neo4j."""
    id: str
    template_id: str
    severity: str
    host: str
    url: str
    matched_at: Optional[datetime]
    cve_ids: List[str] = []
    cwe_ids: List[str] = []
```

---

## 🏗️ Integration Points

### **With Phase 3 (Integration Service)**
```python
# Use service methods
service = NucleiIntegrationService(neo4j_adapter)
results = await service.process_nuclei_output(...)
findings = await service.get_findings_by_severity("CRITICAL")
```

### **With FastAPI**
```python
# Router registration in main.py
from app.api.v1.routers.nuclei import router as nuclei_router
app.include_router(nuclei_router)
```

### **With PostgreSQL** (Phase 3.3)
```python
# Track scans
scan = await db.create_nuclei_scan(target_url, status="running")
await db.update_nuclei_scan(scan_id, status="completed", findings=results)
```

---

## 📊 Endpoint Specification

### **1. POST /nuclei/scan**
```
Request:
{
  "target_url": "http://192.168.1.100",
  "scan_type": "full",
  "templates": ["http-missing-headers", "sql-injection"],
  "metadata": {"project": "pentest-2026"}
}

Response (202 Accepted):
{
  "scan_id": "uuid-xxx",
  "status": "queued",
  "target_url": "http://192.168.1.100"
}
```

### **2. GET /nuclei/scan/{scan_id}**
```
Response (200):
{
  "scan_id": "uuid-xxx",
  "status": "completed",
  "target_url": "http://192.168.1.100",
  "findings_count": 5,
  "started_at": "2026-04-28T08:00:00Z",
  "completed_at": "2026-04-28T08:15:30Z"
}
```

### **3. GET /nuclei/findings?severity=CRITICAL**
```
Response (200):
[
  {
    "id": "uuid-1",
    "template_id": "sql-injection",
    "severity": "CRITICAL",
    "host": "192.168.1.100",
    "url": "http://192.168.1.100/api/search",
    "matched_at": "2026-04-28T08:05:00Z",
    "cve_ids": ["CVE-2024-1234"],
    "cwe_ids": ["CWE-89"]
  }
]
```

### **4. GET /nuclei/findings/{finding_id}**
```
Response (200):
{
  "id": "uuid-1",
  "template_id": "sql-injection",
  ...full finding details...
}
```

### **5. GET /nuclei/stats**
```
Response (200):
{
  "total_findings": 25,
  "critical_count": 3,
  "high_count": 8,
  "medium_count": 10,
  "low_count": 4,
  "scans_completed": 5,
  "last_scan": "2026-04-28T09:00:00Z"
}
```

---

## 🔍 HTTP Status Codes

| Code | Scenario |
|------|----------|
| 200 | Query successful |
| 201 | Scan created |
| 202 | Scan accepted (processing) |
| 400 | Invalid request (validation error) |
| 404 | Resource not found (scan_id, finding_id) |
| 500 | Server error (Neo4j, Parser) |
| 503 | Service unavailable (Neo4j down) |

---

## 🛡️ Input Validation

**Implemented via Pydantic**:
- ✅ URL format validation
- ✅ Enum validation (severity)
- ✅ UUID format (scan_id)
- ✅ Required fields
- ✅ Length constraints
- ✅ Regex patterns

**Error Responses**:
```json
{
  "detail": [
    {
      "loc": ["body", "target_url"],
      "msg": "Must be a valid URL",
      "type": "value_error"
    }
  ]
}
```

---

## 📚 Swagger/OpenAPI

**Automatic from FastAPI**:
- ✅ `/docs` - Interactive Swagger UI
- ✅ `/redoc` - ReDoc documentation
- ✅ `/openapi.json` - OpenAPI schema

**Features**:
- Endpoint descriptions
- Request/response schemas
- Try-it-out testing
- Authentication docs

---

## 🔗 Connection to Phase 5

**Phase 5 (Workflow Integration)** will:
- Call `/nuclei/scan` to trigger scans
- Poll `/nuclei/scan/{id}` for status
- Fetch `/nuclei/findings` for result analysis
- Use findings in pentest workflow

**No changes needed to Phase 4** - Just expose service functionality.

---

## ✅ Success Criteria (Phase 4)

### **Functional**
- ✅ All 5-6 endpoints implemented
- ✅ Request/response models complete
- ✅ Service integration working
- ✅ Error handling comprehensive
- ✅ Documentation complete

### **Quality**
- ✅ Input validation on all endpoints
- ✅ Logging for debugging
- ✅ Error messages descriptive
- ✅ Response times acceptable
- ✅ Swagger working

### **Testing**
- ✅ Unit tests for endpoints
- ✅ Integration with Phase 3
- ✅ Error scenarios tested
- ✅ Manual testing via Swagger

---

## 🚀 Launch Criteria for Phase 4

**Ready to Start When**:
1. ✅ Phase 3 complete & validated
2. ✅ Neo4j connection working
3. ✅ Service methods available
4. ⏳ FastAPI main app configured

**Pre-Implementation**:
```bash
# Start services
docker-compose up -d postgres neo4j

# Verify Phase 3
python validate_phase3.py  # Should pass ✅
```

---

## 📞 Questions & Answers

**Q: Can Phase 4 run without Phase 3.3 (PostgreSQL migrations)?**
- A: Yes! Phase 3.3 is optional for MVP. Scan status can be dummy/hardcoded initially.

**Q: Should we add async processing with Celery?**
- A: No - Phase 4 is synchronous. Phase 5 may add job queueing.

**Q: What about Nuclei CLI integration?**
- A: Deferred to Phase 5. Phase 4 works with pre-generated Nuclei output.

**Q: Rate limiting needed?**
- A: Optional - depends on deployment requirements.

---

## 📖 Reference Materials

- [Phase 3 Complete](PHASE3_IMPLEMENTATION_COMPLETE.md) - Service API
- [Phase 2 Complete](PHASE2_IMPLEMENTATION_COMPLETE.md) - Parser details
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Pydantic Docs](https://docs.pydantic.dev/)

---

## 🎯 Timeline Estimate

**Total Time**: 2 days (1 developer)
- Day 1: Router + Models + Integration (6-7 hours)
- Day 2: Error handling + Tests + Docs (4-5 hours)

**Actual Duration**: Likely 1-2 days with Phase 3 ready

---

**Status**: 🟢 Ready to Start  
**Complexity**: Medium (all dependencies ready)  
**Risk**: LOW  
**Confidence**: 95%  

**Next Action**: Begin Phase 4 implementation once approved

---

## 📝 Implementation Checklist

- [ ] Create `app/api/v1/routers/nuclei.py`
- [ ] Create `app/domain/schemas/nuclei.py`
- [ ] Implement 6 endpoints
- [ ] Add request/response models
- [ ] Integrate with Phase 3 service
- [ ] Add error handling
- [ ] Add logging
- [ ] Test with Swagger UI
- [ ] Write unit tests
- [ ] Create API documentation
- [ ] Register router in main.py
- [ ] Validate endpoints work

---

**Prepared**: 2026-04-28  
**Status**: Ready for implementation  
**Next Phase**: Phase 5 (Workflow Integration)
