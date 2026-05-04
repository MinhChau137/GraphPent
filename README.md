# GraphPent — GraphRAG Penetration Testing Platform

**Phiên bản:** v0.3.0 &nbsp;|&nbsp; **Trạng thái:** Active Research &nbsp;|&nbsp; **Ngôn ngữ:** Python 3.11

> Nền tảng kiểm thử xâm nhập tự động hóa dựa trên **Graph Retrieval-Augmented Generation (GraphRAG)**, kết hợp đồ thị tri thức lai (Neo4j + Weaviate) với LLM Agent (LangGraph) để hỗ trợ phân tích CVE/CWE, dò quét mạng và sinh báo cáo bảo mật có cấu trúc.

---

## Mục lục

1. [Tổng quan & Động lực nghiên cứu](#1-tổng-quan--động-lực-nghiên-cứu)
2. [Kiến trúc hệ thống](#2-kiến-trúc-hệ-thống)
3. [Phân tích từng thành phần](#3-phân-tích-từng-thành-phần)
4. [LangGraph Multi-Agent Workflow](#4-langgraph-multi-agent-workflow)
5. [Pipeline dữ liệu (Phases 4–9)](#5-pipeline-dữ-liệu-phases-49)
6. [Hybrid Retrieval — RRF Scoring](#6-hybrid-retrieval--rrf-scoring)
7. [Cài đặt & Khởi động](#7-cài-đặt--khởi-động)
8. [Cấu hình chi tiết (.env)](#8-cấu-hình-chi-tiết-env)
9. [API Endpoints đầy đủ](#9-api-endpoints-đầy-đủ)
10. [Schema cơ sở dữ liệu](#10-schema-cơ-sở-dữ-liệu)
11. [Tối ưu hóa hệ thống (Phases 10–13)](#11-tối-ưu-hóa-hệ-thống-phases-1013)
12. [Triển khai Production](#12-triển-khai-production)
13. [Benchmark & Đánh giá](#13-benchmark--đánh-giá)
14. [Giám sát & Vận hành](#14-giám-sát--vận-hành)
15. [Troubleshooting](#15-troubleshooting)
16. [Cấu trúc dự án](#16-cấu-trúc-dự-án)

---

## 1. Tổng quan & Động lực nghiên cứu

### Vấn đề

Các hệ thống LLM agent kiểm thử xâm nhập hiện tại (PentestGPT, AutoPenBench) có hai điểm yếu cốt lõi:

| Vấn đề | Biểu hiện |
|--------|-----------|
| **Thiên kiến chiều sâu (Depth-First Bias)** | GPT-4o kiên trì theo 1 attack path qua 5 lần thất bại liên tiếp mà không chuyển hướng |
| **Mất ngữ cảnh** | Không có structured state → agent quên kết quả trước, lặp lại tác vụ đã thất bại |

Isozaki et al. (UMAP '25) đã xác nhận: thay thế cây nhiệm vụ ngôn ngữ tự nhiên bằng **structured todo list** đẩy tỉ lệ thành công Leo thang Đặc quyền từ 0% lên 100% trên easy boxes.

### Giải pháp — GraphPent

```
┌─────────────────────────────────────────────────────────┐
│              GIẢI PHÁP GRAPHPENT                        │
│                                                         │
│  PTT (PentestGPT)           AgentState (GraphPent)      │
│  ──────────────             ──────────────────────      │
│  "Find SQL injection"   →   TypedDict {                 │
│  "Try CVE-2021-..."         query, plan, current_step,  │
│  "Escalate privs"           retrieval_results,          │
│                             graph_context,              │
│  (natural language,         tool_results,               │
│   context lost after        loop_iteration, ...         │
│   few turns)                }  (deterministic,          │
│                                 persisted per node)     │
└─────────────────────────────────────────────────────────┘
```

**GraphPent** giải quyết bằng 3 đổi mới kỹ thuật:

1. **Hybrid Knowledge Graph** — Neo4j (cấu trúc quan hệ) + Weaviate (ngữ nghĩa vector) + RRF Fusion
2. **AgentState TypedDict** — trạng thái có cấu trúc, bền vững qua mọi node LangGraph
3. **Feedback Loop** — tự động re-plan khi phát hiện findings mới (tối đa 3 vòng)

---

## 2. Kiến trúc hệ thống

### Sơ đồ tổng thể

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        GRAPHPENT PLATFORM v0.3.0                        ║
╚══════════════════════════════════════════════════════════════════════════╝

  CLIENT (curl / Web UI / Script)
        │
        │  HTTP REST  (port 8000)
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      FASTAPI APPLICATION                               │
│                                                                       │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ /ingest │  │ /extract │  │/retrieve │  │/workflow │  │/nuclei │ │
│  └────┬────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───┬────┘ │
│       │             │             │              │             │      │
│  ┌────┴─────────────┴─────────────┴──────────────┴─────────────┴──┐  │
│  │                      SERVICE LAYER (21 services)               │  │
│  │  IngestionSvc  ExtractionSvc  GraphSvc  RetrieverSvc  ReportSvc│  │
│  │  JobQueueSvc   SearchSvc      GNNSvc    CollectionSvc  ...     │  │
│  └────┬──────────────────────────────────────────────────────┬────┘  │
│       │                                                      │       │
│  ┌────┴──────────────┐                        ┌─────────────┴────┐  │
│  │   AGENT LAYER     │                        │  WORKER LAYER    │  │
│  │  LangGraph DAG    │                        │  Celery Workers  │  │
│  │  (7 nodes)        │                        │  (4 concurrent)  │  │
│  └────┬──────────────┘                        └─────────────┬────┘  │
└───────┼────────────────────────────────────────────────────┼────────┘
        │                                                    │
        ▼                                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│                        ADAPTER LAYER                                  │
│                                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────┐  ┌──────────┐ │
│  │  Neo4j   │  │ Weaviate │  │PostgreSQL│  │ Redis │  │  MinIO   │ │
│  │  :7687   │  │  :8080   │  │  :5432   │  │ :6379 │  │  :9000   │ │
│  │          │  │          │  │          │  │       │  │          │ │
│  │ Knowledge│  │  Vector  │  │ Metadata │  │ Cache │  │  Object  │ │
│  │  Graph   │  │    DB    │  │ Chunks   │  │ Queue │  │ Storage  │ │
│  └──────────┘  └──────────┘  └──────────┘  └───────┘  └──────────┘ │
│                                                                       │
│  ┌──────────┐  ┌──────────────────────────┐                          │
│  │  Ollama  │  │    Elasticsearch         │                          │
│  │  :11434  │  │    (optional, Phase 5.3) │                          │
│  │ LLM+Emb  │  │    Job/Result indexing   │                          │
│  └──────────┘  └──────────────────────────┘                          │
└───────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────┐
  │                  EXTERNAL TOOLS                          │
  │   Nmap (network scan)    Nuclei (vuln scanner)          │
  └─────────────────────────────────────────────────────────┘
```

### Sơ đồ Mermaid (render trên GitHub/Obsidian)

```mermaid
graph TB
    Client([Client / Script]) --> API[FastAPI :8000]

    subgraph API_Layer["API Layer — 18 Routers"]
        API --> R1[/ingest]
        API --> R2[/extract]
        API --> R3[/retrieve]
        API --> R4[/workflow]
        API --> R5[/nuclei]
        API --> R6[/risk & /optimize]
    end

    subgraph Services["Service Layer"]
        R1 --> IngSvc[IngestionService]
        R2 --> ExtSvc[ExtractionService]
        R3 --> RetSvc[RetrieverService]
        R4 --> AgentGraph[LangGraph Agent]
        R5 --> NucleiSvc[NucleiService]
        R6 --> GNNSvc[GNNService]
    end

    subgraph DataStores["Data Stores"]
        Neo4j[(Neo4j\nKnowledge Graph)]
        Weaviate[(Weaviate\nVector DB)]
        PG[(PostgreSQL\nMetadata)]
        Redis[(Redis\nCache/Queue)]
        MinIO[(MinIO\nObject Store)]
    end

    subgraph LLM["LLM Infrastructure"]
        Ollama[Ollama\nllama3.2:3b\nnomic-embed-text]
    end

    IngSvc --> PG
    IngSvc --> MinIO
    IngSvc --> Weaviate
    ExtSvc --> Ollama
    ExtSvc --> Neo4j
    RetSvc --> Neo4j
    RetSvc --> Weaviate
    AgentGraph --> RetSvc
    AgentGraph --> GNNSvc
    AgentGraph --> NucleiSvc
    GNNSvc --> Neo4j
    NucleiSvc --> Nuclei[Nuclei Scanner]
```

---

## 3. Phân tích từng thành phần

### 3.1 FastAPI Backend

**Vì sao chọn FastAPI?**
- Native async (asyncio) — khớp với Neo4j AsyncDriver và Weaviate async client
- Pydantic v2 validation tự động cho mọi request/response schema
- OpenAPI tự động sinh → dễ test và document

**Cấu trúc router (18 routers):**

| Router | Prefix | Mục đích |
|--------|--------|----------|
| `ingest` | `/ingest` | Upload & xử lý tài liệu (PDF, DOCX, JSON, XML) |
| `extract` | `/extract` | Trích xuất entities/relations bằng Ollama LLM |
| `graph` | `/graph` | CYPHER query, schema, graph upsert |
| `retrieve` | `/retrieve` | Hybrid search (vector + graph) |
| `workflow` | `/workflow` | Multi-agent pentest workflow (LangGraph) |
| `nuclei` | `/nuclei` | Nuclei scanner — quét CVE trên live target |
| `tools` | `/tools` | CVE exploitability analysis |
| `search` | `/search` | Elasticsearch full-text & filter search |
| `job_queue` | `/jobs` | Async job management (Celery) |
| `websocket` | `/ws` | Real-time progress streaming |
| `auth` | `/auth` | JWT login, token refresh |
| `batch` | `/batch` | Batch ingest/extract/upsert |
| `export_import` | `/export` | Export/import graph & metadata |
| `collect` | `/collect` | Nmap network collection (Phase 10) |
| `kg_completion` | `/kg` | Knowledge graph completion — suy luận link mới (Phase 11) |
| `risk` | `/risk` | GNN-based risk scoring, attack paths (Phase 12) |
| `optimize` | `/optimize` | Parameter tuning — α, k, confidence (Phase 13) |
| `dashboard` | `/dashboard` | Metrics, statistics |

---

### 3.2 Neo4j — Knowledge Graph

**Vì sao Neo4j?**

Neo4j lưu trữ **quan hệ có cấu trúc** giữa các entity bảo mật: CWE → Consequence, Mitigation → Weakness, CVE → Platform. Truy vấn CYPHER với BFS/DFS traversal tìm attack chain hiệu quả hơn JOIN trên RDBMS khi graph sâu >3 hop.

**Entity types (17+):**

```
Security Knowledge Graph — Entity Taxonomy

  Weakness-based              Vulnerability
  ─────────────               ─────────────
  Weakness                    CVE
  CWE                         Vulnerability
  CWECategory
  CWEView                     Network (Phase 10)
                              ─────────────
  Mitigation-based            Host
  ─────────────               Port
  Mitigation                  Service
  MitigationStrategy
  Remediation                 Meta
                              ─────────────
  Impact-based                Reference
  ─────────────               Standard
  Consequence                 AttackVector
  Impact                      AttackPattern
                              DetectionMethod
  Scope-based                 TestCase
  ─────────────
  AffectedPlatform
  AffectedProduct
  AffectedComponent
```

**Relationship types (20+):**

```
  Mitigation:    MITIGATED_BY, HAS_MITIGATION, IMPLEMENTS_MITIGATION
  Impact:        HAS_CONSEQUENCE, CAUSES_IMPACT
  Scope:         AFFECTS, IMPACTS, TARGETS
  Hierarchy:     CHILD_OF, PARENT_OF, VARIANT_OF, PREDECESSOR_OF
  Mapping:       MAPPED_TO, REFERENCES, IMPLEMENTS, RELATED_TO
  Detection:     DETECTABLE_BY, TESTED_BY
  Chain:         PRECEDES, ENABLES, REQUIRES
  Network:       HAS_PORT, RUNS_SERVICE, EXPOSES, HOSTED_ON
```

---

### 3.3 Weaviate — Vector Database

**Vì sao Weaviate?**

Weaviate lưu vector embedding của các text chunk để tìm kiếm theo **ngữ nghĩa**. Khi user hỏi "SQL injection bypass WAF", tìm kiếm vector sẽ tìm được chunk nói về "filter evasion" dù không chứa từ khóa "bypass WAF" — điều Neo4j CYPHER không làm được.

**Collection schema:**

```
docs_chunks {
  chunk_id    : UUID
  content     : text       ← indexed for BM25 keyword search
  metadata    : object     ← document_id, chunk_index, source
  _embedding  : float[]    ← nomic-embed-text-v1.5 (768-dim)
}
```

**Hai chế độ tìm kiếm:**
- `near_text` — pure semantic (cosine similarity)
- `hybrid` — BM25 keyword + vector, controlled by `alpha` parameter

---

### 3.4 Ollama — Local LLM

**Vì sao Ollama (local)?**

- **Bảo mật**: dữ liệu CVE/pentest không gửi ra ngoài cloud
- **Chi phí**: zero API cost cho lab/research
- **Tùy chỉnh**: dễ swap model (llama3.2:3b → llama3.1:8b → Mistral)

**Hai nhiệm vụ chính:**

| Nhiệm vụ | Model | Endpoint |
|----------|-------|----------|
| Entity/Relation Extraction | llama3.2:3b | `/api/generate` |
| Text Embedding (chunk indexing) | nomic-embed-text-v1.5 | `/api/embeddings` |

**Extraction prompt strategy:**

```
System: "You are a cybersecurity knowledge extraction system.
         Extract ONLY from: Weakness, Mitigation, AffectedPlatform, Consequence.
         Relations ONLY: MITIGATED_BY, AFFECTS, HAS_CONSEQUENCE, RELATED_TO.
         Return strict JSON with confidence scores."

User:   <chunk_text>

Retry:  4 attempts, exponential backoff (5s → 40s)
```

---

### 3.5 PostgreSQL — Relational Metadata

**Vì sao PostgreSQL?**

Neo4j và Weaviate không phù hợp lưu **metadata quan hệ** (document ↔ chunks, job status, user records). PostgreSQL với SQLAlchemy ORM xử lý transactions, foreign keys, và pagination hiệu quả.

**Tables chính:**

```sql
documents   ← filename, minio_path, hash, chunks_count, created_at
chunks      ← document_id (FK), chunk_index, content, weaviate_uuid, hash
```

---

### 3.6 Redis — Cache & Job Queue

**Vì sao Redis?**

- **Cache**: lưu workflow state tạm thời (TTL 1h) cho `/workflow/multi-agent`
- **Celery Broker**: message queue cho async tasks (nuclei scan, graph upsert)
- **Session**: token blacklist cho JWT logout

---

### 3.7 MinIO — Object Storage

**Vì sao MinIO?**

Raw documents (PDF, JSON lớn) không nên lưu trong PostgreSQL BLOB. MinIO cung cấp S3-compatible API — dễ migrate sang AWS S3 hoặc Cloudflare R2 khi production.

**Bucket layout:**

```
graphrag-bucket/
├── raw/{uuid}_{filename}          ← original uploaded files
└── processed/{uuid}/chunks.json  ← chunked output (optional)
```

---

### 3.8 Celery Workers — Async Processing

**Vì sao Celery?**

Nuclei scan và graph upsert của 10.000+ chunks là long-running tasks — không thể block HTTP request. Celery cho phép:

- Submit job → trả về `job_id` ngay
- 4 workers xử lý song song
- Retry on failure với exponential backoff
- Kết quả index vào Elasticsearch (Phase 5.3) để query sau

**Task types:**

```
scan_target_async   ← Nuclei scan trên live target
process_scan_results ← Parse & store Nuclei output
upsert_to_neo4j_async ← Bulk entity/relation write
```

---

### 3.9 Elasticsearch (Phase 5.3, optional)

**Vì sao Elasticsearch?**

Neo4j full-text tốt nhưng chậm với filter phức tạp (date range + severity + status). Elasticsearch cung cấp:
- Full-text search trên job descriptions và scan results
- Aggregation: count by severity, by date
- Index lifecycle: auto-rotate cũ hơn 30 ngày

---

## 4. LangGraph Multi-Agent Workflow

### Sơ đồ DAG

```
┌─────────────────────────────────────────────────────────────────┐
│                    LANGGRAPH DAG (Phase 8 + 10)                 │
│                                                                 │
│                    ┌─────────────┐                              │
│    START ─────────►│  collection │  Nmap scan → store hosts     │
│                    │    node     │  in Neo4j (Phase 10)         │
│                    └──────┬──────┘  (skip on iteration > 0)     │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │   planner   │  Analyze query → determine   │
│                    │    node     │  stages (retrieve? tools?)   │
│                    └──────┬──────┘                              │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │  retrieval  │  HybridRetriever → RRF       │
│                    │    node     │  (Neo4j + Weaviate)          │
│                    └──────┬──────┘                              │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │   graph_    │  GNNService risk score →     │
│                    │ reasoning   │  decide: needs_tools?        │
│                    │    node     │                              │
│                    └──────┬──────┘                              │
│                           │                                     │
│            ┌──────────────┼──────────────────┐                  │
│            │ needs_tools  │                  │ no tools         │
│     ┌──────▼──────┐       │          ┌───────▼──────┐           │
│     │    tool     │       │          │    report    │           │
│     │    node     │       │          │    node      │           │
│     │  (Nuclei)   │       │          │  (Markdown)  │           │
│     └──────┬──────┘       │          └───────┬──────┘           │
│            │              │                  │                  │
│            └──────────────┘──────────────────┘                  │
│                           │                                     │
│                    ┌──────▼──────┐                              │
│                    │   human_    │  Manual review gate          │
│                    │  approval   │  new_findings_count > 0?     │
│                    │    node     │  loop_iteration < max?       │
│                    └──────┬──────┘                              │
│                           │                                     │
│              ┌────────────┴────────────┐                        │
│              │ new findings            │ no new findings        │
│              │ & iter < max            │ or iter >= max         │
│              ▼                         ▼                        │
│           planner                     END                       │
│        (next iteration)                                         │
└─────────────────────────────────────────────────────────────────┘
```

### AgentState — Trạng thái có cấu trúc

```python
class AgentState(TypedDict):
    # Input
    query: str
    user_id: str

    # Planning
    plan: str
    current_step: str

    # Data pipeline
    ingested_documents: list[dict]
    extracted_chunks: list[dict]

    # Retrieval
    retrieval_results: list[dict]
    search_mode: str           # "hybrid" | "vector" | "graph"

    # Graph
    graph_context: dict

    # Tools
    tool_results: list[dict]

    # Report
    report: dict
    report_markdown: str
    final_answer: str

    # Human-in-the-loop
    human_approval: bool
    approval_timestamp: str

    # Metadata
    workflow_id: str
    start_time: str
    end_time: str
    error: str
    error_step: str

    # Phase 10: Feedback loop
    scan_target: str
    collection_results: dict
    new_findings_count: int
    loop_iteration: int
    max_loop_iterations: int
```

**Lý do dùng TypedDict thay vì dict thông thường:**
- Type-safe: mypy/pyright bắt lỗi sai key tại compile time
- Serializable: dễ lưu vào Redis (JSON) và restore
- Explicit schema: mỗi node chỉ đọc/ghi field mình cần

---

### Mô tả từng node

| Node | Input quan trọng | Output | Lý do tồn tại |
|------|-----------------|--------|---------------|
| `collection_node` | `scan_target` | `collection_results` | Thu thập topology mạng (hosts, ports, services) — cung cấp context thực tế trước khi planner phân tích |
| `planner_node` | `query`, `collection_results` | `plan`, `current_step` | Quyết định chiến lược — có cần retrieval? có cần scan? — tránh chạy tool không cần thiết |
| `retrieval_node` | `query`, `plan` | `retrieval_results` | Truy xuất knowledge từ CVE/CWE graph + vector DB — cung cấp context cho reasoning |
| `graph_reasoning_node` | `retrieval_results`, `collection_results` | `graph_context`, `needs_tools` | GNN risk scoring — ưu tiên vuln cần scan thực tế, quyết định `needs_tools` flag |
| `tool_node` | `graph_context`, `scan_target` | `tool_results` | Chạy Nuclei scanner — xác nhận vuln có exploit được không |
| `report_node` | `tool_results`, `retrieval_results` | `report_markdown` | Tổng hợp findings thành báo cáo markdown có cấu trúc (by severity) |
| `human_approval_node` | `report_markdown` | `human_approval`, `new_findings_count` | Human-in-the-loop — reviewer xác nhận, quyết định có loop lại không |

---

## 5. Pipeline dữ liệu (Phases 4–9)

### Tổng quan flow

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Phase 4 │───►│  Phase 5 │───►│  Phase 6 │───►│  Phase 7 │───►│  Phase 8 │
│  Ingest  │    │ Extract  │    │  Graph   │    │ Retrieve │    │ Workflow │
│          │    │          │    │  Upsert  │    │  Hybrid  │    │ LangGraph│
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │               │
  Documents       Entities        Neo4j KG        RRF Results    AI Report
  Chunks          Relations       Weaviate Vec     Ranked          Markdown
  MinIO           JSON            PostgreSQL       JSON
  PostgreSQL
```

---

### Phase 4: Document Ingestion

```
  User uploads: PDF / DOCX / JSON / XML
          │
          ▼
  ┌─────────────────────────────────┐
  │  1. FORMAT DETECTION            │
  │     PyPDF2, python-docx, lxml   │
  │     → extract raw text          │
  └─────────────────┬───────────────┘
                    │
                    ▼
  ┌─────────────────────────────────┐
  │  2. CHUNKING                    │
  │     Sliding window              │
  │     chunk_size: 500 tokens      │
  │     overlap: 50 tokens          │
  └─────────────────┬───────────────┘
                    │
                    ▼
  ┌─────────────────────────────────┐
  │  3. DEDUPLICATION               │
  │     SHA256(content) → hash      │
  │     Skip if hash exists in PG   │
  └─────────────────┬───────────────┘
                    │
                    ▼
  ┌─────────────────────────────────┐
  │  4. ATOMIC STORE (3 destinations)│
  │     PostgreSQL: documents.chunks │
  │     MinIO: raw/{uuid}_{name}     │
  │     Weaviate: embed + index      │
  └─────────────────┬───────────────┘
                    │
                    ▼
  Response: { document_id, chunks_count, minio_path }
```

**Endpoint:** `POST /ingest/document` (multipart form)
**Batch:** `python scripts/batch_ingest_cve.py` — async 5 files concurrently

---

### Phase 5: Entity & Relation Extraction

```
  Input: chunk_id (from PostgreSQL)
          │
          ▼
  ┌─────────────────────────────────┐
  │  1. FETCH CHUNK                 │
  │     SELECT content FROM chunks  │
  │     WHERE id = chunk_id         │
  └─────────────────┬───────────────┘
                    │
                    ▼
  ┌─────────────────────────────────┐
  │  2. DATA TYPE DETECTION         │
  │     CWE XML → cwe extraction    │
  │     NVD JSON → cve extraction   │
  │     Generic → general security  │
  └─────────────────┬───────────────┘
                    │
                    ▼
  ┌─────────────────────────────────┐
  │  3. LLM EXTRACTION (Ollama)     │
  │     Model: llama3.2:3b          │
  │     Retry: 4x exponential       │
  │     Output: JSON {              │
  │       entities: [{              │
  │         id, type, name,         │
  │         confidence: 0.0-1.0,    │
  │         properties: {}          │
  │       }],                       │
  │       relations: [{             │
  │         source_id, target_id,   │
  │         type, confidence        │
  │       }]                        │
  │     }                           │
  └─────────────────┬───────────────┘
                    │
                    ▼
  ┌─────────────────────────────────┐
  │  4. VALIDATION & FILTERING      │
  │     Entity confidence >= 0.85   │
  │     Relation confidence >= 0.75 │
  │     Reject "unknown-entity"     │
  │     Fix CWE ID → descriptions   │
  └─────────────────┬───────────────┘
                    │
                    ▼
  Response: ExtractionResult { entities[], relations[] }
```

**Endpoint:** `POST /extract/chunk/{id}`

---

### Phase 6: Graph Upsert (Neo4j)

```
  Input: ExtractionResult
          │
          ▼
  ┌─────────────────────────────────────────────────┐
  │  CYPHER MERGE — Idempotent Upsert               │
  │                                                 │
  │  MERGE (n:Weakness {id: $id})                   │
  │    ON CREATE SET                                │
  │      n.name = $name,                            │
  │      n.created_at = timestamp()                 │
  │    ON MATCH SET                                 │
  │      n.updated_at = timestamp()                 │
  │                                                 │
  │  Chạy trong transaction (batch)                 │
  │  Retry: 3x exponential backoff                  │
  └─────────────────┬───────────────────────────────┘
                    │
                    ▼
  ┌─────────────────────────────────────────────────┐
  │  RELATIONSHIP CREATION                          │
  │                                                 │
  │  MATCH (src {id: $source_id})                   │
  │  MATCH (tgt {id: $target_id})                   │
  │  MERGE (src)-[r:$TYPE]->(tgt)                   │
  │  SET r.confidence = $confidence,                │
  │      r.source_chunk_id = $chunk_id,             │
  │      r.created_at = timestamp()                 │
  └─────────────────┬───────────────────────────────┘
                    │
                    ▼
  Response: { entities_upserted, relations_created }
```

---

### Phase 7: Hybrid Retrieval (RRF)

```
  Query: "SQL injection bypass authentication"
          │
    ┌─────┴──────┐
    │            │
    ▼            ▼
  ┌─────────┐  ┌────────────────────┐
  │ VECTOR  │  │   GRAPH SEARCH     │
  │ SEARCH  │  │                    │
  │         │  │ 1. Full-text index │
  │ Embed   │  │    (Lucene/Neo4j)  │
  │ query   │  │ 2. BFS expansion   │
  │ → cosine│  │    max 4 hops      │
  │ sim top-│  │ 3. Return nodes +  │
  │ K       │  │    relationships   │
  └────┬────┘  └────────┬───────────┘
       │                │
       ▼                ▼
  [V1:0.92, V2:0.88,  [G1, G2, G3, G4, G5...]
   V3:0.81, ...]
       │                │
       └────────┬───────┘
                │
                ▼
  ┌───────────────────────────────────────────┐
  │       RECIPROCAL RANK FUSION (RRF)        │
  │                                           │
  │  score(d) = α · RRF_graph(d)              │
  │           + (1-α) · RRF_vec(d)            │
  │                                           │
  │  RRF_x(d) = 1 / (k + rank_x(d))          │
  │                                           │
  │  Default: α = 0.7, k = 60.0              │
  │  (Graph-biased: cấu trúc quan trọng hơn  │
  │   với CVE/CWE có hierarchy rõ ràng)       │
  └───────────────────┬───────────────────────┘
                      │
                      ▼
  Final: Top-N results ranked by RRF score
         { chunk_id, content, score, source }
```

**Endpoint:** `POST /retrieve/query`
**Parameters:** `query`, `limit` (default 10), `alpha` (0.0–1.0), `mode` (hybrid/vector/graph)

---

### Phase 8–9: Workflow & Tools

```
  POST /workflow/multi-agent {
    query: "Scan 192.168.1.100 for CVE vulnerabilities",
    scan_target: "192.168.1.100",
    max_loop_iterations: 3
  }
          │
          ▼
  LangGraph DAG execution (7 nodes, see Section 4)
          │
          ▼
  Response: {
    workflow_id: "uuid",
    status: "completed",
    final_answer: "...",
    retrieval_results: [...],
    tool_results: [...],          ← Nuclei scan output
    report: { markdown: "..." },
    collection_summary: { hosts, ports, services },
    loop_iterations: 2,
    latency_ms: 4200
  }
```

---

## 6. Hybrid Retrieval — RRF Scoring

### Tại sao hybrid tốt hơn đơn lẻ?

| Phương pháp | Điểm mạnh | Điểm yếu |
|-------------|-----------|----------|
| Vector only | Tìm ngữ nghĩa tương tự ("WAF bypass" → "filter evasion") | Bỏ qua cấu trúc quan hệ CWE hierarchy |
| Graph only | Theo dõi chain CWE → Consequence → Mitigation chính xác | Miss các chunk không có entity được extract |
| **Hybrid RRF** | Kết hợp cả hai, rank theo tổng hợp | Cần tune α cho từng domain |

### Công thức RRF

```
score(d) = α × [1 / (k + rank_graph(d))]
         + (1-α) × [1 / (k + rank_vec(d))]

Trong đó:
  α = 0.7        ← trọng số cho graph (bias về cấu trúc)
  k = 60.0       ← hằng số RRF (tránh overfit vị trí 1)
  rank_x(d)      ← thứ hạng của document d trong kết quả x
```

### Kết quả benchmark (NDCG@10)

| Mode | NDCG@10 | Latency p95 |
|------|---------|-------------|
| Vector only | 0.08 | 45ms |
| Graph only | 0.07 | 62ms |
| **Hybrid α=0.7** | **0.11** | **70ms** |

---

## 7. Cài đặt & Khởi động

### Yêu cầu hệ thống

| Tài nguyên | Tối thiểu | Khuyến nghị |
|------------|-----------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16 GB (Ollama cần 4-6GB) |
| Disk | 20 GB | 50 GB+ (CVE dataset lớn) |
| GPU | Không bắt buộc | NVIDIA (tăng tốc Ollama) |
| OS | Linux/macOS/Windows (WSL2) | Ubuntu 22.04 LTS |
| Docker | 24.0+ | 24.0+ |
| Docker Compose | 2.20+ | 2.24+ |

### Bước 1 — Clone & chuẩn bị

```bash
git clone <repo-url> GraphPent
cd GraphPent

# Tạo file cấu hình
cp .env.example .env
```

### Bước 2 — Cấu hình .env

Xem chi tiết tại [Mục 8](#8-cấu-hình-chi-tiết-env). Cấu hình tối thiểu cần đổi:

```bash
# Bắt buộc đổi cho production
POSTGRES_PASSWORD=<strong-password>
NEO4J_PASSWORD=<strong-password>
MINIO_ROOT_PASSWORD=<strong-password>
JWT_SECRET_KEY=<random-256-bit-hex>

# Target whitelist (thêm IP lab của bạn)
ALLOWED_TARGETS=["127.0.0.1","localhost","192.168.1.100"]
```

### Bước 3 — Khởi động

```bash
# Build & start tất cả services (lần đầu ~5-10 phút pull images)
make up

# Hoặc thủ công:
docker compose up --build -d

# Theo dõi logs startup
docker compose logs -f backend ollama
```

### Bước 4 — Bootstrap dữ liệu

```bash
# Khởi tạo schema PostgreSQL + Neo4j indexes + Weaviate collections
make bootstrap

# Hoặc từng bước:
docker compose exec backend python scripts/bootstrap/postgres_init.sql
docker compose exec neo4j cypher-shell -f /var/lib/neo4j/scripts/neo4j_bootstrap.cypher
docker compose exec backend python scripts/bootstrap/weaviate_bootstrap.py
```

### Bước 5 — Pull Ollama models

```bash
# Kéo model LLM (llama3.2:3b ~2GB)
docker compose exec ollama ollama pull llama3.2:3b

# Kéo embedding model (~300MB)
docker compose exec ollama ollama pull nomic-embed-text

# Kiểm tra
docker compose exec ollama ollama list
```

### Bước 6 — Kiểm tra hoạt động

```bash
# Health check
curl http://localhost:8000/health

# Kiểm tra tất cả services
docker compose ps

# Xem logs backend
docker compose logs backend --tail 50
```

### Các URL truy cập

| Service | URL | Credentials |
|---------|-----|-------------|
| **GraphPent API** | http://localhost:8000 | — |
| **Swagger UI** | http://localhost:8000/docs | — |
| **ReDoc** | http://localhost:8000/redoc | — |
| **Neo4j Browser** | http://localhost:7474 | neo4j / (NEO4J_PASSWORD) |
| **MinIO Console** | http://localhost:9001 | (MINIO_ROOT_USER/PASSWORD) |
| **Weaviate** | http://localhost:8080 | anonymous |
| **Ollama** | http://localhost:11434 | — |

---

## 8. Cấu hình chi tiết (.env)

```bash
# ─── Application ─────────────────────────────────────────────────────────────
APP_ENV=development          # development | production
LOG_LEVEL=INFO               # DEBUG | INFO | WARNING | ERROR
APP_NAME=graphpent

# ─── PostgreSQL ───────────────────────────────────────────────────────────────
POSTGRES_DB=pentest_graphrag
POSTGRES_USER=graphrag_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_HOST=postgres        # docker service name
POSTGRES_PORT=5432

# ─── Redis ────────────────────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ─── Neo4j ────────────────────────────────────────────────────────────────────
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
# NEO4J_MAX_POOL_SIZE=50     # tăng cho high concurrency

# ─── Weaviate ─────────────────────────────────────────────────────────────────
WEAVIATE_HOST=weaviate
WEAVIATE_PORT=8080
WEAVIATE_GRPC_PORT=50051
WEAVIATE_URL=http://weaviate:8080
WEAVIATE_API_KEY=            # để trống = anonymous (lab)

# ─── MinIO ────────────────────────────────────────────────────────────────────
MINIO_ENDPOINT=minio:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_BUCKET=graphrag-bucket

# ─── Ollama / LLM ─────────────────────────────────────────────────────────────
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2:3b              # hoặc llama3.1:8b, mistral:7b
EMBEDDING_MODEL=nomic-embed-text-v1.5

# ─── Elasticsearch (Phase 5.3, optional) ─────────────────────────────────────
ELASTICSEARCH_HOSTS=http://elasticsearch:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=

# ─── Nuclei Scanner ───────────────────────────────────────────────────────────
NUCLEI_ENDPOINT=http://nuclei-service:8080
NUCLEI_TIMEOUT=300

# ─── Security ─────────────────────────────────────────────────────────────────
JWT_SECRET_KEY=your-256-bit-secret-hex
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=60
ALLOWED_TARGETS=["127.0.0.1","localhost","192.168.1.100","dvwa.local"]
MAX_TOOL_TIMEOUT=300
RATE_LIMIT_PER_MIN=30

# ─── Hybrid Retrieval (Phase 7, tunable) ──────────────────────────────────────
RRF_ALPHA=0.7                # 0.0=pure vector, 1.0=pure graph
RRF_K=60.0                   # RRF constant (default 60)

# ─── Extraction Confidence Gates (Phase 5) ────────────────────────────────────
ENTITY_CONFIDENCE_THRESHOLD=0.85
RELATION_CONFIDENCE_THRESHOLD=0.75

# ─── KG Completion (Phase 11) ─────────────────────────────────────────────────
KG_COMPLETION_MIN_CONFIDENCE=0.65
KG_COMPLETION_MAX_DEGREE=2

# ─── GNN Risk Scoring (Phase 12) ──────────────────────────────────────────────
GNN_PAGERANK_WEIGHT=0.50     # tầm quan trọng trong graph
GNN_SEVERITY_WEIGHT=0.30     # CVSS score contribution
GNN_BETWEENNESS_WEIGHT=0.20  # bottleneck node contribution

# ─── Workflow (Phase 10) ──────────────────────────────────────────────────────
MAX_LOOP_ITERATIONS=3        # số vòng feedback loop tối đa
NMAP_OPTIONS=-sV -sC -O --script vuln
ATTACK_PATH_MAX_HOPS=4
```

---

## 9. API Endpoints đầy đủ

### Core Pipeline

```bash
# Phase 4: Ingest document
POST /ingest/document
Content-Type: multipart/form-data
Body: file=@data/nvdcve-2.0-modified.json

# Phase 5: Extract entities from chunk
POST /extract/chunk/{chunk_id}

# Phase 6: Execute Cypher query
POST /graph/query
{ "query": "MATCH (n:Weakness) RETURN n LIMIT 20" }

# Phase 7: Hybrid retrieval
POST /retrieve/query
{
  "query": "SQL injection authentication bypass",
  "limit": 10,
  "alpha": 0.7,
  "mode": "hybrid"
}

# Phase 8: Run multi-agent pentest workflow
POST /workflow/multi-agent
{
  "query": "Find critical vulnerabilities on target",
  "user_id": "analyst-01",
  "scan_target": "192.168.1.100",
  "max_loop_iterations": 3
}
```

### Advanced Endpoints

```bash
# Async job submission (Phase 5.1)
POST /jobs/submit
{ "job_type": "NUCLEI_SCAN", "target_url": "http://192.168.1.100", "priority": 5 }

GET /jobs/{job_id}/status

# WebSocket real-time progress (Phase 5.2)
WS /ws/workflow/{workflow_id}

# Advanced search with filters (Phase 5.3)
POST /search/advanced
{ "query": "CVE-2024", "filters": { "severity": "critical", "year": 2024 } }

# Batch operations (Phase 5.5)
POST /batch/extract
{ "chunk_ids": [1, 2, 3, 4, 5], "batch_size": 5 }

# Export graph data (Phase 5.6)
GET /export/graph?format=json&entity_types=Weakness,CVE

# Network collection / Nmap scan (Phase 10)
POST /collect/scan
{ "target": "192.168.1.0/24", "options": "-sV -sC" }

# KG completion — infer missing relationships (Phase 11)
POST /kg/complete
{ "entity_id": "cwe-89", "max_degree": 2 }

# Risk scoring & attack path (Phase 12)
POST /risk/score
{ "entity_ids": ["cwe-89", "cwe-352"] }

GET /risk/attack-path?from=cwe-89&to=Host:192.168.1.100&max_hops=4

# Parameter optimization (Phase 13)
POST /optimize/rrf
{ "alpha": 0.7, "k": 60, "test_queries": ["SQL injection", "XSS"] }
```

### System Endpoints

```bash
GET /health           # Liveness check
GET /config           # Safe config exposure (không lộ secrets)
GET /dashboard/stats  # Tổng số entities, relations, chunks, documents
```

---

## 10. Schema cơ sở dữ liệu

### PostgreSQL

```sql
-- Documents: metadata của file đã upload
CREATE TABLE documents (
    id            SERIAL PRIMARY KEY,
    filename      VARCHAR(500),
    content_type  VARCHAR(100),
    minio_path    VARCHAR(1000) UNIQUE NOT NULL,  -- s3://bucket/raw/...
    doc_metadata  JSON,
    hash          VARCHAR(64) UNIQUE,             -- SHA256, dedup
    chunks_count  INTEGER DEFAULT 0,
    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW()
);

-- Chunks: text segment được index vào Weaviate
CREATE TABLE chunks (
    id            SERIAL PRIMARY KEY,
    document_id   INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index   INTEGER NOT NULL,
    content       TEXT NOT NULL,
    chunk_metadata JSON,
    weaviate_uuid UUID,                           -- reference to Weaviate object
    hash          VARCHAR(64) UNIQUE,             -- SHA256, dedup
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_weaviate ON chunks(weaviate_uuid);
```

### Neo4j

```cypher
-- Tạo fulltext index cho keyword search
CREATE FULLTEXT INDEX entity_text FOR (n:Weakness|CWE|CVE|Mitigation)
ON EACH [n.name, n.description];

-- Tạo B-tree index cho lookup theo ID
CREATE INDEX entity_id FOR (n:Weakness) ON (n.id);

-- Ví dụ node
(n:Weakness {
  id: "cwe-89",
  name: "Improper Neutralization of Special Elements in SQL Command",
  description: "...",
  severity: "high",
  created_at: datetime("2024-01-01T00:00:00"),
  updated_at: datetime("2024-06-15T10:30:00")
})

-- Ví dụ relationship với provenance
(n:Weakness)-[r:HAS_CONSEQUENCE {
  confidence: 0.92,
  source_chunk_id: 1042,
  created_at: datetime("2024-01-01T00:00:00")
}]->(m:Consequence {id: "consequence-auth-bypass"})

-- Query hữu ích
-- Tìm tất cả mitigations cho SQL Injection
MATCH (w:Weakness {id: "cwe-89"})-[:MITIGATED_BY]->(m:Mitigation)
RETURN m.name, m.description;

-- Attack chain từ weakness đến consequence (max 4 hops)
MATCH path = (w:Weakness)-[*1..4]->(c:Consequence)
WHERE w.name CONTAINS "SQL"
RETURN path LIMIT 10;

-- Đếm theo loại entity
MATCH (n)
RETURN labels(n)[0] AS type, count(n) AS count
ORDER BY count DESC;

-- Network topology (Phase 10)
MATCH (h:Host)-[:HAS_PORT]->(p:Port)-[:RUNS_SERVICE]->(s:Service)
RETURN h.ip, p.number, s.name;
```

### Weaviate

```json
{
  "class": "docs_chunks",
  "vectorizer": "none",
  "properties": [
    { "name": "chunk_id",    "dataType": ["text"] },
    { "name": "content",     "dataType": ["text"],   "tokenization": "word" },
    { "name": "document_id", "dataType": ["int"] },
    { "name": "chunk_index", "dataType": ["int"] },
    { "name": "source",      "dataType": ["text"] }
  ]
}
```

Embedding được sinh bởi Ollama (`nomic-embed-text-v1.5`, 768-dim) và truyền vào qua API `vectors` parameter.

---

## 11. Tối ưu hóa hệ thống (Phases 10–13)

### Phase 10 — Network Collection & Feedback Loop

```
Thêm Nmap vào đầu workflow:
  scan_target → collection_node → lưu Host/Port/Service vào Neo4j
  → planner có context về topology thực tế → reasoning chính xác hơn

Feedback loop:
  Sau mỗi cycle: đếm new_findings_count
  Nếu > 0 VÀ loop_iteration < max_loop_iterations:
    → quay lại planner với context mới
  Mặc định: max 3 vòng (tránh infinite loop)
```

**Tham số:**
```bash
MAX_LOOP_ITERATIONS=3
NMAP_OPTIONS=-sV -sC -O --script vuln
ATTACK_PATH_MAX_HOPS=4
```

---

### Phase 11 — Knowledge Graph Completion

```
Bài toán: KG có các "missing link" — entity A và C liên quan
          nhưng không có edge trực tiếp A→C

Giải pháp: Link prediction dựa trên neighborhood similarity
  1. Lấy neighbors của entity A (depth 1-2)
  2. Lấy neighbors của entity C (depth 1-2)
  3. Tính Jaccard similarity của neighbor sets
  4. Nếu similarity > min_confidence (0.65):
     → tạo edge RELATED_TO với confidence score

Ứng dụng: Suy luận "CVE-2024-XXXX AFFECTS CWECategory-X"
          khi chưa có label trực tiếp nhưng có path gián tiếp
```

**Tham số:**
```bash
KG_COMPLETION_MIN_CONFIDENCE=0.65
KG_COMPLETION_MAX_DEGREE=2
```

---

### Phase 12 — GNN Risk Scoring

```
Mục tiêu: Ưu tiên vulnerability nào cần scan thực tế
          (không scan tất cả → tiết kiệm thời gian)

Công thức risk score:
  risk(v) = w_pr  × pagerank(v)       ← tầm quan trọng trong KG
           + w_sev × normalized_cvss(v) ← CVSS severity
           + w_bet × betweenness(v)    ← bottleneck (nhiều path qua đây)

Mặc định:
  w_pr  = 0.50
  w_sev = 0.30
  w_bet = 0.20

Output: Ranked list vulnerabilities → tool_node chỉ scan top-K
```

**API:**
```bash
POST /risk/score
{ "entity_ids": ["cve-2024-1234", "cwe-89"] }

# Response:
{
  "scores": [
    { "id": "cve-2024-1234", "risk_score": 0.87, "pagerank": 0.92, "cvss": 9.8 },
    { "id": "cwe-89",        "risk_score": 0.71, "pagerank": 0.65, "cvss": 8.1 }
  ]
}
```

---

### Phase 13 — Parameter Optimization

```
Vấn đề: α=0.7 tốt nhất cho CWE/CVE nhưng có thể khác với network scan data

Giải pháp: Grid search trên tập test queries:
  for α in [0.3, 0.5, 0.7, 0.9]:
    for k in [30, 60, 100]:
      score = evaluate_ndcg(alpha=α, k=k, queries=test_queries)
  return best(α, k)

Endpoint:
  POST /optimize/rrf
  { "alpha_range": [0.3, 0.9], "k_range": [30, 100], "test_queries": [...] }
```

---

## 12. Triển khai Production

### Docker Compose (9 services)

```yaml
# docker-compose.yml — services overview
services:
  postgres:16-alpine    ← Primary RDBMS, init scripts, health check
  redis:7-alpine        ← Cache + Celery message broker
  neo4j:5.20.0-community← Graph DB, APOC plugin, 4GB heap
  weaviate:1.26.1       ← Vector store, gRPC :50051 + REST :8080
  minio:latest          ← S3-compatible, console :9001
  ollama:latest         ← LLM inference, GPU passthrough
  backend               ← FastAPI app :8000, depends_on all above
  celery_worker         ← 4 concurrent async workers
  batch-processor       ← profile: batch (chạy riêng khi cần)
```

### Makefile commands

```bash
make up               # docker compose up --build -d
make down             # docker compose down
make restart          # down + up
make clean            # down -v (xóa volumes!)
make health           # curl health check all services
make bootstrap        # khởi tạo schema tất cả databases
make test             # pytest
make test-coverage    # pytest --cov với HTML report
make load-sample      # ingest sample CVE data
```

### Môi trường Production

```bash
# .env production overrides
APP_ENV=production
LOG_LEVEL=WARNING

# External databases (thay Docker containers)
POSTGRES_HOST=db.internal.company.com
NEO4J_URI=bolt://graph.internal.company.com:7687
REDIS_URL=redis://cache.internal.company.com:6379/0

# Larger LLM model
OLLAMA_MODEL=llama3.1:8b

# Security tightening
RATE_LIMIT_PER_MIN=10
JWT_EXPIRY_MINUTES=30
ALLOWED_TARGETS=["pentest-lab.company.com", "192.168.10.0/24"]
```

### Scaling

| Bottleneck | Triệu chứng | Giải pháp |
|------------|-------------|-----------|
| Ollama LLM | Extraction queue tăng | Chạy 2 Ollama instance trên port khác nhau + load balance |
| Neo4j heap | OOM khi graph > 5M nodes | Tăng `NEO4J_HEAP_INITIAL_SIZE`, `NEO4J_HEAP_MAX_SIZE` |
| Weaviate | Slow vector search > 1M vectors | Sharding hoặc HNSW parameter tuning |
| Backend | CPU high khi nhiều workflow | `docker service scale graphpent_backend=3` (Swarm) |
| Celery | Job queue backlog | Tăng `--concurrency` từ 4 lên 8 |

### Backup & Recovery

```bash
# PostgreSQL backup
docker compose exec postgres pg_dump \
  -U graphrag_user pentest_graphrag \
  > backup/postgres_$(date +%Y%m%d).sql

# Neo4j backup (community edition — offline dump)
docker compose stop neo4j
docker compose exec neo4j \
  bin/neo4j-admin database dump neo4j --to-path=/data/backups
docker compose start neo4j

# MinIO sync
docker compose exec minio \
  mc mirror minio/graphrag-bucket ./backup/minio_$(date +%Y%m%d)/

# Restore PostgreSQL
docker compose exec -T postgres psql \
  -U graphrag_user -d pentest_graphrag < backup/postgres_20260501.sql
```

---

## 13. Benchmark & Đánh giá

### Framework đánh giá

```bash
# Chạy full benchmark suite
python evaluation/runner.py

# Output: evaluation/results/benchmark_results_YYYYMMDD_HHMMSS.csv
```

### Metrics

| Metric | Ý nghĩa | Cách tính |
|--------|---------|-----------|
| **Precision@K** | Tỷ lệ kết quả top-K đúng | TP@K / K |
| **Recall@K** | Tỷ lệ tổng số relevant được tìm ra | TP@K / total_relevant |
| **MRR** | Vị trí kết quả đúng đầu tiên | mean(1/rank_first_relevant) |
| **NDCG@K** | Chất lượng ranking (xét vị trí) | DCG@K / IDCG@K |
| **Latency p95** | 95th percentile response time | ms |

### Kết quả hiện tại

| Scenario | Mode | Precision@5 | NDCG@10 | Latency p95 |
|----------|------|------------|---------|-------------|
| CWE hierarchy | Hybrid α=0.7 | 0.82 | 0.11 | 70ms |
| CVE keyword | Hybrid α=0.7 | 0.79 | 0.10 | 68ms |
| Attack chain | Graph only | 0.85 | 0.13 | 85ms |
| Semantic query | Vector only | 0.74 | 0.09 | 45ms |
| **Decision Accuracy (workflow)** | **Hybrid** | **100%** | — | — |

### Chạy evaluation tùy chỉnh

```bash
# Evaluate chỉ retrieval
python evaluation/runner.py --mode retrieval --scenarios cwe_hierarchy,cve_lookup

# Evaluate workflow end-to-end
python evaluation/runner.py --mode workflow --target 127.0.0.1

# Phân tích kết quả
python -c "
import pandas as pd
df = pd.read_csv('evaluation/results/benchmark_results_latest.csv')
print(df.groupby('mode')[['ndcg_10','precision_5','latency_p95']].mean())
"
```

---

## 14. Giám sát & Vận hành

### Health checks

```bash
# GraphPent API
curl http://localhost:8000/health

# Neo4j
curl http://localhost:7474/db/data/

# Weaviate
curl http://localhost:8080/v1/.well-known/ready

# PostgreSQL
docker compose exec postgres pg_isready -U graphrag_user

# Redis
docker compose exec redis redis-cli ping

# Ollama
curl http://localhost:11434/api/tags
```

### Logs

```bash
# Real-time logs
docker compose logs -f backend

# Filter errors
docker compose logs backend | grep "ERROR\|CRITICAL"

# Logs từ thời điểm cụ thể
docker compose logs backend --since "2026-05-01T08:00:00"

# Tất cả services
docker compose logs --tail 100
```

### Resource monitoring

```bash
# CPU/Memory tất cả containers
docker stats

# Neo4j disk
docker compose exec neo4j df -h /data

# Weaviate data size
docker compose exec weaviate du -sh /var/lib/weaviate

# PostgreSQL table sizes
docker compose exec postgres psql -U graphrag_user -d pentest_graphrag \
  -c "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) 
      FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;"
```

### Prometheus metrics (nếu bật)

```bash
# Metric endpoint
curl http://localhost:8000/metrics

# Key metrics exposed:
# graphpent_request_duration_seconds{endpoint}
# graphpent_neo4j_query_duration_seconds
# graphpent_weaviate_search_duration_seconds
# graphpent_extraction_total{status}
# graphpent_workflow_loop_iterations
```

---

## 15. Troubleshooting

### Services không khởi động

```bash
# Xem logs chi tiết
docker compose logs <service> --tail 100

# Rebuild service
docker compose up --build <service> -d

# Restart service
docker compose restart <service>

# Kiểm tra port conflict
netstat -tlnp | grep "8000\|7687\|8080\|5432\|6379"
```

### Neo4j connection failed

```bash
# Test kết nối
docker compose exec backend python -c "
from app.adapters.neo4j_client import Neo4jAdapter
import asyncio
async def test():
    a = Neo4jAdapter()
    result = await a.run_query('RETURN 1 as n')
    print('OK:', result)
asyncio.run(test())
"

# Kiểm tra Neo4j logs
docker compose logs neo4j --tail 50

# Thường gặp: NEO4J_PASSWORD không khớp với volume đã tạo trước
# Fix: docker compose down -v && docker compose up -d
```

### Extraction fails (Ollama)

```bash
# Kiểm tra Ollama
docker compose logs ollama --tail 30

# Kiểm tra model đã load
docker compose exec ollama ollama list

# Test inference thủ công
curl -X POST http://localhost:11434/api/generate \
  -d '{"model": "llama3.2:3b", "prompt": "What is SQL injection?", "stream": false}'

# Nếu model chưa có
docker compose exec ollama ollama pull llama3.2:3b
```

### Weaviate embedding lỗi

```bash
# Kiểm tra embedding endpoint
curl -X POST http://localhost:11434/api/embeddings \
  -d '{"model": "nomic-embed-text", "prompt": "test"}'

# Kiểm tra Weaviate schema
curl http://localhost:8080/v1/schema

# Xóa và tạo lại collection
curl -X DELETE http://localhost:8080/v1/schema/docs_chunks
docker compose exec backend python scripts/bootstrap/weaviate_bootstrap.py
```

### Workflow endpoint 404

```bash
# Kiểm tra router được register
docker compose exec backend python -c "
from app.main import app
routes = [r.path for r in app.routes]
print([r for r in routes if 'workflow' in r])
"

# Kiểm tra LangGraph cài đặt
docker compose exec backend pip show langgraph
```

### Out of memory

```bash
# Giảm concurrency Celery
# Trong docker-compose.yml, đổi:
# command: celery -A app.workers worker --concurrency=2

# Giảm Neo4j heap
# NEO4J_HEAP_INITIAL_SIZE=512m
# NEO4J_HEAP_MAX_SIZE=2G

# Dùng model nhỏ hơn
# OLLAMA_MODEL=llama3.2:1b
```

---

## 16. Cấu trúc dự án

```
GraphPent/
├── app/
│   ├── main.py                         # FastAPI app, 18 routers, lifespan
│   ├── config/
│   │   └── settings.py                 # Pydantic BaseSettings, .env loader
│   │
│   ├── adapters/                        # External service clients
│   │   ├── postgres.py                  # SQLAlchemy ORM models + async session
│   │   ├── neo4j_client.py              # Neo4j AsyncDriver, MERGE upsert, retry
│   │   ├── weaviate_client.py           # Weaviate v4 client, embedding, upsert
│   │   ├── elasticsearch_client.py      # ES client, index management (Phase 5.3)
│   │   ├── llm_client.py               # Ollama extraction + embedding
│   │   ├── minio_client.py             # S3-compatible object storage
│   │   ├── nmap_adapter.py             # Nmap subprocess wrapper (Phase 10)
│   │   └── nuclei_parser/              # Nuclei output parsing
│   │       ├── nuclei_parser.py
│   │       ├── models.py
│   │       └── base.py
│   │
│   ├── agents/langgraph/               # Multi-agent workflow
│   │   ├── graph.py                    # LangGraph DAG definition (7 nodes)
│   │   ├── state.py                    # AgentState TypedDict
│   │   └── nodes.py                    # Node implementations (async functions)
│   │
│   ├── api/v1/routers/                 # REST API (18 routers)
│   │   ├── ingest.py                   # POST /ingest/document
│   │   ├── extract.py                  # POST /extract/chunk/{id}
│   │   ├── graph.py                    # Graph CYPHER queries
│   │   ├── retrieve.py                 # Hybrid search
│   │   ├── workflow.py                 # Multi-agent workflow
│   │   ├── nuclei.py                   # Nuclei scanner API
│   │   ├── tools.py                    # CVE analysis tools
│   │   ├── search.py                   # ES search + filters (Phase 5.3)
│   │   ├── job_queue.py                # Celery job management (Phase 5.1)
│   │   ├── websocket.py                # WebSocket streaming (Phase 5.2)
│   │   ├── auth.py                     # JWT auth (Phase 5.4)
│   │   ├── batch.py                    # Batch operations (Phase 5.5)
│   │   ├── export_import.py            # Export/import (Phase 5.6)
│   │   ├── collect.py                  # Nmap collection (Phase 10)
│   │   ├── kg_completion.py            # KG completion (Phase 11)
│   │   ├── risk.py                     # GNN risk scoring (Phase 12)
│   │   ├── optimize.py                 # Parameter tuning (Phase 13)
│   │   └── dashboard.py               # Metrics
│   │
│   ├── services/                       # Business logic (21 modules)
│   │   ├── ingestion_service.py        # Phase 4: parse, chunk, index
│   │   ├── extraction_service.py       # Phase 5: LLM extract + validate
│   │   ├── graph_service.py            # Phase 6: Neo4j upsert
│   │   ├── retriever_service.py        # Phase 7: RRF hybrid search
│   │   ├── pentest_orchestrator.py     # Phase 8: workflow coordination
│   │   ├── report_service.py           # Markdown report generation
│   │   ├── tool_service.py             # Nuclei tool wrapper
│   │   ├── gnn_service.py              # GNN risk scoring (Phase 12)
│   │   ├── collection_service.py       # Nmap + graph store (Phase 10)
│   │   ├── kg_completion_service.py    # Link prediction (Phase 11)
│   │   ├── optimization_service.py     # Grid search tuning (Phase 13)
│   │   ├── search_service.py           # ES search (Phase 5.3)
│   │   ├── job_queue_service.py        # Celery job submission (Phase 5.1)
│   │   ├── websocket_manager.py        # WS connection manager (Phase 5.2)
│   │   ├── auth_service.py             # JWT + bcrypt (Phase 5.4)
│   │   ├── batch_service.py            # Batch orchestration (Phase 5.5)
│   │   ├── export_service.py           # Data export (Phase 5.6)
│   │   ├── import_service.py           # Data import (Phase 5.6)
│   │   ├── job_progress_tracker.py     # Progress tracking
│   │   └── nuclei_services/            # Nuclei-specific services
│   │
│   ├── domain/
│   │   ├── models.py                   # Entity/Relationship domain models
│   │   ├── graph_schema.py             # Neo4j schema definitions
│   │   └── schemas/                    # Pydantic request/response schemas (12 files)
│   │
│   ├── core/
│   │   ├── logger.py                   # Structlog configuration
│   │   ├── security.py                 # Request ID, audit logging
│   │   └── auth_middleware.py          # JWT middleware, RBAC
│   │
│   ├── utils/
│   │   ├── chunking.py                 # Sliding window chunker
│   │   ├── parsers.py                  # PDF/DOCX/JSON/XML parsers
│   │   ├── batch_loader.py             # Async batch file loader
│   │   └── helpers.py                  # Shared utilities
│   │
│   └── workers/
│       ├── config.py                   # Celery app configuration
│       └── nuclei_tasks.py             # Celery task definitions
│
├── evaluation/                         # Benchmark framework
│   ├── runner.py                       # Benchmark orchestrator
│   ├── scenarios.py                    # Test scenarios & ground truth queries
│   ├── metrics.py                      # Precision, Recall, NDCG, MRR
│   ├── ground_truth.py                 # Labeled relevant results
│   └── results/                        # CSV benchmark outputs
│
├── scripts/
│   ├── batch_ingest_cve.py            # Async batch upload CVE files
│   ├── batch_extract_upsert.py        # Batch extraction & graph upsert
│   ├── batch_full_pipeline_cve.py     # Full pipeline orchestration
│   └── bootstrap/
│       ├── postgres_init.sql           # PostgreSQL schema + indexes
│       ├── neo4j_bootstrap.cypher      # Neo4j indexes + constraints
│       ├── weaviate_bootstrap.py       # Weaviate collection setup
│       └── minio_bootstrap.py         # MinIO bucket creation
│
├── data/
│   ├── cwec_v4.19.1.xml               # CWE v4.19.1 (1000+ weaknesses)
│   ├── nvdcve-2.0-modified.json       # NVD CVE dataset
│   └── cvelistV5-main/                # CVE List V5 (GitHub mirror)
│
├── tests/
│   ├── unit/                          # Unit tests per service
│   ├── integration/                   # End-to-end API tests
│   └── conftest.py                    # Pytest fixtures
│
├── diagram/                           # Architecture diagrams
├── docs/                              # Phase documentation
├── docker-compose.yml                 # 9-service stack definition
├── Dockerfile                         # Backend container (Python 3.11-slim)
├── Dockerfile.ollama                  # Ollama with GPU support
├── Makefile                           # Dev commands
├── requirements.txt                   # Python dependencies
└── .env.example                       # Configuration template
```

---

## Tài liệu tham khảo kỹ thuật

| Công nghệ | Tài liệu | Ghi chú |
|-----------|----------|---------|
| Neo4j 5.x | https://neo4j.com/docs/ | APOC plugin cần thiết cho bulk operations |
| Weaviate 1.26 | https://weaviate.io/developers/weaviate | Dùng gRPC cho production throughput |
| LangGraph | https://langchain-ai.github.io/langgraph/ | StateGraph với TypedDict state |
| FastAPI | https://fastapi.tiangolo.com/ | Dùng asyncio lifespan cho connection pooling |
| Ollama | https://ollama.com/library | nomic-embed-text tốt nhất cho security text |
| MITRE CWE | https://cwe.mitre.org/ | Nguồn dữ liệu cwec_v4.19.1.xml |
| NVD CVE | https://nvd.nist.gov/developers/vulnerabilities | API v2.0 feed |

---

**Version:** 0.3.0 &nbsp;|&nbsp; **Cập nhật:** Tháng 5/2026 &nbsp;|&nbsp; **Tác giả:** GraphPent Research Team
