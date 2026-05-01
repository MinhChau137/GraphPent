# 🚀 Phase 5 Roadmap: Advanced Features & Scalability

**Phase**: 5 of 5 (Week 3 - Days 3-4)  
**Duration**: 3-4 days  
**Status**: STARTING  
**Dependencies**: ✅ Phase 4 (REST API) - COMPLETE

---

## 🎯 Phase 5 Overview

**Phase 5 Goal**: Scale the system for production workloads with background processing, real-time updates, and security.

**Available Features** (select/implement as needed):
1. ✅ **Phase 5.1: Async Job Queues** (SELECTED) - Background scan processing
2. Phase 5.2: WebSocket Support - Real-time scan updates
3. Phase 5.3: Advanced Filtering - Elasticsearch integration
4. Phase 5.4: Authentication & Authorization - RBAC with JWT
5. Phase 5.5: Batch Operations - Bulk scan management
6. Phase 5.6: Export/Import - Data portability

---

## 🔄 Phase 5.1: Async Job Queues (CURRENT)

**What We're Building**:
1. Celery worker integration
2. Redis as message broker
3. Background task management
4. Job status tracking
5. Async scan processing pipeline
6. Job retry logic with exponential backoff
7. Task monitoring endpoints

**What We're NOT Building**:
- ❌ WebSocket real-time (Phase 5.2)
- ❌ Authentication/Authorization (Phase 5.4)
- ❌ Elasticsearch (Phase 5.3)

---

## 📋 Phase 5.1 Detailed Tasks

### **Task 5.1.1: Infrastructure Setup** (2 hours)

**Components to Add**:
```
app/
├── workers/                        [NEW]
│   ├── __init__.py
│   ├── config.py                  - Celery configuration
│   ├── nuclei_tasks.py            - Background task definitions
│   └── task_handlers.py           - Task execution logic
│
├── domain/schemas/
│   └── job_queue.py              [NEW] - Job models
│
└── services/
    ├── __init__.py
    └── job_queue_service.py       [NEW] - Queue orchestration
```

**Dependencies to Install**:
- celery[redis] >= 5.3.0
- redis >= 5.0.0
- kombu >= 5.3.0

**docker-compose.yml Updates**:
```yaml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data

celery_worker:
  build: .
  command: celery -A app.workers.config worker --loglevel=info
  depends_on:
    - redis
    - postgres
    - neo4j
```

---

### **Task 5.1.2: Celery Configuration** (1 hour)

**app/workers/config.py**:
```python
from celery import Celery

# Configure Celery with Redis broker
app = Celery(
    'graphpent',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1',
)

# Task settings
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=3600,           # 1 hour hard limit
    task_soft_time_limit=3300,      # 55 min soft limit
    broker_connection_retry_on_startup=True,
)
```

---

### **Task 5.1.3: Job Queue Models** (1.5 hours)

**app/domain/schemas/job_queue.py**:

Enums:
```python
JobStatusEnum = [pending, running, completed, failed, cancelled, retrying]
JobTypeEnum = [nuclei_scan, batch_scan, result_import, report_generation]
```

Models:
```python
JobQueue
├─ id (UUID)
├─ job_id (Celery task ID)
├─ job_type (enum)
├─ status (enum)
├─ priority (int: 1-10)
├─ target_url (str)
├─ payload (JSON)
├─ result (JSON)
├─ error_message (optional)
├─ retry_count (int)
├─ max_retries (int)
├─ created_at (datetime)
├─ started_at (optional datetime)
├─ completed_at (optional datetime)

JobQueueRequest
├─ target_url
├─ scan_type
├─ priority (1-10, default 5)
├─ metadata
└─ callback_url (optional webhook)

JobQueueResponse
├─ job_id
├─ status
├─ progress (%)
├─ eta_seconds (optional)
└─ result (optional)
```

**Database Schema**:
```sql
CREATE TABLE job_queue (
    id UUID PRIMARY KEY,
    job_id VARCHAR UNIQUE NOT NULL,
    job_type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    priority INTEGER DEFAULT 5,
    target_url VARCHAR,
    payload JSONB,
    result JSONB,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    CHECK (priority BETWEEN 1 AND 10),
    CHECK (retry_count <= max_retries)
);

CREATE INDEX idx_job_queue_status ON job_queue(status);
CREATE INDEX idx_job_queue_created_at ON job_queue(created_at DESC);
CREATE INDEX idx_job_queue_priority_status ON job_queue(priority DESC, status);
```

---

### **Task 5.1.4: Celery Task Definitions** (2 hours)

**app/workers/nuclei_tasks.py**:

Tasks:
```python
@shared_task(bind=True, max_retries=3)
def scan_target_async(self, job_id, target_url, scan_type):
    """Background Nuclei scan task"""
    # 1. Update job status to 'running'
    # 2. Get integration service
    # 3. Execute Nuclei scan
    # 4. Process findings
    # 5. Update job with results
    # 6. Handle errors with retry

@shared_task
def process_scan_results(self, scan_id, job_id):
    """Process completed scan results"""

@shared_task(bind=True, max_retries=5)
def upsert_to_neo4j_async(self, scan_id, findings):
    """Async Neo4j upsert with retry"""

@shared_task
def generate_report(job_id):
    """Generate report for completed scan"""
```

---

### **Task 5.1.5: Job Queue Service** (2 hours)

**app/services/job_queue_service.py**:

Public Methods:
```python
class JobQueueService:
    async def submit_job(job_type, target_url, priority=5, metadata=None)
        → Returns: JobQueueResponse with job_id
    
    async def get_job_status(job_id)
        → Returns: JobQueueResponse with current status
    
    async def get_job_result(job_id)
        → Returns: JobQueueResponse with result (if completed)
    
    async def cancel_job(job_id)
        → Returns: Success/Error response
    
    async def list_jobs(status=None, limit=20, offset=0)
        → Returns: Paginated job list
    
    async def get_job_history(target_url, limit=10)
        → Returns: Job history for target
    
    async def retry_failed_job(job_id, max_retries=3)
        → Returns: New job_id for retry
```

