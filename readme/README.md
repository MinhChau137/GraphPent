# GraphPent

> Phiên bản: v0.3.0 | Cập nhật: 05/2026

---

## Mục lục

1. [Bức tranh tổng thể](#1-bức-tranh-tổng-thể)
2. [Kiến trúc 7 lớp](#2-kiến-trúc-7-lớp)
3. [Activity Diagram — Luồng hoạt động đầy đủ](#3-activity-diagram--luồng-hoạt-động-đầy-đủ)
4. [Phân tích từng lớp — Input / Output / Kết quả](#4-phân-tích-từng-lớp--input--output--kết-quả)
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
1. **Hybrid Knowledge Graph** — Neo4j (quan hệ có cấu trúc) + Weaviate (ngữ nghĩa vector) + RRF Fusion
2. **AgentState TypedDict** — state có cấu trúc, tồn tại qua mọi node LangGraph
3. **Feedback Loop** — tự động re-plan khi có findings mới (tối đa 3 vòng)

---

## 2. Kiến trúc 7 lớp

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

7 lớp → 7 LangGraph nodes:

```
collection_node → planner_node → retrieval_node → graph_reasoning_node
    (L1+L2)          (L2+L4)          (L3)               (L5+L6)
                                                              │
                                         ┌────────────────────┤
                                        YES                   NO
                                         │               (no tools)
                                    tool_node          report_node
                                       (L7)               (L7)
                                         │                   ▲
                                         └─────────────────── ┘
                                                   │
                                       human_approval_node (L7)
                                         │               │
                                    loop lại           END
                                    (planner)
```

---

## 3. Activity Diagram — Luồng hoạt động đầy đủ

### 3.1 Pipeline dữ liệu (offline — build knowledge base)

```
NGUỒN DỮ LIỆU
  data/cwec_v4.19.1.xml        ← CWE v4.19 (1000+ weakness)
  data/nvdcve-2.0-*.json       ← NVD CVE dataset
  data/cvelistV5-main/         ← CVE List V5
        │
        ▼
[PHASE 4: INGESTION]  POST /ingest/document
  1. Detect format: PDF / DOCX / JSON / XML
  2. Chunking: sliding window, 500 tokens, overlap 50
  3. SHA256 dedup → skip nếu đã có
  4. Lưu 3 nơi song song:
     ├── PostgreSQL: documents + chunks tables
     ├── MinIO:      raw/{uuid}_{filename}
     └── Weaviate:   embed (nomic-embed-text, 768-dim) → index
        │
        ▼
[PHASE 5: EXTRACTION]  POST /extract/chunk/{chunk_id}
  1. SELECT content FROM chunks WHERE id = chunk_id
  2. Detect type: CWE XML / NVD JSON / generic
  3. LLM (llama3.2:3b): extract → JSON {entities[], relations[]}
  4. Filter: entity.confidence >= 0.85, relation.confidence >= 0.75
  5. Retry 4x, exponential backoff (5s → 40s)
        │
        ▼
[PHASE 6: GRAPH UPSERT]  Neo4j
  MERGE (n:Weakness {id: $id})
    ON CREATE SET n.name, n.created_at
    ON MATCH  SET n.updated_at
  MERGE (src)-[r:TYPE {confidence, source_chunk_id}]->(tgt)
  → Idempotent, batch transaction, retry 3x
```

### 3.2 Multi-agent workflow (online — khi analyst chạy pentest)

```
REQUEST: POST /workflow/multi-agent
{
  "query": "Find vulnerabilities on target",
  "scan_target": "192.168.1.100",
  "max_loop_iterations": 3
}
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ NODE 1: collection_node   (L1 + L2)                         │
│                                                             │
│ ĐIỀU KIỆN CHẠY: scan_target != null AND loop_iteration == 0│
│                                                             │
│ INPUT từ state:                                             │
│   state["scan_target"]      → "192.168.1.100"               │
│   state["loop_iteration"]   → 0                             │
│                                                             │
│ XỬ LÝ:                                                      │
│   1. Kiểm tra ALLOWED_TARGETS whitelist                     │
│   2. Gọi CollectionService.collect_and_store(target)        │
│      → subprocess Nmap: -sV -sC -O --script vuln            │
│   3. Parse kết quả → lưu Neo4j:                             │
│      (Host)-[:HAS_PORT]->(Port)-[:RUNS_SERVICE]->(Service)  │
│                                                             │
│ OUTPUT ghi vào state:                                       │
│   state["collection_results"] = [{                          │
│     "hosts": 3,                                             │
│     "open_ports": 12,                                       │
│     "host_ips": ["192.168.1.100", ...],                     │
│     "new_findings_count": 15                                │
│   }]                                                        │
│   state["new_findings_count"] = 15                          │
│   state["current_step"]      = "planner"                    │
│                                                             │
│ EDGE CASE:                                                  │
│   target không có trong ALLOWED_TARGETS → PermissionError   │
│   Nmap không cài → FileNotFoundError, skip (không crash)    │
│   loop_iteration > 0 → skip (trả về state hiện tại)        │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ NODE 2: planner_node   (L2 + L4)                            │
│                                                             │
│ INPUT từ state:                                             │
│   state["query"]             → "Find vulnerabilities..."    │
│   state["loop_iteration"]    → 0                            │
│   state["collection_results"]→ [{hosts, host_ips, ...}]     │
│   state["scan_target"]       → "192.168.1.100"              │
│                                                             │
│ XỬ LÝ (iteration 0):                                        │
│   ─ L4: Trigger KG Completion background (fire-and-forget)  │
│     kg_completion_service.complete_graph(                   │
│       max_entities=10, max_degree=2)                        │
│   ─ Query enrichment với host_ips từ collection:            │
│     "Find vulnerabilities... discovered_hosts:192.168.1.100"│
│   ─ Search mode:                                            │
│       "CVE-" trong query → graph_only                       │
│       ngược lại          → hybrid                           │
│   ─ needs_tools = True nếu:                                 │
│       target trong whitelist OR collection_results có data  │
│       OR query chứa "scan"/"exploit"/"test"/"verify"        │
│                                                             │
│ XỬ LÝ (iteration > 0):                                      │
│   ─ Lấy risk_targets từ GNNService.get_prioritized_targets  │
│   ─ Enrich query: "... high_risk:cwe-89,cve-2024-1234"      │
│   ─ Cập nhật scan_target theo top risk node                 │
│                                                             │
│ OUTPUT ghi vào state:                                       │
│   state["plan"] = {                                         │
│     "query":        "Find vulnerabilities... discovered_hosts:...",
│     "search_mode":  "hybrid",                               │
│     "needs_tools":  True,                                   │
│     "loop_iteration": 0,                                    │
│     "risk_targets": [],       ← [] ở iteration 0           │
│     "kg_completion_triggered": True,                        │
│     "plan_created_at": "2026-05-10T10:30:00"                │
│   }                                                         │
│   state["kg_completion_result"] = {                         │
│     "status": "triggered_background",                       │
│     "iteration": 0                                          │
│   }                                                         │
│   state["prioritized_targets"] = []  ← [] ở iteration 0    │
│   state["current_step"] = "retrieval"                       │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ NODE 3: retrieval_node   (L3)                               │
│                                                             │
│ INPUT từ state:                                             │
│   state["query"]        → "Find vulnerabilities..."         │
│   state["plan"]["search_mode"] → "hybrid"                   │
│                                                             │
│ XỬ LÝ:                                                      │
│   alpha_map = {                                             │
│     "vector_only": 1.0,                                     │
│     "graph_only":  0.0,                                     │
│     "hybrid":      0.7   ← NOTE: code dùng 0.7, paper khuyến nghị 0.3
│   }                                                         │
│   → HybridRetrieverService.hybrid_retrieve(                 │
│       query=query, limit=20, alpha=0.7, mode="hybrid"       │
│     )                                                       │
│                                                             │
│   Bên trong hybrid_retrieve:                                │
│     ┌─ Graph: Neo4j fulltext + BFS 4 hops ─┐               │
│     └─ Vector: Weaviate near_text cosine  ─┘               │
│              ↓ RRF Fusion                                   │
│     score(d) = α·RRF_graph(d) + (1-α)·RRF_vec(d)           │
│     RRF_x(d) = 1/(60 + rank_x(d))                          │
│                                                             │
│ OUTPUT ghi vào state:                                       │
│   state["retrieval_results"] = [                            │
│     {                                                       │
│       "id":          "cwe-89",                              │
│       "content":     "Improper Neutralization...",          │
│       "final_score": 0.0523,                                │
│       "metadata": {                                         │
│         "type": "Weakness",                                 │
│         "source": "neo4j"                                   │
│       }                                                     │
│     },                                                      │
│     ... (tối đa 20 items)                                   │
│   ]                                                         │
│   state["current_step"] = "graph_reasoning"                 │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ NODE 4: graph_reasoning_node   (L5 + L6)                    │
│                                                             │
│ INPUT từ state:                                             │
│   state["retrieval_results"] → list 20 items                │
│   state["attack_paths"]      → [] (lần đầu)                │
│                                                             │
│ XỬ LÝ bước 1 — Extract key entities từ top 5 results:      │
│   Với mỗi result trong retrieval_results[:5]:               │
│     Infer type từ ID pattern:                               │
│       "CVE-..." → type="CVE"                                │
│       "CWE-..." → type="Weakness"                           │
│       còn lại   → type="chunk"                              │
│   key_entities = [                                          │
│     {"id": "cwe-89", "type": "Weakness", "score": 0.052},  │
│     {"id": "CVE-2023-50164", "type": "CVE", "score": 0.041}│
│   ]                                                         │
│                                                             │
│ XỬ LÝ bước 2 — L5: GNN risk summary:                       │
│   GNNService.get_risk_summary()                             │
│   gnn_risk_summary = {                                      │
│     "severity_counts": {"critical": 2, "high": 5, ...},    │
│     "top_risks": [                                          │
│       {"id": "cwe-89", "risk_score": 0.87,                  │
│        "pagerank": 0.92, "cvss": 9.8,                       │
│        "risk_tier": "CRITICAL"},                            │
│       ...                                                   │
│     ]                                                       │
│   }                                                         │
│                                                             │
│ XỬ LÝ bước 3 — L5: Attack paths (BFS max 4 hops):          │
│   Với mỗi source_id trong top_risks[:2]:                    │
│     GNNService.find_attack_paths(                           │
│       source_id="cwe-89",                                   │
│       target_label="CVE",                                   │
│       max_hops=4                                            │
│     )                                                       │
│   attack_paths = [                                          │
│     {                                                       │
│       "source": "cwe-89",                                   │
│       "path_nodes": ["cwe-89","consequence-auth","CVE-..."],│
│       "rel_types": ["HAS_CONSEQUENCE","MAPPED_TO"],         │
│       "hops": 2,                                            │
│       "path_risk": 0.74                                     │
│     }                                                       │
│   ]                                                         │
│                                                             │
│ XỬ LÝ bước 4 — L6: Build recommendations:                  │
│   critical nodes   → "High-risk nodes: cwe-89 — prioritise" │
│   CVE entities     → "2 CVE(s) — run Nuclei templates"      │
│   attack_paths     → "Shortest: 2 hops (path_risk=0.740)"   │
│                                                             │
│ QUYẾT ĐỊNH conditional edge:                                │
│   needs_tools = state["plan"]["needs_tools"]                │
│              AND len(retrieval_results) > 0                 │
│   True  → current_step = "tool"                             │
│   False → current_step = "report"                           │
│                                                             │
│ OUTPUT ghi vào state:                                       │
│   state["graph_context"] = {                                │
│     "key_entities":    [{"id","type","score"}, ...],        │
│     "gnn_risk":        {severity_counts, top_risks},        │
│     "attack_paths":    [...] (tối đa 5),                    │
│     "recommendations": [                                    │
│       "High-risk nodes: cwe-89 — prioritise for scanning",  │
│       "2 CVE(s) retrieved — run Nuclei templates",          │
│       "Shortest attack path: 2 hops (path_risk=0.740)"      │
│     ]                                                       │
│   }                                                         │
│   state["gnn_risk_summary"] = {severity_counts, top_risks}  │
│   state["attack_paths"]     = [...] (tối đa 5)              │
│   state["current_step"]     = "tool" hoặc "report"          │
└─────────────────────────────────────────────────────────────┘
      │
      ├── needs_tools == True ──────────────────────────────────┐
      │                                                         │
      ▼                                                         │
┌─────────────────────────────────────────────────────────────┐│
│ NODE 5: tool_node   (L7 — Execution)                        ││
│                                                             ││
│ INPUT từ state:                                             ││
│   state["retrieval_results"] → list (lấy [:5] để extract)  ││
│   state["scan_target"]       → "192.168.1.100"              ││
│   state["new_findings_count"]→ 0 (lần đầu)                 ││
│                                                             ││
│ XỬ LÝ bước 1 — Extract CVEs từ top 5 retrieval results:    ││
│   Với result trong retrieval_results[:5]:                   ││
│     if "CVE" in result["metadata"]["type"]:                 ││
│       cves.append(result["id"])                             ││
│   cves = ["CVE-2023-50164", "CVE-2022-22965"]               ││
│                                                             ││
│ XỬ LÝ bước 2 — Nuclei scan (nếu scan_target có):           ││
│   PentestToolService.run_nuclei_scan(                       ││
│     target="192.168.1.100",                                 ││
│     severity="critical,high"                                ││
│   )                                                         ││
│   nuclei_result = {                                         ││
│     "findings": [                                           ││
│       {"template_id": "CVE-2023-50164",                     ││
│        "severity": "critical",                              ││
│        "matched_at": "http://192.168.1.100/login"},         ││
│       ...                                                   ││
│     ]                                                       ││
│   }                                                         ││
│   nuclei_findings_count = len(findings)                     ││
│                                                             ││
│ XỬ LÝ bước 3 — CVE exploitability analysis:                ││
│   Với mỗi cve_id trong cves[:3]:                            ││
│     tool_results.append({                                   ││
│       "cve_id": "CVE-2023-50164",                           ││
│       "analysis": "Potentially exploitable - check Nuclei", ││
│       "recommended_action": "Run Nuclei scan"               ││
│     })                                                      ││
│                                                             ││
│ OUTPUT ghi vào state:                                       ││
│   state["tool_results"] = [                                 ││
│     {                                                       ││
│       "tool": "nuclei",                                     ││
│       "source": "nuclei",                                   ││
│       "target": "192.168.1.100",                            ││
│       "template_id": "CVE-2023-50164",                      ││
│       "severity": "critical",                               ││
│       "matched_at": "http://192.168.1.100/login"            ││
│     },                                                      ││
│     {                                                       ││
│       "cve_id": "CVE-2022-22965",                           ││
│       "analysis": "Potentially exploitable",                ││
│       "recommended_action": "Run Nuclei scan"               ││
│     }                                                       ││
│   ]                                                         ││
│   state["new_findings_count"] = 0 + nuclei_findings_count   ││
│   state["current_step"] = "report"                          ││
└─────────────────────────────────────────────────────────────┘│
      │                                                         │
      └────────────────────────────────────────────────────────┘
      │                                                         │
      ▼  (cả hai nhánh đều tới đây)                             │
┌─────────────────────────────────────────────────────────────┐
│ NODE 6: report_node   (L7 — Output)                         │
│                                                             │
│ INPUT từ state (tổng hợp tất cả 7 lớp):                     │
│   state["query"]              → query gốc                   │
│   state["collection_results"] → L1 output                   │
│   state["kg_completion_result"]→ L4 output                  │
│   state["gnn_risk_summary"]   → L5 output                   │
│   state["attack_paths"]       → L5 output                   │
│   state["graph_context"]      → L6 output                   │
│   state["retrieval_results"]  → L3 output                   │
│   state["tool_results"]       → L7 tool output              │
│   state["prioritized_targets"]→ L6 output                   │
│   state["loop_iteration"]     → vòng hiện tại               │
│                                                             │
│ XỬ LÝ:                                                      │
│   report_content = {                                        │
│     "query":          "...",                                │
│     "timestamp":      "2026-05-10T10:30:45",                │
│     "loop_iteration": 0,                                    │
│     "collection": {                                         │
│       "scans_performed": 1,                                 │
│       "summary": {hosts:3, open_ports:12, ...}              │
│     },                                                      │
│     "retrieval": {                                          │
│       "total_results": 20,                                  │
│       "top_results":   [...5 items...]                      │
│     },                                                      │
│     "kg_completion": {status:"triggered_background",...},   │
│     "gnn": {                                                │
│       "risk_summary":        {severity_counts, top_risks},  │
│       "attack_paths":        [...5 items...],               │
│       "prioritized_targets": [...5 items...]                │
│     },                                                      │
│     "reasoning": {                                          │
│       "key_entities":    [...],                             │
│       "recommendations": [...]                              │
│     },                                                      │
│     "tools": {                                              │
│       "analyses_performed": 3,                              │
│       "findings": [...tool_results...]                      │
│     },                                                      │
│     "status": "completed"                                   │
│   }                                                         │
│   → ReportService.generate_markdown_report(report_content)  │
│   → final_answer = "Analysis complete (0 iteration(s)).     │
│     Retrieved 20 resources, 2 attack path(s) found,         │
│     3 tool finding(s). Top recommendation: ..."             │
│                                                             │
│ OUTPUT ghi vào state:                                       │
│   state["report"]          = report_content (dict đầy đủ)   │
│   state["report_markdown"] = "# Security Report\n..."       │
│   state["final_answer"]    = "Analysis complete..."         │
│   state["current_step"]    = "human_approval"               │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ NODE 7: human_approval_node   (L7 — Feedback Loop Gate)     │
│                                                             │
│ INPUT từ state:                                             │
│   state["loop_iteration"]    → 0                            │
│   state["new_findings_count"]→ 3 (từ Nuclei)               │
│   state["max_loop_iterations"]→ 3                           │
│                                                             │
│ XỬ LÝ:                                                      │
│   audit_log("human_approval_node", {approved: True, ...})   │
│   → loop_iteration += 1  (0 → 1)                            │
│   → new_findings_count = 0  (reset cho vòng tiếp theo)      │
│                                                             │
│ OUTPUT ghi vào state:                                       │
│   state["human_approval"]    = True                         │
│   state["approval_timestamp"]= "2026-05-10T10:31:02"        │
│   state["loop_iteration"]    = 1   ← đã tăng               │
│   state["new_findings_count"]= 0   ← đã reset              │
│                                                             │
│ CONDITIONAL EDGE (trong graph.py):                          │
│   new_findings_count_TRƯỚC_RESET > 0                        │
│   AND loop_iteration_MỚI (1) < max_loop_iterations (3)     │
│     TRUE  → quay lại planner_node (vòng 2)                  │
│     FALSE → END                                             │
└─────────────────────────────────────────────────────────────┘
      │
      ├─ CÓ findings mới & còn vòng → planner_node (iteration=1)
      └─ Không → END: trả về state cuối cùng làm response
```

---

## 4. Phân tích từng lớp — Input / Output / Kết quả

---

### L1 — Data Collection

**Node:** `collection_node` | **File:** [app/agents/langgraph/nodes.py](../app/agents/langgraph/nodes.py)

**Điều kiện chạy:**
- `state["scan_target"]` không null
- `state["loop_iteration"] == 0` (bỏ qua ở các vòng sau)

**INPUT (đọc từ AgentState):**

| Field | Kiểu | Ví dụ | Mô tả |
|-------|------|-------|-------|
| `scan_target` | `str` | `"192.168.1.100"` | IP / CIDR / hostname cần scan |
| `loop_iteration` | `int` | `0` | Vòng hiện tại (chỉ scan ở vòng 0) |

**XỬ LÝ:**
```
CollectionService.collect_and_store("192.168.1.100")
  → subprocess: nmap -sV -sC -O --script vuln 192.168.1.100
  → parse XML output
  → Neo4j: MERGE (h:Host {ip})-[:HAS_PORT]->(p:Port)-[:RUNS_SERVICE]->(s:Service)
```

**OUTPUT (ghi vào AgentState):**

| Field | Kiểu | Ví dụ | Mô tả |
|-------|------|-------|-------|
| `collection_results` | `List[Dict]` | `[{"hosts":3, "open_ports":12, "host_ips":["192.168.1.100"], "new_findings_count":15}]` | Kết quả Nmap đã parse |
| `new_findings_count` | `int` | `15` | Số entity Neo4j mới được tạo |
| `current_step` | `str` | `"planner"` | Chỉ dẫn node tiếp theo |

**Kết quả hiện tại:** Implement đầy đủ. Security check whitelist có. Skip graceful khi Nmap chưa cài.

---

### L2 — Ingestion & Normalization

**Node:** `planner_node` (planning) + pipeline offline | **File:** [app/services/ingestion_service.py](../app/services/ingestion_service.py)

**INPUT (pipeline offline):**

| Nguồn | Kiểu | Ví dụ |
|-------|------|-------|
| Uploaded file | `multipart/form-data` | `cwec_v4.19.1.xml`, `nvdcve-2.0.json` |
| Hoặc batch | Script args | `python scripts/batch_ingest_cve.py` |

**XỬ LÝ pipeline:**
```
1. Format detection → extract raw text
2. Sliding window chunking: chunk_size=500 tokens, overlap=50
3. SHA256(content) → skip chunk nếu hash đã tồn tại trong PostgreSQL
4. Lưu song song:
   - PostgreSQL: INSERT INTO documents(...); INSERT INTO chunks(document_id, content, weaviate_uuid, hash)
   - MinIO: PUT raw/{uuid}_{filename}
   - Weaviate: embed via Ollama nomic-embed-text → POST /v1/objects với vector 768-dim
```

**OUTPUT (pipeline offline):**

```json
{
  "document_id": 42,
  "chunks_count": 318,
  "minio_path": "graphrag-bucket/raw/uuid_cwec_v4.19.1.xml",
  "weaviate_indexed": 318,
  "duplicates_skipped": 12
}
```

**OUTPUT (planner_node trong workflow):**

| Field | Kiểu | Ví dụ |
|-------|------|-------|
| `plan["search_mode"]` | `str` | `"hybrid"` hoặc `"graph_only"` |
| `plan["needs_tools"]` | `bool` | `True` |
| `plan["enriched_query"]` | `str` | `"...discovered_hosts:192.168.1.100"` |
| `kg_completion_result` | `Dict` | `{"status":"triggered_background","iteration":0}` |

**Kết quả hiện tại:** Đã ingest toàn bộ CWE v4.19 + NVD CVE. Dedup hoạt động. Batch async 5 files song song.

---

### L3 — GraphRAG Retrieval

**Node:** `retrieval_node` | **File:** [app/services/retriever_service.py](../app/services/retriever_service.py)

**INPUT (đọc từ AgentState):**

| Field | Kiểu | Ví dụ | Mô tả |
|-------|------|-------|-------|
| `query` | `str` | `"SQL injection authentication bypass"` | Query gốc (không enriched ở bước này) |
| `plan["search_mode"]` | `str` | `"hybrid"` | `vector_only` / `graph_only` / `hybrid` |

**XỬ LÝ:**
```python
alpha_map = {"vector_only": 1.0, "graph_only": 0.0, "hybrid": 0.7}
alpha = alpha_map[search_mode]  # = 0.7 cho hybrid

HybridRetrieverService.hybrid_retrieve(query, limit=20, alpha=0.7, mode="hybrid")
```

Bên trong `hybrid_retrieve`:
```
GRAPH SEARCH (Neo4j):
  CALL db.index.fulltext.queryNodes("entity_text", $query)
  YIELD node, score
  → BFS expansion: MATCH (n)-[*1..4]->(neighbor)
  → Trả về: [{id, content, graph_score, rank_graph}]

VECTOR SEARCH (Weaviate):
  nearText: {concepts: [query], certainty: 0.7}
  → HNSW cosine similarity top-20
  → Trả về: [{chunk_id, content, vector_score, rank_vec}]

RRF FUSION:
  score(d) = 0.7 × (1/(60 + rank_graph(d)))
           + 0.3 × (1/(60 + rank_vec(d)))
  → Sort descending → top 20
```

**OUTPUT (ghi vào AgentState):**

| Field | Kiểu | Ví dụ |
|-------|------|-------|
| `retrieval_results` | `List[Dict]` (max 20) | Xem bên dưới |
| `current_step` | `str` | `"graph_reasoning"` |

```json
retrieval_results = [
  {
    "id": "cwe-89",
    "content": "Improper Neutralization of Special Elements used in an SQL Command",
    "final_score": 0.0523,
    "metadata": {"type": "Weakness", "source": "neo4j", "severity": "high"}
  },
  {
    "id": "chunk_sqli_01",
    "content": "SQL injection can bypass authentication by...",
    "final_score": 0.0441,
    "metadata": {"type": "chunk", "source": "weaviate", "document_id": 42}
  },
  ...
]
```

**Kết quả benchmark (run v2, 2026-05-03):**

| Mode | Alpha | NDCG@10 | P@10 | MRR | Latency p95 |
|------|-------|---------|------|-----|-------------|
| B1 Vector-only | 1.0 | 0.2440 | 0.2167 | 0.4722 | 153ms |
| B2 Graph-only | 0.0 | 0.8551 | 0.7917 | 1.0000 | 24ms |
| **G-0.3 Hybrid** | **0.3** | **0.8741** | **0.8167** | **1.0000** | **66ms** |
| G-0.5 Hybrid | 0.5 | 0.8617 | 0.8000 | 1.0000 | 63ms |
| G-0.7 Hybrid | 0.7 | 0.2440 | 0.2167 | 0.4722 | 63ms |

> **Lưu ý code vs paper:** Code hiện tại dùng `alpha=0.7` trong `retrieval_node` (hardcode). Paper khuyến nghị `alpha=0.3` từ benchmark. Nếu muốn chạy đúng theo khuyến nghị, cần sửa dòng `"hybrid": 0.7` → `"hybrid": 0.3` hoặc đọc từ `RRF_ALPHA` trong `.env`.

**Per-scenario NDCG@10 với G-0.3:**

| Scenario | NDCG@10 |
|----------|---------|
| Retrieval Accuracy | 0.8830 |
| CVE Linking | 0.7848 |
| Finding Correlation | 0.9608 |
| Multi-hop Reasoning | 0.8305 |
| Remediation Quality | 0.9216 |

---

### L4 — Knowledge Graph Completion

**Trigger:** `planner_node` iteration 0 (background) | **File:** [app/services/kg_completion_service.py](../app/services/kg_completion_service.py)

**INPUT:**

| Tham số | Giá trị | Nguồn |
|---------|---------|-------|
| `max_entities` | `10` | Hardcode trong `planner_node` |
| `max_degree` | `2` | Hardcode (= `KG_COMPLETION_MAX_DEGREE` env) |

**XỬ LÝ (Jaccard link prediction):**
```
Với mỗi cặp (entity_A, entity_C) chưa có edge trực tiếp:

  neighbors_A = Neo4j MATCH (A)-[*1..2]->(n) RETURN n.id
  neighbors_C = Neo4j MATCH (C)-[*1..2]->(n) RETURN n.id

  jaccard = |neighbors_A ∩ neighbors_C| / |neighbors_A ∪ neighbors_C|

  Nếu jaccard >= 0.65:
    MERGE (A)-[:RELATED_TO {confidence: jaccard, inferred: true}]->(C)
```

**OUTPUT (ghi vào AgentState):**

| Field | Kiểu | Ví dụ |
|-------|------|-------|
| `kg_completion_result` | `Dict` | `{"entities_processed": 10, "relations_predicted": 7, "relations_stored": 5, "status": "completed"}` |

> Kết quả được ghi vào state SAU khi background task hoàn thành. Ở iteration 0 chỉ có `{"status":"triggered_background"}`.

**Kết quả hiện tại:** Background trigger hoạt động. Neo4j graph được enrich với inferred edges có nhãn `inferred: true`.

---

### L5 — GNN Structural Reasoning

**Node:** `graph_reasoning_node` (phần GNN) | **File:** [app/services/gnn_service.py](../app/services/gnn_service.py)

**INPUT (đọc từ AgentState + gọi service):**

| Nguồn | Tham số | Mô tả |
|-------|---------|-------|
| State | `retrieval_results[:5]` | Top 5 results để extract entity IDs |
| GNNService | `get_risk_summary()` | Không cần input — tính trên toàn graph |
| GNNService | `find_attack_paths(source_id, target_label="CVE", max_hops=4)` | Từng source node trong top_risks[:2] |

**XỬ LÝ risk scoring:**
```
risk(v) = 0.50 × pagerank(v)
         + 0.30 × normalized_cvss(v)   [cvss / 10.0]
         + 0.20 × betweenness(v)

Dùng Neo4j GDS (Graph Data Science):
  CALL gds.pageRank.stream(...)
  CALL gds.betweenness.stream(...)
  → Nếu GDS không có → fallback: in-degree normalization
```

**OUTPUT (ghi vào AgentState):**

| Field | Kiểu | Ví dụ |
|-------|------|-------|
| `gnn_risk_summary` | `Dict` | Xem bên dưới |
| `attack_paths` | `List[Dict]` (max 5) | Xem bên dưới |

```json
gnn_risk_summary = {
  "severity_counts": {"critical": 2, "high": 8, "medium": 15, "low": 31},
  "top_risks": [
    {
      "id": "cwe-89",
      "name": "SQL Injection",
      "risk_score": 0.87,
      "pagerank": 0.92,
      "cvss": 9.8,
      "risk_tier": "CRITICAL"
    },
    {
      "id": "CVE-2023-50164",
      "name": "Apache Struts RCE",
      "risk_score": 0.74,
      "risk_tier": "HIGH"
    }
  ]
}

attack_paths = [
  {
    "source": "cwe-89",
    "path_nodes": ["cwe-89", "consequence-auth-bypass", "CVE-2023-50164"],
    "rel_types": ["HAS_CONSEQUENCE", "MAPPED_TO"],
    "hops": 2,
    "path_risk": 0.74
  }
]
```

**Kết quả hiện tại:** GNNService implement đầy đủ với Neo4j GDS. Có fallback khi GDS plugin chưa cài.

---

### L6 — Reasoning & Decision

**Node:** `graph_reasoning_node` (phần cuối) | **File:** [app/agents/langgraph/nodes.py](../app/agents/langgraph/nodes.py)

**INPUT (từ các bước trước trong cùng node):**

| Biến nội bộ | Ví dụ |
|-------------|-------|
| `key_entities` (từ bước 1) | `[{"id":"cwe-89","type":"Weakness","score":0.052}]` |
| `gnn_risk_summary` (từ bước 2) | `{severity_counts, top_risks}` |
| `attack_paths` (từ bước 3) | `[{source, path_nodes, hops, path_risk}]` |
| `state["plan"]["needs_tools"]` | `True` |

**XỬ LÝ — build recommendations:**
```python
# Rule 1: Critical/High risk nodes
critical = [r for r in top_risks if r["risk_tier"] in ("CRITICAL", "HIGH")]
if critical:
    recommendations.append(f"High-risk nodes: {ids} — prioritise for scanning")

# Rule 2: CVE entities in retrieval
if cve_entities:
    recommendations.append(f"{N} CVE(s) — run Nuclei with matching templates")

# Rule 3: Shortest attack path
if attack_paths:
    shortest = min(attack_paths, key=lambda p: p["hops"])
    recommendations.append(f"Shortest path: {hops} hops (path_risk={risk:.3f})")
```

**OUTPUT (ghi vào AgentState):**

| Field | Kiểu | Ví dụ |
|-------|------|-------|
| `graph_context` | `Dict` | Xem bên dưới |
| `current_step` | `str` | `"tool"` hoặc `"report"` |

```json
graph_context = {
  "key_entities": [
    {"id": "cwe-89", "type": "Weakness", "score": 0.052},
    {"id": "CVE-2023-50164", "type": "CVE", "score": 0.041}
  ],
  "gnn_risk": { ... },
  "attack_paths": [ ... ],
  "recommendations": [
    "High-risk nodes detected: cwe-89, CVE-2023-50164 — prioritise for scanning",
    "2 CVE(s) retrieved — run Nuclei with matching templates",
    "Shortest attack path: 2 hops (path_risk=0.740)"
  ]
}
```

---

### L7 — Execution & Feedback

**Nodes:** `tool_node` + `report_node` + `human_approval_node`

#### tool_node

**INPUT (đọc từ AgentState):**

| Field | Kiểu | Ví dụ |
|-------|------|-------|
| `retrieval_results` | `List[Dict]` | Lấy [:5] để extract CVEs |
| `scan_target` | `str \| None` | `"192.168.1.100"` |
| `new_findings_count` | `int` | `0` (tích lũy từ trước) |

**OUTPUT (ghi vào AgentState):**

| Field | Kiểu | Ví dụ |
|-------|------|-------|
| `tool_results` | `List[Dict]` | Nuclei findings + CVE analyses |
| `new_findings_count` | `int` | `3` (cũ + Nuclei mới) |

```json
tool_results = [
  {
    "tool": "nuclei",
    "source": "nuclei",
    "target": "192.168.1.100",
    "template_id": "CVE-2023-50164",
    "severity": "critical",
    "matched_at": "http://192.168.1.100/login"
  },
  {
    "cve_id": "CVE-2022-22965",
    "analysis": "Potentially exploitable - check with Nuclei",
    "recommended_action": "Run Nuclei scan"
  }
]
```

#### report_node

**INPUT:** Tất cả fields của AgentState (tổng hợp 7 lớp)

**OUTPUT (ghi vào AgentState):**

| Field | Kiểu | Ví dụ |
|-------|------|-------|
| `report` | `Dict` | Structured dict theo 7 lớp |
| `report_markdown` | `str` | `"# Security Report\n## Critical Findings..."` |
| `final_answer` | `str` | `"Analysis complete (0 iteration(s)). Retrieved 20 resources, 2 attack path(s)..."` |

#### human_approval_node

**INPUT (đọc từ AgentState):**

| Field | Kiểu | Giá trị |
|-------|------|---------|
| `loop_iteration` | `int` | `0` → sẽ thành `1` |
| `new_findings_count` | `int` | `3` → sẽ reset về `0` |

**OUTPUT (ghi vào AgentState):**

| Field | Kiểu | Ví dụ |
|-------|------|-------|
| `human_approval` | `bool` | `True` |
| `approval_timestamp` | `str` | `"2026-05-10T10:31:02"` |
| `loop_iteration` | `int` | `1` (tăng thêm 1) |
| `new_findings_count` | `int` | `0` (reset) |

**Conditional edge logic (trong graph.py):**
```python
def should_continue_loop(state):
    # Đọc TRƯỚC KHI human_approval_node reset
    new_findings = state.get("new_findings_count", 0)
    # Đọc SAU KHI human_approval_node tăng
    loop_iteration = state.get("loop_iteration", 0)
    max_iter = state.get("max_loop_iterations", 3)

    if new_findings > 0 and loop_iteration < max_iter:
        return "planner"   # quay lại
    return END
```

> **Điểm tinh tế:** `human_approval_node` tăng `loop_iteration` trước khi conditional edge check. Vì vậy ở vòng 0: `loop_iteration` sau tăng = 1, so sánh với `max_loop_iterations=3` → 1 < 3 → tiếp tục nếu có findings.

---

## 5. Stack công nghệ — Tại sao chọn cái này?

| Công nghệ | Vai trò | Lý do chọn |
|-----------|---------|------------|
| **Neo4j** | Knowledge graph | CYPHER BFS/DFS tìm attack chain: depth > 3 hop hiệu quả hơn JOIN trên RDBMS |
| **Weaviate** | Vector DB | Tìm ngữ nghĩa: "bypass WAF" → "filter evasion" dù không có từ khóa trùng |
| **Ollama (local)** | LLM + Embedding | CVE/pentest data không gửi ra cloud; zero API cost |
| **PostgreSQL** | Metadata | document↔chunk FK, SHA256 dedup, job status |
| **Redis** | Cache + Queue | Celery broker cho async tasks; cache workflow state TTL 1h |
| **MinIO** | Object storage | Raw documents; S3-compatible → dễ migrate AWS S3 |
| **LangGraph** | Agent orchestration | TypedDict state persist qua mọi node; conditional edges rõ ràng trong code |
| **FastAPI** | API framework | Native async khớp với Neo4j AsyncDriver + Weaviate async client |
| **Celery** | Async workers | Long-running tasks (Nuclei scan, bulk upsert) không block HTTP |

---

## 6. Benchmark — Số liệu thực tế

### Kết quả chính thức (run v2, 2026-05-03)

```
========================================================================================
Table 3. Retrieval Comparison (avg trên 12 queries × 5 scenarios)
========================================================================================
Mode                    P@5    R@5   P@10   R@10  F1@10    MRR  NDCG@10    Latency
----------------------------------------------------------------------------------------
B1 (Vector-only)      0.2833 0.0821 0.2167 0.1231 0.1545 0.4722   0.2440   153.1ms
B2 (Graph-only)       0.9500 0.2887 0.7917 0.4617 0.5718 1.0000   0.8551    24.3ms
G-0.1 (Hybrid)        0.9667 0.2963 0.8167 0.4844 0.5957 1.0000   0.8741    68.5ms  ★
G-0.2 (Hybrid)        0.9667 0.2963 0.8167 0.4844 0.5957 1.0000   0.8741    59.0ms  ★
G-0.3 (Hybrid)        0.9667 0.2963 0.8167 0.4844 0.5957 1.0000   0.8741    65.7ms  ★ ← paper
G-0.5 (Hybrid)        0.9667 0.2963 0.8000 0.4765 0.5849 1.0000   0.8617    62.8ms
G-0.7 (Hybrid)        0.2833 0.0821 0.2167 0.1231 0.1545 0.4722   0.2440    62.9ms
========================================================================================
★ = best NDCG@10
```

**5 insights quan trọng:**
1. GraphRAG > Vector-only **3.6×** (NDCG 0.8741 vs 0.2440)
2. Graph component là chủ lực: B2 alone = 0.8551, latency **24ms** (6.3× nhanh hơn vector)
3. Hybrid thêm +2.2% so với pure graph (vector bổ sung IDOR và XSS)
4. **Alpha=0.7 = vector-only**: graph bị át hoàn toàn — cài đặt sai phá hủy hệ thống
5. MRR=1.0 cho tất cả hybrid ≤0.5: result đầu luôn relevant

---

## 7. Cách chạy project ngay bây giờ

```bash
# 1. Chuẩn bị
cp .env.example .env
# Sửa .env: POSTGRES_PASSWORD, NEO4J_PASSWORD, MINIO_ROOT_PASSWORD, JWT_SECRET_KEY

# 2. Khởi động
make up
docker compose logs -f backend ollama

# 3. Bootstrap databases
make bootstrap

# 4. Pull Ollama models (~2.3GB)
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text

# 5. Kiểm tra
curl http://localhost:8000/health

# 6. Nạp dữ liệu (cần chạy 1 lần)
python scripts/batch_ingest_cve.py

# 7. Benchmark
python evaluation/runner.py
```

**URL truy cập:**

| Service | URL |
|---------|-----|
| Swagger UI | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 |
| MinIO Console | http://localhost:9001 |

---

## 8. Cấu trúc thư mục — Cần biết file nào?

```
GraphPent/
├── app/agents/langgraph/
│   ├── graph.py      ← DAG: nodes, edges, conditional routing
│   ├── state.py      ← AgentState TypedDict (22+ fields, 7 lớp)
│   └── nodes.py      ← 7 node functions (source of truth cho I/O)
│
├── app/services/
│   ├── retriever_service.py     ← RRF fusion logic (alpha, k, scoring)
│   ├── gnn_service.py           ← PageRank + CVSS + Betweenness
│   ├── kg_completion_service.py ← Jaccard link prediction
│   ├── ingestion_service.py     ← Chunking, dedup, multi-store index
│   └── extraction_service.py   ← LLM entity/relation extraction
│
├── evaluation/
│   ├── runner.py          ← Benchmark thực: gọi API, đo latency
│   ├── ground_truth.json  ← Ground truth labels cho 5 scenarios
│   └── results/           ← CSV outputs (mới nhất: benchmark_20260503_081607.csv)
│
├── readme/
│   ├── RESULTS.MD         ← Số liệu benchmark chính thức (đọc đây trước)
│   └── BENCHMARK_REPORT.md ← Phân tích chi tiết
│
└── .env                   ← RRF_ALPHA=0.3 (quan trọng — không dùng 0.7)
```

---

## 9. Câu hỏi thường gặp

**Q: RRF_ALPHA trong .env đặt bao nhiêu?**
→ `RRF_ALPHA=0.3`. Alpha=0.7 (default cũ) làm graph mất tác dụng hoàn toàn, NDCG giảm từ 0.8741 xuống 0.2440.

**Q: Code `retrieval_node` dùng alpha=0.7, benchmark dùng 0.3 — cái nào đúng?**
→ Benchmark dùng API endpoint `/retrieve/query` với `alpha` truyền vào. `retrieval_node` hiện hardcode 0.7 trong `alpha_map`. Để nhất quán với paper, sửa `"hybrid": 0.7` → `"hybrid": 0.3` trong `nodes.py:216`.

**Q: Feedback loop hoạt động thế nào?**
→ `tool_node` đếm `new_findings_count` từ Nuclei. `human_approval_node` tăng `loop_iteration` và reset counter. Conditional edge trong `graph.py` check: `new_findings > 0 AND loop_iteration < max`. Nếu đúng → quay `planner_node`.

**Q: Tại sao graph-only (B2) lại nhanh hơn vector-only (B1)?**
→ B2: Neo4j fulltext index + BFS = 24ms. B1: Ollama embed query (mạng) + Weaviate HNSW search = 153ms. Embedding inference trên CPU là bottleneck chính của vector search.

**Q: KG Completion có block retrieval không?**
→ Không. `planner_node` dùng `asyncio.ensure_future()` — fire-and-forget. Retrieval chạy ngay mà không đợi KG completion xong.

---

*Cập nhật: 2026-05-10 | Contact: chau.ntm137@gmail.com*
