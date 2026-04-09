# GraphRAG Pentest Platform

Nền tảng GraphRAG (Graph Retrieval-Augmented Generation) cho Penetration Testing, sử dụng kiến trúc hybrid với Neo4j graph database và Weaviate vector database.

## 📋 Tổng quan

Hệ thống này cho phép:
- **Ingest**: Upload và xử lý tài liệu (PDF, DOCX, JSON)
- **Extract**: Trích xuất entities và relationships từ văn bản
- **Graph**: Lưu trữ và truy vấn dữ liệu dưới dạng đồ thị tri thức
- **Retrieve**: Tìm kiếm hybrid (vector + graph) với fusion reranking
- **Workflow**: Multi-agent workflow tự động cho phân tích bảo mật

## 🏗️ Kiến trúc hệ thống

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI       │    │   PostgreSQL    │    │     Redis       │
│   Backend       │    │   (Metadata)    │    │   (Cache)       │
│                 │    │                 │    │                 │
│ • REST API      │    │ • Documents      │    │ • Sessions      │
│ • Async tasks   │    │ • Chunks         │    │ • Results       │
│ • Validation    │    │ • Jobs           │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │     Neo4j       │
                    │  (Graph DB)     │
                    │                 │
                    │ • Entities      │
                    │ • Relationships │
                    │ • Graph queries │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Weaviate      │
                    │ (Vector DB)     │
                    │                 │
                    │ • Embeddings    │
                    │ • Similarity    │
                    │ • Hybrid search │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │    Ollama       │
                    │    (LLM)        │
                    │                 │
                    │ • Text analysis │
                    │ • Entity ext.   │
                    │ • Summarization │
                    └─────────────────┘
```

## 🚀 Cài đặt và chạy

### Yêu cầu hệ thống

- Docker & Docker Compose
- 8GB RAM (khuyến nghị)
- 20GB dung lượng ổ cứng

### 1. Chuẩn bị môi trường

```bash
# Clone hoặc tạo thư mục project
cd GraphPent

# Copy file cấu hình
cp .env.example .env
```

### 2. Cấu hình môi trường (.env)

```bash
# Database
POSTGRES_DB=pentest_graphrag
POSTGRES_USER=graphrag_user
POSTGRES_PASSWORD=your_password_here
POSTGRES_HOST=postgres

# Neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123

# Weaviate
WEAVIATE_URL=http://weaviate:8080
WEAVIATE_API_KEY=

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_BUCKET=graphrag-bucket

# LLM
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2:3b
```

### 3. Khởi động hệ thống

```bash
# Build và chạy tất cả services
docker compose up --build -d

# Kiểm tra trạng thái
docker compose ps

# Xem logs
docker compose logs -f backend
```

### 4. Truy cập các giao diện

- **API Documentation**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474 (neo4j/password123)
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin123)
- **Weaviate**: http://localhost:8080/v1/.well-known/ready

## 📚 API Endpoints

### 🔄 Ingest (Upload tài liệu)

```bash
# Upload file
curl -X POST http://localhost:8000/ingest/document \
  -F "file=@document.pdf" \
  -F "metadata={\"source\": \"manual\"}"

# Response
{
  "document_id": 1,
  "filename": "document.pdf",
  "chunks_count": 25,
  "status": "success"
}
```

### 🔍 Extract (Trích xuất entities)

```bash
# Extract từ chunk
curl -X POST http://localhost:8000/extract/chunk/1

# Response
{
  "entities": [...],
  "relationships": [...],
  "status": "success"
}
```

### 🕸️ Graph (Đồ thị tri thức)

```bash
# Upsert entities và relationships
curl -X POST http://localhost:8000/graph/upsert \
  -H "Content-Type: application/json" \
  -d @extraction_result.json

# Query đồ thị
curl -X POST http://localhost:8000/graph/query \
  -H "Content-Type: application/json" \
  -d '{"query": "MATCH (n:CVE) RETURN n LIMIT 5"}'
```

### 🔎 Retrieve (Tìm kiếm hybrid)

```bash
# Hybrid search
curl -X POST http://localhost:8000/retrieve/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "CVE-2023-XXXX vulnerability",
    "limit": 10
  }'

# Response
{
  "results": [
    {
      "id": "cve-2023-xxxx",
      "content": "CVE: CVE-2023-XXXX...",
      "metadata": {"type": "CVE"},
      "graph_score": 0.8,
      "vector_score": 0.0,
      "final_score": 0.48
    }
  ],
  "total": 1
}
```

### 🤖 Workflow (Multi-agent)

```bash
# Chạy workflow tự động
curl -X POST http://localhost:8000/workflow/run \
  -H "Content-Type: application/json" \
  -d '{
    "query": "analyze CVE-2023-XXXX vulnerability"
  }'

