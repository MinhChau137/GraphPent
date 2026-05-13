# GraphPent — Plan hoàn thiện từng lớp

> Cập nhật: 2026-05-10 | Dựa trên audit code thực tế

---

## Tóm tắt nhanh

| Layer | Trạng thái | Việc cần làm | Ưu tiên |
|-------|-----------|--------------|---------|
| L1 Collection | ✅ Hoàn chỉnh | Nhỏ: thêm re-scan option | Thấp |
| L2 Ingestion | ✅ Hoàn chỉnh | Fix async bug; thêm extraction_jobs | Trung bình |
| L3 Retrieval | ⚠️ Bug alpha | **Fix alpha=0.7→0.3 trong nodes.py** | **Cao** |
| L4 KG Completion | ✅ Hoàn chỉnh | Thêm evaluation metrics | Trung bình |
| L5 GNN | ⚠️ Weight sai doc | Làm rõ/tune weights; ablation study | **Cao** |
| L6 Reasoning | ✅ Hoàn chỉnh | Cải thiện recommendation rules | Thấp |
| L7 Execution | ✅ Hoàn chỉnh | PDF export; import loaders | Thấp |
| Evaluation | ⚠️ Còn hạn chế | Mở rộng ground truth; fix BaseRetriever | **Cao** |

---

## Các vấn đề cần fix ngay (Critical)

### 1. L3 — Alpha hardcode sai (nodes.py:216)

**Vấn đề:**
```python
# nodes.py dòng 212-216 — HIỆN TẠI (SAI)
alpha_map = {
    "vector_only": 1.0,
    "graph_only":  0.0,
    "hybrid":      0.7   ← hardcode, bỏ qua settings
}
```
Benchmark xác nhận alpha=0.7 cho NDCG=0.2440 (bằng vector-only). Optimal là **0.3**.

**Fix:**
```python
# nodes.py — CẦN SỬA
from app.config.settings import settings as _settings

alpha_map = {
    "vector_only": 1.0,
    "graph_only":  0.0,
    "hybrid":      _settings.RRF_ALPHA   ← đọc từ .env
}
```

Đồng thời cập nhật `.env` và `.env.example`:
```bash
RRF_ALPHA=0.3   # đổi từ 0.7 → 0.3
```

---

### 2. L5 — GNN weights không khớp tài liệu

**Vấn đề:** Code và tài liệu nói khác nhau về trọng số.

| Nguồn | pagerank | severity | betweenness |
|-------|---------|---------|-------------|
| `gnn_service.py` (code thực) | **0.25** | **0.60** | **0.15** |
| README / ONBOARDING (tài liệu) | 0.50 | 0.30 | 0.20 |
| `settings.py` default | 0.25 | 0.60 | 0.15 |

**Việc cần làm:** Chạy ablation study để xác định bộ weights tối ưu, rồi cập nhật tài liệu cho nhất quán.

```bash
# Thử 3 bộ weights, đo NDCG@10 workflow end-to-end
POST /risk/score với từng cấu hình:
  Config A: pagerank=0.50, severity=0.30, betweenness=0.20  ← theo README
  Config B: pagerank=0.25, severity=0.60, betweenness=0.15  ← theo code hiện tại
  Config C: pagerank=0.40, severity=0.40, betweenness=0.20  ← balanced
```

---

### 3. Evaluation — BaseRetriever chưa kết nối thực

**Vấn đề:** `eval_pipeline.py` có `BaseRetriever.search()` và `.correlate_finding()` là `raise NotImplementedError`. MockRetriever có data cứng. Không có cầu nối với API thực.

**Việc cần làm:** Thêm `RealAPIRetriever` vào `eval_pipeline.py`:

```python
class RealAPIRetriever(BaseRetriever):
    """Gọi POST /retrieve/query để lấy kết quả thực."""
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def search(self, query, mode, top_k=10, alpha=0.3):
        import httpx
        resp = httpx.post(f"{self.base_url}/retrieve/query",
                         json={"query": query, "limit": top_k,
                               "mode": mode, "alpha": alpha})
        items = resp.json().get("results", [])
        return [RetrievedItem(id=r["id"], score=r["final_score"],
                              text=r["content"], metadata=r.get("metadata"))
                for r in items]

    def correlate_finding(self, finding_text, mode, top_k=5, alpha=0.3):
        results = self.search(finding_text, mode, top_k, alpha)
        matched_cwes = self.extract_cwes(results)
        matched_cves = self.extract_cves(results)
        return {
            "matched_cwes": list(matched_cwes),
            "matched_cves": list(matched_cves),
            "decision_true_positive": len(matched_cwes) > 0
        }
```

