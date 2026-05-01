# Phase 5.3: Advanced Filtering with Elasticsearch

Full-text search and advanced filtering for jobs, findings, and results using Elasticsearch. Enables rapid querying across millions of records with complex filters.

## Overview

Phase 5.3 adds Elasticsearch integration to GraphPent, enabling:
- **Full-text search** across job targets, findings, descriptions
- **Advanced filtering** by status, severity, CVE/CWE IDs, date ranges
- **Aggregated statistics** with severity breakdown
- **High performance** even with millions of indexed records
- **Pagination** support for large result sets

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────┐
│                     Client                               │
│  GET /api/v1/search/jobs?query=sql&status=completed    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Search API Router                           │
│          (app/api/v1/routers/search.py)                │
│  - POST /search/jobs (JSON request)                    │
│  - GET /search/jobs (query params)                     │
│  - POST /search/findings (JSON request)                │
│  - GET /search/findings (query params)                 │
│  - GET /search/statistics                              │
│  - GET /search/health                                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│             Search Service                              │
│        (app/services/search_service.py)                │
│  - search_jobs(request)                                │
│  - search_findings(request)                            │
│  - get_statistics()                                    │
│  - index_job_from_queue()                              │
│  - index_finding()                                     │
│  - health_check()                                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│          Elasticsearch Client                           │
│   (app/adapters/elasticsearch_client.py)               │
│  - search_jobs() → query builder + ES call            │
│  - search_findings() → query builder + ES call        │
│  - index_job/finding/result()                         │
│  - delete_job_data()                                  │
│  - health_check()                                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           Elasticsearch Server                          │
│  Port 9200 (HTTP API)                                  │
│  Three indexes: jobs, findings, results               │
│  Analyzer: Standard + English stopwords               │
└─────────────────────────────────────────────────────────┘
```

### Indexes

**graphpent-jobs**
- Stores job metadata for searching
- Fields: job_id, job_type, status, priority, target_url, error_message, findings_count, timestamps, duration
- Used for: Job search and filtering

**graphpent-findings**
- Stores individual findings for searching
- Fields: finding_id, job_id, template_id, target_url, severity, host, url, cve_ids, cwe_ids, description, timestamps
- Used for: Finding search and filtering, CVE/CWE queries

**graphpent-results**
- Stores aggregated job results
- Fields: job_id, target_url, findings_count, severity breakdown, neo4j status
- Used for: Result search and statistics

## API Reference

### Search Jobs

#### POST /api/v1/search/jobs
```json
{
  "query": "SQL injection",
  "status": "completed",
  "target_url": "https://example.com",
  "date_from": "2026-04-01T00:00:00",
  "date_to": "2026-04-30T23:59:59",
  "priority_min": 5,
  "priority_max": 10,
  "page": 1,
  "size": 20
}
```

**Response**:
```json
{
  "results": [
    {
      "job_id": "uuid",
      "job_type": "scan",
      "status": "completed",
      "priority": 8,
      "target_url": "https://example.com",
      "findings_count": 42,
      "created_at": "2026-04-15T10:30:00",
      "started_at": "2026-04-15T10:30:05",
      "completed_at": "2026-04-15T10:31:05",
      "duration_seconds": 120.5
    }
  ],
  "total": 150,
  "page": 1,
  "size": 20,
  "total_pages": 8,
  "has_more": true
}
```

#### GET /api/v1/search/jobs?query=sql&status=completed&page=1&size=20

Same response as POST, but using query string parameters for convenience.

### Search Findings

#### POST /api/v1/search/findings
```json
{
  "query": "XSS vulnerability",
  "severity": "CRITICAL",
  "job_id": "job-uuid",
  "cve_id": "CVE-2024-1234",
  "cwe_id": "CWE-79",
  "date_from": "2026-04-01T00:00:00",
  "page": 1,
  "size": 20
}
```

**Response**:
```json
{
  "results": [
    {
      "finding_id": "uuid",
      "job_id": "job-uuid",
      "template_id": "xss-reflection",
      "target_url": "https://example.com",
      "severity": "CRITICAL",
      "host": "example.com",
      "url": "https://example.com/search?q=alert",
      "cve_ids": ["CVE-2024-1234"],
      "cwe_ids": ["CWE-79"],
      "description": "Reflected XSS in search parameter",
      "created_at": "2026-04-15T10:30:00"
    }
  ],
  "total": 350,
  "page": 1,
  "size": 20,
  "total_pages": 18,
  "has_more": true
}
```

#### GET /api/v1/search/findings?severity=CRITICAL&cve_id=CVE-2024-1234&page=1&size=20

### Statistics

#### GET /api/v1/search/statistics?job_id=job-uuid

**Response**:
```json
{
  "total_findings": 1542,
  "average_findings_per_job": 38.5,
  "total_jobs_indexed": 40,
  "severity_distribution": {
    "CRITICAL": 15,
    "HIGH": 145,
    "MEDIUM": 782,
    "LOW": 600
  }
}
```

### Health Check

#### GET /api/v1/search/health

**Response**:
```json
{
  "status": "healthy",
  "elasticsearch_status": true,
  "indexes": {
    "jobs": {"status": "green"},
    "findings": {"status": "green"},
    "results": {"status": "green"}
  }
}
```

## Search Query Examples

### Find Critical Vulnerabilities
```
GET /api/v1/search/findings?severity=CRITICAL&page=1&size=50
```

### Find Specific CVE
```
GET /api/v1/search/findings?cve_id=CVE-2024-1234&page=1&size=100
```

### Search by Target
```
GET /api/v1/search/jobs?target_url=example.com&page=1&size=20
```

### Search by Date Range
```
POST /api/v1/search/findings
{
  "date_from": "2026-04-01T00:00:00",
  "date_to": "2026-04-30T23:59:59",
  "page": 1,
  "size": 100
}
```

### Combined Filters
```
POST /api/v1/search/jobs
{
  "query": "SQL",
  "status": "completed",
  "priority_min": 7,
  "date_from": "2026-04-15T00:00:00",
  "page": 1,
  "size": 20
}
```

## Integration with Phase 5.1

When a job completes in Phase 5.1:

1. JobQueueService updates job status
2. Optionally calls SearchService to index results:
   ```python
   search_service = await get_search_service()
   await search_service.index_job_from_queue(
       job_id=job.job_id,
       job_type=job.job_type,
       status=job.status,
       priority=job.priority,
       target_url=job.target_url,
       findings_count=results.get("findings_count"),
   )
   ```

3. For each finding discovered:
   ```python
   await search_service.index_finding(
       finding_id=finding["id"],
       job_id=job.job_id,
       template_id=finding["template_id"],
       target_url=job.target_url,
       severity=finding["severity"],
       host=finding["host"],
       url=finding["url"],
       cve_ids=finding.get("cve_ids", []),
       cwe_ids=finding.get("cwe_ids", []),
   )
   ```

## Installation & Setup

### 1. Install Elasticsearch Docker Image
```bash
docker run -d \
  --name elasticsearch \
  -e discovery.type=single-node \
  -e xpack.security.enabled=false \
  -p 9200:9200 \
  -p 9300:9300 \
  docker.elastic.co/elasticsearch/elasticsearch:8.0.0