# Response
{
  "status": "success",
  "final_answer": "Analysis report...",
  "retrieval_count": 5,
  "steps_completed": "end"
}
```

## 🛠️ Sử dụng nâng cao

### Batch Processing CVE Data

Script `batch_full_pipeline_cve.py` sẽ tự động scan và xử lý **tất cả file JSON CVE** trong thư mục `/data`:

1. **Tự động scan**: Tìm tất cả file `.json` trong `/data`
2. **Ingest**: Upload và chunking tài liệu
3. **Extract**: Sử dụng LLM để trích xuất entities & relations  
4. **Graph**: Upsert dữ liệu vào Neo4j knowledge graph

```bash
# Chạy batch processing cho TẤT CẢ CVE data trong /data
make batch-process

# Hoặc dùng Docker Compose
docker compose --profile batch up batch-processor

# Xem kết quả xử lý
docker compose exec backend cat batch_cve_log.json
```

**Lưu ý**: Đảm bảo file CVE JSON đã được đặt trong thư mục `data/` của project.

### Manual Data Ingestion Pipeline

```bash
# 1. Upload tài liệu
DOC_ID=$(curl -s -X POST http://localhost:8000/ingest/document \
  -F "file=@cve-data.json" | jq -r '.document_id')

# 2. Extract entities
curl -X POST http://localhost:8000/extract/chunk/$DOC_ID > extraction_result.json

# 3. Upsert vào đồ thị
curl -X POST http://localhost:8000/graph/upsert \
  -H "Content-Type: application/json" \
  -d @extraction_result.json
```

### Database Queries

```bash
# Kiểm tra documents
docker compose exec postgres psql -U graphrag_user -d pentest_graphrag -c "
SELECT id, filename, created_at FROM documents;"

# Kiểm tra graph nodes
docker compose exec neo4j cypher-shell -u neo4j -p password123 "
MATCH (n) RETURN labels(n)[0] as type, count(n) as count
ORDER BY count DESC LIMIT 5;"

# Kiểm tra vector collections
curl http://localhost:8080/v1/schema
```

## 🔧 Troubleshooting

### Service không khởi động

```bash
# Kiểm tra logs
docker compose logs <service_name>

# Restart service
docker compose restart <service_name>

# Rebuild nếu cần
docker compose up --build <service_name>
```

### API trả về lỗi 500

```bash
# Kiểm tra backend logs
docker compose logs backend --tail 50

# Test kết nối database
docker compose exec backend python -c "
from app.adapters.neo4j_client import Neo4jAdapter
adapter = Neo4jAdapter()
print('Neo4j connected')
"
```

### Workflow endpoint trả về 404

- Đảm bảo đã cài đặt `langgraph` trong requirements.txt
- Kiểm tra router được enable trong `app/main.py`
- Restart backend sau khi thay đổi

### Không tìm thấy dữ liệu

```bash
# Kiểm tra dữ liệu trong databases
docker compose exec neo4j cypher-shell -u neo4j -p password123 "MATCH (n) RETURN count(n);"
docker compose exec postgres psql -U graphrag_user -d pentest_graphrag -c "SELECT count(*) FROM documents;"
```

### Memory issues

```bash
# Tăng RAM cho Docker Desktop
# Hoặc giảm batch size trong scripts
# Hoặc chạy services riêng lẻ
docker compose up postgres neo4j backend -d
```

## 🧪 Testing

```bash
# Chạy unit tests
docker compose exec backend python -m pytest tests/

# Test API endpoints
docker compose exec backend python -c "
import requests
response = requests.get('http://localhost:8000/health')
print(response.json())
"
```

## 📊 Monitoring

### Health Checks

```bash
# Tất cả services
curl http://localhost:8000/health

# Individual services
curl http://localhost:8080/v1/.well-known/ready  # Weaviate
curl http://localhost:7474/browser/             # Neo4j
```

### Logs

```bash
# Theo dõi logs real-time
docker compose logs -f backend

# Lọc logs theo level
docker compose logs backend | grep ERROR
```

## 🚀 Production Deployment

### Environment Variables

```bash
# Production settings
APP_ENV=production
LOG_LEVEL=WARNING
OLLAMA_MODEL=llama3.2:7b  # Model lớn hơn

# Security
ALLOWED_TARGETS=["your-domain.com"]
MAX_TOOL_TIMEOUT=600
```

### Scaling

```bash
# Chạy multiple backend instances
docker compose up --scale backend=3 -d

