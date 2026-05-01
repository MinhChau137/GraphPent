# Phase 5.2: WebSocket Real-Time Updates

Complete implementation of real-time job update delivery for GraphPent using WebSocket protocol.

## Overview

Phase 5.2 extends Phase 5.1 (Async Job Queues) with real-time update capabilities. Instead of clients polling job status, they receive instant notifications for:
- Progress updates (percentage, current task, ETA)
- Status changes (pending → running → completed)
- Results delivery (findings, severity breakdown)
- Queue metrics (active jobs, success rate)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Client (Browser/App)                 │
├─────────────────────────────────────────────────────────────┤
│  const ws = new WebSocket('ws://localhost:8000/api/v1/...')│
│  ws.onmessage = (msg) => updateUI(JSON.parse(msg.data))    │
└────────────────────┬────────────────────────────────────────┘
                     │ WebSocket Frame
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  WebSocket Router                            │
│                  (app/api/v1/routers/websocket.py)          │
│  - /api/v1/ws/jobs/{job_id}  (individual job updates)      │
│  - /api/v1/ws/metrics         (queue statistics)            │
│  - /api/v1/ws/live            (multi-job subscription)      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│           WebSocket Connection Manager                       │
│           (app/services/websocket_manager.py)               │
│  - Connection tracking (active_connections dict)            │
│  - Subscription management (job_subscriptions dict)         │
│  - Message broadcasting (broadcast_* methods)               │
│  - Singleton pattern (get_ws_manager())                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│             Job Progress Tracker                             │
│           (app/services/job_progress_tracker.py)            │
│  - Progress persistence (PostgreSQL metadata)               │
│  - Status transitions (database + broadcast)                │
│  - Metrics aggregation (queue statistics)                   │
│  - Metrics broadcast loop (periodic updates)                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Job Queue Service                              │
│           (app/services/job_queue_service.py)               │
│  - Job lifecycle management                                 │
│  - Celery task submission                                   │
│  - Callback to progress tracker                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Celery Tasks / Workers                          │
│         (app/workers/nuclei_tasks.py)                       │
│  - Emit progress updates via update_state()                 │
│  - Call progress_tracker for broadcasts                     │
│  - Update status on completion                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│             PostgreSQL + Redis                               │
│  - Job data persistence (JobQueue table)                    │
│  - Celery message broker (scans, default queues)            │
│  - Task result storage                                      │
└─────────────────────────────────────────────────────────────┘
```

### Message Flow

1. **Client connects**: WebSocket → Connection Manager → assign connection_id
2. **Client subscribes**: SUBSCRIBE msg → Manager tracks subscription
3. **Job progresses**: Celery task → Progress Tracker → broadcast_progress_update()
4. **All subscribers receive**: broadcast_* → sends to all subscribed connections
5. **Job completes**: Status changes → auto-unsubscribe + result delivery

### Data Models

```python
# Client → Server Messages
ClientMessage:
  message_type: SUBSCRIBE | UNSUBSCRIBE | PING
  job_id: Optional[str]
  data: Optional[dict]

# Server → Client Messages  
ServerMessage:
  message_type: CONNECTED | PROGRESS_UPDATE | STATUS_UPDATE | RESULT_READY | ERROR | PONG | METRICS_UPDATE
  job_id: Optional[str]
  data: dict (contains progress/status/result info)
  timestamp: datetime

# Progress Data
JobProgressData:
  job_id: str
  status: "running"
  progress: 0-100
  current_task: str
  estimated_remaining_seconds: Optional[int]
  processed_items: Optional[int]
  total_items: Optional[int]

# Status Data
JobStatusData:
  job_id: str
  previous_status: str
  current_status: str
  error_message: Optional[str]

# Result Data
JobResultData:
  job_id: str
  target_url: str
  findings_count: int
  severity_breakdown: dict
  neo4j_status: str
  neo4j_count: Optional[int]
  completion_time_seconds: Optional[float]
