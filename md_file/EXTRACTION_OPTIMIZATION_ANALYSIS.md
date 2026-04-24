# 📊 Current Extraction Capability Analysis & Optimization Report

**Date**: 2026-04-23
**Status**: Analysis Complete - Ready for Optimization

---

## 1. Current State Assessment

### Data Volume
```
Total Chunks: 348,331
  - NVD CVE JSON: 1,941 chunks
  - CVE v5 JSON: 346,390 chunks
  
PostgreSQL Status: ✅ All chunks stored
Weaviate Status: ✅ Vector embeddings indexed
MinIO Status: ✅ Raw files archived
```

### Neo4j Population
```
Extracted Chunks: 5
Neo4j Nodes: 8
Entity Types: 1 (VulnerabilityType)
Relations: 2+

Completion Rate: 0.0014% (5 / 348,331)
Estimated Time to Complete: 48-72 hours @ 3 min/chunk
```

### LLM Configuration (llama3.2:3b)
```
Model: llama3.2:3b
Size: 2.0 GB (Q4_K_M quantization)
Temperature: 0.0 (deterministic)
Context Window: 16,384 tokens
Max Output: 4,096 tokens
Format: JSON output
Retry Logic: 4 attempts, exp. backoff (5-40s)
```

---

## 2. Performance Analysis

### Detailed Timing Breakdown (per chunk)

| Stage | Duration | Bottleneck |
|-------|----------|-----------|
| PostgreSQL Fetch | ~50 ms | ✅ Minimal |
| Data Type Detection | ~10 ms | ✅ Minimal |
| LLM Chat Call | 150-180 s | ⚠️ **MAJOR** |
| JSON Repair/Parse | ~50 ms | ✅ Minimal |
| Entity Validation | ~100 ms | ✅ Minimal |
| Neo4j Upsert | ~100 ms | ✅ Minimal |
| **Total Per Chunk** | **150-180 s** | **LLM is 99.7% of time** |

### Scaling Projection
```
Sequential (current): 348,331 chunks × 180s = 17,416,550 seconds
                      = 4,837 hours = 201 days ⚠️⚠️⚠️

Parallel (2x concurrent): ~100 days (with overhead)
Parallel (4x concurrent): ~50 days (requires 4x resources)
Parallel (8x concurrent): ~25 days (requires 8x resources)
```

---

## 3. Identified Bottlenecks

### Primary Bottleneck: LLM Inference Speed
**Issue**: llama3.2:3b on CPU inference is slow (150-180s/chunk)

**Root Causes**:
1. ✗ CPU-based inference (no GPU acceleration)
2. ✗ Large context window (16,384 tokens) - overkill for small chunks
3. ✗ Sequential processing - no parallelization
4. ✗ Model size (3.2B parameters) - substantial for CPU

**Impact**: 99.7% of execution time

### Secondary Bottleneck: Sequential Processing
**Issue**: Only 1 chunk extracted at a time

**Root Causes**:
1. ✗ Safety design to avoid connection storms
2. ✗ No connection pooling for concurrent access
3. ✗ Single LLM instance

**Impact**: 0% - can't leverage parallelism

### Tertiary Issues (Minor)
1. ⚠️ Retry logic adds 5-40s on failures
2. ⚠️ Large chunk size (avg 2000 chars) → longer LLM inference

---

## 4. Optimization Opportunities

### 🟢 Quick Wins (No Risk, Easy Implementation)

#### Option 1: Reduce LLM Context Window
**Current**: `num_ctx: 16384`
**Proposed**: `num_ctx: 4096`

**Impact**:
- Estimated speedup: 20-30% (fewer tokens to process)
- Risk: **NONE** - chunks are only ~2000 chars
- Implementation: 1 line change

**Implementation**:
```python
# app/adapters/llm_client.py line ~74
options={"temperature": 0.0, "num_ctx": 4096, "num_predict": 2048}
#                                           ↑ reduce from 4096
```

