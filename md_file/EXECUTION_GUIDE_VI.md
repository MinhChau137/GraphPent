# 📋 HƯỚNG DẪN THỰC THI & KIỂM TRA HOÀN TOÀN

## 🎯 Tóm tắt các sửa lỗi đã hoàn thành

| Ưu tiên | Vấn đề | Giải pháp | Trạng thái |
|---------|--------|----------|----------|
| **Priority 1** | Giá trị confidence không lưu vào Neo4j | Thêm confidence vào `rel_props` khi upsert | ✅ FIXED |
| **Priority 2** | Nút orphaned do tạo unknown-entity | Chặt chẽ yêu cầu source phải local, reject unknown IDs | ✅ FIXED |
| **Priority 3** | Tên relation type không nhất quán | Normalize sang UPPERCASE (RELATED_TO, không RelatedTo) | ✅ FIXED |

---

## 🚀 BƯỚC 1: CHUẨN BỊ HỆ THỐNG

### 1.1 Xóa dữ liệu cũ từ Neo4j
```bash
cd c:\Users\Admin\OneDrive\ -\ Mobifone\ThS\20252\ANM\GraphPent
docker compose exec -T neo4j cypher-shell -u neo4j -p GraphPent "MATCH (n) DETACH DELETE n;"
```

### 1.2 Restart toàn bộ hệ thống
```bash
docker compose down
docker compose up -d
# Chờ ~15 giây để tất cả services start
Start-Sleep -Seconds 15
docker compose logs backend --tail=5
```

**Xác nhận backend ready:**
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## 📊 BƯỚC 2: KIỂM TRA CHẤT LƯỢNG TRÍCH XUẤT

### 2.1 Chạy test 5-chunk
```bash
docker compose exec -T backend python scripts/batch_extract_neo4j.py --mode extract --limit 5
```

**Mong đợi output:**
- ✅ Total Chunks: 5
- ✅ Successfully Extracted: 4-5
- ✅ Relations per chunk: 1.0-1.5
- ✅ Relation filtering: "X accepted, Y rejected"

### 2.2 Phân tích đồ thị đầu ra
```bash
docker compose exec -T backend bash -c "cd /app && python scripts/analyze_graph.py"
```

**Mong đợi cải thiện:**

| Metric | Trước | Sau | Target |
|--------|-------|-----|--------|
| Confidence (sample) | 0.00 ❌ | 0.75-0.92 ✅ | >0.75 |
| Orphaned nodes | 18/44 ❌ | <10 ✅ | <5 |
| Relation types | RelatedTo, RELATED_TO ❌ | RELATED_TO ✅ | Uniform |
| Cross-chunk ratio | 50% | 50%+ ✅ | >30% |

---

## 🧪 BƯỚC 3: KIỂM CHỨNG TỪNG FIX

### 3.1 Fix #1: Confidence Storage ✅

**Query kiểm tra:**
```
docker compose exec -T backend bash -c "cd /app && python -c \"
import asyncio
from neo4j import AsyncGraphDatabase
from app.config.settings import settings

async def check():
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    async with driver.session() as session:
        result = await session.run('MATCH ()-[r]->() RETURN avg(r.confidence) as avg, min(r.confidence) as min, max(r.confidence) as max LIMIT 1')
        rec = [r async for r in result]
        if rec:
            print(f\"Average Confidence: {rec[0].get('avg', 0):.2f}\")
            print(f\"Min Confidence: {rec[0].get('min', 0):.2f}\")
            print(f\"Max Confidence: {rec[0].get('max', 0):.2f}\")
    await driver.close()

asyncio.run(check())
\""
```

**Xác nhận:** Min ≥ 0.75, Avg ≥ 0.80

### 3.2 Fix #2: Orphaned Node Prevention ✅

**Query kiểm tra:**
```
docker compose exec -T backend bash -c "cd /app && python -c \"
import asyncio
from neo4j import AsyncGraphDatabase
from app.config.settings import settings

async def check():
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    async with driver.session() as session:
        result = await session.run('MATCH (n) WHERE NOT (n)--() RETURN count(n) as orphaned')
        rec = [r async for r in result]
        total = (await session.run('MATCH (n) RETURN count(n) as total')).single()
        orphaned = rec[0].get('orphaned', 0) if rec else 0
        total_nodes = total.get('total', 0) if total else 0
        pct = 100 * orphaned / total_nodes if total_nodes > 0 else 0
        print(f\"Orphaned Nodes: {orphaned}/{total_nodes} ({pct:.1f}%)\")
    await driver.close()

asyncio.run(check())
\""
```

**Xác nhận:** Orphaned < 20% (mục tiêu <10%)

### 3.3 Fix #3: Relation Type Normalization ✅

**Query kiểm tra:**
```
docker compose exec -T backend bash -c "cd /app && python -c \"
import asyncio
from neo4j import AsyncGraphDatabase
from app.config.settings import settings

async def check():
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    async with driver.session() as session:
        result = await session.run('MATCH ()-[r]->() RETURN distinct type(r) as rel_type ORDER BY rel_type')
        rec = [r async for r in result]
        print('Relation Types in Database:')
        for r in rec:
            print(f\"  - {r.get('rel_type')}\")
    await driver.close()

asyncio.run(check())
\""
```

