# 🕸️ GraphRAG Pentest Platform

**Nền tảng GraphRAG** (Graph Retrieval-Augmented Generation) cho Penetration Testing tự động hóa, sử dụng kiến trúc **Hybrid Knowledge Graph** kết hợp Neo4j (Graph DB) + Weaviate (Vector DB) + Ollama (Local LLM).

**Phiên bản:** v0.2.0 (Phase 2 - Lab Stage)  
**Mục đích:** Xây dựng hệ thống truy xuất thông tin bảo mật thông minh dựa trên đồ thị tri thức CVE/CWE

## 📋 Tổng quan

Hệ thống cho phép:
- **📄 Ingest** (Phase 4): Upload & xử lý tài liệu (PDF, DOCX, JSON) → Chunking → Vector indexing
- **🔍 Extract** (Phase 5): Trích xuất entities & relationships từ văn bản dùng LLM
- **🕸️ Graph** (Phase 6): Lưu trữ & upsert dữ liệu vào đồ thị tri thức (Neo4j)
- **🔎 Retrieve** (Phase 7): Tìm kiếm hybrid (Vector + Graph) với fusion reranking
- **🤖 Workflow** (Phase 8): Multi-agent workflow tự động cho phân tích bảo mật
- **🛠️ Tools** (Phase 9): CVE analysis, Nuclei scanner integration (Lab-only)

## 🏗️ Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND (Port 8000)                  │
│  Routers: Ingest | Extract | Graph | Retrieve | Workflow | Tools
└─────────────────────────────────────────────────────────────────┘
    ↓                ↓                ↓                ↓
┌──────────┐  ┌──────────┐  ┌─────────────┐  ┌──────────────┐
│PostgreSQL│  │  Redis   │  │  MinIO(S3)  │  │ Ollama (LLM) │
│ (5432)   │  │ (6379)   │  │   (9000)    │  │   (11434)    │
│ Metadata │  │ Cache &  │  │  Document   │  │  Entity/Rel  │
│Document  │  │ Sessions │  │  Storage    │  │  Extraction  │
│ Chunks   │  │          │  │             │  │              │
└──────────┘  └──────────┘  └─────────────┘  └──────────────┘
    ↓
┌──────────────────────────────────────────────────────────┐
│         KNOWLEDGE GRAPHS & VECTOR DATABASES              │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────────┐         ┌─────────────────────┐    │
│  │  Neo4j (7687)   │         │ Weaviate (8080)     │    │
│  │                 │         │                     │    │
│  │ • Entity nodes  │         │ • Chunk vectors     │    │
│  │ • Relationships │         │ • Vector index      │    │
│  │ • Graph query   │         │ • Hybrid search     │    │
│  │ • CYPHER API    │         │ • Similarity search │    │
│  └─────────────────┘         └─────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### 🔌 Integrations
- **PostgreSQL**: Document metadata + chunk storage (SQLAlchemy ORM)
- **Neo4j**: Knowledge graph (CYPHER + APOC plugin)
- **Weaviate**: Vector embeddings + semantic search
- **MinIO**: Object storage (S3-compatible)
- **Ollama**: Local LLM extraction (llama3.2:3b)

## 🚀 Cài đặt & Khởi động

### Yêu cầu hệ thống

- Docker & Docker Compose v2+
- 8GB RAM (khuyến nghị), 16GB+ cho production
- 20GB+ dung lượng ổ cứng
- Windows: WSL2 backend for Docker Desktop

### 1️⃣ Chuẩn bị môi trường

```bash
cd GraphPent

# Tạo file .env từ template
cp .env.example .env
```

### 2️⃣ Cấu hình (.env)

```bash
# 📦 Database
POSTGRES_DB=pentest_graphrag
POSTGRES_USER=graphrag_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_HOST=postgres

# 🕸️ Neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123

# 🔍 Weaviate (vector database)
WEAVIATE_URL=http://weaviate:8080
WEAVIATE_API_KEY=  # anonymous for lab

# 💾 MinIO (object storage)
MINIO_ENDPOINT=minio:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_BUCKET=graphrag-bucket

# 🤖 Ollama (local LLM)
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2:3b
EMBEDDING_MODEL=nomic-embed-text-v1.5

# 🔐 Security
ALLOWED_TARGETS=["127.0.0.1", "localhost"]
MAX_TOOL_TIMEOUT=300
RATE_LIMIT_PER_MIN=30
```