```

## Files Created/Modified

### New Files
- **app/services/websocket_manager.py** (400+ lines)
  - `WebSocketConnectionManager` class
  - Connection lifecycle management
  - Subscription tracking
  - Broadcast methods
  - Singleton factory

- **app/services/job_progress_tracker.py** (300+ lines)
  - `JobProgressTracker` class
  - Progress persistence
  - Status transitions
  - Metrics aggregation
  - Background metrics loop

- **app/api/v1/routers/websocket.py** (350+ lines)
  - 3 WebSocket endpoints
  - Health check endpoint
  - Comprehensive docstrings with examples

### Modified Files
- **app/main.py**
  - Added websocket router import
  - Registered websocket router

### Test Files
- **tests/test_phase5_websocket.py** (600+ lines)
  - 60+ test methods
  - Connection management tests
  - Subscription tests
  - Broadcasting tests
  - Progress tracking tests

## API Reference

### WebSocket Endpoints

#### 1. Individual Job Updates
```
ws://localhost:8000/api/v1/ws/jobs/{job_id}?client_id=optional
```

**Behavior**:
- Auto-subscribes to job upon connection
- Receives all updates for that job
- Disconnects after result delivery (auto-unsubscribe)

**Client Example (JavaScript)**:
```javascript
const jobId = "a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6";
const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/jobs/${jobId}`);

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    
    if (message.message_type === 'progress_update') {
        console.log(`Progress: ${message.data.progress}%`);
        console.log(`Task: ${message.data.current_task}`);
        console.log(`ETA: ${message.data.estimated_remaining_seconds}s`);
    }
    
    if (message.message_type === 'status_update') {
        console.log(`Status: ${message.data.previous_status} → ${message.data.current_status}`);
    }
    
    if (message.message_type === 'result_ready') {
        console.log(`Findings: ${message.data.findings_count}`);
        console.log(`Critical: ${message.data.severity_breakdown.critical}`);
        ws.close(); // Connection auto-closes after result
    }
};
```

**Client Example (Python)**:
```python
import asyncio
import websockets
import json

async def listen_to_job(job_id):
    uri = f"ws://localhost:8000/api/v1/ws/jobs/{job_id}"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            
            if data['message_type'] == 'progress_update':
                print(f"Progress: {data['data']['progress']}%")
            elif data['message_type'] == 'result_ready':
                print(f"Complete! Findings: {data['data']['findings_count']}")
                break

asyncio.run(listen_to_job("job-uuid"))
```

#### 2. Queue Metrics
```
ws://localhost:8000/api/v1/ws/metrics?client_id=optional
```

**Behavior**:
- Receives periodic queue statistics (every 30 seconds)
- No job-specific subscriptions
- Useful for monitoring dashboard

**Message Format**:
```json
{
  "message_type": "metrics_update",
  "data": {
    "total_jobs": 150,
    "pending_jobs": 25,
    "running_jobs": 8,
    "completed_jobs": 110,
    "failed_jobs": 7,
    "success_rate": 93.65,
    "average_completion_time_seconds": 45.3
  },
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

#### 3. Multi-Job Subscription
```
ws://localhost:8000/api/v1/ws/live?client_id=optional
```

**Behavior**:
- Flexible subscribe/unsubscribe from multiple jobs
- Receive queue metrics
- Keep-alive via ping/pong

**Client Protocol**:
```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/live');

// Subscribe to job
ws.send(JSON.stringify({
    message_type: 'subscribe',
    job_id: 'job-uuid-1'
}));

// Subscribe to another job
ws.send(JSON.stringify({
    message_type: 'subscribe',
    job_id: 'job-uuid-2'
}));

// Keep connection alive
setInterval(() => {
    ws.send(JSON.stringify({
        message_type: 'ping'
    }));
}, 30000);

// Unsubscribe from job
ws.send(JSON.stringify({
    message_type: 'unsubscribe',
    job_id: 'job-uuid-1'
}));
```

## Integration with Celery

### Task Progress Reporting

```python
# In Celery task (app/workers/nuclei_tasks.py)