**Xác nhận:** Chỉ thấy `MITIGATED_BY`, `AFFECTS`, `RELATED_TO` (không có mixed case)

---

## 🔄 BƯỚC 4: KIỂM SOÁT CHẤT LƯỢNG HOÀN TOÀN

### 4.1 Chạy test 10-chunk với monitoring
```bash
# Terminal 1: Chạy extraction
docker compose exec -T backend python scripts/batch_extract_neo4j.py --mode extract --limit 10

# Terminal 2: Monitor logs (trong khi terminal 1 chạy)
docker compose logs backend -f --tail=50 | Select-String "Relation filtering|✅|✓|❌"
```

### 4.2 Kết quả kỳ vọng

**Extraction logs:**
```
Relation filtering: X accepted, Y rejected  ← ít rejected hơn
✅ Rel rel-1 (MITIGATED_BY): LOCAL ...      ← confidence được lưu
✓ Rel rel-2 (AFFECTS): CROSS-CHUNK ...     ← cross-chunk hoạt động
❌ Rel rel-3: invalid/unknown IDs ...       ← orphaned nodes được filter
```

### 4.3 Chạy phân tích hoàn toàn
```bash
docker compose exec -T backend bash -c "cd /app && python scripts/analyze_graph.py"
```

**Metrics cần kiểm tra:**

| Thành phần | Dấu hiệu ✅ | Dấu hiệu ❌ |
|-----------|---------|---------|
| Confidence | Min ≥0.75, Avg ≥0.80 | Min <0.75 |
| Orphaned | <30% nodes orphaned | >50% orphaned |
| Relation types | Uniform UPPERCASE | Mixed RelatedTo/RELATED_TO |
| Connectivity | >50% nodes connected | <30% connected |

---

## 📈 BƯỚC 5: THỰC HIỆN TRÍCH XUẤT TOÀN BỘ

### 5.1 Khởi động trích xuất 348K chunks

**Option A: Chạy toàn bộ (29 giờ)**
```bash
docker compose exec -T backend python scripts/batch_extract_neo4j.py --mode extract
```

**Option B: Chạy theo batch với monitoring**
```bash
# Batch 1: 1000 chunks
docker compose exec -T backend python scripts/batch_extract_neo4j.py --mode extract --limit 1000

# Check progress
docker compose exec -T neo4j cypher-shell -u neo4j -p GraphPent "MATCH (n) RETURN count(n) as nodes; MATCH ()-[r]->() RETURN count(r) as relations;"

# Batch 2: 1000 chunks tiếp theo
docker compose exec -T backend python scripts/batch_extract_neo4j.py --mode extract --limit 1000 --skip 1000
```

### 5.2 Giám sát trong quá trình chạy

```bash
# Terminal monitoring GPU
docker compose exec -T backend nvidia-smi

# Monitor entities & relations mỗi 10 phút
watch -n 600 'docker compose exec -T backend bash -c "cd /app && python -c \"
import asyncio
from neo4j import AsyncGraphDatabase
from app.config.settings import settings

async def check():
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    async with driver.session() as session:
        nodes = (await session.run('MATCH (n) RETURN count(n) as count')).single()
        rels = (await session.run('MATCH ()-[r]->() RETURN count(r) as count')).single()
        print(f\"📊 Nodes: {nodes.get('count', 0)}, Relations: {rels.get('count', 0)}\")
    await driver.close()

asyncio.run(check())
\""'
```

---

## ✅ DANH SÁCH KIỂM TRA CUỐI CÙNG

Trước khi coi là hoàn thành, xác nhận:

- [ ] ✅ Priority 1: Tất cả relations có confidence >0.75 (không phải 0.00)
- [ ] ✅ Priority 2: Orphaned nodes <20% (không phải 40%)
- [ ] ✅ Priority 3: Chỉ có 3 relation types (MITIGATED_BY, AFFECTS, RELATED_TO)
- [ ] ✅ Cross-chunk relations >40% từ tổng relations
- [ ] ✅ Success rate ≥95% trên 10-chunk test
- [ ] ✅ GPU được sử dụng (nvidia-smi shows activity)
- [ ] ✅ Extraction time stable ~18-20s/chunk

---

## 🆘 TROUBLESHOOTING

### Vấn đề: Confidence vẫn là 0.00
**Giải pháp:** 
```bash
# Clear DB
docker compose exec neo4j cypher-shell "MATCH (n) DETACH DELETE n;"
# Restart backend để reload code
docker compose restart backend
```

### Vấn đề: Quá nhiều orphaned nodes
**Giải pháp:** 
```bash
# Check LLM output format
docker compose logs backend --tail=100 | Select-String "unknown-entity|invalid/unknown"
# Có thể cần điều chỉnh system prompt
```

### Vấn đề: Extraction quá chậm
**Giải pháp:**
```bash
# Kiểm tra GPU usage
docker compose exec -T backend nvidia-smi
# Nếu không dùng GPU, restart Ollama
docker compose restart ollama
```

---

## 📞 Tiếp theo

Sau khi xác nhận tất cả 3 fixes hoạt động ✅:
1. Chạy trích xuất toàn bộ 348K chunks
2. Phân tích pattern trong knowledge graph
3. Tối ưu query performance trên Neo4j
4. Xây dựng API search interface
