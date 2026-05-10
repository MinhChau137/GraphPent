# GraphPent — Hướng Dẫn Deploy đến Benchmark

**Platform**: GraphRAG Pentest  
**Updated**: 2026-05-03

---

## Mục Lục

1. [Kiến trúc hệ thống](#1-kiến-trúc-hệ-thống)
2. [Yêu cầu hệ thống](#2-yêu-cầu-hệ-thống)
3. [Bước 1 — Cài đặt môi trường](#3-bước-1--cài-đặt-môi-trường)
4. [Bước 2 — Khởi động services](#4-bước-2--khởi-động-services)
5. [Bước 3 — Bootstrap databases](#5-bước-3--bootstrap-databases)
6. [Bước 4 — Nạp dữ liệu](#6-bước-4--nạp-dữ-liệu)
7. [Bước 5 — Kiểm tra hệ thống](#7-bước-5--kiểm-tra-hệ-thống)
8. [Bước 6 — Chạy workflow pentest](#8-bước-6--chạy-workflow-pentest)
9. [Bước 7 — Tinh chỉnh tham số](#9-bước-7--tinh-chỉnh-tham-số)
10. [Bước 8 — Chạy Benchmark](#10-bước-8--chạy-benchmark)
11. [Đọc kết quả Benchmark](#11-đọc-kết-quả-benchmark)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Kiến Trúc Hệ Thống

```
FastAPI :8000
└── 7-Layer GraphRAG Pipeline
    ├── L1  Collection      — Nmap, Nuclei, HTTP crawl
    ├── L2  Ingestion       — LLM extraction → PostgreSQL + Neo4j + Weaviate
    ├── L3  GraphRAG        — Hybrid retrieval (Vector + Graph + RRF)
    ├── L4  KG Completion   — Link prediction, entity resolution
    ├── L5  GNN Risk        — PageRank × CVSS severity scoring
    ├── L6  Reasoning       — Attack-path discovery, recommendations
    └── L7  Execution       — LangGraph multi-agent workflow

Infrastructure
├── PostgreSQL  :5432  — raw chunks, job queue, reports
├── Redis       :6379  — query cache (TTL 1h)
├── Neo4j       :7474/:7687  — knowledge graph (CWE/CVE/Finding nodes)
├── Weaviate    :8080  — vector index (nomic-embed-text-v1.5)
├── MinIO       :9001  — object storage (reports, artifacts)
└── Ollama      :9443  — local LLM (llama3.1:8b)
```

### Luồng dữ liệu

```
Input (query)
    │
    ▼
[L3] Weaviate vector search ──┐
[L3] Neo4j fulltext search ───┤  RRF fusion (alpha)
                               ▼
                         top-K results
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
             [L5] GNN risk         [L6] Reasoning
             score per node        attack paths
                    └──────────┬──────────┘
                               ▼
                    [L7] LangGraph report
```

---

## 2. Yêu Cầu Hệ Thống

| Phần mềm       | Phiên bản tối thiểu |
|---------------|---------------------|
| Docker        | 20.10+              |
| Docker Compose| 2.0+                |
| Python        | 3.11+               |
| Make          | bất kỳ              |

**Tài nguyên tối thiểu**: 4 CPU / 8 GB RAM  
**Khuyến nghị**: 8 CPU / 16 GB RAM (Ollama + Neo4j ngốn nhiều RAM)

**Ports sử dụng**: 8000, 5432, 6379, 7474, 7687, 8080, 9001, 9443

> Kiểm tra conflict trước khi khởi động:
> ```powershell
> netstat -ano | findstr "8000 7474 8080"
> ```

---

## 3. Bước 1 — Cài Đặt Môi Trường

### 3.1 Clone và tạo file `.env`

```bash
cp .env.example .env
```

Mở `.env` và chỉnh các giá trị sau (bắt buộc đổi password):

```env
# ── Database ───────────────────────────────────────────────
POSTGRES_PASSWORD=<đổi-mật-khẩu-mạnh>
NEO4J_PASSWORD=<đổi-mật-khẩu-mạnh>

# ── Targets cho phép scan (thêm IP lab của bạn) ────────────
ALLOWED_TARGETS=127.0.0.1,localhost,192.168.1.100,dvwa.local

# ── LLM models ─────────────────────────────────────────────
OLLAMA_MODEL=llama3.1:8b
EMBEDDING_MODEL=nomic-embed-text-v1.5

# ── Retrieval (giữ nguyên mặc định khi mới cài) ────────────
RRF_ALPHA=0.3
RRF_K=60.0
```

> **Lưu ý**: `RRF_ALPHA=0.3` là giá trị tối ưu từ benchmark. Đừng đổi sang 0.7 (default cũ) vì graph bị bỏ qua.

### 3.2 Cài Python dependencies (để chạy benchmark)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 4. Bước 2 — Khởi Động Services

### 4.1 Build và start tất cả containers

```bash
make up
# hoặc trực tiếp:
docker compose up --build -d
```

Chờ **1–2 phút** để tất cả containers healthy.

### 4.2 Kiểm tra trạng thái

```bash
make status
# Hoặc:
docker compose ps
```

Tất cả services phải ở trạng thái `healthy` hoặc `Up`:

```
NAME         STATUS         PORTS
backend      Up (healthy)   0.0.0.0:8000->8000/tcp
postgres     Up (healthy)   0.0.0.0:5432->5432/tcp
neo4j        Up (healthy)   0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp
weaviate     Up (healthy)   0.0.0.0:8080->8080/tcp
redis        Up             0.0.0.0:6379->6379/tcp
minio        Up             0.0.0.0:9001->9001/tcp
ollama       Up             0.0.0.0:9443->9443/tcp
```

### 4.3 Pull Ollama models

Bước này cần làm **một lần** sau lần đầu khởi động (mất 5–15 phút tùy tốc độ mạng):

```bash
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text-v1.5
```

Kiểm tra đã pull xong:

```bash
docker compose exec ollama ollama list
```

### 4.4 Theo dõi logs

```bash
make logs-backend       # chỉ backend
make logs-all           # tất cả services
docker compose logs -f ollama   # theo dõi riêng Ollama
```

---

## 5. Bước 3 — Bootstrap Databases

Bootstrap khởi tạo schema, indexes, và constraints. Chỉ cần chạy **một lần**.

```bash
make bootstrap
```

Lệnh này chạy tuần tự:

| Sub-command              | Làm gì                                                |
|--------------------------|-------------------------------------------------------|
| `bootstrap-postgres`     | Tự động chạy khi container postgres khởi động lần đầu |
| `bootstrap-neo4j`        | Tạo fulltext index `nodeSearch`, unique constraints   |
| `bootstrap-weaviate`     | Tạo class `Document` với vector dimensions=768       |
| `bootstrap-minio`        | Tạo bucket `graphrag-bucket`                         |

Kiểm tra Neo4j index đã tạo:

```bash
docker compose exec neo4j cypher-shell -u neo4j -p password123 \
  "SHOW INDEXES YIELD name, type WHERE name = 'nodeSearch'"
```

---

## 6. Bước 4 — Nạp Dữ Liệu

### 6.1 Load data

```bash
# Load data từ file cve json
docker compose exec backend python /app/scripts/batch_pipeline_optimized.py  --mode cve  --year 2024  --data-dir /app/data

# Load data từ file cwe, nvd thì đổi mode tương ứng và bỏ tag --year
```

### 6.3 Kiểm tra dữ liệu đã nạp

```bash
# Đếm nodes trong Neo4j
docker compose exec neo4j cypher-shell -u neo4j -p password123 \
  "MATCH (n) RETURN labels(n)[0] AS type, count(n) AS cnt ORDER BY cnt DESC"

# Đếm vectors trong Weaviate
curl -s http://localhost:8080/v1/objects | python -m json.tool | grep totalResults

# Đếm chunks trong PostgreSQL
docker compose exec postgres psql -U graphrag_user -d pentest_graphrag \
  -c "SELECT count(*) FROM documents;"
```

Kết quả tối thiểu để benchmark hoạt động đúng:

| Store     | Tối thiểu |
|-----------|-----------|
| Neo4j CWE nodes | 200+ |
| Neo4j CVE nodes | 100+ |
| Weaviate chunks  | 500+ |

---

## 7. Bước 5 — Kiểm Tra Hệ Thống

### 7.1 Health check

```bash
make health
# hoặc:
curl http://localhost:8000/health
```

Kết quả mong đợi:
```json
{"status": "ok", "services": {"postgres": "ok", "redis": "ok", "neo4j": "ok", "weaviate": "ok"}}
```

### 7.2 Swagger UI

Mở trình duyệt: **http://localhost:8000/docs**

### 7.3 Test hybrid retrieval thủ công

```bash
curl -X POST http://localhost:8000/retrieve/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SQL injection",
    "limit": 10,
    "mode": "hybrid",
    "alpha": 0.3,
    "use_cache": false
  }'
```

Kết quả tốt — top result có `id` dạng `cwe-89` hoặc CVE ID, không phải chỉ số chunk:
```json
{
  "results": [
    {"id": "cwe-89", "final_score": 0.98, ...},
    {"id": "CVE-2024-1317", "final_score": 0.91, ...},
    ...
  ]
}
```

### 7.4 Test graph-only (kiểm tra Neo4j fulltext)

```bash
curl -X POST http://localhost:8000/retrieve/query \
  -H "Content-Type: application/json" \
  -d '{"query": "SQL injection", "limit": 10, "mode": "graph_only", "alpha": 0.0, "use_cache": false}'
```

### 7.5 Test GNN risk summary

```bash
curl http://localhost:8000/risk/summary
```

Kết quả mong đợi có `top_risks` list với `id`, `risk_score`, `risk_level`.

### 7.6 Test multi-agent workflow

```bash
curl -X POST http://localhost:8000/workflow/multi-agent \
  -H "Content-Type: application/json" \
  -d '{"query": "SQL injection vulnerability analysis", "user_id": "test"}'
```

Kết quả đầy đủ gồm: `gnn.risk_summary`, `gnn.attack_paths`, `reasoning.key_entities`, `final_answer`.

---

## 8. Bước 6 — Chạy Workflow Pentest

### 8.1 Nmap scan

```bash
curl -X POST http://localhost:8000/tools/nmap/scan \
  -H "Content-Type: application/json" \
  -d '{"target": "192.168.1.100"}'
```

> Target phải có trong `ALLOWED_TARGETS` trong `.env`.

### 8.2 Nuclei vulnerability scan

```bash
curl -X POST http://localhost:8000/tools/nuclei/scan \
  -H "Content-Type: application/json" \
  -d '{
    "target": "http://dvwa.local",
    "templates": ["cves", "exposures"]
  }'
```

### 8.3 CVE analysis

```bash
curl -X POST http://localhost:8000/tools/cve/analyze \
  -H "Content-Type: application/json" \
  -d '{"cve_id": "CVE-2021-44228"}'
```

### 8.4 Full multi-agent workflow

```bash
curl -X POST http://localhost:8000/workflow/multi-agent \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Analyze vulnerabilities on target 192.168.1.100",
    "user_id": "analyst01"
  }'
```

Kiểm tra trạng thái:
```bash
curl http://localhost:8000/workflow/status/<workflow-id>
```

---

## 9. Bước 7 — Tinh Chỉnh Tham Số

Tất cả tham số trong `.env`. Sau khi chỉnh: `make restart`.

### RRF Retrieval (quan trọng nhất)

```env
RRF_ALPHA=0.3    # Optimal theo benchmark — đừng tăng quá 0.5
RRF_K=60.0       # Constant trong RRF fusion, giữ nguyên
```

| Alpha | Hành vi                          | NDCG@10 |
|-------|----------------------------------|---------|
| 0.0   | Graph-only                       | 0.8165  |
| 0.1–0.5 | **Hybrid (khuyến nghị)**       | **0.8355** |
| 0.7   | Vector dominant — graph mất tác dụng | 0.2374 |
| 1.0   | Vector-only                      | 0.2374  |

### LLM Extraction

```env
ENTITY_CONFIDENCE_THRESHOLD=0.85   # Hạ xuống 0.70 nếu graph quá thưa
RELATION_CONFIDENCE_THRESHOLD=0.75
```

### GNN Risk Weights (tổng phải = 1.0)

```env
GNN_W_PAGERANK=0.50      # Trung tâm đồ thị
GNN_W_SEVERITY=0.30      # CVSS score
GNN_W_BETWEENNESS=0.20   # Cầu nối giữa các cluster
```

### Workflow

```env
MAX_LOOP_ITERATIONS=3    # Số vòng reasoning tối đa
ATTACK_PATH_MAX_HOPS=4   # Chiều sâu tìm attack path trong Neo4j
```

---

## 10. Bước 8 — Chạy Benchmark

### 10.1 Cấu trúc benchmark

```
evaluation/
├── config.py        — BenchmarkConfig (base_url, num_runs, output_dir)
├── scenarios.py     — 5 test scenarios với queries
├── ground_truth.py  — relevant IDs cho từng query (CWE + CVE + chunk)
├── metrics.py       — P@k, R@k, MRR, NDCG@k, F1
└── runner.py        — async runner, in Table 3/4/5
```

### 10.2 Đảm bảo API đang chạy

```bash
curl http://localhost:8000/health
```

### 10.3 Chạy benchmark

Từ thư mục gốc dự án (với virtualenv đã activate):

```bash
python -m evaluation.runner
```

Hoặc trực tiếp:

```bash
python evaluation/runner.py
```

### 10.4 Theo dõi tiến trình

Nếu `tqdm` đã cài, sẽ hiển thị progress bar. Tổng thời gian ước tính:
- 12 queries × 7 modes × 1 run = **84 API calls**
- Mỗi call ~50–150ms → tổng ~5–15 giây

### 10.5 Output

```
Results saved: evaluation/results/benchmark_20260503_HHMMSS.csv

========================================================================================
Table 3. Retrieval Comparison (avg across all scenarios)
========================================================================================
Mode                    P@5    R@5   P@10   R@10  F1@10    MRR  NDCG@10    Latency
----------------------------------------------------------------------------------------
B1 (Vector-only)      0.2833 ...
B2 (Graph-only)       0.8833 ...
G-0.1 (Hybrid)        0.9000 ...  <--
...
========================================================================================

Table 4. NDCG@10 per Scenario
...

Table 5. Alpha Optimization
...
```

### 10.6 Cấu hình benchmark

Chỉnh trong [evaluation/config.py](evaluation/config.py):

```python
class BenchmarkConfig(BaseModel):
    base_url: str = "http://localhost:8000"   # URL API
    num_runs: int = 1                          # 1 là đủ (system deterministic)
    output_dir: str = "evaluation/results"
```

Để test nhiều runs (tính variance):
```python
num_runs: int = 3
```

### 10.7 Thêm query mới vào ground truth

1. Thêm query vào scenario trong [evaluation/scenarios.py](evaluation/scenarios.py)
2. Chạy graph-only để xem IDs thực tế trả về:
   ```bash
   curl -X POST http://localhost:8000/retrieve/query \
     -d '{"query": "YOUR_QUERY", "limit": 15, "mode": "graph_only", "alpha": 0.0, "use_cache": false}'
   ```
3. Chạy vector-only để xem chunk IDs:
   ```bash
   curl -X POST http://localhost:8000/retrieve/query \
     -d '{"query": "YOUR_QUERY", "limit": 15, "mode": "vector_only", "alpha": 1.0, "use_cache": false}'
   ```
4. Thêm relevant IDs đã xác minh vào [evaluation/ground_truth.py](evaluation/ground_truth.py)
5. Chạy lại benchmark

---

## 11. Đọc Kết Quả Benchmark

### Metrics giải thích

| Metric  | Ý nghĩa                                                  | Tốt khi |
|---------|----------------------------------------------------------|---------|
| P@5     | Trong 5 kết quả đầu, bao nhiêu % relevant               | → 1.0   |
| R@5     | Bao nhiêu % tổng relevant được tìm thấy trong top-5     | Tùy bộ  |
| P@10    | Trong 10 kết quả đầu, bao nhiêu % relevant               | → 1.0   |
| R@10    | Bao nhiêu % tổng relevant trong top-10                   | Tùy bộ  |
| F1@10   | Harmonic mean của P@10 và R@10                           | → 1.0   |
| MRR     | Mean Reciprocal Rank — kết quả relevant đầu tiên ở vị trí bao nhiêu | → 1.0 |
| NDCG@10 | Normalized DCG — ranking quality, main metric           | → 1.0   |

> **MRR=1.0** nghĩa là kết quả đầu tiên luôn relevant — đây là lý tưởng.

### Kết quả đạt được (2026-05-03)

```
Mode             NDCG@10   MRR     Latency
B1 Vector-only   0.2374    0.4722   104ms
B2 Graph-only    0.8165    1.0000    37ms
G-0.1 Hybrid     0.8355    1.0000    99ms  ← Optimal
G-0.3 Hybrid     0.8355    1.0000   105ms  ← Optimal
G-0.7 Hybrid     0.2374    0.4722   102ms  ← Graph bị bỏ qua
```

### Cách đọc Table 4 (per-scenario)

Mỗi dòng = 1 scenario. `*` đánh dấu mode tốt nhất cho scenario đó:

```
Retrieval Accuracy:    B2=0.8084, G-0.3=0.8539 *   ← Hybrid thắng
CVE Linking:           B2=G-0.3=0.8240 *            ← Tie
Remediation Quality:   B2=G-0.3=1.0000 *            ← Perfect
Multi-hop Reasoning:   B2=G-0.3=0.6680 *            ← Thấp hơn (auth-bypass ít relevant IDs)
```

### Khi nào nên re-benchmark

- Sau khi ingest thêm CVE data mới
- Sau khi chỉnh `RRF_ALPHA`
- Sau khi thêm ground truth queries mới
- Sau khi rebuild Neo4j hoặc Weaviate

---

## 12. Troubleshooting

### Services không khởi động

```bash
docker compose ps          # xem trạng thái từng service
docker compose logs -f     # xem log lỗi
make clean                 # rebuild từ đầu (xóa volumes!)
```

### Neo4j không kết nối

```bash
# Test kết nối
docker compose exec neo4j cypher-shell -u neo4j -p password123 "RETURN 1"

# Xem logs
docker compose logs neo4j

# Thường gặp: password sai → kiểm tra NEO4J_PASSWORD trong .env khớp với container
```

### Weaviate trả về metadata null

Đây là hành vi bình thường khi chunk không có metadata. Hệ thống đã xử lý — node type được infer từ ID pattern (`cwe-*` → Weakness, `CVE-*` → CVE, số → chunk).

```bash
# Kiểm tra schema
curl http://localhost:8080/v1/schema

# Reinitialize nếu schema lỗi
docker compose exec backend python /app/scripts/bootstrap/weaviate_bootstrap.py
```

### Benchmark trả về NDCG@10 = 0.0 cho tất cả

Nguyên nhân thường gặp:
1. **API không chạy** — kiểm tra `curl http://localhost:8000/health`
2. **Chưa load data** — chạy `make load-sample` và ingest CVE
3. **Ground truth sai** — IDs trong `ground_truth.py` không khớp với IDs thực tế trong Neo4j

Để debug ground truth:
```bash
# Xem IDs thực tế cho query "SQL injection" trong graph
curl -X POST http://localhost:8000/retrieve/query \
  -d '{"query": "SQL injection", "limit": 15, "mode": "graph_only", "alpha": 0.0, "use_cache": false}' \
  -H "Content-Type: application/json" | python -m json.tool
```

### Benchmark chạy chậm (>30 giây)

- Ollama đang load model lần đầu — chờ `ollama list` trả về model
- Redis cache bị disable — đảm bảo `use_cache: false` chỉ dùng trong benchmark
- Weaviate cold start — chạy một vài queries thủ công trước

### Lỗi Unicode khi in bảng (Windows)

Runner đã dùng `<--` thay `◄`. Nếu vẫn lỗi:
```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m evaluation.runner
```

### Hết RAM / OOM Kill

```bash
docker stats    # xem memory usage
```

Giảm tải: trong `docker-compose.yml` thêm limit cho Ollama và Neo4j:
```yaml
ollama:
  deploy:
    resources:
      limits:
        memory: 6G
neo4j:
  deploy:
    resources:
      limits:
        memory: 2G
```

---

## Verification Checklist

### Deploy xong

- [ ] `curl http://localhost:8000/health` → `{"status": "ok"}`
- [ ] Swagger UI: http://localhost:8000/docs
- [ ] Neo4j Browser: http://localhost:7474 (login neo4j / password từ .env)
- [ ] `docker compose ps` — tất cả Up/healthy

### Dữ liệu xong

- [ ] `MATCH (n:CWE) RETURN count(n)` > 200 trong Neo4j
- [ ] `MATCH (n:CVE) RETURN count(n)` > 100 trong Neo4j
- [ ] `/retrieve/query` với `mode: graph_only` trả `cwe-89` cho query "SQL injection"

### Benchmark xong

- [ ] `python -m evaluation.runner` chạy không lỗi
- [ ] File CSV tạo trong `evaluation/results/`
- [ ] B2 (Graph-only) NDCG@10 > 0.8
- [ ] G-0.3 (Hybrid) NDCG@10 >= B2 NDCG@10
- [ ] MRR = 1.0 cho B2 và G-0.1–G-0.5