---

## Plan chi tiết từng lớp

---

### L1 — Data Collection

**Trạng thái:** Hoàn chỉnh ✅

**Vấn đề nhỏ:** Chỉ scan ở `loop_iteration == 0`. Nếu scan_target thay đổi trong feedback loop (planner chọn target mới từ GNN), L1 không re-scan.

**Việc cần làm:**

- [ ] Xem xét thêm flag `force_rescan=True` trong planner khi `scan_target` thay đổi so với lần trước
- [ ] Thêm test case: scan target không có trong whitelist → PermissionError được handle đúng
- [ ] Verify Nmap output format: confirm `collect_and_store()` parse được output từ `-sV -sC -O --script vuln`

**Kết quả cần có sau khi hoàn thiện:**
```
collection_results = [{
  "hosts": N,
  "open_ports": M,
  "host_ips": [...],
  "services": [{"ip","port","service","version"}, ...],
  "new_findings_count": K
}]
→ Neo4j: (Host)-[:HAS_PORT]->(Port)-[:RUNS_SERVICE]->(Service)
```

---

### L2 — Ingestion & Normalization

**Trạng thái:** Hoàn chỉnh, có 2 vấn đề nhỏ ⚠️

**Vấn đề 1 — Async inconsistency (`ingestion_service.py:82`):**
```python
# HIỆN TẠI (legacy sync query trong async context)
existing = session.query(Chunk).filter(Chunk.hash == chunk_hash).first()

# CẦN SỬA
result = await session.execute(
    select(Chunk).where(Chunk.hash == chunk_hash)
)
existing = result.scalar_one_or_none()
```

**Vấn đề 2 — TODO extraction_jobs (`extraction_service.py:171`):**
```python
# TODO: Thêm bảng extraction_jobs và lưu entities_json
# Cần thiết để: audit trail, retry failed chunks, dashboard stats
```

**Việc cần làm:**

- [ ] **Fix:** Sửa `session.query()` → `await session.execute(select(...))` trong `ingestion_service.py:82`
- [ ] **Thêm:** Bảng `extraction_jobs` trong PostgreSQL schema:
  ```sql
  CREATE TABLE extraction_jobs (
      id SERIAL PRIMARY KEY,
      chunk_id INTEGER REFERENCES chunks(id),
      status VARCHAR(20),  -- pending / running / done / failed
      entities_json JSON,
      relations_json JSON,
      error_message TEXT,
      created_at TIMESTAMP DEFAULT NOW(),
      updated_at TIMESTAMP DEFAULT NOW()
  );
  ```
- [ ] **Test:** Chạy `batch_ingest_cve.py` → verify không có SQLAlchemy warning về sync/async

---

### L3 — GraphRAG Retrieval

**Trạng thái:** ⚠️ Bug alpha hardcode — ảnh hưởng trực tiếp đến kết quả

**Việc cần làm:**

