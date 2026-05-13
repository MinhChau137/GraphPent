# GraphPent — Deployment & System Guide

**Version**: 2026-05  
**Platform**: GraphRAG-based Penetration Testing Knowledge System  

---

## Table of Contents

1. [System Overview](#1-system-overview)  
2. [Architecture](#2-architecture)  
3. [Prerequisites](#3-prerequisites)  
4. [Environment Setup](#4-environment-setup)  
5. [Infrastructure Startup](#5-infrastructure-startup)  
6. [Data Ingestion Pipeline](#6-data-ingestion-pipeline)  
7. [GNN Training Pipeline](#7-gnn-training-pipeline)  
8. [API Reference](#8-api-reference)  
9. [Configuration Reference](#9-configuration-reference)  
10. [Troubleshooting](#10-troubleshooting)  

---

## 1. System Overview

GraphPent là hệ thống pentest tự động dựa trên GraphRAG (Graph-Retrieval Augmented Generation). Hệ thống xây dựng knowledge graph từ kết quả scan mạng, ánh xạ với CVE/CWE/ATT&CK, sau đó dùng GNN để phát hiện mối nguy và sinh attack path.

### Mục tiêu

| Mục tiêu | Cách đạt |
|---|---|
| Phát hiện CVE tiềm năng từ service | Link prediction GNN (Service → Vulnerability) |
| Ưu tiên mục tiêu tấn công | Blended risk score: CVSS × PageRank × GNN proximity |
| Tìm attack path | Cypher shortest-path qua graph edges |
| Trả lời câu hỏi pentest | Hybrid retrieval (RRF: Graph + Vector, α=0.3) |
| Đề xuất technique tấn công | TTP→CWE→CVE→Service chain traversal |
| Làm đầy quan hệ thiếu trong graph | CSNT L4: Template rules + Structural + Neural |
| Phát hiện triple sai/nhiễu | CSNT Anomaly Detection (thống kê + confidence) |

---

## 2. Architecture

### 2.1 Kiến trúc 7 lớp

```
┌─────────────────────────────────────────────────────────────┐
│  L7  Execution     LangGraph multi-agent workflow           │
│  L6  Reasoning     Attack-path + GNN risk scoring          │
│  L5  GNN           R-GCN link prediction (Service→CVE)     │
│  L4  KG Completion CSNT: structural+neural+template+conf   │
│  L3  GraphRAG      Hybrid retrieval: RRF(graph, vector)    │
│  L2  Ingestion     LLM extraction → Neo4j + Weaviate       │
│  L1  Collection    Nmap / Nuclei / HTTP crawl               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Infrastructure

```
FastAPI :8000
├── PostgreSQL  :5432   raw chunks, job queue, reports
├── Redis       :6379   query cache (TTL 1h)
├── Neo4j       :7474   knowledge graph browser
│             :7687   bolt protocol
├── Weaviate    :8080   vector index (nomic-embed-text-v1.5)
├── MinIO       :9000   S3-compatible object storage
│   (console)  :9001
└── Ollama      :11434  local LLM (llama3.2:3b / llama3.1:8b)
```

### 2.3 Knowledge Graph Schema

**Node types (8 loại từ Nmap — Group 1)**

| Label | ID pattern | Key properties |
|---|---|---|
| Host | `host-{ip}` | ip, hostname, os, mac |
| IP | `ip-{ip}` | address, version, subnet |
| Port | `port-{ip}-{proto}-{port}` | port, protocol, state |
| Service | `service-{ip}-{port}` | product, version, cpe, full_name |
| Application | `app-{product}-{version}` | product, version, vendor, cpe |
| URL | `url-{ip}-{port}` | url, scheme, path |
| NetworkZone | `zone-{subnet}` | subnet, cidr |
| Domain | `domain-{fqdn}` | fqdn, host_ip |

**Node types (vulnerability — Group 2)**

| Label | ID pattern | Key properties |
|---|---|---|
| Vulnerability | `CVE-YYYY-NNNNN` | cvss_score, cvss_severity, attack_vector, cpe_affected |
| CWE | `cwe-NNN` | name, description, abstraction |

**Node types (threat intel — Group 3)**

| Label | ID pattern | Key properties |
|---|---|---|
| TTP | `ttp-T{id}` | technique_id, tactic, platforms, is_subtechnique |

**Edges**

```
Host       -[HAS_PORT]->      Port
Host       -[EXPOSES]->       Service
Host       -[RUNS]->          Application
Port       -[RUNS_SERVICE]->  Service
Service    -[RUNS]->          Application
Service    -[HAS_VULN]->      Vulnerability    ← training target
Vulnerability -[HAS_WEAKNESS]-> CWE
TTP        -[MAPPED_TO]->     CWE
TTP        -[CHILD_OF]->      TTP
```

### 2.4 GNN Architecture (R-GCN)

```
Input:  10-dim feature vectors per node
Layer1: Relational GCN → hidden_dim (default 64)
Layer2: Relational GCN → hidden_dim
Head:   dot-product + sigmoid → link score [0,1]

Training signal: HAS_VULN edges (CPE-matched, confidence ≥ 0.60)
Negative sampling: 2× random (Service, Vulnerability) pairs not in HAS_VULN
Loss: Binary Cross-Entropy
```

---

## 3. Prerequisites

### 3.1 Yêu cầu hệ thống

| Thành phần | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| CPU | 4 cores | 8 cores |
| Disk | 20 GB | 50 GB |
| OS | Linux / Windows 10+ / macOS | Ubuntu 22.04 |

### 3.2 Phần mềm cần cài

```bash
# Docker + Docker Compose
docker --version     # >= 24.0
docker compose version  # >= 2.20

# Python (host-side scripts)
python --version     # >= 3.11

# Nmap (để chạy scan thực)
nmap --version       # >= 7.94
```

### 3.3 Python dependencies (host scripts)

```bash
pip install neo4j numpy
pip install torch   # optional — numpy fallback available nếu không có GPU
```

---

## 4. Environment Setup

### 4.1 Tạo file .env

```bash
cp .env.example .env
```

Chỉnh sửa các giá trị sau trong `.env`:

```env
# Neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-strong-password

# PostgreSQL
POSTGRES_USER=graphrag_user
POSTGRES_PASSWORD=your-strong-password
POSTGRES_DB=pentest_graphrag

# LLM
OLLAMA_MODEL=llama3.1:8b         # hoặc llama3.2:3b cho máy yếu
EMBEDDING_MODEL=nomic-embed-text-v1.5

# Lab safety — whitelist các IP được phép scan
ALLOWED_TARGETS=192.168.1.0/24,10.0.0.0/8

# GNN weights (tổng phải = 1.0)
GNN_W_PAGERANK=0.10
GNN_W_SEVERITY=0.80
GNN_W_BETWEENNESS=0.10

# GraphRAG retrieval
RRF_ALPHA=0.3   # 0.0 = pure graph, 1.0 = pure vector, 0.3 optimal
```

---

## 5. Infrastructure Startup

### 5.1 Khởi động toàn bộ stack

```bash
docker compose up -d
```

Kiểm tra trạng thái:

```bash
docker compose ps
# Tất cả services phải ở trạng thái "healthy"
```

### 5.2 Kiểm tra từng service

```bash
# Neo4j
curl http://localhost:7474

# FastAPI
curl http://localhost:8000/health

# Weaviate
curl http://localhost:8080/v1/.well-known/ready

# Ollama
curl http://localhost:11434/api/tags
```

### 5.3 Pull Ollama model

```bash
docker exec graphrag-ollama ollama pull llama3.2:3b
docker exec graphrag-ollama ollama pull nomic-embed-text-v1.5
```

### 5.4 Bootstrap databases

```bash
# Neo4j indexes
docker exec graphrag-neo4j cypher-shell \
  -u $NEO4J_USER -p $NEO4J_PASSWORD \
  -f /scripts/bootstrap/neo4j_init.cypher

# PostgreSQL schema
docker exec graphrag-postgres psql \
  -U $POSTGRES_USER -d $POSTGRES_DB \
  -f /scripts/bootstrap/postgres_init.sql
```

---

## 6. Data Ingestion Pipeline

Chạy theo đúng thứ tự sau. Mỗi bước là tiền đề của bước tiếp theo.

### Bước 0 — Kiểm tra graph readiness

```bash
python scripts/check_graph_readiness.py
```

Output cho biết node counts, edge counts, và GNN readiness checklist.

---

### Bước 1 — Ingest Nmap scan (Group 1 nodes)

**Tạo file scan mẫu (nếu chưa có):**

```bash
python scripts/generate_sample_nmap.py --hosts 10 --out data/sample_nmap_scan.xml
```

**Parse và ingest vào Neo4j:**

```bash
# Dry run trước
python scripts/ingest_nmap_standalone.py \
  --file data/sample_nmap_scan.xml --dry-run

# Ingest thực
python scripts/ingest_nmap_standalone.py \
  --file data/sample_nmap_scan.xml

# Re-ingest (wipe + overwrite)
python scripts/ingest_nmap_standalone.py \
  --file data/sample_nmap_scan.xml --wipe-group1
```

Kết quả mong đợi:

```
[Host]          10 nodes
[IP]            10 nodes
[Service]       40+ nodes
[Application]   20+ nodes
[Port]          40+ nodes
```

**Với scan thực tế:**

```bash
# Chạy nmap và lưu XML
nmap -sV -sC --top-ports 1000 -oX data/scan.xml 192.168.1.0/24

# Ingest kết quả
python scripts/ingest_nmap_standalone.py --file data/scan.xml
```

---

### Bước 2 — Ingest CVE/CVSS (Group 2 nodes)

```bash
# Ingest CVE từ NVD batch (đã có sẵn trong project)
python scripts/batch_ingest_cve.py

# Hoặc ingest CVSS trực tiếp
python scripts/ingest_cvss_direct.py
```

Kết quả mong đợi: 100,000+ Vulnerability nodes, 20,000+ CWE nodes.

---

### Bước 3 — Link Service → CVE (HAS_VULN edges)

Đây là bước tạo training labels cho GNN.

```bash
python scripts/link_service_cve.py --min-confidence 0.60
```

Options:

| Flag | Default | Ý nghĩa |
|---|---|---|
| `--min-confidence` | 0.60 | Ngưỡng confidence tối thiểu cho edge |
| `--dry-run` | false | Preview, không ghi Neo4j |
| `--limit` | 10000 | Số edge tối đa tạo ra |

Kết quả mong đợi: 20+ HAS_VULN edges (cần ít nhất 20 để train GNN).

Kiểm tra:

```cypher
// Neo4j Browser: http://localhost:7474
MATCH (s:Service)-[r:HAS_VULN]->(v:Vulnerability)
RETURN count(r) AS has_vuln_count
```

---

### Bước 4 — Ingest MITRE ATT&CK TTPs (Group 3 nodes)

```bash
# Tự động download từ MITRE GitHub
python scripts/ingest_attack_ttp.py

# Hoặc dùng file local
python scripts/ingest_attack_ttp.py --file data/enterprise-attack.json

# Preview (không ghi Neo4j)
python scripts/ingest_attack_ttp.py --dry-run
```

Kết quả mong đợi: ~700 TTP nodes, MAPPED_TO edges sang CWE (nếu CWE đã ingest).

---

### Bước 5 — Kiểm tra sau ingest

```bash
python scripts/check_graph_readiness.py
```

Checklist GNN readiness:

```
[OK]  Host         >= 10   nodes
[OK]  Service      >= 50   nodes
[OK]  Vulnerability >= 100 nodes
[OK]  CWE          >= 10   nodes
[OK]  HAS_VULN     >= 20   edges
→ GNN: READY
```

---

## 7. L4 CSNT Completion (tùy chọn — sau ingest)

L4 CSNT chạy tự động mỗi khi workflow pentest khởi động (iteration 0).
Có thể gọi thủ công qua API:

### Bước 5b — Chạy CSNT full pass

```bash
# Full pass: Template + Structural + Neural + Confidence + Anomaly detection
curl -X POST http://localhost:8000/api/v1/kg/csnt/complete \
  -H "Content-Type: application/json" \
  -d '{"min_confidence": 0.60, "max_edges_per_rule": 500, "run_neural": true, "run_anomaly": true}'
```

Kết quả trả về:

```json
{
  "summary": {
    "template_edges": 45,
    "structural_edges": 23,
    "neural_edges": 12,
    "total_predicted": 68,
    "edges_written": 61,
    "triples_scored": 340,
    "confidence_updated": 128,
    "anomalies_flagged": 7
  },
  "anomalies": [...],
  "sample_predictions": [...]
}
```

### CSNT Components

| Component | Endpoint | Chức năng |
|---|---|---|
| **T** Template | `POST /kg/csnt/complete` | Rule-based: same-version CVE, TTP chain, host bridge |
| **S** Structural | `POST /kg/csnt/complete` | Common neighbors, path scan |
| **N** Neural | `POST /kg/csnt/complete` | GNN cosine similarity (cần gnn_embedding) |
| **C** Confidence | `POST /kg/csnt/score-triples` | Multi-factor scoring trên toàn bộ edges |
| Anomaly | `GET /kg/csnt/anomalies` | Phát hiện outliers, orphaned CVEs, low-conf edges |

### Template rules (T)

| Rule | Mô tả | Confidence |
|---|---|---|
| `same_version_rule` | Service cùng product+version → dùng chung CVE | 0.80 |
| `ttp_cwe_chain` | TTP→CWE→CVE→Service ⟹ TTP TARGETS Service | 0.73–0.82 |
| `host_service_bridge` | Host→Service→CVE ⟹ Host HAS_VULN CVE | 0.65–0.80 |
| `ttp_platform_app` | TTP platform match OS → TARGETS Application | 0.70 |

### Anomaly types

| Type | Ý nghĩa |
|---|---|
| `vuln_count_outlier` | Service cùng version nhưng số CVE lệch nhiều |
| `orphaned_high_cvss` | CVE ≥ 7.0 không có Service nào link |
| `service_no_cve` | Service có product+version nhưng không có CVE |
| `low_confidence_inferred` | Inferred edge với confidence < 0.50 |

---

## 9. GNN Training Pipeline

### Bước 6 — Export graph cho GNN

```bash
python scripts/export_graph_for_gnn.py --out data/gnn
```

Output tại `data/gnn/`:

| File | Nội dung |
|---|---|
| `nodes.json` | `[{id, type, features: [10 floats]}]` |
| `edges.json` | `[{src, dst, rel_type, weight, src_idx, dst_idx}]` |
| `node_index.json` | `{node_id: integer_index}` |
| `meta.json` | Statistics, feature_dim, edge types |

Feature vectors (10-dim):

| Node type | Dimensions |
|---|---|
| Service | port/65535, protocol_cat, has_cpe, has_version, product_hash, version_hash, vendor_hash, is_web_port, 0, 0 |
| Vulnerability | cvss/10, severity_cat, attack_vector_cat, n_products/20, n_vendors/10, has_cpe, 0, 0, 0, 0 |
| CWE | cwe_num/1000, 0×9 |
| Host | subnet_hash, os_hash, 0×8 |
| Application | product_hash, version_hash, vendor_hash, has_cpe, 0×6 |

---

### Bước 7 — Train GNN

**Với PyTorch (khuyến nghị):**

```bash
pip install torch

python scripts/train_gnn_link_predictor.py \
  --data data/gnn \
  --model models/gnn_link_predictor.pt \
  --epochs 200 \
  --dim 64 \
  --lr 0.01 \
  --neg-ratio 2
```

**Không có PyTorch (numpy fallback):**

```bash
# Tự động dùng numpy nếu torch không có; capped 50 epochs
python scripts/train_gnn_link_predictor.py --data data/gnn
```

**Training output:**

| File | Nội dung |
|---|---|
| `models/gnn_link_predictor.pt` | PyTorch state dict |
| `data/gnn/embeddings.json` | `{node_id: [64 floats]}` — node embeddings |
| `data/gnn/train_log.json` | Loss/AUC per epoch |

Mục tiêu: AUC ≥ 0.70 sau 200 epochs.

---

### Bước 8 — Infer và ghi edges vào Neo4j

```bash
# Dry run — xem predicted edges
python scripts/infer_gnn_edges.py \
  --data data/gnn \
  --model models/gnn_link_predictor.pt \
  --min-score 0.55 \
  --top 1000 \
  --dry-run

# Ghi vào Neo4j
python scripts/infer_gnn_edges.py \
  --data data/gnn \
  --model models/gnn_link_predictor.pt \
  --min-score 0.55 \
  --top 1000
```

Script này sẽ:
1. Load trained model (hoặc `embeddings.json` nếu không có model)
2. Score tất cả `(Service, Vulnerability)` pairs chưa có edge
3. Tạo `HAS_VULN` edges mới với `source="gnn"` và `confidence=score`
4. Ghi `gnn_embedding` property lên tất cả nodes
5. GNN service sẽ tự tính `gnn_vuln_proximity` khi chạy risk scoring

---

### Bước 9 — Trigger risk scoring

```bash
curl -X POST http://localhost:8000/api/v1/gnn/compute-risk
```

API này sẽ:
1. Chạy PageRank + Betweenness Centrality (Neo4j GDS hoặc degree fallback)
2. Tính `gnn_vuln_proximity` từ GNN embeddings (cho Service nodes)
3. Ghi `risk_score = 0.10×PR + 0.80×max(CVSS, GNN_proximity) + 0.10×BC` lên mọi node

---

## 8. API Reference

### Core endpoints

```
GET  /health                          — Healthcheck
GET  /api/v1/graph/stats              — Graph statistics
POST /api/v1/query                    — Hybrid RAG query
POST /api/v1/scan/nmap                — Trigger Nmap scan
POST /api/v1/gnn/compute-risk         — Run risk scoring
GET  /api/v1/gnn/high-risk?limit=20   — Top risky nodes
GET  /api/v1/gnn/attack-paths/{id}    — Attack paths from node
GET  /api/v1/gnn/risk-summary         — Risk snapshot
POST /api/v1/workflow/pentest         — Run full pentest workflow
```

### Ví dụ query

```bash
# Hybrid RAG query
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Apache HTTP Server có CVE nào nguy hiểm?",
    "mode": "hybrid",
    "limit": 5
  }'

# Top risk nodes
curl http://localhost:8000/api/v1/gnn/high-risk?limit=10

# Attack path từ một host
curl "http://localhost:8000/api/v1/gnn/attack-paths/host-192.168.1.1?max_hops=4"
```

### Query modes

| Mode | RRF alpha | Dùng khi |
|---|---|---|
| `hybrid` | 0.3 | Mặc định — cân bằng graph + vector |
| `vector_only` | 1.0 | Câu hỏi ngữ nghĩa tự do |
| `graph_only` | 0.0 | Traversal CVE/service cụ thể |

---

## 9. Configuration Reference

Xem đầy đủ tại [app/config/settings.py](../app/config/settings.py).

| Setting | Default | Ý nghĩa |
|---|---|---|
| `RRF_ALPHA` | 0.3 | Hybrid retrieval weight (0=graph, 1=vector) |
| `RRF_K` | 60.0 | RRF smoothing constant |
| `GNN_W_PAGERANK` | 0.10 | PageRank weight trong risk score |
| `GNN_W_SEVERITY` | 0.80 | CVSS/GNN proximity weight |
| `GNN_W_BETWEENNESS` | 0.10 | Betweenness centrality weight |
| `ATTACK_PATH_MAX_HOPS` | 4 | Max depth trong attack path search |
| `KG_MIN_CONFIDENCE` | 0.65 | Min confidence cho KG completion edges |
| `MAX_LOOP_ITERATIONS` | 3 | Max iterations trong feedback loop |
| `ALLOWED_TARGETS` | 127.0.0.1 | IP whitelist cho scan tools |

**Lưu ý về GNN weights**: Ba weights `GNN_W_*` phải cộng lại bằng 1.0. Trong pentest context, `GNN_W_SEVERITY=0.80` cho CVSS là ground truth chính; `GNN_W_PAGERANK` và `GNN_W_BETWEENNESS` là tie-breaker.

---

## 10. Troubleshooting

### Neo4j không kết nối

```bash
# Kiểm tra container
docker compose logs neo4j

# Test kết nối bolt
python -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password123')); d.verify_connectivity(); print('OK')"
```

### Không có HAS_VULN edges sau link_service_cve.py

Nguyên nhân phổ biến: Service nodes không có CPE hoặc product name.

```cypher
// Kiểm tra
MATCH (s:Service) WHERE s.product IS NOT NULL RETURN count(s)
MATCH (s:Service) WHERE s.cpe IS NOT NULL RETURN count(s)
```

Nếu count = 0: ingest lại Nmap với file XML có đầy đủ service detection (`-sV`).

### GNN AUC thấp (< 0.60)

Nguyên nhân:
- Quá ít positive edges (< 50 HAS_VULN) → tăng `--min-confidence` thấp hơn
- Feature vectors toàn 0 → kiểm tra Service.product, Vulnerability.cvss_score

```bash
python scripts/check_graph_readiness.py
# Xem phần "Feature coverage"
```

### LLM trả về kết quả rỗng

```bash
# Kiểm tra Ollama đã pull model chưa
docker exec graphrag-ollama ollama list

# Pull model nếu thiếu
docker exec graphrag-ollama ollama pull llama3.2:3b
```

### PageRank/Betweenness không chạy (GDS plugin)

Hệ thống tự động fallback về degree-based scoring. Để dùng GDS:

```bash
# Thêm vào docker-compose.yml
NEO4J_PLUGINS: '["apoc","graph-data-science"]'
```

---

## Luồng Pipeline Hoàn Chỉnh

```
[Nmap XML]
    ↓ ingest_nmap_standalone.py
[Neo4j: Host/Port/Service/App nodes]
    ↓ batch_ingest_cve.py
[Neo4j: Vulnerability/CWE nodes]
    ↓ link_service_cve.py
[Neo4j: HAS_VULN edges (CPE-matched)]
    ↓ ingest_attack_ttp.py
[Neo4j: TTP nodes, MAPPED_TO→CWE]
    ↓ export_graph_for_gnn.py
[data/gnn/nodes.json, edges.json]
    ↓ train_gnn_link_predictor.py
[models/gnn_link_predictor.pt, embeddings.json]
    ↓ infer_gnn_edges.py
[Neo4j: GNN HAS_VULN edges, gnn_embedding props]
    ↓ POST /api/v1/gnn/compute-risk
[Neo4j: risk_score, gnn_vuln_proximity on all nodes]
    ↓
[FastAPI: /query, /gnn/high-risk, /gnn/attack-paths]
```

---

*Cập nhật: 2026-05-13*