### 3️⃣ Khởi động hệ thống

```bash
# Build & start all services
make up

# Hoặc: docker compose up --build -d

# Kiểm tra status
docker compose ps

# View logs
docker compose logs -f backend
```

### 4️⃣ Truy cập giao diện

| Giao diện | URL | Login |
|-----------|-----|-------|
| **Swagger Docs** | http://localhost:8000/docs | — |
| **ReDoc** | http://localhost:8000/redoc | — |
| **Neo4j Browser** | http://localhost:7474 | neo4j / password123 |
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin123 |
| **Weaviate** | http://localhost:8080 | (anonymous) |

## � Luồng Xử Lý Dữ Liệu (Data Pipeline)

### **Phase 4: Ingestion** ✅

```
┌──────────┐
│ Upload   │ (PDF, DOCX, JSON, etc)
└─────────┬┘
          ↓
   ┌────────────────────┐
   │ 1. Parse Document  │ ← Detect format, extract text
   └────────────────────┘
          ↓
   ┌────────────────────┐
   │ 2. Chunk Text      │ ← Sliding window chunking
   └────────────────────┘
          ↓
   ┌────────────────────┐
   │ 3. Deduplication   │ ← SHA256 hash check
   └────────────────────┘
          ↓
   ┌────────────────────┐
   │ 4. Store Atomically│ ← DB + MinIO + Weaviate
   └────────────────────┘
          ↓
    Output: { document_id, chunks_count }
```

**Endpoint:** `POST /ingest/document`

**Databaseе:** `documents` + `chunks` tables  
**Storage:** MinIO (raw/{uuid}_{filename})

---

### **Phase 5: Extraction** ✅

```
┌──────────────────┐
│ Fetch Chunk      │
└─────────┬────────┘
          ↓
┌──────────────────────────────────┐
│ LLM Extraction (Ollama)          │
│                                  │
│ Prompt: Extract from CVE/CWE     │
│ Output: JSON entities + relations│
└──────────┬───────────────────────┘
           ↓
┌──────────────────────────────────┐
│ Validation & Name Enrichment     │
│                                  │
│ • Ensure meaningful entity names │
│ • Fix CWE ID → Descriptions     │
│ • Validate entity types         │
└──────────┬───────────────────────┘
           ↓
    Output: ExtractionResult
    { entities[], relations[] }
```

**Endpoint:** `POST /extract/chunk/{id}`

**LLM Model:** llama3.2:3b (Ollama)  
**Confidence:** tracked in provenance

---

### **Phase 6: Graph Upsert** ✅

```
┌──────────────────────────────────┐
│ Neo4j MERGE (Entity Upsert)      │
│                                  │
│ MERGE (n:${type} {id: ...})     │
│   ON CREATE: set properties      │
│   ON MATCH: update properties    │
│ Result: Deduped graph nodes     │
└──────────┬───────────────────────┘
           ↓
┌──────────────────────────────────┐
│ Create Relationships             │
│                                  │
│ MATCH (source)-[r:TYPE]->(target)
│ Properties: provenance, metadata │
└──────────┬───────────────────────┘
           ↓
    Output: { entities_upserted, relations_created }
```

**Service:** `GraphService.process_extraction_result()`

**Neo4j:** Dynamic labels (Weakness, CWE, VulnerabilityType, ...)

---

### **Phase 7: Hybrid Retrieval** ✅

```
Query: "SQL injection vulnerability"
           ↓
    ┌──────┴──────┐
    ↓             ↓
Vector Search   Graph Traversal
(Weaviate)      (Neo4j)
├─ Embed query   ├─ Fulltext search
├─ Cosine sim    ├─ Keyword match
├─ Top-K         ├─ BFS expansion
↓                ↓
[V1, V2, V3...] [G1, G2, G3...]
    ↓             ↓
    └──────┬──────┘
           ↓
    ┌─────────────────────────────┐
    │ Fusion Reranking (α=0.7)   │
    │ score = α*graph +           │
    │         (1-α)*vector       │
    └──────────┬──────────────────┘
               ↓
    Final Results (ranked)
```

**Endpoint:** `POST /retrieve/query`

**Parameters:** `query`, `limit`, `alpha` (0.0-1.0)

---

### **Phase 8: Multi-Agent Workflow** ✅

```
LangGraph DAG:
    planner → retrieval → graph_reasoning
                             ↓
                         tool → report
                                  ↓
                           human_approval → END
```