```

### 2. Install Python Dependencies
```bash
pip install elasticsearch>=8.0.0
```

### 3. Configure Settings
```env
ELASTICSEARCH_HOSTS=["localhost:9200"]
ELASTICSEARCH_USER=
ELASTICSEARCH_PASSWORD=
```

### 4. Start Search Service
```bash
# Elasticsearch automatically creates indexes on first query
python -m uvicorn app.main:app --reload
```

### 5. Verify Installation
```bash
curl http://localhost:8000/api/v1/search/health
```

## Performance Tuning

### Index Settings
```python
# Current settings in elasticsearch_client.py
{
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
        "analyzer": {
            "default": {
                "type": "standard",
                "stopwords": "_english_"
            }
        }
    }
}
```

### Optimization for Production
- Increase shards for distributed indexing
- Add replicas for redundancy
- Use field aliases for backward compatibility
- Consider ILM (Index Lifecycle Management) for old data

### Query Optimization
- Use filters for exact matches (faster)
- Use queries for full-text search (relevance-scored)
- Always filter before querying when possible

## Client Examples

### JavaScript/TypeScript
```javascript
// Full-text search for critical vulnerabilities
const response = await fetch('/api/v1/search/findings', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    query: 'SQL injection',
    severity: 'CRITICAL',
    page: 1,
    size: 50
  })
});