@celery_app.task(bind=True, max_retries=3, time_limit=3600)
def scan_target_async(self, job_db_id, target_url, scan_type, metadata):
    try:
        progress_tracker = asyncio.run(get_progress_tracker())
        
        # Update status to running
        asyncio.run(progress_tracker.update_job_status(
            job_db_id,
            JobStatusEnum.RUNNING.value
        ))
        
        # Run scan with progress reporting
        for i, finding in enumerate(findings):
            # Update progress
            asyncio.run(progress_tracker.update_job_progress(
                job_db_id,
                progress=int((i / len(findings)) * 100),
                current_task="Scanning vulnerabilities",
                processed_items=i,
                total_items=len(findings),
            ))
            
            # Process finding...
        
        # Mark complete
        asyncio.run(progress_tracker.mark_job_complete(
            job_db_id,
            target_url=target_url,
            findings_count=len(findings),
            severity_breakdown=severity_breakdown,
            neo4j_status="synced",
        ))
        
    except Exception as e:
        asyncio.run(progress_tracker.update_job_status(
            job_db_id,
            JobStatusEnum.FAILED.value,
            error_message=str(e)
        ))
```

## Real-Time Update Flow

### 1. Job Submission
```
POST /api/v1/jobs/scan
  → JobQueueService.submit_job()
  → Create JobQueue record (status: PENDING)
  → Submit to Celery
  → Return job_id (202 Accepted)
```

### 2. Client Subscribes to Updates
```
WebSocket: ws://localhost:8000/api/v1/ws/jobs/{job_id}
  → Manager accepts connection
  → Auto-subscribes to job_id
  → Client ready to receive updates
```

### 3. Task Starts
```
Celery worker picks up task
  → Celery calls scan_target_async()
  → Task updates status → RUNNING
  → ProgressTracker broadcasts status_update
  → WebSocket sends to all subscribers
```

### 4. Progress Updates
```
During scan:
  → Every N findings processed
  → Task calls update_job_progress()
  → ProgressTracker updates metadata in DB
  → Broadcasts progress_update message
  → All subscribers receive progress%
```

### 5. Task Completes
```
Scan finished:
  → Task calls mark_job_complete()
  → ProgressTracker:
    - Updates status → COMPLETED
    - Stores results in DB
    - Broadcasts result_ready
  → WebSocket sends result to subscribers
  → Auto-unsubscribes (result delivered)
  → Client detects ws.close()
```

## Performance Considerations

### Connection Management
- **In-memory tracking**: Dictionary-based O(1) lookups
- **Single broadcast queue**: All subscribers receive in parallel
- **Lazy cleanup**: Connections removed only on disconnect/error

### Database Updates
- **Async operations**: Non-blocking progress updates
- **Metadata storage**: Only JSON stored (no binary)
- **Indexed lookups**: job_id indexed for fast queries

### Message Overhead
- **JSON format**: Human-readable, debuggable
- **Compressed payloads**: Only essential fields included
- **Binary option**: WebSocket supports binary frames (future)

### Scalability
- **Horizontal scaling**: Each server handles own connections
- **Redis pub/sub ready**: Future implementation for multi-server
- **Connection pooling**: FastAPI handles WebSocket concurrency

## Troubleshooting

### Issue: WebSocket connection refused
```
Error: Connection refused: ws://localhost:8000/api/v1/ws/jobs/...