**Endpoint:** `POST /workflow/run`

**State:** query, retrieval_results, graph_context, tool_results, final_answer

---

## 📚 API Endpoints (Đầy đủ)

| Endpoint | Method | Phase | Mô tả |
|----------|--------|-------|-------|
| `/health` | GET | — | Health check |
| `/config` | GET | — | Safe config exposure |
| **`/ingest/document`** | POST | 4 | Upload & ingest document |
| **`/extract/chunk/{id}`** | POST | 5 | Extract entities from chunk |
| **`/retrieve/query`** | POST | 7 | Hybrid search (vector + graph) |
| **`/workflow/run`** | POST | 8 | Run multi-agent workflow |
| `/tools/cve/analyze` | POST | 9 | CVE exploitability |
| `/tools/nuclei/cve` | POST | 9 | Nuclei scanner |
| `/graph/query` | POST | 6 | CYPHER query execution |
| `/dashboard/*` | GET | — | Metrics & monitoring |

### 📝 API Examples

#### Ingest Document
```bash
curl -X POST http://localhost:8000/ingest/document \
  -F "file=@data/nvdcve-2.0-modified.json"
```

#### Extract Entities
```bash
curl -X POST http://localhost:8000/extract/chunk/1
```

#### Hybrid Retrieve
```bash
curl -X POST http://localhost:8000/retrieve/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SQL injection in CWE-89",
    "limit": 10,
    "alpha": 0.7
  }'
```

#### Run Workflow
```bash
curl -X POST http://localhost:8000/workflow/run \
  -H "Content-Type: application/json" \
  -d '{"query": "Find critical CVEs from 2024"}'
```

## 🛠️ Batch Processing Scripts

### 📥 Batch Ingest CVE Data

Tự động scan & upload tất cả file JSON CVE từ thư mục:

```bash
python scripts/batch_ingest_cve.py
# Nhập đường dẫn thư mục (VD: /data/cve_json)
# → Upload async 5 files concurrently
# → Create documents & chunks
```

**Code:** `scripts/batch_ingest_cve.py`

---

### 🔄 Batch Extract & Upsert

Extraction từ chunks và upsert vào Neo4j:

```bash
python scripts/batch_extract_upsert.py --start 1 --end 100
# --start: Chunk ID bắt đầu (default: 1)
# --end: Chunk ID kết thúc (default: 10)
```

**Output:** Chi tiết log từng chunk (success/error)

**Code:** `scripts/batch_extract_upsert.py`

---

### 🚀 Full Pipeline (Automatic)

Orchestrate toàn bộ pipeline: Ingest → Extract → Upsert:

```bash
python scripts/batch_full_pipeline_cve.py
# 1. Scan /data/cve_json
# 2. Ingest tất cả files
# 3. Extract entities per chunk
# 4. Upsert to Neo4j
# 5. Log summary results
```

**Code:** `scripts/batch_full_pipeline_cve.py`

---

## 📊 Database Schemas

### PostgreSQL

```sql
-- Documents Table
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    filename VARCHAR,
    content_type VARCHAR,
    minio_path VARCHAR UNIQUE NOT NULL,
    doc_metadata JSON,
    hash VARCHAR UNIQUE,
    chunks_count INTEGER,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Chunks Table
CREATE TABLE chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER,
    content TEXT,
    chunk_metadata JSON,
    weaviate_uuid UUID,
    hash VARCHAR UNIQUE,
    created_at TIMESTAMP
);
```

**Access:**
```bash
docker compose exec postgres psql -U graphrag_user -d pentest_graphrag
```

---

### Neo4j

**Dynamic Labels:**
```
├── Weakness (CWE weakness)
├── CWE (CWE reference)
├── VulnerabilityType (SQL Injection, XSS, ...)
├── Mitigation
├── Consequence
├── DetectionMethod
├── Platform
└── ... (any entity.type value)
```

**Node Properties:**
```
{
  id: "cwe-89",
  name: "SQL Injection",
  properties: {...},
  created_at: timestamp,
  updated_at: timestamp
}
```

**Relationships:**
```
├── :LEADS_TO (CWE → Consequence)
├── :MITIGATES (Mitigation → Weakness)
├── :HAS_CONSEQUENCE (Weakness → Consequence)
├── :RELATED_TO (Entity → Entity)
└── :MENTIONED_IN (Entity → Document)
```