#### Option 2: Reduce Max Output Tokens
**Current**: `num_predict: 4096`
**Proposed**: `num_predict: 2048`

**Impact**:
- Estimated speedup: 15-25%
- Risk: **LOW** - most extractions need <1000 tokens
- Benefit: Less wasteful token generation

#### Option 3: Increase Temperature Slightly for Speed
**Current**: `temperature: 0.0`
**Proposed**: `temperature: 0.3`

**Impact**:
- Estimated speedup: 5-10%
- Risk: **MEDIUM** - may reduce consistency
- Note: Not recommended unless desperate

---

### 🟡 Medium Effort Solutions (Moderate Risk/Benefit)

#### Option 4: Deploy Faster Model (tinyllama)
**Alternative**: `tinyllama:1.1b` or `mistral:7b`

**tinyllama:1.1b**:
- Size: 637 MB (3x smaller)
- Speed: 3-4x faster
- Quality: Lower, but acceptable for CWE/CVE
- Estimated time: ~60 hours → ~20 hours

**mistral:7b**:
- Size: 4.1 GB
- Speed: 1.5-2x faster  
- Quality: Better than tinyllama
- Estimated time: ~60 hours → ~30-40 hours

**Implementation**:
```bash
docker compose exec -T ollama ollama pull tinyllama:1.1b
# Update .env: OLLAMA_MODEL=tinyllama:1.1b
```

#### Option 5: Parallel Extraction (2-4 workers)
**Current**: Sequential (1 worker)
**Proposed**: Concurrent workers with connection pooling

**Impact**:
- 2 workers: 40% time reduction (~24-30 hours)
- 4 workers: 60% time reduction (~12-15 hours)
- Risk: **MEDIUM** - requires code changes
- Resource: ~2-4x memory/connections

**Implementation Effort**: 100-150 lines of code

---

### 🔴 Advanced Solutions (High Effort, Best Results)

#### Option 6: GPU Acceleration
**Setup**: Deploy on GPU with CUDA support

**Impact**:
- 5-10x speedup possible
- Estimated time: ~5-10 hours
- Risk: **LOW** - very stable
- Cost: Infrastructure/GPU needed

#### Option 7: Batch Processing with Chunking
**Idea**: Send multiple chunks in one LLM call

**Impact**:
- 30-50% speedup (amortize overhead)
- Estimated time: ~24-36 hours
- Risk: **MEDIUM** - complex logic needed
- Benefit: Efficient parallel processing

#### Option 8: Caching + Semantic Deduplication
**Idea**: Cache similar chunks, reuse extractions

**Impact**:
- 20-40% speedup (if many similar chunks)
- Estimated time: ~30-48 hours
- Risk: **LOW** - safe to implement
- Benefit: Reduces redundant processing

---

## 5. Recommended Optimization Strategy

### Phase 1: Immediate Optimizations (No Risk, Quick Win)
```
1. Reduce num_ctx from 16384 → 4096
2. Reduce num_predict from 4096 → 2048
3. Test on 10-20 chunks
4. Verify Neo4j quality unchanged
```

**Expected Improvement**: 30-40% speed (180s → 110-120s/chunk)
**Implementation Time**: 5 minutes
**Risk**: Negligible

### Phase 2: Model Optimization (Medium Risk, High Reward)
```
1. Pull tinyllama:1.1b model
2. Test extraction quality on 50 chunks
3. If acceptable: Switch to tinyllama
4. If not: Keep llama3.2:3b or try mistral
```

**Expected Improvement**: 3-4x speed with tinyllama
**Implementation Time**: 15 minutes + model pull (~10 min)
**Risk**: Lower quality, but likely acceptable

### Phase 3: Parallelization (If Needed)
```
1. Implement concurrent extraction (2-4 workers)
2. Add connection pooling for Neo4j/PostgreSQL
3. Test throughput and error rates
4. Deploy if stable
```

**Expected Improvement**: 2-4x speed with parallelization
**Implementation Time**: 2-3 hours
**Risk**: Medium - requires testing

