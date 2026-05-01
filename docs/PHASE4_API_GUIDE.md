# Phase 4: REST API Endpoints - Complete Guide

**Phase**: 4 of 5  
**Date**: April 28, 2026  
**Status**: ✅ COMPLETE

---

## 📖 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [API Endpoints](#api-endpoints)
4. [Request/Response Models](#requestresponse-models)
5. [Usage Examples](#usage-examples)
6. [Error Handling](#error-handling)
7. [Deployment](#deployment)
8. [Testing](#testing)

---

## 🎯 Overview

**Phase 4** provides a complete REST API for Nuclei scanning operations. All endpoints are:

✅ **Fully Async**: Using FastAPI with async/await  
✅ **Well-Documented**: Swagger/OpenAPI auto-generated  
✅ **Type-Safe**: Full Pydantic validation  
✅ **Error-Handled**: Comprehensive error responses  
✅ **Production-Ready**: Logging, monitoring, security  

### **Base URL**
```
http://localhost:8000/api/v1/nuclei
```

### **Documentation URLs**
```
Swagger UI:  http://localhost:8000/docs
ReDoc:       http://localhost:8000/redoc
```

---

## 🏗️ Architecture

### **Request Flow**

```
HTTP Request
    ↓
FastAPI Router (nuclei.py)
    ├─ Path validation
    ├─ Request body parsing (Pydantic)
    └─ Dependency injection
    ↓
Service Layer
    ├─ NucleiIntegrationService (Phase 3.1)
    ├─ NucleiPostgresService (Phase 3.3)
    └─ Neo4jAdapter (Phase 3.2)
    ↓
Database Layer
    ├─ PostgreSQL (nuclei_scans, nuclei_findings)
    └─ Neo4j (:DiscoveredVulnerability)
    ↓
HTTP Response
    └─ JSON + Status Code
```

### **Dependency Injection**

```python
# Global service instances (singleton pattern)
get_integration_service() → NucleiIntegrationService
get_postgres_service() → NucleiPostgresService

# FastAPI automatic injection
@router.get("/endpoint")
async def handler(service = Depends(get_integration_service)):
    # service is automatically injected
    await service.method()
```

---

## 📡 API Endpoints

### **1. Health & Status**

#### `GET /health`
Check API and database connectivity.

**Response**:
```json
{
  "status": "healthy",
  "neo4j": "connected",
  "postgres": "connected",
  "version": "1.0.0"
}
```

**Status Codes**:
- `200` - Healthy
- `500` - Service error

---

### **2. Scan Management**

#### `POST /scan`
Create a new scan record.

**Request**:
```json
{
  "target_url": "http://192.168.1.100",
  "scan_type": "full",
  "metadata": {
    "tags": ["internal", "prod"],
    "description": "Morning scan"
  }
}
```

**Response** (201):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "target_url": "http://192.168.1.100",
  "status": "pending",
  "scan_type": "full",
  "findings_count": 0,
  "neo4j_status": "pending",
  "started_at": "2026-04-28T10:00:00Z",
  "completed_at": null,
  "error_message": null
}
```

---

#### `GET /scan/{scan_id}`
Get scan details by ID.

**Path Parameters**:
- `scan_id` (string, UUID) - Scan identifier

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "target_url": "http://192.168.1.100",
  "status": "completed",
  "scan_type": "full",
  "findings_count": 5,
  "neo4j_status": "upserted",
  "started_at": "2026-04-28T10:00:00Z",
  "completed_at": "2026-04-28T10:05:00Z",
  "error_message": null
}
```

**Status Codes**:
- `200` - OK
- `404` - Scan not found
- `500` - Server error

---

#### `GET /scans`
List recent scans with optional filtering.

**Query Parameters**:
- `limit` (integer, 1-100) - Max scans to return (default: 20)
- `status` (string, optional) - Filter by status: pending|running|completed|failed

**Response** (200):
```json
{
  "total": 50,
  "count": 10,
  "scans": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "target_url": "http://192.168.1.100",
      "status": "completed",
      "scan_type": "full",
      "findings_count": 5,
      "neo4j_status": "upserted",
      "started_at": "2026-04-28T10:00:00Z",
      "completed_at": "2026-04-28T10:05:00Z",
      "error_message": null
    }
  ]
}
```

---

#### `DELETE /scan/{scan_id}`
Delete a scan and all its findings (cascade delete).

**Path Parameters**:
- `scan_id` (string, UUID) - Scan identifier

**Response** (204):
No content (empty response)

**Status Codes**:
- `204` - Deleted successfully
- `404` - Scan not found
- `500` - Server error

---

### **3. Nuclei Processing**

#### `POST /scan/{scan_id}/process`
Process Nuclei output for a scan.

**Path Parameters**:
- `scan_id` (string, UUID) - Parent scan identifier

**Request Body**:
```json
{
  "nuclei_output": "{\"template-id\":\"sql-injection\",\"severity\":\"critical\",\"host\":\"192.168.1.100\",\"url\":\"http://192.168.1.100/api\",\"matched-at\":\"2026-04-28T10:00:00Z\",\"cve-id\":\"CVE-2024-1234\",\"cwe-id\":\"CWE-89\"}",
  "target_url": "http://192.168.1.100",
  "scan_id": null
}
```

**Response** (200):
```json
{
  "scan_id": "550e8400-e29b-41d4-a716-446655440000",
  "findings_count": 1,
  "findings_stored": 1,
  "findings_failed": 0,
  "cve_relationships": 1,
  "cwe_relationships": 1,
  "status": "completed",
  "parser_warnings": 0,
  "relationship_errors": 0
}
```

---

### **4. Finding Queries**

#### `GET /findings`
Query findings with optional filtering.

**Query Parameters**:
- `severity` (string, optional) - Filter by: CRITICAL|HIGH|MEDIUM|LOW|INFO
- `host` (string, optional) - Filter by target host
- `template_id` (string, optional) - Filter by Nuclei template
- `limit` (integer, 1-1000) - Max results (default: 50)
- `offset` (integer) - Pagination offset (default: 0)

**Example Queries**:
```bash
# Get all critical findings
GET /findings?severity=CRITICAL&limit=10

# Get findings for specific host
GET /findings?host=192.168.1.100&limit=20

# Get findings from specific template
GET /findings?template_id=sql-injection&limit=50

# Paginated results
GET /findings?limit=10&offset=20
```

**Response** (200):
```json
{
  "total": 25,
  "count": 10,
  "limit": 10,
  "offset": 0,
  "findings": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "scan_id": "550e8400-e29b-41d4-a716-446655440000",
      "template_id": "sql-injection",
      "severity": "CRITICAL",
      "host": "192.168.1.100",
      "url": "http://192.168.1.100/api/search",
      "matched_at": "2026-04-28T10:02:00Z",
      "cve_ids": ["CVE-2024-1234"],
      "cwe_ids": ["CWE-89"],
      "neo4j_id": "neo4j-uuid",
      "metadata": {}
    }
  ]
}
```

---

#### `GET /findings/{finding_id}`
Get specific finding by ID.

**Path Parameters**:
- `finding_id` (string, UUID) - Finding identifier

**Response** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "scan_id": "550e8400-e29b-41d4-a716-446655440000",
  "template_id": "sql-injection",
  "severity": "CRITICAL",
  "host": "192.168.1.100",
  "url": "http://192.168.1.100/api/search",
  "matched_at": "2026-04-28T10:02:00Z",
  "cve_ids": ["CVE-2024-1234"],
  "cwe_ids": ["CWE-89"],
  "neo4j_id": "neo4j-uuid",
  "metadata": {}
}
```

---

### **5. Statistics**

#### `GET /statistics`
Get system-wide statistics.

**Response** (200):
```json
{
  "total_scans": 100,
  "total_findings": 523,
  "critical_findings": 45,
  "scans_completed": 95,
  "last_scan": "2026-04-28T10:05:00Z",
  "findings_by_severity": {
    "CRITICAL": 45,
    "HIGH": 120,
    "MEDIUM": 200,
    "LOW": 150,
    "INFO": 8
  },
  "findings_by_host": {
    "192.168.1.100": 150,
    "192.168.1.101": 200,
    "192.168.1.102": 173
  }
}
```

---

## 🔄 Request/Response Models

### **Enums**

#### `SeverityEnum`
```python
CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
INFO = "INFO"
```

#### `ScanStatusEnum`
```python
PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
```

#### `Neo4jStatusEnum`
```python
PENDING = "pending"
UPSERTED = "upserted"
FAILED = "failed"
```

---

### **Request Models**

#### `CreateScanRequest`
```python
target_url: str          # Target URL/IP
scan_type: str = "full"  # Scan type
metadata: dict = None    # Additional metadata
```

#### `ProcessNucleiOutputRequest`
```python
nuclei_output: str           # Nuclei output (JSONL/JSON/list)
target_url: str = None       # Target URL for context
scan_id: str = None          # Custom scan ID
```

#### `FindingsQueryRequest`
```python
severity: SeverityEnum = None      # Severity filter
host: str = None                   # Host filter
template_id: str = None            # Template filter
limit: int = 100                   # Max results
offset: int = 0                    # Pagination
```

---

### **Response Models**

#### `ScanMetadata`
```python
id: str                      # Scan UUID
target_url: str              # Target
status: ScanStatusEnum       # Current status
scan_type: str               # Scan type
findings_count: int          # Number of findings
neo4j_status: Neo4jStatusEnum # Neo4j status
started_at: datetime         # Start time
completed_at: datetime       # Completion time
error_message: str           # Error if failed
```

#### `FindingResponse`
```python
id: str                 # Finding UUID
scan_id: str            # Parent scan
template_id: str        # Nuclei template
severity: SeverityEnum  # Severity
host: str               # Target host
url: str                # Target URL
matched_at: datetime    # Discovery time
cve_ids: list[str]      # Related CVEs
cwe_ids: list[str]      # Related CWEs
neo4j_id: str           # Neo4j node ID
metadata: dict          # Additional data
```

---

## 💡 Usage Examples

### **Example 1: Complete Scanning Workflow**

```bash
#!/bin/bash

# 1. Create scan
SCAN=$(curl -X POST http://localhost:8000/api/v1/nuclei/scan \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "http://localhost:3000",
    "scan_type": "full"
  }')

SCAN_ID=$(echo $SCAN | jq -r '.id')
echo "Scan created: $SCAN_ID"

# 2. Get scan details
curl http://localhost:8000/api/v1/nuclei/scan/$SCAN_ID

# 3. Process Nuclei output
NUCLEI_OUTPUT='{"template-id":"open-redirect","severity":"medium","host":"localhost","url":"http://localhost:3000/api/redirect","matched-at":"2026-04-28T10:00:00Z"}'

RESULT=$(curl -X POST http://localhost:8000/api/v1/nuclei/scan/$SCAN_ID/process \
  -H "Content-Type: application/json" \
  -d "{\"nuclei_output\": \"$NUCLEI_OUTPUT\"}")

echo "Processing result: $RESULT"

# 4. Query findings
curl "http://localhost:8000/api/v1/nuclei/findings?host=localhost"

# 5. Get statistics
curl http://localhost:8000/api/v1/nuclei/statistics
```

### **Example 2: Python Client**

```python
import httpx
import json

BASE_URL = "http://localhost:8000/api/v1/nuclei"

async def scan_target(target_url: str):
    async with httpx.AsyncClient() as client:
        # Create scan
        response = await client.post(
            f"{BASE_URL}/scan",
            json={"target_url": target_url, "scan_type": "full"}
        )
        scan = response.json()
        scan_id = scan["id"]
        print(f"Scan created: {scan_id}")
        
        # Process sample output
        nuclei_output = json.dumps({
            "template-id": "sql-injection",
            "severity": "critical",
            "host": target_url,
            "url": f"{target_url}/api",
            "matched-at": "2026-04-28T10:00:00Z",
            "cve-id": "CVE-2024-1234"
        })
        
        response = await client.post(
            f"{BASE_URL}/scan/{scan_id}/process",
            json={"nuclei_output": nuclei_output}
        )
        result = response.json()
        print(f"Findings: {result['findings_count']}")
        
        # Query findings
        response = await client.get(
            f"{BASE_URL}/findings",
            params={"severity": "CRITICAL", "limit": 10}
        )
        findings = response.json()
        print(f"Found {findings['total']} critical findings")

# Run
import asyncio
asyncio.run(scan_target("http://localhost:3000"))
```

---

## ⚠️ Error Handling

### **Error Response Format**

```json
{
  "error": "Error message",
  "detail": "Detailed explanation",
  "status_code": 400
}
```

### **Common Status Codes**

| Code | Meaning | Example |
|------|---------|---------|
| 200 | OK | GET succeeded |
| 201 | Created | POST scan succeeded |
| 204 | No Content | DELETE succeeded |
| 400 | Bad Request | Invalid JSON |
| 404 | Not Found | Scan ID doesn't exist |
| 500 | Server Error | Database connection failed |

### **Error Scenarios**

```bash
# Missing required field
curl -X POST http://localhost:8000/api/v1/nuclei/scan \
  -H "Content-Type: application/json" \
  -d '{"scan_type": "full"}'
# Response: 400 Bad Request

# Invalid scan ID
curl http://localhost:8000/api/v1/nuclei/scan/invalid-uuid
# Response: 404 Not Found

# Database error
curl http://localhost:8000/api/v1/nuclei/statistics
# Response: 500 Internal Server Error
```

---

## 🚀 Deployment

### **Prerequisites**

✅ PostgreSQL running  
✅ Neo4j running  
✅ Phase 3 schema migrated  
✅ Python virtual environment activated  
✅ All dependencies installed  

### **Starting the Server**

```bash
# Development (with auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker
```

### **Using Docker Compose**

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f graphpent-fastapi

# Stop
docker-compose down
```

---

## 🧪 Testing

### **Health Check Test**

```bash
curl http://localhost:8000/api/v1/nuclei/health
```

### **Swagger UI Test**

1. Open `http://localhost:8000/docs`
2. Click "Try it out" on any endpoint
3. Fill in parameters
4. Click "Execute"

### **Automated Tests**

```bash
# Run all tests
pytest tests/api/nuclei/

# Run specific test
pytest tests/api/nuclei/test_endpoints.py::test_create_scan -v

# Run with coverage
pytest tests/api/nuclei/ --cov=app/api/v1/routers/nuclei
```

---

## 📚 Integration Notes

### **How Phase 4 Integrates with Phase 3**

```
Phase 3 Services (Complete)
├── NucleiIntegrationService
├── NucleiStorageManager
├── NucleiPostgresService
└── Neo4jAdapter

         ↓ (Dependency Injection)

Phase 4 REST API (New)
├── Scan endpoints → NucleiPostgresService
├── Process endpoint → NucleiIntegrationService
├── Query endpoints → NucleiIntegrationService
└── Stats endpoint → NucleiPostgresService
```

### **Data Flow Example**

```
1. Client: POST /scan
   ↓
2. Router: Create scan via NucleiPostgresService
   ↓
3. Database: Insert into nuclei_scans
   ↓
4. Response: ScanMetadata with ID

5. Client: POST /scan/{id}/process
   ↓
6. Router: Process output via NucleiIntegrationService
   ↓
7. Services: Store in Neo4j + PostgreSQL
   ↓
8. Response: ProcessingResult with stats
```

---

## ✅ Verification Checklist

After deployment:

- [ ] Health endpoint returns 200
- [ ] Can create a scan
- [ ] Can retrieve scan by ID
- [ ] Can list scans
- [ ] Can delete scan
- [ ] Can process Nuclei output
- [ ] Can query findings
- [ ] Can get specific finding
- [ ] Can get statistics
- [ ] All responses are valid JSON
- [ ] Swagger UI shows all endpoints
- [ ] Error handling works correctly

---

## 📚 API Reference Links

- [Swagger UI](http://localhost:8000/docs) - Interactive API explorer
- [ReDoc](http://localhost:8000/redoc) - Alternative API documentation
- [OpenAPI Schema](http://localhost:8000/openapi.json) - Machine-readable spec

---

**Phase 4**: ✅ **COMPLETE & PRODUCTION READY**

*Last Updated: April 28, 2026*