**Query Examples:**
```cypher
-- Find all SQL injection related entities
MATCH (n) WHERE n.name CONTAINS "SQL Injection"
RETURN n LIMIT 20

-- Find relationships
MATCH (n)-[r]->(m) 
WHERE n.name CONTAINS "CWE"
RETURN n, r, m LIMIT 10

-- Count by type
MATCH (n) RETURN labels(n)[0] as type, count(n) as count
ORDER BY count DESC
```

**Access:**
```bash
docker compose exec neo4j cypher-shell -u neo4j -p password123
```

---

### Weaviate

**Collection:** `Chunks` (vector database)

```json
{
  "chunk_id": "uuid",
  "content": "chunk text",
  "document_id": 1,
  "_embedding": [0.1, 0.2, ...]  // vector
}
```

**Access:**
```bash
curl http://localhost:8080/v1/schema
curl -X POST http://localhost:8080/v1/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{ Get { Chunks { chunk_id content } } }"}'
```

---

## 🏗️ Project Structure

```
GraphPent/
├── app/
│   ├── main.py                    # FastAPI app entry
│   ├── config/settings.py         # Pydantic Settings (env config)
│   │
│   ├── core/
│   │   ├── logger.py              # Structlog logging
│   │   └── security.py            # Request ID, audit log
│   │
│   ├── adapters/                  # External service integrations
│   │   ├── postgres.py            # SQLAlchemy models + session
│   │   ├── neo4j_client.py        # Neo4j async driver
│   │   ├── weaviate_client.py     # Vector search client
│   │   ├── minio_client.py        # S3-compatible storage
│   │   └── llm_client.py          # Ollama LLM client
│   │
│   ├── services/                  # Business logic layer
│   │   ├── ingestion_service.py   # Phase 4: Parse + Chunk + Index
│   │   ├── extraction_service.py  # Phase 5: LLM extraction
│   │   ├── graph_service.py       # Phase 6: Neo4j upsert
│   │   ├── retriever_service.py   # Phase 7: Hybrid search
│   │   ├── report_service.py      # Phase 8: Report generation
│   │   └── tool_service.py        # Phase 9: Tool wrappers
│   │
│   ├── agents/langgraph/          # Multi-agent workflow
│   │   ├── graph.py               # LangGraph DAG
│   │   ├── state.py               # AgentState schema
│   │   └── nodes.py               # Agent node implementations
│   │
│   ├── api/v1/routers/            # REST API endpoints
│   │   ├── ingest.py              # POST /ingest/document
│   │   ├── extract.py             # POST /extract/chunk/{id}
│   │   ├── graph.py               # Graph query endpoints
│   │   ├── retrieve.py            # POST /retrieve/query
│   │   ├── workflow.py            # POST /workflow/run
│   │   ├── tools.py               # CVE/Nuclei tools
│   │   └── dashboard.py           # Metrics endpoints
│   │
│   ├── domain/schemas/            # Pydantic data models
│   │   ├── extraction.py          # Entity, Relation, ExtractionResult
│   │   ├── document.py            # Document schemas
│   │   └── pentest.py             # Pentest-specific schemas
│   │
│   └── utils/                     # Helper functions
│       ├── chunking.py            # Text chunking
│       ├── parsers.py             # PDF/DOCX/JSON parsing
│       └── helpers.py             # Utility functions
│
├── evaluation/                    # Benchmark framework
│   ├── runner.py                  # Benchmark orchestrator
│   ├── scenarios.py               # Test scenarios & queries
│   ├── metrics.py                 # Precision, Recall, NDCG, MRR
│   ├── ground_truth.py            # Ground truth data
│   └── results/                   # CSV benchmark outputs
│
├── scripts/
│   ├── batch_ingest_cve.py       # Batch upload CVE files
│   ├── batch_extract_upsert.py   # Batch extraction & graph upsert
│   ├── batch_full_pipeline_cve.py # Full pipeline orchestration
│   └── bootstrap/                 # Database initialization scripts
│       ├── postgres_init.sql
│       ├── neo4j_bootstrap.cypher
│       ├── weaviate_bootstrap.py
│       └── minio_bootstrap.py
│
├── data/
│   ├── cwec_v4.19.1.xml          # CWE XML dataset
│   ├── nvdcve-2.0-modified.json  # CVE JSON dataset
│   └── samples/                   # Sample test data
│
├── tests/                         # Unit & integration tests
│
├── docker-compose.yml             # All services (7 containers)
├── Dockerfile                     # Backend container
├── Dockerfile.ollama              # Ollama container
├── Makefile                       # Dev commands
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## � Troubleshooting

### ❌ Services không khởi động

```bash
# Kiểm tra logs chi tiết
docker compose logs <service_name> --tail 50