---

### **Task 5.1.6: New API Endpoints** (2 hours)

**app/api/v1/routers/job_queue.py** [NEW]:

Endpoints:
```
POST   /api/v1/jobs/scan              - Submit async scan
GET    /api/v1/jobs/{job_id}          - Get job status
GET    /api/v1/jobs/{job_id}/result   - Get job result
DELETE /api/v1/jobs/{job_id}          - Cancel job
GET    /api/v1/jobs                   - List jobs (paginated)
GET    /api/v1/jobs/history/{target}  - Job history
POST   /api/v1/jobs/{job_id}/retry    - Retry failed job
GET    /api/v1/jobs/stats             - Queue statistics
```

**Request/Response Examples**:
```python
# Request
POST /api/v1/jobs/scan
{
    "target_url": "http://target.com",
    "scan_type": "full",
    "priority": 7,
    "metadata": {"custom": "value"}
}

# Response (202 Accepted)
{
    "job_id": "uuid-123",
    "status": "pending",
    "created_at": "2026-04-29T10:00:00Z",
    "estimated_completion": "2026-04-29T10:15:00Z"
}

# Status Check
GET /api/v1/jobs/uuid-123

{
    "job_id": "uuid-123",
    "status": "running",
    "progress": 45,
    "started_at": "2026-04-29T10:01:00Z",
    "eta_seconds": 500,
    "current_task": "Running nuclei templates..."
}

# Get Result (when completed)
GET /api/v1/jobs/uuid-123/result

{
    "job_id": "uuid-123",
    "status": "completed",
    "result": {
        "scan_id": "scan-uuid",
        "findings_count": 24,
        "severity_breakdown": {
            "CRITICAL": 2,
            "HIGH": 5,
            "MEDIUM": 12,
            "LOW": 5,
            "INFO": 0
        },
        "neo4j_status": "upserted"
    },
    "completed_at": "2026-04-29T10:15:23Z"
}
```

---

### **Task 5.1.7: Integration Tests** (2 hours)

**tests/test_job_queue.py**:

Test Classes:
```python
TestJobSubmission        - Submit jobs, validation
TestJobStatusTracking    - Get status, progress updates
TestJobCancellation      - Cancel pending/running jobs
TestJobRetry             - Retry failed jobs
TestJobHistory           - Query job history
TestCeleryWorker         - Worker task execution
TestErrorHandling        - Task failures, retries
TestQueueStatistics      - Queue metrics
```

---

### **Task 5.1.8: Documentation** (1.5 hours)

**docs/PHASE5_1_ASYNC_JOBS.md**:
- Architecture overview with diagram
- Setup instructions (Celery + Redis)
- Configuration guide
- API reference (all endpoints)
- Usage examples (Python + Bash)
- Deployment guide
- Troubleshooting

---

## 📊 Phase 5.1 Metrics

- **New Code**: 800+ lines
- **Database**: 1 table, 4 indexes
- **Celery Tasks**: 4 async tasks
- **API Endpoints**: 8 new endpoints
- **Tests**: 40+ test methods
- **Dependencies**: 3 new packages (celery, redis, kombu)

---

## 🔗 Integration Points

**With Phase 4 REST API**:
- Existing POST /scan remains synchronous (quick verification)
- New POST /jobs/scan handles async operations
- Both return different status codes (200 vs 202)

**With Phase 3 Services**:
- NucleiIntegrationService used within Celery tasks
- NucleiPostgresService updated for job tracking
- Neo4j operations remain async-friendly

**Database**:
- New job_queue table
- job_id foreign key link from nuclei_scans
- Cascade updates for status tracking

---

## 🚀 Benefits

1. **Scalability**: Long scans don't block HTTP requests
2. **User Experience**: Instant response with job ID, poll for status
3. **Reliability**: Automatic retry on failure with exponential backoff
4. **Monitoring**: Full job history and statistics
5. **Prioritization**: High-priority scans processed first
6. **Resource Management**: Queue prevents system overload

---

## 📅 Timeline Estimate

| Task | Duration | Status |
|------|----------|--------|
| 5.1.1: Infrastructure | 2 hrs | ⏳ |
| 5.1.2: Celery Config | 1 hr | ⏳ |
| 5.1.3: Job Models | 1.5 hrs | ⏳ |
| 5.1.4: Celery Tasks | 2 hrs | ⏳ |
| 5.1.5: Queue Service | 2 hrs | ⏳ |
| 5.1.6: API Endpoints | 2 hrs | ⏳ |
| 5.1.7: Tests | 2 hrs | ⏳ |
| 5.1.8: Documentation | 1.5 hrs | ⏳ |
| **Total** | **14 hours** | **⏳** |

---

## ✅ Phase 5.1 Completion Criteria

- [x] Docker Compose includes Redis + Celery worker
- [x] Celery tasks execute in background
- [x] Job queue database table created
- [x] All 8 endpoints functional
- [x] Status polling works correctly
- [x] Job cancellation works
- [x] Retry logic implemented
- [x] 40+ tests passing
- [x] Complete documentation with examples
- [x] Production-ready error handling

---

## Next Phases

**Phase 5.2**: WebSocket Support (real-time updates)  
**Phase 5.3**: Advanced Filtering (Elasticsearch)  
**Phase 5.4**: Authentication & Authorization (JWT + RBAC)  
**Phase 5.5**: Batch Operations (bulk scans)  
**Phase 5.6**: Export/Import (data portability)
