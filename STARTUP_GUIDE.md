# 🚀 GraphPent Phase 7-9 Startup Guide

**Project**: GraphRAG Pentest Platform  
**Status**: 🟢 **Production Ready** (Phases 7-9 Complete)  
**Last Updated**: April 30, 2026

---

## 📋 Table of Contents

1. [System Architecture](#-system-architecture)
2. [Prerequisites](#-prerequisites)
3. [Quick Start](#-quick-start)
4. [Full System Startup](#-full-system-startup)
5. [Testing](#-testing)
6. [Troubleshooting](#-troubleshooting)

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI 0.115.0                       │
│                   (API Gateway)                          │
└──────────────┬──────────────────────────────────────────┘
               │
    ┌──────────┼──────────┬─────────────┬─────────────┐
    │          │          │             │             │
┌───▼────┐ ┌──▼────┐ ┌───▼──┐ ┌────────▼─┐ ┌───────▼──┐
│ Phase7 │ │Phase8 │ │Phase9│ │PostgreSQL│ │  Redis   │
│Retrieve│ │Agents │ │Tools │ │ (ORM)    │ │(Cache)   │
└────┬───┘ └──┬────┘ └──┬───┘ └─────────┘ └──────────┘
     │        │        │
     └────┬───┴────┬───┘
          │        │
     ┌────▼──┐ ┌──▼─────┐
     │Neo4j  │ │Weaviate│
     │(Graph)│ │(Vector)│
     └───────┘ └────────┘
```

### Phase 7: Retrieve & Analytics
- **Hybrid Retrieval** with Vector + Graph + RRF fusion
- **Redis Caching** for performance (1-hour TTL)
- **Analytics Dashboard** metrics (latency, mode distribution)

### Phase 8: Multi-Agent Workflow
- **LangGraph Orchestration** with 6 specialized agents
- **Conditional Routing** for dynamic tool execution
- **Human-in-Loop** approval workflow

### Phase 9: Pentest Tools
- **CVE Analysis** with exploitability scoring
- **Nuclei Integration** for security scanning
- **Finding Correlation** (CVE + Nuclei results)

---

## 📦 Prerequisites

### Required
- **Docker** 20.10+
- **Docker Compose** 2.0+
- **Python** 3.11+ (for CLI scripts)
- **Git**

### Recommended
- **Nuclei** binary (optional, HTTP API fallback available)
- **Postman** or **curl** for API testing
- **Redis CLI** for cache management

### System Resources
- **Minimum**: 4 CPU cores, 8GB RAM
- **Recommended**: 8 CPU cores, 16GB RAM

### Ports Required
```
8000  - FastAPI (main API)
5432  - PostgreSQL
6379  - Redis
7474  - Neo4j Browser
7687  - Neo4j Bolt (database)
8080  - Weaviate API
9200  - Elasticsearch (optional Phase 5)
8888  - Ollama (optional)
8081  - MinIO (data storage)
```

---

## 🚀 Quick Start (5 minutes)

### Option A: Docker Compose (Recommended)

```bash
# 1. Navigate to project root
cd /path/to/GraphPent

# 2. Build images
docker-compose build

# 3. Start all services
docker-compose up -d

# 4. Wait for services to be ready (~30 seconds)
docker-compose logs -f app

# 5. Test API
curl http://localhost:8000/docs
```

### Option B: Manual Startup (Development)

```bash
# 1. Start infrastructure services
docker-compose up -d postgres redis neo4j weaviate minio

# 2. Create Python environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your settings

# 5. Run migrations
python -m alembic upgrade head  # if applicable

# 6. Start FastAPI
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🔧 Full System Startup

### Step 1: Initialize Environment

```bash
# Clone repository
git clone <repo-url>
cd GraphPent

# Create .env file
cat > .env << EOF
# PostgreSQL
POSTGRES_DB=graphrag
POSTGRES_USER=graphrag
POSTGRES_PASSWORD=SecurePassword123!
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/0

# Neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=SecurePassword456!

# Weaviate
WEAVIATE_URL=http://weaviate:8080

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=SecurePassword789!
MINIO_BUCKET=graphrag-bucket

# JWT
JWT_SECRET_KEY=your-super-secret-key-change-in-production

# Allowed scanning targets (lab only - expand carefully!)
ALLOWED_TARGETS=["127.0.0.1", "localhost", "192.168.1.100"]

# Nuclei configuration
NUCLEI_ENDPOINT=http://nuclei:8080
NUCLEI_TIMEOUT=300
EOF
```

### Step 2: Build and Start Services

```bash
# Build Docker images with caching
docker-compose build --no-cache

# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs for debugging
docker-compose logs -f app
```

### Step 3: Bootstrap Database

```bash
# Neo4j initialization (creates indexes, constraints)
docker-compose exec neo4j cypher-shell -u neo4j -p SecurePassword456! \
  < scripts/bootstrap/neo4j_bootstrap.cypher

# PostgreSQL initialization (creates analytics tables)
docker-compose exec postgres psql -U graphrag -d graphrag \
  < scripts/bootstrap/postgres_init.sql

# MinIO bucket setup
python scripts/bootstrap/minio_bootstrap.py

# Weaviate schema initialization
python scripts/bootstrap/weaviate_bootstrap.py
```

### Step 4: Load Sample Data

```bash
# Load sample CVEs and CWEs
python scripts/fixtures/load_sample_data.py

# Verify data loaded
docker-compose exec neo4j cypher-shell \
  "MATCH (c:CVE) RETURN count(c) as cve_count"
```

### Step 5: Test API

```bash
# 1. Open Swagger UI
curl http://localhost:8000/docs
# Or open browser: http://localhost:8000/docs

# 2. Test Phase 7 - Retrieval
curl -X POST http://localhost:8000/retrieve/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SQL injection vulnerability",
    "limit": 10,
    "mode": "hybrid"
  }'

# 3. Test Phase 8 - Workflow
curl -X POST http://localhost:8000/workflow/multi-agent \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Analyze security vulnerabilities",
    "user_id": "analyst01"
  }'

# 4. Test Phase 9 - Tools
curl -X POST http://localhost:8000/tools/cve/analyze \
  -H "Content-Type: application/json" \
  -d '{"cve_json": {...}}'
```

---

## 🧪 Testing

### Integration Tests

```bash
# Run full integration test suite (Phase 7-9)
python tests/test_phase_7_9_integration.py

# Expected output:
# 🟢 ALL TESTS PASSED (15/15)
```

### Unit Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run specific test file
pytest tests/test_extraction.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

### Manual Testing with curl

```bash
# Phase 7 - Analytics
curl http://localhost:8000/retrieve/stats?hours=24

# Phase 8 - Workflow status
curl http://localhost:8000/workflow/status/workflow-id-here

# Phase 9 - Health check
curl http://localhost:8000/tools/health

# Cache management
curl -X GET http://localhost:8000/retrieve/cache-clear
```

### Performance Testing

```bash
# Generate load with Apache Bench
ab -n 100 -c 10 http://localhost:8000/retrieve/stats

# Or with wrk
wrk -t4 -c100 -d30s http://localhost:8000/retrieve/stats
```

---

## 🛑 Stopping and Cleanup

```bash
# Stop all services (keeps data)
docker-compose down

# Stop and remove all data
docker-compose down -v

# View stopped containers
docker-compose ps -a

# Clean up Docker (CAREFUL - removes unrelated images too)
docker system prune -a
```

---

## 📊 Monitoring

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f app

# Last 100 lines, follow
docker-compose logs -f --tail=100 app

# Specific time range
docker-compose logs --since 2024-04-30 --until 2024-05-01 app
```

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Tool service health
curl http://localhost:8000/tools/health

# Neo4j browser
open http://localhost:7474

# Weaviate console
curl http://localhost:8080/v1/.well-known/ready
```

### Metrics & Analytics

```bash
# Get retrieval analytics
curl http://localhost:8000/retrieve/stats?hours=24

# Get workflow metrics (Phase 8)
curl http://localhost:8000/workflow/metrics

# Export metrics to file
curl http://localhost:8000/metrics > metrics.txt
```

---

## ❓ Troubleshooting

### Issue: Services won't start

```bash
# Check Docker daemon
docker ps

# View detailed logs
docker-compose logs -f

# Rebuild from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Issue: Database connection failed

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Test connection
docker-compose exec postgres pg_isready -U graphrag -d graphrag

# View PostgreSQL logs
docker-compose logs postgres

# Reset PostgreSQL
docker-compose exec postgres psql -U graphrag -d graphrag -c "SELECT version();"
```

### Issue: Neo4j won't connect

```bash
# Check Neo4j status
docker-compose exec neo4j cypher-shell -u neo4j -p SecurePassword456! "RETURN 1"

# View Neo4j logs
docker-compose logs neo4j

# Reset Neo4j (WARNING: deletes all data)
docker-compose down -v neo4j
docker volume rm graphpent_neo4j_data
docker-compose up -d neo4j
```

### Issue: Redis cache not working

```bash
# Test Redis
docker-compose exec redis redis-cli ping

# Flush cache
docker-compose exec redis redis-cli FLUSHALL

# Monitor cache operations
docker-compose exec redis redis-cli MONITOR
```

### Issue: Weaviate search returning no results

```bash
# Check schema
curl http://localhost:8080/v1/schema

# Check object count
curl http://localhost:8080/v1/objects

# Reset Weaviate (WARNING: deletes all vectors)
docker-compose down -v weaviate
docker-compose up -d weaviate
python scripts/bootstrap/weaviate_bootstrap.py
```

### Issue: Nuclei scan fails

```bash
# Check if Nuclei is installed locally
nuclei -version

# Test HTTP API fallback
curl -X POST http://localhost:8080/scan \
  -H "Content-Type: application/json" \
  -d '{"target": "example.com"}'

# Install Nuclei locally
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
```

### Issue: Out of memory

```bash
# Check container memory usage
docker stats

# Increase Docker memory limit in docker-compose.yml
# Add to each service:
# deploy:
#   resources:
#     limits:
#       memory: 2G

# Rebuild and restart
docker-compose down
docker-compose up -d
```

---

## 🔐 Security Checklist

Before production deployment:

- [ ] Change all default passwords in `.env`
- [ ] Enable SSL/TLS for API (nginx reverse proxy)
- [ ] Configure firewall rules
- [ ] Set up rate limiting
- [ ] Enable authentication (JWT already implemented)
- [ ] Use environment-specific secrets (not in .env)
- [ ] Configure backup strategy for Neo4j/PostgreSQL
- [ ] Set up monitoring and alerting
- [ ] Review audit logs
- [ ] Test disaster recovery

---

## 📞 Support & Documentation

### API Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Detailed Guides
- [Phase 7-9 Completion Report](./PHASE_7_9_COMPLETION.md)
- [Architecture Overview](./README.md)
- [API Reference](./API_REFERENCE.md)

### Troubleshooting
- Check logs: `docker-compose logs -f`
- Run tests: `python tests/test_phase_7_9_integration.py`
- Review code: `app/api/v1/routers/`

---

## ✅ Verification Checklist

After startup, verify:

- [ ] API responds on http://localhost:8000/docs
- [ ] PostgreSQL: Data is persistent
- [ ] Neo4j: Graph data loaded (`MATCH (n) RETURN count(n)`)
- [ ] Weaviate: Vectors stored and searchable
- [ ] Redis: Cache working (check latency < 100ms)
- [ ] Phase 7: `/retrieve/query` returns results
- [ ] Phase 8: `/workflow/multi-agent` completes successfully
- [ ] Phase 9: `/tools/cve/analyze` scores CVEs correctly
- [ ] Auth: JWT tokens working if enabled
- [ ] Logs: No critical errors in `docker-compose logs`

---

## 🎯 Next Steps

1. **Load Production Data**
   ```bash
   python scripts/batch_ingest_cve.py --source nvd --limit 1000
   ```

2. **Configure Monitoring**
   ```bash
   # Add Prometheus & Grafana to docker-compose.yml
   ```

3. **Enable Authentication**
   - Create user accounts
   - Generate JWT tokens
   - Configure RBAC roles

4. **Deploy to Production**
   - Set up Kubernetes manifests
   - Configure CI/CD pipelines
   - Deploy with Helm

---

**Ready to go!** 🚀

For detailed API usage, see [PHASE_7_9_COMPLETION.md](./PHASE_7_9_COMPLETION.md)
