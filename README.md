# GraphPent — Hướng dẫn cho thành viên mới

> Phiên bản: v0.3.0 | Cập nhật: 05/2026 | Dành cho: thành viên mới tham gia dự án ThS

---

## Mục lục

1. [Bức tranh tổng thể](#1-bức-tranh-tổng-thể)
2. [Kiến trúc 7 lớp](#2-kiến-trúc-7-lớp)
3. [Activity Diagram — Luồng hoạt động đầy đủ](#3-activity-diagram--luồng-hoạt-động-đầy-đủ)
4. [Phân tích từng lớp & kết quả hiện tại](#4-phân-tích-từng-lớp--kết-quả-hiện-tại)
5. [Stack công nghệ — Tại sao chọn cái này?](#5-stack-công-nghệ--tại-sao-chọn-cái-này)
6. [Benchmark — Số liệu thực tế](#6-benchmark--số-liệu-thực-tế)
7. [Cách chạy project ngay bây giờ](#7-cách-chạy-project-ngay-bây-giờ)
8. [Cấu trúc thư mục — Cần biết file nào?](#8-cấu-trúc-thư-mục--cần-biết-file-nào)
9. [Câu hỏi thường gặp](#9-câu-hỏi-thường-gặp)

---

## 1. Bức tranh tổng thể

### Vấn đề nghiên cứu giải quyết

Các LLM agent pentest hiện có (PentestGPT, AutoPenBench) thất bại theo hai cách:

| Triệu chứng | Nguyên nhân gốc |
|-------------|-----------------|
| Agent bám vào 1 attack path qua 5 lần thất bại liên tiếp | **Depth-first bias** — không có cơ chế nhận biết "thất bại" để chuyển hướng |
| Agent lặp lại công việc đã làm, quên kết quả cũ | **Mất context** — state lưu trong natural language, không có cấu trúc |

### GraphPent giải quyết bằng cách nào?

```
CÁI CŨ (PentestGPT)              CÁI MỚI (GraphPent)
─────────────────────             ─────────────────────────────
"Find SQL injection"         →    AgentState TypedDict {
"Try CVE-2021-..."                  query, plan, retrieval_results,
"Escalate privs"                    graph_context, tool_results,
                                    loop_iteration, new_findings_count...
(ngôn ngữ tự nhiên,                }
 mất context sau vài turn)          (có cấu trúc, persisted mỗi node)
```

**Ba đổi mới kỹ thuật:**
1. **Hybrid Knowledge Graph** — Neo4j (quan hệ) + Weaviate (ngữ nghĩa) + RRF Fusion
2. **AgentState TypedDict** — state có cấu trúc, tồn tại qua mọi node LangGraph
3. **Feedback Loop** — tự động re-plan khi có findings mới (tối đa 3 vòng)

---

## 2. Kiến trúc 7 lớp

Project được tổ chức thành **7 lớp logic** (không phải 7 service Docker, nhưng là 7 vai trò xử lý):

```
┌────┬──────────────────────────┬──────────────────────────────────────────────┐
│ L# │ Tên lớp                  │ Chức năng                                    │
├────┼──────────────────────────┼──────────────────────────────────────────────┤
│ L1 │ Data Collection          │ Thu thập dữ liệu: Nmap scan → topology mạng  │
│ L2 │ Ingestion & Normalization│ Upload doc, chunk, deduplicate, lưu metadata  │
│ L3 │ GraphRAG Retrieval       │ Hybrid search: Neo4j graph + Weaviate vector  │
│ L4 │ KG Completion            │ Suy luận link còn thiếu trong knowledge graph │
│ L5 │ GNN Structural Reasoning │ PageRank + CVSS + Betweenness → risk score    │
│ L6 │ Reasoning & Decision     │ Tổng hợp context → quyết định cần tool không  │
│ L7 │ Execution & Feedback     │ Chạy Nuclei, sinh báo cáo, feedback loop      │
└────┴──────────────────────────┴──────────────────────────────────────────────┘
```

Các lớp này được thực thi bởi **7 node trong LangGraph DAG**:

```
collection_node  →  planner_node  →  retrieval_node  →  graph_reasoning_node
     (L1+L2)          (L2+L4)           (L3)                  (L5+L6)
                                                                    │
                                              ┌─────────────────────┤
                                              │                     │
                                         tool_node            report_node
                                           (L7)                  (L7)
                                              │                     │
                                              └──────┬──────────────┘
                                                     │
                                           human_approval_node
                                                   (L7)
                                              ┌──────┴──────┐
                                              │             │
                                          planner         END
                                        (loop lại)
```

---

## 3. Activity Diagram — Luồng hoạt động đầy đủ

### 3.1 Pipeline dữ liệu (offline — chuẩn bị knowledge base)

```
╔══════════════════════════════════════════════════════════════════════════╗
║              PIPELINE DỮ LIỆU (chạy 1 lần để build knowledge base)     ║
╚══════════════════════════════════════════════════════════════════════════╝

  ┌────────────────────────────────────────────────────────┐
  │  NGUỒN DỮ LIỆU                                         │
  │  data/cwec_v4.19.1.xml   ← CWE v4.19 (1000+ weakness) │
  │  data/nvdcve-2.0-*.json  ← NVD CVE dataset             │
  │  data/cvelistV5-main/    ← CVE List V5                 │
  └──────────────┬─────────────────────────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────────────────────────┐
  │  PHASE 4: DOCUMENT INGESTION                            │
  │  POST /ingest/document                                  │
  │                                                         │
  │  1. Format detection (PDF/DOCX/JSON/XML)                │
  │  2. Chunking: sliding window 500 tokens, overlap 50     │
  │  3. Deduplication: SHA256(content) → skip nếu đã có    │
  │  4. Lưu song song:                                      │
  │     ├── PostgreSQL: bảng documents + chunks             │
  │     ├── MinIO: raw/{uuid}_{filename}                    │
  │     └── Weaviate: embed(nomic-embed-text) → index       │
  └──────────────┬──────────────────────────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────────────────────────┐
  │  PHASE 5: ENTITY & RELATION EXTRACTION                  │
  │  POST /extract/chunk/{chunk_id}                         │
  │                                                         │
  │  1. Fetch chunk content từ PostgreSQL                   │
  │  2. Detect data type: CWE XML / NVD JSON / generic      │
  │  3. LLM extraction (Ollama llama3.2:3b):                │
  │     Input : chunk_text                                  │
  │     Output: {                                           │
  │       entities: [{id, type, name, confidence}],         │
  │       relations: [{source_id, target_id, type, conf}]   │
  │     }                                                   │
  │  4. Validation:                                         │
  │     entity.confidence  >= 0.85 → giữ lại               │
  │     relation.confidence >= 0.75 → giữ lại              │
  │  5. Retry: 4 lần, exponential backoff (5s → 40s)        │
  └──────────────┬──────────────────────────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────────────────────────┐
  │  PHASE 6: GRAPH UPSERT (Neo4j)                          │
  │                                                         │
  │  MERGE (n:Weakness {id: $id})                           │
  │    ON CREATE SET n.name = $name, n.created_at = now()   │
  │    ON MATCH  SET n.updated_at = now()                   │
  │                                                         │
  │  → Idempotent: chạy nhiều lần vẫn an toàn              │
  │  → Batch transaction: retry 3x exponential backoff      │
  │  → Relationship: MERGE (src)-[r:TYPE]->(tgt)            │
  │    SET r.confidence, r.source_chunk_id                  │
  └─────────────────────────────────────────────────────────┘

  Kết quả sau pipeline này:
  ✓ Neo4j: 17+ loại entity node, 20+ loại relationship
  ✓ Weaviate: vector index của tất cả text chunks
  ✓ PostgreSQL: metadata đầy đủ cho dedup và audit
```

---

### 3.2 Multi-agent workflow (online — khi analyst chạy pentest)

```
╔══════════════════════════════════════════════════════════════════════════╗
║           MULTI-AGENT WORKFLOW (POST /workflow/multi-agent)             ║
╚══════════════════════════════════════════════════════════════════════════╝

  Analyst gửi request:
  {
    "query": "Find vulnerabilities on target",
    "scan_target": "192.168.1.100",
    "max_loop_iterations": 3
  }
         │
         ▼
  ╔══════════════════════════════╗
  ║   [NODE 1] collection_node  ║  ← L1: Data Collection
  ║   (chỉ chạy iteration == 0) ║
  ╚══════════════════════════════╝
         │
         │ Kiểm tra: scan_target có trong ALLOWED_TARGETS?
         │   ├── KHÔNG → lỗi security, dừng
         │   └── CÓ → chạy Nmap: -sV -sC -O --script vuln
         │
         │ Kết quả Nmap → lưu vào Neo4j:
         │   (h:Host)-[:HAS_PORT]->(p:Port)-[:RUNS_SERVICE]->(s:Service)
         │
         ▼
  ╔══════════════════════════════╗
  ║   [NODE 2] planner_node     ║  ← L2+L4: Planning + KG Completion
  ╚══════════════════════════════╝
         │
         │ Iteration 0:
         │   → Trigger KG Completion (fire-and-forget, background)
         │   → Chọn search_mode:
         │       query chứa "CVE-" → graph_only
         │       còn lại           → hybrid
         │
         │ Iteration > 0 (feedback loop):
         │   → Lấy risk_targets từ GNN result vòng trước
         │   → Enrich query với host/risk context
         │
         │ Output plan: {
         │   search_mode, needs_tools,
         │   risk_targets, kg_completion_triggered
         │ }
         │
         ▼
  ╔══════════════════════════════╗
  ║   [NODE 3] retrieval_node   ║  ← L3: GraphRAG Hybrid Retrieval
  ╚══════════════════════════════╝
         │
         │ Gọi HybridRetrieverService.hybrid_retrieve(
         │   query  = enriched_query,
         │   limit  = 20,
         │   alpha  = 1.0 / 0.0 / 0.7  (theo search_mode),
         │   mode   = vector_only / graph_only / hybrid
         │ )
         │
         │ Bên trong hybrid_retrieve:
         │   ┌─────────────────┐   ┌──────────────────────────┐
         │   │  GRAPH SEARCH   │   │    VECTOR SEARCH          │
         │   │  Neo4j fulltext │   │  Weaviate near_text       │
         │   │  + BFS 4 hops   │   │  cosine similarity top-K  │
         │   └────────┬────────┘   └─────────────┬────────────┘
         │            │                           │
         │            └───────────┬───────────────┘
         │                        │
         │              RRF FUSION:
         │              score(d) = α × RRF_graph(d) + (1-α) × RRF_vec(d)
         │              RRF_x(d) = 1 / (k + rank_x(d)),  k=60
         │              α = 0.3  (khuyến nghị từ benchmark)
         │
         │ Output: retrieval_results (top 20, ranked by RRF score)
         │
         ▼
  ╔══════════════════════════════════╗
  ║ [NODE 4] graph_reasoning_node   ║  ← L5+L6: GNN + Reasoning
  ╚══════════════════════════════════╝
         │
         │ Bước 1 — Extract entities từ top 5 retrieval results
         │
         │ Bước 2 — L5: GNNService risk scoring
         │   risk(v) = 0.50 × pagerank(v)
         │            + 0.30 × normalized_cvss(v)
         │            + 0.20 × betweenness(v)
         │   → gnn_risk_summary: {severity_counts, top_risks[]}
         │
         │ Bước 3 — L5: Attack path finding (BFS, max 4 hops)
         │   MATCH path = (src)-[*1..4]->(dst)
         │   → attack_paths: [{source, path_nodes, hops, path_risk}]
         │
         │ Bước 4 — L6: Build graph_context
         │   → {key_entities, attack_paths, recommendations}
         │
         │ Bước 5 — Quyết định conditional edge:
         │   needs_tools = plan.needs_tools
         │                 AND retrieval_results không rỗng
         │
         ▼
         │
    ┌────┴────────────────────────────────────────┐
    │ needs_tools == True?                        │
    │                                             │
   YES                                            NO
    │                                             │
    ▼                                             ▼
  ╔═══════════════╗                    ╔══════════════════╗
  ║ [NODE 5]      ║                    ║ [NODE 6]         ║
  ║ tool_node     ║                    ║ report_node      ║
  ╚═══════════════╝                    ╚══════════════════╝
    │                                             ▲
    │ 1. Extract CVEs từ retrieval results        │
    │ 2. Chạy Nuclei scan:                        │
    │    severity=critical,high                   │
    │    target=scan_target                        │
    │ 3. Phân tích CVE exploitability             │
    │ 4. Đếm new_findings_count                   │
    │    (dùng cho feedback loop)                 │
    │                                             │
    └─────────────────────────────────────────────┘
                                         │
  ╔══════════════════════════════════════╝
  ║ [NODE 6] report_node                          ← L7: Report
  ╚══════════════════════════════════════╗
         │
         │ Tổng hợp từ tất cả 7 lớp:
         │ report = {
         │   query, timestamp, iteration,
         │   collection: {hosts, ports, services},
         │   retrieval: {top_results, search_mode},
         │   kg_completion: {entities_processed, relations_predicted},
         │   gnn: {top_risks, severity_counts},
         │   reasoning: {key_entities, attack_paths, recommendations},
         │   tools: {nuclei_findings, cve_analyses},
         │   status: "completed"
         │ }
         │
         │ Sinh report_markdown (Markdown có cấu trúc theo severity)
         │ Sinh final_answer (tóm tắt 1 đoạn)
         │
         ▼
  ╔══════════════════════════════════════╗
  ║ [NODE 7] human_approval_node        ║  ← L7: Feedback Loop Gate
  ╚══════════════════════════════════════╝
         │
         │ Đặt human_approval = True (auto-approve hiện tại)
         │ Ghi audit log
         │ Tăng loop_iteration += 1
         │ Reset new_findings_count = 0
         │
         ▼
         │
    ┌────┴────────────────────────────────────────┐
    │ Điều kiện tiếp tục loop?                    │
    │                                             │
    │ new_findings_count > 0                      │
    │ AND loop_iteration < max_loop_iterations    │
    │                                             │
   YES                                            NO
    │                                             │
    ▼                                             ▼
  planner_node                                  END
  (vòng tiếp theo,                          (trả về response)
   enriched context)
```

---

### 3.3 Luồng đánh giá / benchmark (evaluation pipeline)

```
╔═══════════════════════════════════════════════════════════════╗
║             EVALUATION PIPELINE (chạy để đo kết quả)         ║
╚═══════════════════════════════════════════════════════════════╝

  evaluation/ground_truth.json
  ├── retrieval_queries  (4 queries: SQL injection, XSS, IDOR, CSRF)
  ├── cve_queries        (1 query: CVE linking)
  ├── finding_cases      (finding correlation)
  ├── multi_hop_queries  (multi-hop reasoning)
  └── remediation_cases  (remediation quality)
         │
         ▼
  python evaluation/runner.py
         │
         │ Gọi POST /retrieve/query cho từng query × mode:
         │   B1_vector_only  (alpha=1.0)
         │   B2_graph_only   (alpha=0.0)
         │   G_0.1 → G_0.7  (hybrid, alpha=0.1..0.7)
         │
         │ Tính metrics:
         │   Precision@K, Recall@K, MRR, NDCG@10
         │   Latency (avg, p95)
         │
         ▼
  evaluation/results/benchmark_YYYYMMDD_HHMMSS.csv
  + console output: Table 3, Table 4, Table 5

         Hoặc chạy eval_pipeline (mock + per-scenario):
  python evaluation/eval_pipeline.py
         │
         ▼
  outputs/retrieval_summary.csv
  outputs/cve_linking_summary.csv
  outputs/correlation_summary.csv
  outputs/multi_hop_summary.csv
  outputs/remediation_summary.csv
  + outputs/charts/*.png  (6 biểu đồ)
```

---

## 4. Phân tích từng lớp & kết quả hiện tại

### L1 — Data Collection (`collection_node`)

**Vị trí code:** [app/agents/langgraph/nodes.py](app/agents/langgraph/nodes.py) — hàm `collection_node()` (line ~39)

**Làm gì:**
- Nhận `scan_target` (IP / CIDR / hostname)
- Kiểm tra whitelist `ALLOWED_TARGETS` (bảo mật)
- Chạy Nmap subprocess: `-sV -sC -O --script vuln`
- Lưu kết quả vào Neo4j: `(Host)-[:HAS_PORT]->(Port)-[:RUNS_SERVICE]->(Service)`
- **Chỉ chạy ở iteration 0** — các vòng sau skip (tránh re-scan tốn thời gian)

**Service liên quan:** [app/services/collection_service.py](app/services/collection_service.py)

**Trạng thái hiện tại:** Đã implement đầy đủ. Có whitelist security check. Kết quả Nmap được parse và lưu vào KG.

---

### L2 — Ingestion & Normalization (`planner_node` + pipeline scripts)

**Vị trí code:**
- [app/services/ingestion_service.py](app/services/ingestion_service.py) — chunking, dedup, lưu
- [app/agents/langgraph/nodes.py](app/agents/langgraph/nodes.py) — `planner_node()` (line ~108)
- [scripts/batch_ingest_cve.py](scripts/batch_ingest_cve.py) — batch upload async

**Làm gì:**
- Nhận PDF/DOCX/JSON/XML → extract raw text
- Sliding window chunker: 500 tokens, overlap 50
- SHA256 dedup: bỏ qua chunk đã có
- Lưu vào PostgreSQL (metadata) + MinIO (raw file) + Weaviate (vector)
- `planner_node`: quyết định `search_mode`, trigger KG Completion background

**Trạng thái hiện tại:** Đã ingest toàn bộ dataset CWE v4.19 và NVD CVE. Dedup hoạt động. Batch script xử lý async 5 files song song.

---

### L3 — GraphRAG Retrieval (`retrieval_node`)

**Vị trí code:**
- [app/services/retriever_service.py](app/services/retriever_service.py) — `HybridRetrieverService`
- [app/agents/langgraph/nodes.py](app/agents/langgraph/nodes.py) — `retrieval_node()` (line ~199)

**Làm gì:**
- **Graph search**: Neo4j fulltext index → BFS expansion max 4 hops
- **Vector search**: Weaviate `near_text` / `hybrid` cosine similarity
- **RRF Fusion**: `score(d) = α × RRF_graph(d) + (1-α) × RRF_vec(d)`

**Tham số quan trọng:**

| Tham số | Giá trị | Ý nghĩa |
|---------|---------|---------|
| `alpha` | **0.3** (khuyến nghị) | Trọng số graph; 0.7+ = graph mất tác dụng |
| `k` | 60.0 | RRF constant, tránh overfit rank #1 |
| `limit` | 20 | Số kết quả trả về |

**Kết quả benchmark (run v2, 2026-05-03):**

| Mode | NDCG@10 | P@10 | MRR | Latency |
|------|---------|------|-----|---------|
| B1 Vector-only | 0.2440 | 0.2167 | 0.4722 | 153ms |
| B2 Graph-only | 0.8551 | 0.7917 | 1.0000 | **24ms** |
| **G-0.3 Hybrid** | **0.8741** | **0.8167** | **1.0000** | 66ms |
| G-0.5 Hybrid | 0.8617 | 0.8000 | 1.0000 | 63ms |
| G-0.7 Hybrid | 0.2440 | 0.2167 | 0.4722 | 63ms |

> **Điểm quan trọng:** G-0.7 = B1 (vector-only). Alpha=0.7 làm graph hoàn toàn mất tác dụng.
> Alpha tối ưu: **0.1–0.3**. MRR=1.0 nghĩa là kết quả đầu tiên luôn relevant.

**Per-scenario NDCG@10 (G-0.3):**

| Scenario | NDCG@10 |
|----------|---------|
| Retrieval Accuracy | 0.8830 |
| CVE Linking | 0.7848 |
| Finding Correlation | **0.9608** |
| Multi-hop Reasoning | 0.8305 |
| Remediation Quality | **0.9216** |

---

### L4 — KG Completion (`planner_node` background trigger)

**Vị trí code:**
- [app/services/kg_completion_service.py](app/services/kg_completion_service.py)
- [app/api/v1/routers/kg_completion.py](app/api/v1/routers/kg_completion.py) — `POST /kg/complete`

**Làm gì:**
Suy luận các "missing link" — khi entity A và C có liên quan gián tiếp nhưng chưa có edge trực tiếp:

```
1. Lấy neighbors của A (depth 1-2)
2. Lấy neighbors của C (depth 1-2)
3. Tính Jaccard similarity của 2 neighbor sets
4. Nếu similarity > 0.65:
   → Tạo edge: (A)-[:RELATED_TO {confidence: sim}]->(C)
```

**Tham số:**
- `KG_COMPLETION_MIN_CONFIDENCE = 0.65`
- `KG_COMPLETION_MAX_DEGREE = 2`

**Kết quả hiện tại:** Trigger background ở iteration 0. Output: `{entities_processed, relations_predicted}` trong `AgentState.kg_completion_result`.

---

### L5 — GNN Structural Reasoning (`graph_reasoning_node`)

**Vị trí code:**
- [app/services/gnn_service.py](app/services/gnn_service.py) — GNNService
- [app/agents/langgraph/nodes.py](app/agents/langgraph/nodes.py) — `graph_reasoning_node()` (line ~244)

**Làm gì:**
Tính risk score cho từng vulnerability dựa trên **vị trí trong graph**, không chỉ dựa vào CVSS:

```
risk(v) = 0.50 × pagerank(v)       ← tầm quan trọng trong KG
         + 0.30 × normalized_cvss(v) ← mức độ nguy hiểm (CVSS)
         + 0.20 × betweenness(v)    ← nút bottleneck (nhiều path qua)
```

Sau đó tìm attack paths (BFS, max 4 hops):
```cypher
MATCH path = (src)-[*1..4]->(dst)
WHERE src.id IN $top_risk_entities
RETURN path
```

**Output:**
- `gnn_risk_summary`: `{severity_counts: {critical: N, high: M, ...}, top_risks: [...]}`
- `attack_paths`: `[{source, path_nodes, rel_types, hops, path_risk}]`
- `prioritized_targets`: vulns được ưu tiên scan Nuclei

---

### L6 — Reasoning & Decision (`graph_reasoning_node` phần cuối)

**Vị trí code:** [app/agents/langgraph/nodes.py](app/agents/langgraph/nodes.py) — `graph_reasoning_node()` bước 4

**Làm gì:**
Tổng hợp tất cả context từ L3+L5 thành `graph_context`:

```python
graph_context = {
    "key_entities": [...],      # entities quan trọng nhất
    "attack_paths": [...],      # attack chains tìm được
    "recommendations": {
        "critical_risks": [...],
        "cve_templates": [...],
        "attack_paths": [...]
    }
}
```

Quyết định conditional edge:
- `needs_tools = True` → route sang `tool_node` (chạy Nuclei)
- `needs_tools = False` → route thẳng sang `report_node`

---

### L7 — Execution & Feedback (`tool_node` + `report_node` + `human_approval_node`)

**Vị trí code:**
- [app/agents/langgraph/nodes.py](app/agents/langgraph/nodes.py) — 3 functions cuối
- [app/services/tool_service.py](app/services/tool_service.py) — Nuclei wrapper
- [app/services/report_service.py](app/services/report_service.py) — Markdown report

**`tool_node` làm gì:**
1. Extract CVEs từ retrieval_results
2. Chạy Nuclei: `nuclei -target <scan_target> -severity critical,high`
3. Phân tích CVE exploitability
4. Đếm `new_findings_count` (dùng cho feedback loop)

**`report_node` làm gì:**
Tổng hợp tất cả 7 lớp thành:
- `report` (dict có cấu trúc đầy đủ)
- `report_markdown` (Markdown theo severity)
- `final_answer` (tóm tắt 1 đoạn)

**`human_approval_node` làm gì:**
- Auto-approve (có thể tích hợp manual review gate sau)
- Tăng `loop_iteration`
- Reset `new_findings_count = 0`
- Conditional edge: tiếp tục loop hay END

**Feedback loop:**
```
Sau mỗi cycle: new_findings_count > 0 AND loop_iteration < 3?
  CÓ → quay lại planner với enriched context
  KHÔNG → END (trả về response)
```

---

## 5. Stack công nghệ — Tại sao chọn cái này?

| Công nghệ | Vai trò | Lý do chọn |
|-----------|---------|------------|
| **Neo4j** | Knowledge graph | CYPHER BFS/DFS tìm attack chain hiệu quả hơn JOIN trên RDBMS khi depth > 3 hop |
| **Weaviate** | Vector DB | Tìm ngữ nghĩa: "bypass WAF" → "filter evasion" dù không có từ khóa trùng |
| **Ollama (local)** | LLM + Embedding | Dữ liệu CVE/pentest không gửi ra cloud; zero API cost |
| **PostgreSQL** | Metadata | Lưu document↔chunk relationships, dedup hashes, job status |
| **Redis** | Cache + Queue | Celery message broker cho async tasks; cache workflow state (TTL 1h) |
| **MinIO** | Object storage | Raw documents; S3-compatible API → dễ migrate AWS S3 sau |
| **LangGraph** | Agent orchestration | TypedDict state persisted qua mọi node; conditional edges; không dùng string |
| **FastAPI** | API framework | Native async (asyncio) khớp với Neo4j AsyncDriver và Weaviate async client |
| **Celery** | Async workers | Long-running tasks (Nuclei scan, bulk upsert) không block HTTP request |

---

## 6. Benchmark — Số liệu thực tế

### Tóm tắt kết quả (run v2, 2026-05-03 — kết quả mới nhất)

```
========================================================================================
Table 3. Retrieval Comparison (trung bình trên 12 queries × 5 scenarios)
========================================================================================
Mode                    P@5    R@5   P@10   R@10  F1@10    MRR  NDCG@10    Latency
----------------------------------------------------------------------------------------
B1 (Vector-only)      0.2833 0.0821 0.2167 0.1231 0.1545 0.4722   0.2440   153.1ms
B2 (Graph-only)       0.9500 0.2887 0.7917 0.4617 0.5718 1.0000   0.8551    24.3ms
G-0.1 (Hybrid)        0.9667 0.2963 0.8167 0.4844 0.5957 1.0000   0.8741    68.5ms  ★
G-0.2 (Hybrid)        0.9667 0.2963 0.8167 0.4844 0.5957 1.0000   0.8741    59.0ms  ★
G-0.3 (Hybrid)        0.9667 0.2963 0.8167 0.4844 0.5957 1.0000   0.8741    65.7ms  ★ ← khuyến nghị
G-0.5 (Hybrid)        0.9667 0.2963 0.8000 0.4765 0.5849 1.0000   0.8617    62.8ms
G-0.7 (Hybrid)        0.2833 0.0821 0.2167 0.1231 0.1545 0.4722   0.2440    62.9ms
========================================================================================
★ = joint-best NDCG@10
```

### Các insight quan trọng

1. **GraphRAG > Vector-only 3.6×**: NDCG 0.8741 vs 0.2440
2. **Graph component là yếu tố quyết định**: B2 (graph-only) đã đạt 0.8551 với latency chỉ 24ms
3. **Hybrid thêm +2.2% so với graph-only**: Vector bổ sung cho IDOR và XSS (chunk content)
4. **Alpha tối ưu: 0.1–0.3**. Alpha=0.5 bắt đầu giảm; alpha=0.7 tương đương vector-only
5. **MRR=1.0 cho tất cả hybrid ≤ 0.5 và B2**: kết quả đầu tiên luôn relevant
6. **XSS đạt NDCG=1.0 (hoàn hảo)** sau khi bổ sung 10 CVE nodes vào ground truth
7. **Multi-hop Reasoning cải thiện 24.3%**: từ 0.668 → 0.831 sau khi mở rộng GT

### Lịch sử chạy benchmark

| Run | Ngày | NDCG@10 Hybrid | Thay đổi |
|-----|------|---------------|---------|
| v1 | 2026-05-03 | 0.8355 | Baseline sau fix ground truth |
| **v2** | **2026-05-03** | **0.8741** | +CVE data, +10 XSS nodes GT, limit 15→20 |

---

## 7. Cách chạy project ngay bây giờ

### Yêu cầu

- Docker 24.0+ và Docker Compose 2.20+
- RAM tối thiểu 8GB (Ollama cần 4-6GB)
- 20GB+ disk

### Bước 1 — Chuẩn bị

```bash
cd GraphPent
cp .env.example .env
# Sửa .env: đặt password cho PostgreSQL, Neo4j, MinIO, JWT_SECRET_KEY
```

### Bước 2 — Khởi động services

```bash
make up
# hoặc: docker compose up --build -d

# Theo dõi startup
docker compose logs -f backend ollama
```

### Bước 3 — Bootstrap databases

```bash
make bootstrap
```

### Bước 4 — Pull Ollama models

```bash
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
```

### Bước 5 — Kiểm tra hoạt động

```bash
curl http://localhost:8000/health
```

### Bước 6 — Nạp dữ liệu CVE/CWE

```bash
# Batch ingest toàn bộ CVE data (async, ~30-60 phút tùy dataset size)
python scripts/batch_ingest_cve.py
```

### Bước 7 — Chạy benchmark

```bash
# Benchmark chính (cần API đang chạy)
python evaluation/runner.py

# Evaluation pipeline (dùng mock retriever, không cần API)
python evaluation/eval_pipeline.py

# Sinh biểu đồ từ kết quả evaluation
python plot_evaluation.py
```

### URL truy cập

| Service | URL | Login |
|---------|-----|-------|
| GraphPent API Swagger | http://localhost:8000/docs | — |
| Neo4j Browser | http://localhost:7474 | neo4j / (NEO4J_PASSWORD từ .env) |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin123 |
| Weaviate | http://localhost:8080 | anonymous |

---

## 8. Cấu trúc thư mục — Cần biết file nào?

```
GraphPent/
│
├── app/agents/langgraph/
│   ├── graph.py      ← Định nghĩa DAG: nodes, edges, conditional routing
│   ├── state.py      ← AgentState TypedDict (22+ fields, 7 lớp)
│   └── nodes.py      ← 7 hàm node implementation (577 lines)
│
├── app/services/
│   ├── retriever_service.py    ← HybridRetriever: RRF fusion logic
│   ├── gnn_service.py          ← PageRank + CVSS + Betweenness risk score
│   ├── kg_completion_service.py ← Jaccard link prediction
│   ├── ingestion_service.py    ← Chunking, dedup, index
│   ├── extraction_service.py   ← LLM entity/relation extraction
│   └── graph_service.py        ← Neo4j MERGE upsert
│
├── app/adapters/
│   ├── neo4j_client.py   ← AsyncDriver, MERGE, retry
│   └── weaviate_client.py ← Embed, upsert, near_text search
│
├── evaluation/
│   ├── runner.py          ← Benchmark chính: gọi API thực, đo latency
│   ├── eval_pipeline.py   ← Pipeline 5 evaluators (có mock + real mode)
│   ├── ground_truth.json  ← Labels: relevant_ids cho từng query
│   └── results/           ← CSV outputs từ runner.py
│
├── outputs/               ← CSV + JSON từ eval_pipeline.py
├── scripts/
│   └── batch_ingest_cve.py ← Async batch ingest CVE files
│
├── RESULTS.MD             ← Kết quả benchmark chi tiết (đọc cái này)
├── BENCHMARK_REPORT.md    ← Report dài hơn với phân tích
└── PAPER.md               ← Draft bài báo
```

---

## 9. Câu hỏi thường gặp

**Q: Tại sao alpha=0.3 thay vì 0.7?**

A: Alpha là trọng số cho vector search. `alpha=0.7` nghĩa là 70% vector + 30% graph → graph mất tác dụng. Benchmark cho thấy `alpha=0.7` cho NDCG=0.2440 bằng với vector-only. Dải tối ưu là **0.1–0.3** (70–90% trọng số cho graph).

**Q: RRF_ALPHA trong .env phải đặt bao nhiêu?**

A: Đặt `RRF_ALPHA=0.3`. Đây là giá trị khuyến nghị từ benchmark. Nếu dùng 0.7 (default cũ), hệ thống hoạt động như vector-only.

**Q: Sự khác biệt giữa `evaluation/runner.py` và `evaluation/eval_pipeline.py`?**

A: `runner.py` gọi API thực (`POST /retrieve/query`), đo latency thực tế, output CSV với nhiều modes. `eval_pipeline.py` có 5 evaluators chi tiết (retrieval, CVE linking, finding correlation, multi-hop, remediation) và có thể chạy với mock retriever hoặc real API.

**Q: Feedback loop hoạt động như thế nào?**

A: Sau mỗi cycle workflow, `human_approval_node` kiểm tra `new_findings_count > 0 AND loop_iteration < max_loop_iterations`. Nếu đúng → quay lại `planner_node` với context từ vòng trước. `tool_node` đếm findings mới từ Nuclei scan. Mặc định tối đa 3 vòng.

**Q: Tại sao dùng LangGraph thay vì viết agent tay?**

A: LangGraph enforces typed state (TypedDict) được persist qua mọi node — không mất context. Conditional edges được định nghĩa rõ ràng trong code, không phụ thuộc LLM quyết định routing. Dễ debug vì mỗi node có input/output rõ ràng.

**Q: Mock retriever trong eval_pipeline.py có đáng tin không?**

A: Mock retriever có hardcoded responses để test pipeline logic. Kết quả thực từ `runner.py` (gọi API thực) mới là kết quả báo cáo trong paper. Xem `RESULTS.MD` để có số liệu chính thức.

---

*Cập nhật lần cuối: 2026-05-10 | Liên hệ: chau.ntm137@gmail.com*