Solution:
1. Verify FastAPI server running: curl http://localhost:8000/health
2. Check CORS settings in app/main.py
3. Verify WebSocket router included in main.py
4. Check firewall allows WebSocket (port 8000)
```

### Issue: No messages received after connection
```
Solution:
1. Verify job exists: GET /api/v1/jobs/{job_id}
2. Check job status is RUNNING (not PENDING)
3. Monitor server logs: tail logs/app.log
4. Verify Celery worker is running: celery -A app.workers.config inspect active
5. Check Redis connection: redis-cli ping
```

### Issue: Connection drops unexpectedly
```
Solution:
1. Send periodic pings: every 30 seconds
2. Implement auto-reconnect in client
3. Check server logs for exceptions
4. Monitor connection count: GET /api/v1/ws/health
5. Verify system resources (memory, connections)
```

### Issue: High latency on messages
```
Solution:
1. Check database query performance (pg_stat_statements)
2. Monitor Celery task queue length
3. Verify Redis connection latency: redis-cli --latency
4. Check network bandwidth
5. Scale workers: increase CELERY_WORKER_CONCURRENCY
```

## Testing

### Run WebSocket Tests
```bash
# Install pytest-asyncio
pip install pytest-asyncio

# Run all WebSocket tests
pytest tests/test_phase5_websocket.py -v

# Run specific test class
pytest tests/test_phase5_websocket.py::TestWebSocketConnectionManager -v

# Run with coverage
pytest tests/test_phase5_websocket.py --cov=app.services.websocket_manager --cov-report=html
```

### Manual Testing with websocat

```bash
# Install websocat: https://github.com/vi/websocat

# Subscribe to job updates
websocat ws://localhost:8000/api/v1/ws/live

# Send subscribe message
{"message_type": "subscribe", "job_id": "your-job-id"}

# Watch for updates
# (you should see progress_update messages)

# Send keep-alive
{"message_type": "ping"}

# Unsubscribe
{"message_type": "unsubscribe", "job_id": "your-job-id"}
```

## Deployment

### Development
```bash
# Terminal 1: Start FastAPI
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Start Celery worker
celery -A app.workers.config worker --loglevel=info

# Terminal 3: Start Redis (if not containerized)
redis-server
```

### Production (Docker Compose)
```bash
# Start all services
docker-compose up -d

# Check services
docker-compose ps

# View logs
docker-compose logs -f fastapi
docker-compose logs -f celery_worker
docker-compose logs -f redis

# Verify WebSocket endpoint
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
  http://localhost:8000/api/v1/ws/health
```

### Environment Variables
```env
REDIS_URL=redis://localhost:6379/2
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
WS_METRICS_UPDATE_INTERVAL=30  # seconds
```

## Future Enhancements

- [ ] Redis pub/sub for multi-server broadcasting
- [ ] WebSocket binary frames (Protocol Buffers)
- [ ] Client-side reconnection logic (exponential backoff)
- [ ] Message compression (deflate)
- [ ] Authorization/authentication on WebSocket
- [ ] Rate limiting per connection
- [ ] Message history/replay
- [ ] WebSocket stress testing tools
- [ ] Dashboard with real-time metrics
- [ ] Mobile app support

## Security Considerations

1. **Connection validation**: Verify job_id ownership before subscription
2. **Rate limiting**: Limit messages per second per connection
3. **Input validation**: Validate all client messages
4. **Timeout handling**: Close idle connections after 5 minutes
5. **Error messages**: Don't leak sensitive info in error responses
6. **CORS**: Restrict origins if not public API
7. **TLS**: Use wss:// in production (WebSocket Secure)

## Metrics & Monitoring

### Key Metrics
- Active WebSocket connections
- Messages per second
- Average message latency
- Connection uptime
- Broadcast fan-out count
- Memory usage per connection

### Monitoring Integration
```python
# In progress_tracker.py or main.py
from prometheus_client import Counter, Gauge, Histogram

ws_connections = Gauge('ws_connections_active', 'Active WebSocket connections')
ws_messages_sent = Counter('ws_messages_sent_total', 'Total messages sent')
ws_broadcast_latency = Histogram('ws_broadcast_latency_seconds', 'Broadcast latency')
```

## References

- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [WebSocket Protocol RFC 6455](https://tools.ietf.org/html/rfc6455)
- [ASGI Specification](https://asgi.readthedocs.io/)
- [Celery Task Progress Documentation](https://docs.celeryproject.org/en/stable/userguide/tasks.html#task-states)