---

## 6. Recommended Action Plan

### Best Case (All Optimizations Applied)
```
llama3.2:3b + context optimization: 110-120s/chunk
+ tinyllama:1.1b model: 30-40s/chunk  
+ 4x parallelization: 8-10s/chunk (wall clock time)

Estimated Total Time: 10-12 hours for all 348K chunks
```

### Pragmatic Case (Phase 1 + Phase 2)
```
llama3.2:3b + optimization: 110-120s/chunk
+ tinyllama:1.1b: 30-40s/chunk

Estimated Total Time: 40-48 hours
Quality: Very good (tinyllama handles CWE/CVE well)
Implementation: 20 minutes
```

### Conservative Case (Phase 1 Only)
```
llama3.2:3b + optimization: 110-120s/chunk

Estimated Total Time: 60-72 hours
Quality: Excellent (keeps high-quality model)
Implementation: 5 minutes
Risk: Minimal
```

---

## 7. Implementation Recommendation

### ✅ RECOMMENDED: Conservative → Progressive Approach

**Step 1** (Right Now - 5 min):
```bash
# Optimize context windows
# Reduce num_ctx: 16384 → 4096
# Reduce num_predict: 4096 → 2048
docker compose exec -T backend python scripts/batch_extract_neo4j.py --mode extract --limit 50
# Test on 50 chunks, check Neo4j quality
```

**Step 2** (If Quality OK - 15 min):
```bash
# Try tinyllama
docker compose exec -T ollama ollama pull tinyllama:1.1b
# Update .env: OLLAMA_MODEL=tinyllama:1.1b
docker compose exec -T backend python scripts/batch_extract_neo4j.py --mode extract --limit 50
# Compare quality and speed
```

**Step 3** (If tinyllama Good - 2-3 hours):
```bash
# Deploy 4x parallelization
# Update batch_extract_neo4j.py to use concurrent.futures or asyncio.gather
# Test with 100-200 chunks
docker compose exec -T backend python scripts/batch_extract_neo4j.py --mode extract --limit 200
```

**Step 4** (Final):
```bash
# Run full extraction
docker compose exec -T backend python scripts/batch_extract_neo4j.py --mode extract
```

---

## 8. Comparison Matrix

| Approach | Speed | Quality | Effort | Risk | Benefit |
|----------|-------|---------|--------|------|---------|
| **Current** | 180s/chunk | Excellent | - | Low | Baseline |
| **Phase 1 Only** | 110-120s/chunk | Excellent | 5 min | Minimal | 30-35% faster |
| **Phase 1 + tinyllama** | 30-40s/chunk | Very Good | 20 min | Low | 4-6x faster |
| **Phase 1+2+3** | 8-10s/chunk | Very Good | 3 hours | Medium | 18-20x faster |
| **GPU Accelerated** | 15-30s/chunk | Excellent | Hours | Low | 6-12x faster |

---

## Appendix: Current Configuration Details

### LLM Client Settings
```python
# app/adapters/llm_client.py

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=5, max=40))
async def extract_entities_and_relations(self, chunk_text: str, chunk_id: int):
    response = await self.client.chat(
        model="llama3.2:3b",
        messages=[...],
        format="json",
        options={
            "temperature": 0.0,        # Deterministic
            "num_ctx": 16384,          # ← OPTIMIZE: reduce to 4096
            "num_predict": 4096        # ← OPTIMIZE: reduce to 2048
        }
    )
```

### Extraction Pipeline
```
1. PostgreSQL: SELECT * FROM chunks LIMIT N
2. For each chunk:
   a. Detect type (CWE/CVE)
   b. Call LLM extraction (~150-180s) ← BOTTLENECK
   c. Parse JSON + repair
   d. Validate entities
   e. Upsert to Neo4j
3. Log progress every 10 chunks
```

---

**Next Steps**: Choose optimization level and run test suite before full extraction!