- [ ] **Fix critical:** `nodes.py:216` — alpha đọc từ `settings.RRF_ALPHA` (xem mục Critical #1)
- [ ] **Fix:** `.env` và `.env.example` — đổi `RRF_ALPHA=0.7` → `RRF_ALPHA=0.3`
- [ ] **Verify:** Chạy benchmark sau khi fix, confirm NDCG@10 = 0.8741 (không thay đổi so với run v2 vì runner.py dùng alpha trực tiếp qua API)
- [ ] **Test thêm:** Mở rộng ground truth với 5-10 queries ngoài 4 queries hiện tại
- [ ] **Document:** Cập nhật README: "RRF_ALPHA mặc định = 0.3, không phải 0.7"

**Kết quả benchmark hiện tại (để so sánh sau khi fix):**

| Mode | NDCG@10 |
|------|---------|
| Vector-only (α=1.0) | 0.2440 |
| Graph-only (α=0.0) | 0.8551 |
| **Hybrid α=0.3** | **0.8741** ← target |
| Hybrid α=0.7 (bug hiện tại trong workflow) | 0.2440 |

---

### L4 — Knowledge Graph Completion

**Trạng thái:** Hoàn chỉnh ✅

**Ghi chú quan trọng:** Implementation thực tế dùng **LLM** (không phải Jaccard như tài liệu mô tả).

```python
# kg_completion_service.py — thực tế
async def _predict_relations(entity_id, neighbors):
    prompt = f"Given entity {entity_id} with neighbors {neighbors}, predict missing security relationships..."
    response = await llm_client.generate(prompt)
    return _parse_predictions(response)  # JSON parse + validate vs _VALID_REL_TYPES
```

**Việc cần làm:**

- [ ] **Cập nhật tài liệu:** ONBOARDING.md L4 section — thay "Jaccard similarity" bằng mô tả LLM-based prediction
- [ ] **Thêm evaluation metrics cho L4:**
  - Precision/Recall của predicted relations (dùng held-out edges làm ground truth)
  - Tỉ lệ relations được validate vs bị reject (confidence < 0.65)
  - So sánh: graph với KG completion vs không có → NDCG@10 thay đổi bao nhiêu?
- [ ] **Test:** Verify `_VALID_REL_TYPES` (23 types) cover đủ các loại relations trong domain pentest

**Metrics cần đo:**
```
kg_completion_result = {
  "entities_processed": N,
  "relations_predicted": M,
  "relations_stored": K,     ← K/M = acceptance rate (target > 60%)
  "conflicts_detected": C
}
```

---

### L5 — GNN Structural Reasoning

**Trạng thái:** ⚠️ Weights cần clarify và tune

**Việc cần làm:**

- [ ] **Ablation study:** Chạy 3 bộ weights (xem mục Critical #2), đo tác động đến attack path quality
- [ ] **Quyết định bộ weights chính thức** và cập nhật đồng thời: code + `.env.example` + tài liệu
- [ ] **Thêm evaluation cho L5:**
  - Đo `attack_paths` quality: % path nào thực sự dẫn đến exploitable vuln
  - Đo `risk_score` calibration: node có CVSS 9.8 có risk_score > 0.75 không?
- [ ] **Verify GDS fallback:** Test trên môi trường không có Neo4j GDS plugin → fallback degree-based có hoạt động không

**Công thức hiện tại (code):**
```
risk(v) = 0.25 × pagerank(v)
         + 0.60 × normalized_cvss(v)
         + 0.15 × betweenness(v)
```

**Metrics cần đo:**
```
Top-3 risk nodes: precision (có trong ground truth high-risk?)
Attack paths found: coverage (% known attack chains được phát hiện?)
Latency: compute_risk_scores() cho graph 10K nodes
```

---

### L6 — Reasoning & Decision

**Trạng thái:** Hoàn chỉnh ✅

**Vấn đề:** Recommendation rules hiện tại rất đơn giản (3 rules cố định).

**Việc cần làm:**

- [ ] **Cải thiện recommendation rules** — thêm 2 rules:
  ```python
  # Rule 4: Network topology context
  if collection_results and attack_paths:
      open_services = collection_results[0].get("services", [])
      for path in attack_paths:
          if any(s["service"] in path["path_nodes"] for s in open_services):
              recommendations.append(
                  f"Service {s['service']} on port {s['port']} matches attack path"
              )

  # Rule 5: KG completion thêm liên kết mới
  if kg_completion_result.get("relations_stored", 0) > 0:
      recommendations.append(
          f"KG Completion added {N} new relations — re-run retrieval for updated context"
      )
  ```
- [ ] **Test:** Verify `needs_tools` logic đúng — test case: query không có CVE, không có scan_target → `needs_tools=False`
- [ ] **Đo:** Accuracy của routing decision (needs_tools=True khi nên có, False khi không cần)

---

### L7 — Execution & Feedback

**Trạng thái:** Hoàn chỉnh với 2 feature chưa implement

**Vấn đề 1 — PDF export stub (`export_service.py:231`):**
```python
raise NotImplementedError("PDF export coming in future release")
```

**Vấn đề 2 — import loaders (`import_service.py:125,135,145`):**
```python
# TODO: Implement file loading
# TODO: Implement API loading
# TODO: Implement database loading
```

**Việc cần làm:**

- [ ] **PDF export** (nếu cần cho thesis): implement bằng `reportlab` hoặc `weasyprint`:
  ```python
  from reportlab.lib.pagesizes import A4
  from reportlab.platypus import SimpleDocTemplate, Paragraph
  # render markdown_report → PDF
  ```
- [ ] **Import loaders:** Implement file loader tối thiểu (JSON/CSV) cho `import_service.py`
- [ ] **Feedback loop test:** Chạy workflow với `max_loop_iterations=2`, verify:
  - `loop_iteration` tăng đúng
  - `new_findings_count` reset đúng
  - Planner enriched query ở vòng 2 có `high_risk:` prefix

**Test end-to-end:**
```bash
POST /workflow/multi-agent {
  "query": "SQL injection vulnerabilities",
  "scan_target": "127.0.0.1",
  "max_loop_iterations": 2
}
# Expected: 2 vòng, report có đủ collection + retrieval + gnn + tools
```

---

## Evaluation — Hoàn thiện framework đo lường

**Trạng thái:** ⚠️ Ground truth nhỏ, RealRetriever chưa kết nối eval_pipeline

### Việc cần làm:

**1. Mở rộng ground truth (`evaluation/ground_truth.json`):**

| Dataset | Hiện tại | Mục tiêu |
|---------|---------|----------|
| retrieval_queries | 4 queries | 10+ queries |
| cve_queries | 1 query | 5+ queries |
| finding_cases | 3-5 cases | 10+ cases |
| multi_hop_queries | 2 queries | 5+ queries |
| remediation_cases | 3 cases | 8+ cases |

Thêm queries cho các loại vuln chưa có: Command Injection, Path Traversal, XXE, SSRF, Deserialization.

**2. Kết nối eval_pipeline với API thực:**

```python
# Thêm vào eval_pipeline.py (xem mục Critical #3)
class RealAPIRetriever(BaseRetriever):
    ...
```

Cập nhật entry point:
```python
if __name__ == "__main__":
    # Chọn retriever
    retriever = RealAPIRetriever("http://localhost:8000")  # thực
    # retriever = MockGraphRAGRetriever()  # mock (test không cần API)

    pipeline = GraphRAGEvaluationPipeline(retriever)
    pipeline.run_all("evaluation/ground_truth.json", ...)
```

**3. Thêm per-layer metrics:**

| Layer | Metric cần đo | Cách đo |
|-------|--------------|---------|
| L1 | % hosts discovered vs total | Manual verify với known topology |
| L2 | Extraction precision (entities) | Sample 20 chunks, manual annotation |
| L3 | NDCG@10, MRR, latency | `runner.py` (đã có) |
| L4 | KG completion precision | Held-out edge test |
| L5 | Risk score calibration | Top-5 risks vs CVSS ordering |
| L6 | Routing accuracy | Test 10 queries: needs_tools T/F |
| L7 | Workflow end-to-end | 5 test scenarios với expected report |

**4. Benchmark sau khi fix alpha:**

```bash
# Sau khi fix RRF_ALPHA=0.3 trong .env
python evaluation/runner.py
# Expected: run v3 với kết quả tương đương run v2 (0.8741)
# Nếu thấp hơn → có vấn đề khác cần điều tra
```

---

## Thứ tự thực hiện (theo ưu tiên)

### Tuần 1 — Fix critical bugs

```
[x] Đọc plan này
[ ] Fix nodes.py:216 — alpha đọc từ settings
[ ] Cập nhật .env và .env.example: RRF_ALPHA=0.3
[ ] Fix ingestion_service.py:82 — async session
[ ] Chạy lại runner.py → verify NDCG không thay đổi (benchmark đã dùng API trực tiếp)
```

### Tuần 2 — Evaluation hoàn thiện

```
[ ] Thêm RealAPIRetriever vào eval_pipeline.py
[ ] Mở rộng ground_truth.json: +6 retrieval queries, +4 CVE queries
[ ] Chạy eval_pipeline với real retriever
[ ] So sánh kết quả Mock vs Real retriever
```

### Tuần 3 — GNN ablation & L4 eval

```
[ ] Chạy ablation: 3 bộ GNN weights (A, B, C)
[ ] Đo tác động đến attack path quality
[ ] Chọn bộ weights chính thức, cập nhật settings + tài liệu
[ ] Thêm L4 evaluation: held-out edge precision
```

### Tuần 4 — Polish & tổng hợp

```
[ ] Thêm extraction_jobs table
[ ] Cải thiện recommendation rules (rule 4, 5)
[ ] End-to-end workflow test (2-vòng feedback loop)
[ ] Cập nhật ONBOARDING.md: L4 dùng LLM (không phải Jaccard)
[ ] Tổng hợp per-layer metrics vào BENCHMARK_REPORT.md
```

---

## File cần sửa — tổng hợp

| File | Dòng | Thay đổi |
|------|------|---------|
| `app/agents/langgraph/nodes.py` | 216 | `"hybrid": 0.7` → `_settings.RRF_ALPHA` |
| `.env` | - | `RRF_ALPHA=0.3` |
| `.env.example` | - | `RRF_ALPHA=0.3` |
| `app/services/ingestion_service.py` | 82 | `session.query()` → `await session.execute(select(...))` |
| `evaluation/eval_pipeline.py` | ~215 | Thêm `RealAPIRetriever` class |
| `evaluation/ground_truth.json` | - | Thêm queries mới |
| `readme/ONBOARDING.md` | L4 section | Sửa "Jaccard" → "LLM-based prediction" |

---

*Tổng: ~4 tuần, ưu tiên cao nhất là fix alpha (1 dòng code, impact lớn)*