const {results, total, has_more} = await response.json();
console.log(`Found ${total} critical SQL injection vulnerabilities`);
results.forEach(finding => {
  console.log(`${finding.host}: ${finding.description}`);
});
```

### Python
```python
import httpx
import asyncio

async def search_jobs():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://localhost:8000/api/v1/search/jobs',
            json={
                'query': 'example.com',
                'status': 'completed',
                'page': 1,
                'size': 20
            }
        )
        data = response.json()
        
        print(f"Found {data['total']} jobs")
        for job in data['results']:
            print(f"{job['job_id']}: {job['findings_count']} findings in {job['duration_seconds']:.1f}s")

asyncio.run(search_jobs())
```

### cURL
```bash
# Search for jobs
curl -X POST http://localhost:8000/api/v1/search/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SQL injection",
    "status": "completed",
    "priority_min": 5,
    "page": 1,
    "size": 20
  }'

# Get statistics
curl http://localhost:8000/api/v1/search/statistics

# Check health
curl http://localhost:8000/api/v1/search/health
```

## Troubleshooting

### Issue: "Connection refused: Elasticsearch"
```
Solution:
1. Verify Elasticsearch running: docker ps | grep elasticsearch
2. Check port 9200 open: curl -v http://localhost:9200
3. Check settings: ELASTICSEARCH_HOSTS in .env
4. Restart container: docker restart elasticsearch
```

### Issue: "Index not found"
```
Solution:
1. This is normal on first query - indexes auto-create
2. Ensure data is indexed: POST /api/v1/search/jobs or /findings
3. Check ES status: curl http://localhost:9200/_cat/indices
```

### Issue: "No results returned"
```
Solution:
1. Verify data was indexed
2. Try simpler query without filters first
3. Check Elasticsearch logs: docker logs elasticsearch
4. Use health check endpoint to verify ES is accessible
```

### Issue: "Search is slow"
```
Solution:
1. Check index size: curl http://localhost:9200/_cat/indices
2. Review slow query logs
3. Add more shards: PUT /graphpent-jobs/_settings
4. Delete old indexes if needed
5. Increase Elasticsearch heap memory
```

## Monitoring & Maintenance

### Monitor Index Health
```bash
curl http://localhost:9200/_cat/indices
curl http://localhost:9200/_cat/health
curl http://localhost:9200/graphpent-jobs/_stats
```

### Rebuild Indexes (if corrupted)
```bash
# Delete all indexes
curl -X DELETE http://localhost:9200/graphpent-*

# Restart will auto-recreate on next index operation
```

### Export/Backup
```bash
# Snapshot all indexes
curl -X PUT http://localhost:9200/_snapshot/backup
```

## Future Enhancements

- [ ] Redis caching for frequent searches
- [ ] Machine learning-based relevance tuning
- [ ] Saved searches/alerts
- [ ] Full-text search suggestions/autocomplete
- [ ] Export search results to CSV/JSON
- [ ] Search analytics dashboard
- [ ] Multi-index search
- [ ] Custom analyzers for domain-specific terms
- [ ] Real-time search results with WebSocket
- [ ] Advanced filtering UI component library

## API Limits

- Maximum page size: 100 results per page
- Maximum query timeout: 30 seconds
- Maximum result set: 10,000 results (use pagination)
- Index retention: 90 days (configurable)

## References

- [Elasticsearch Official Docs](https://www.elastic.co/docs/current)
- [Elasticsearch Query DSL](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
- [FastAPI Elasticsearch Integration](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