# Restart service
docker compose restart <service_name>

# Rebuild nếu có thay đổi
docker compose up --build <service_name> -d
```

### ❌ API trả về 500 error

```bash
# Xem backend logs
docker compose logs backend --tail 100

# Test kết nối Neo4j
docker compose exec backend python -c "
from app.adapters.neo4j_client import Neo4jAdapter
try:
    adapter = Neo4jAdapter()
    print('✅ Neo4j connected')
except Exception as e:
    print(f'❌ Neo4j error: {e}')
"

# Test kết nối PostgreSQL
docker compose exec postgres pg_isready
```

### ❌ Extraction fails

```bash
# Kiểm tra Ollama đang chạy
docker compose logs ollama --tail 20

# Kiểm tra model đã load
docker compose exec ollama ollama list

# Chạy inference test
curl -X POST http://localhost:11434/api/generate \
  -d '{"model": "llama3.2:3b", "prompt": "test"}'
```

### ❌ Memory/Storage issues

```bash
# Giảm batch size
BATCH_SIZE=5 python scripts/batch_extract_upsert.py

# Xóa logs cũ
docker compose exec backend rm logs/*

# Kiểm tra disk space
df -h
```

### ❌ Workflow endpoint 404

```bash
# Đảm bảo langgraph được cài
pip list | grep langgraph

# Kiểm tra workflow router được enable trong main.py
docker compose exec backend grep "workflow_router" app/main.py

# Restart backend
docker compose restart backend
```

---

## 🧪 Testing & Validation

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# All services status
docker compose ps

# Service-specific checks
curl http://localhost:8080/v1/.well-known/ready          # Weaviate
curl http://localhost:7474/browser/                       # Neo4j
docker compose exec postgres pg_isready                   # PostgreSQL
docker compose exec redis redis-cli ping                  # Redis
```

### API Smoke Tests

```bash
# Test ingest
curl -X POST http://localhost:8000/ingest/document \
  -F "file=@data/samples/test.json"

# Test extract
curl -X POST http://localhost:8000/extract/chunk/1

# Test retrieve
curl -X POST http://localhost:8000/retrieve/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "limit": 5}'

# Test workflow
curl -X POST http://localhost:8000/workflow/run \
  -H "Content-Type: application/json" \
  -d '{"query": "test query"}'
```

### Unit Tests

```bash
# Run all tests
docker compose exec backend python -m pytest tests/ -v

# Run specific test file
docker compose exec backend python -m pytest tests/test_extraction.py -v

# With coverage
docker compose exec backend python -m pytest tests/ --cov=app --cov-report=html
```

---

## 📊 Monitoring & Performance

### Logs Monitoring

```bash
# Real-time logs
docker compose logs -f backend

# Filter by error level
docker compose logs backend | grep ERROR

# View specific timestamp
docker compose logs backend --since 2024-04-20T10:00:00
```

### Query Performance

```bash
# Neo4j query stats
docker compose exec neo4j cypher-shell -u neo4j -p password123
> :stats on
> MATCH (n) RETURN count(n);

# PostgreSQL query analysis
docker compose exec postgres psql -U graphrag_user -d pentest_graphrag
> EXPLAIN ANALYZE SELECT * FROM documents;
```

### Resource Usage

```bash
# Monitor Docker stats
docker stats

# Check Neo4j memory
docker compose exec neo4j df -h /data

# Check Weaviate memory
docker compose exec weaviate du -sh /var/lib/weaviate
```

---

## 🔄 Data Management

### Backup

```bash
# Backup PostgreSQL
docker compose exec postgres pg_dump -U graphrag_user pentest_graphrag > backup.sql

# Backup Neo4j
docker compose exec neo4j bin/neo4j-admin database dump neo4j --to-path=/data/backups

# Backup MinIO
docker compose exec minio mc mirror minio/graphrag-bucket ./backup/minio
```

### Reset & Clean

```bash
# Stop and remove all containers & volumes
docker compose down -v

# Clean up all data
docker system prune -a --volumes

# Restart fresh
docker compose up --build -d
make bootstrap
```

### Data Import/Export

```bash
# Export Neo4j data
docker compose exec neo4j cypher-shell -u neo4j -p password123 \
  "MATCH (n) RETURN n" > graph_export.json

# Import CVE data
python scripts/batch_ingest_cve.py

# Export PostgreSQL
docker compose exec postgres pg_dump -U graphrag_user pentest_graphrag > db_export.sql
```

---

## 🔧 Development Guide

### Running Locally (Without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run with local databases (pre-configured)
python -m uvicorn app.main:app --reload --port 8000
```

### Code Style & Linting

```bash
# Format code
black app/ scripts/

# Lint
flake8 app/ --max-line-length=120

# Type checking
mypy app/ --ignore-missing-imports
```

### Adding New Router

1. Create `app/api/v1/routers/new_router.py`:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/new", tags=["New Feature"])

@router.get("/endpoint")
async def new_endpoint():
    return {"status": "success"}
```

2. Add to `app/main.py`:
```python
from app.api.v1.routers.new_router import router as new_router
app.include_router(new_router)
```

3. Test:
```bash
curl http://localhost:8000/new/endpoint
```

---

## 📈 Benchmarking & Evaluation

### Run Benchmark Suite

```bash
# Run full benchmark (5 scenarios, 3 modes, 3 runs each)
python evaluation/runner.py

# Output: evaluation/results/benchmark_results_YYYYMMDD_HHMMSS.csv
```

### Benchmark Metrics

- **Precision@K**: Fraction of top-K results that are relevant
- **Recall@K**: Fraction of all relevant results retrieved in top-K  
- **MRR**: Mean Reciprocal Rank (position of first relevant result)
- **NDCG@K**: Normalized Discounted Cumulative Gain
- **Latency**: Query response time (ms)

### Analyze Results

```bash
# View latest results
ls -la evaluation/results/ | tail -5

# Parse CSV
pandas read_csv("evaluation/results/benchmark_results_*.csv")
```

---

## 🚀 Production Deployment

### Environment Configuration

```bash
# Production .env
APP_ENV=production
LOG_LEVEL=WARNING

# Database scaling
POSTGRES_HOST=external-postgres.example.com
NEO4J_URI=bolt://external-neo4j:7687

# External cache
REDIS_URL=redis://external-redis:6379

# LLM (larger model)
OLLAMA_MODEL=llama3.2:7b

# Security
ALLOWED_TARGETS=["api.example.com", "app.example.com"]
MAX_TOOL_TIMEOUT=600
```

### Scaling Considerations

- **LLM Bottleneck:** Single Ollama instance limits throughput
  - Solution: Run multiple Ollama instances or use cloud LLM APIs
  
- **Graph Growth:** Neo4j memory can fill up with large graphs
  - Solution: Archive old data, implement retention policies
  
- **Vector Indexing:** Weaviate scaling for large collections
  - Solution: Use Weaviate cluster or sharding

### Docker Swarm / Kubernetes

```bash
# Deploy with Docker Swarm
docker stack deploy -c docker-compose.yml graphrag

# Scale backend services
docker service scale graphrag_backend=3
```

---

## 📞 Support & Community

- **Issues:** Báo cáo bugs trên GitHub Issues
- **Discussions:** Thảo luận trên GitHub Discussions  
- **Documentation:** Xem thêm `docs/` folder
- **Contributing:** Pull requests được chào đón!

---

## 📄 License

MIT License - Xem `LICENSE` file

---

**Version:** 0.2.0 (Phase 2 - Lab Stage)  
**Last Updated:** April 2026  
**Status:** ✅ Core pipeline complete | ⏳ Dashboard & full tool integration pending

## 🤝 Contributing

Chúng tôi hoan nghênh đóng góp! Vui lòng làm theo các bước:

1. Fork repository
2. Tạo feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push branch: `git push origin feature/amazing-feature`
5. Tạo Pull Request

---

## 📚 Resource Links

- **Neo4j Documentation:** https://neo4j.com/docs/
- **Weaviate Docs:** https://weaviate.io/developers/weaviate
- **LangChain/LangGraph:** https://docs.langchain.com/
- **FastAPI:** https://fastapi.tiangolo.com/
- **PostgreSQL:** https://www.postgresql.org/docs/
- **MITRE CVE:** https://cve.mitre.org/
- **MITRE CWE:** https://cwe.mitre.org/