# External databases
# Cấu hình POSTGRES_HOST, NEO4J_URI, etc. trỏ đến external DB
```

## 🤝 Contributing

1. Fork repository
2. Tạo feature branch: `git checkout -b feature/new-feature`
3. Commit changes: `git commit -am 'Add new feature'`
4. Push: `git push origin feature/new-feature`
5. Tạo Pull Request

## 📝 License

MIT License - Xem file LICENSE để biết thêm chi tiết.

## 📞 Support

- **Issues**: Tạo issue trên GitHub
- **Discussions**: Thảo luận trên GitHub Discussions
- **Documentation**: Xem docs/ folder

# Khởi động hệ thống chính
docker compose up -d

# Chạy batch processing TỰ ĐỘNG (không cần nhập gì)
make batch-process

# Hoặc dùng Docker Compose
docker compose --profile batch up batch-processor

---

**Phiên bản**: 0.2.0
**Cập nhật cuối**: April 2026

   curl -X POST http://localhost:8000/graph/upsert -H "Content-Type: application/json" -d @extraction_result.json

curl -X POST http://localhost:8000/retrieve/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "vulnerability in DVWA or SQL injection",
    "limit": 10,
    "alpha": 0.65
  }'

  curl -X POST http://localhost:8000/workflow/run \
  -H "Content-Type: application/json" \
  -d '{"query": "Tìm vulnerability SQL injection trong DVWA"}'

// View all entities
MATCH (n) RETURN n LIMIT 20
MATCH (n)-[r]->(m) RETURN n,r,m625

// Find specific vulnerabilities
MATCH (n) WHERE n.name CONTAINS "CVE" RETURN n

// Find relations
MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 10

// Search by type
MATCH (n:Container) RETURN n

curl -X POST http://localhost:8000/tools/cve/analyze \
  -H "Content-Type: application/json" \
  -d '{"cve_json": {
    "containers": {
        "cna": {
            "affected": [
                {
                    "product": "n/a",
                    "vendor": "n/a",
                    "versions": [
                        {
                            "status": "affected",
                            "version": "n/a"
                        }
                    ]
                }
            ],
            "descriptions": [
                {
                    "lang": "en",
                    "value": "ip_input.c in BSD-derived TCP/IP implementations allows remote attackers to cause a denial of service (crash or hang) via crafted packets."
                }
            ],
            "problemTypes": [
                {
                    "descriptions": [
                        {
                            "description": "n/a",
                            "lang": "en",
                            "type": "text"
                        }
                    ]
                }
            ],
            "providerMetadata": {
                "dateUpdated": "2005-12-17T00:00:00.000Z",
                "orgId": "8254265b-2729-46b6-b9e3-3dfca2d5bfca",
                "shortName": "mitre"
            },
            "references": [
                {
                    "tags": [
                        "x_refsource_CONFIRM"
                    ],
                    "url": "http://www.openbsd.org/errata23.html#tcpfix"
                },
                {
                    "name": "5707",
                    "tags": [
                        "vdb-entry",
                        "x_refsource_OSVDB"
                    ],
                    "url": "http://www.osvdb.org/5707"
                }
            ],
            "x_legacyV4Record": {
                "CVE_data_meta": {
                    "ASSIGNER": "cve@mitre.org",
                    "ID": "CVE-1999-0001",
                    "STATE": "PUBLIC"
                },
                "affects": {
                    "vendor": {
                        "vendor_data": [
                            {
                                "product": {
                                    "product_data": [
                                        {
                                            "product_name": "n/a",
                                            "version": {
                                                "version_data": [
                                                    {
                                                        "version_value": "n/a"
                                                    }
                                                ]
                                            }
                                        }
                                    ]
                                },
                                "vendor_name": "n/a"
                            }
                        ]
                    }
                },
                "data_format": "MITRE",
                "data_type": "CVE",
                "data_version": "4.0",
                "description": {
                    "description_data": [
                        {
                            "lang": "eng",
                            "value": "ip_input.c in BSD-derived TCP/IP implementations allows remote attackers to cause a denial of service (crash or hang) via crafted packets."
                        }
                    ]
                },
                "problemtype": {
                    "problemtype_data": [
                        {
                            "description": [
                                {
                                    "lang": "eng",
                                    "value": "n/a"
                                }
                            ]
                        }
                    ]
                },
                "references": {
                    "reference_data": [
                        {
                            "name": "http://www.openbsd.org/errata23.html#tcpfix",
                            "refsource": "CONFIRM",
                            "url": "http://www.openbsd.org/errata23.html#tcpfix"
                        },
                        {
                            "name": "5707",
                            "refsource": "OSVDB",
                            "url": "http://www.osvdb.org/5707"
                        }
                    ]
                }
            }
        },
        "adp": [
            {
                "providerMetadata": {
                    "orgId": "af854a3a-2127-422b-91ae-364da2661108",
                    "shortName": "CVE",
                    "dateUpdated": "2024-08-01T16:03:04.917Z"
                },
                "title": "CVE Program Container",
                "references": [
                    {
                        "tags": [
                            "x_refsource_CONFIRM",
                            "x_transferred"
                        ],
                        "url": "http://www.openbsd.org/errata23.html#tcpfix"
                    },
                    {
                        "name": "5707",
                        "tags": [
                            "vdb-entry",
                            "x_refsource_OSVDB",
                            "x_transferred"
                        ],
                        "url": "http://www.osvdb.org/5707"
                    }
                ]
            }
        ]
    },
    "cveMetadata": {
        "assignerOrgId": "8254265b-2729-46b6-b9e3-3dfca2d5bfca",
        "assignerShortName": "mitre",
        "cveId": "CVE-1999-0001",
        "datePublished": "2000-02-04T05:00:00.000Z",
        "dateReserved": "1999-06-07T00:00:00.000Z",
        "dateUpdated": "2024-08-01T16:03:04.917Z",
        "state": "PUBLISHED"
    },
    "dataType": "CVE_RECORD",
    "dataVersion": "5.1"
}}'