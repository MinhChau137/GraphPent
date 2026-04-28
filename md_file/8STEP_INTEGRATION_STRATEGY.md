# 🔄 8-Step Pipeline Integration Strategy

**Objective**: Map proposed 8-step workflow onto current project architecture  
**Status**: Ready for Phase 1.0 + Phase 2.0 planning  
**Last Updated**: April 28, 2026

---

## 📊 Executive Overview

### The 8-Step Pipeline (Your Proposal)
```
1. Data Collection     → 2. Normalization    → 3. GraphRAG + Retrieval
   (Multi-tool)          (Graph Facts)          (Storage & Query)
        ↓                     ↓                      ↓
4. KG Completion      → 5. GNN Reasoning    → 6. Reasoning Engine
   (Predict Relations)   (Risk Embedding)       (Planning)
        ↓                     ↓                      ↓
7. Action Execution   ← 8. Result Update   ← (Feedback Loop)
   (Run Tools)            (Graph Update)
```

### Current Project Pipeline (Phases 4-9)
```
4. Ingest        → 5. Extract       → 6. Graph        → 7. Retrieve
   (Documents)       (Entities/Rel)    (Neo4j Store)      (Hybrid Query)
        ↓                ↓                  ↓                  ↓
   8. Workflow      → 9. Tools        (Orchestration & Execution)
```

### Proposed Integration Approach
```
Phase 1.0 (6-8 weeks): Foundation Layer
├─ Step 1-2: Enhanced Data Collection (Nuclei + existing CVE)
├─ Step 3: GraphRAG (Neo4j with label separation)
├─ Step 7-8: Basic Nuclei execution + result storage
└─ Roadmap: Steps 4-6 deferred to Phase 2.0

Phase 2.0 (8-12 weeks): Intelligence Layer
├─ Step 4: KG Completion model (CSNT-style)
├─ Step 5: GNN Reasoning (GPRP-style)
├─ Step 6: Reasoning Engine (enhanced planning)
└─ Step 1: Multi-tool orchestration (Nmap, Nessus, Burp)
```

---

## 🎯 Step-by-Step Mapping

### **Step 1: Data Collection**

**Purpose**: Gather vulnerability data from multiple sources

#### Current State
```
✅ CVE/CWE ingestion (Phase 4)
   └─ Endpoint: POST /ingest/document
   └─ Formats: JSON, PDF, DOCX
   
❌ Nuclei scanning
❌ Nmap, Nessus, Burp
❌ Topology & asset inventory
```

#### Phase 1.0 Enhancement
```
Nuclei Parser Integration (NEW)
├─ Trigger: POST /nuclei/scan endpoint
├─ Input: Target URL + scan templates
├─ Output: JSON findings with CVE/CWE links
└─ Storage: PostgreSQL + MinIO (raw outputs)

Keep existing CVE ingestion unchanged
```

**File Location**: `app/api/v1/routers/nuclei.py`  
**Service**: `NucleiIntegrationService`

#### Phase 2.0 Roadmap
```
Multi-Tool Data Collection
├─ Nmap (network discovery)
├─ Nessus (vulnerability scan)
├─ Burp (webapp scan)
├─ Topology (network graph)
└─ Asset Inventory (track devices)

Architecture: Tool adapter factory pattern
```

---

### **Step 2: Normalization & Graph Facts**

**Purpose**: Convert all outputs into standardized graph entities/relationships

#### Current State
```
✅ LLM Extraction (Phase 5)
   └─ Endpoint: POST /extract/chunk/{id}
   └─ Input: Raw text chunks
   └─ Output: JSON {entities[], relations[]}

✅ Graph Upsert (Phase 6)
   └─ Service: GraphService.process_extraction_result()
   └─ Target: Neo4j MERGE operations
```

#### Phase 1.0 Enhancement
```
Nuclei Finding Normalization (NEW)
├─ Input: Raw Nuclei JSON output
├─ Parser: app/adapters/nuclei_parser/nuclei_parser.py
├─ Output: Structured Finding model
│  {
│    id: UUID
│    template_id: string
│    severity: enum[CRITICAL, HIGH, MEDIUM, LOW, INFO]
│    cve_id: string[] (optional)
│    cwe_id: string[] (optional)
│    url: string
│    timestamp: datetime
│    matched_at: string
│    evidence: string
│  }
└─ Storage: Create :DiscoveredVulnerability nodes in Neo4j

Relationship Normalization
├─ Finding -[:CORRELATES_TO]→ CVE (new)
├─ Finding -[:CLASSIFIED_AS]→ CWE (new)
└─ Keeping existing: CVE -[:RELATES_TO]→ CWE

Architecture Decision: Label Separation Strategy
├─ :CVE, :CWE, :Weakness (EXISTING knowledge layer)
├─ :DiscoveredVulnerability, :Finding (NEW findings layer)
└─ Single Neo4j instance, no schema disruption
```

**Implementation**:
```python
# app/services/nuclei_integration_service.py

class NucleiIntegrationService:
    async def parse_and_normalize(self, nuclei_output: dict) -> NormalizationResult:
        # 1. Parse Nuclei JSON
        finding = self.parser.parse(nuclei_output)
        
        # 2. Create entities
        finding_entity = Entity(
            type="DiscoveredVulnerability",
            properties={...}
        )
        
        # 3. Create relationships
        relationships = []
        if finding.cve_id:
            relationships.append(
                Relationship(
                    source="DiscoveredVulnerability",
                    target="CVE",
                    type="CORRELATES_TO",
                    properties={"finding_id": finding.id, "cve_id": finding.cve_id}
                )
            )
        
        # 4. Upsert to Neo4j
        await self.graph_service.upsert_entities(finding_entity)
        await self.graph_service.create_relationships(relationships)
        
        return NormalizationResult(
            entity=finding_entity,
            relationships=relationships
        )
```

---

### **Step 3: GraphRAG Storage & Retrieval**

**Purpose**: Store knowledge in graph and enable intelligent retrieval

#### Current State ✅ (Mostly Complete)
```
Neo4j Graph Storage (Phase 6)
├─ :CVE {id, description, score, ...}
├─ :CWE {id, name, ...}
├─ :Weakness (extracted from descriptions)
└─ Relationships with provenance

Hybrid Retrieval (Phase 7)
├─ Vector search: Weaviate (chunk embeddings)
├─ Graph search: Neo4j (keyword + BFS)
├─ Fusion reranking: α·graph + (1-α)·vector
└─ Endpoint: POST /retrieve/query
```

#### Phase 1.0 Enhancement
```
Enhanced Storage (BACKWARD COMPATIBLE)
├─ Add: :DiscoveredVulnerability nodes (label separation)
├─ Add: Relationships to existing CVE/CWE
├─ Keep: Existing CVE/CWE graph intact
└─ Result: Mixed knowledge + findings graph

Enhanced Retrieval
├─ Expanded query scope:
│  ├─ Knowledge layer (CVE/CWE)
│  ├─ Findings layer (DiscoveredVulnerability)
│  └─ Combined results with source tracking
├─ Example query:
│  "Show me SQL injection CVEs and actual findings"
│  Returns:
│  - CVEs with high CVSS + descriptions
│  - Nuclei findings with CVE correlation
│  - Evidence + remediation
└─ Feature flag: HYBRID_FINDINGS_SEARCH

Neo4j Schema Enhancement
```
BEFORE (Phase 0):
(:CVE) -[:RELATES_TO]→ (:CWE)
(:CWE) -[:REFINES]→ (:Weakness)

AFTER (Phase 1.0):
(:CVE) -[:RELATES_TO]→ (:CWE)
(:CWE) -[:REFINES]→ (:Weakness)
(:DiscoveredVulnerability) -[:CORRELATES_TO]→ (:CVE)  [NEW]
(:DiscoveredVulnerability) -[:CLASSIFIED_AS]→ (:CWE) [NEW]
```

Implementation Pattern:
```cypher
// Find all SQL injection knowledge + recent findings
MATCH (cwe:CWE)-[:REFINES]->(weakness:Weakness)
WHERE weakness.name CONTAINS "SQL Injection"

OPTIONAL MATCH (finding:DiscoveredVulnerability)-[:CLASSIFIED_AS]->(cwe)
OPTIONAL MATCH (finding)-[:CORRELATES_TO]->(cve:CVE)

RETURN {
  weakness: weakness,
  related_cves: collect(DISTINCT cve),
  recent_findings: collect(finding),
  source: "mixed"
} as result
```

---

### **Step 4: KG Completion** (DEFERRED TO PHASE 2.0)

**Purpose**: Predict missing relationships using ML model

#### Phase 1.0 Status
```
❌ Not implemented (deferred)
   Reason: Requires ML infrastructure
           Adds complexity to Phase 1
```

#### Phase 2.0 Roadmap
```
Implementation Plan
├─ Model: CSNT-style (Cross-graph Self-training Network)
├─ Task: Predict missing relationships
│  ├─ Input: Current graph + node embeddings
│  ├─ Output: Predicted relationships with confidence
│  └─ Examples:
│     - Finding X likely maps to CWE Y
│     - CVE A likely related to CVE B
│     - Missing attack path connections
├─ Integration:
│  ├─ Preprocessing: Extract node features + adjacency
│  ├─ Model training: On historical CVE graph
│  ├─ Inference: Periodically update Neo4j
│  └─ Validation: Manual review before merging
└─ Metrics: Precision, recall, F1-score

Infrastructure Needed:
├─ ML model server (PyTorch/TensorFlow)
├─ Embedding generation (GNN pre-training)
├─ Neo4j APOC procedures (for batch operations)
└─ Background job scheduler (Celery/APScheduler)
```

---

### **Step 5: GNN Reasoning** (DEFERRED TO PHASE 2.0)

**Purpose**: Generate embeddings and estimate risk propagation

#### Phase 1.0 Status
```
❌ Not implemented (deferred)
   Reason: Requires advanced ML
           Depends on KG Completion
```

#### Phase 2.0 Roadmap
```
Implementation Plan
├─ Architecture: GPRP-style GNN (Graph Propagation for Risk Prediction)
├─ Components:
│  ├─ Graph Encoder: Convert Neo4j to embeddings
│  ├─ Message Passing: Aggregate neighbor information
│  ├─ Risk Propagation: Calculate node importance
│  └─ Node Ranking: Identify high-risk attack targets
├─ Features:
│  ├─ Node features:
│  │  ├─ CVE CVSS score
│  │  ├─ CWE severity
│  │  ├─ Finding exploit status
│  │  └─ Asset criticality (from topology)
│  ├─ Edge features:
│  │  ├─ Relationship type (CORRELATES_TO, RELATES_TO)
│  │  ├─ Temporal recency (when finding was discovered)
│  │  └─ Evidence strength
│  └─ Context features:
│     ├─ Attack complexity
│     ├─ Privileges required
│     └─ User interaction needed
├─ Outputs:
│  ├─ Risk scores per node
│  ├─ Attack propagation paths
│  ├─ Critical asset identification
│  └─ Remediation priority ranking
└─ Storage: Embeddings cached in Redis/Weaviate

Example: Risk Propagation Calculation
Input:  Finding("HTTP Missing Headers") →[CORRELATES_TO]→ CVE-2021-12345
        CVE-2021-12345 →[RELATES_TO]→ CWE-693
        Network topology: [Web-Server] →[depends-on]→ [DB-Server]

GNN Processing:
1. Find all nodes connected to web server
2. Propagate risk through relationships
3. Estimate likelihood of lateral movement
4. Calculate overall system risk

Output: {
  immediate_risk: HIGH (web server compromised)
  propagation_risk: CRITICAL (can reach DB)
  critical_assets: [DB-Server, Internal-Network]
  recommended_actions: [patch_cve, disable_service, isolate_network]
}
```

---

### **Step 6: Reasoning Engine** (PHASE 1.0 + 2.0)

**Purpose**: Select targets and plan pentest actions

#### Phase 1.0: Basic Planning
```
Current: Multi-agent workflow (Phase 8)
├─ DAG: planner → retrieval → graph_reasoning → tool → report

Phase 1.0 Enhancement:
├─ Input: Nuclei findings + CVE correlation
├─ Planning:
│  ├─ Query: "What are top 3 vulnerabilities in CVE knowledge base?"
│  ├─ Retrieval: Hybrid search (knowledge + findings)
│  ├─ Analysis: LLM reasoning on findings
│  └─ Output: Prioritized list of findings
├─ Actions available (Phase 1):
│  ├─ Run Nuclei scan (with new templates)
│  ├─ Generate report with findings
│  ├─ Suggest remediation (from CVE knowledge)
│  └─ Link findings to CVEs
└─ Integration:
   ├─ Enhanced state (WorkflowState)
   ├─ New nodes in DAG for finding analysis
   └─ Feature flag: ENHANCED_REASONING_V1

Updated Workflow DAG:
planner
  ↓
retrieval → [CVE results, Finding results]
  ↓
finding_analyzer (NEW) → Correlate findings with CVEs
  ↓
graph_reasoning → Identify patterns
  ↓
tool_selector (NEW) → Choose next action (scan/report/etc)
  ↓
tool_executor → Run selected tool
  ↓
report_generator
  ↓
human_approval → END
```

#### Phase 2.0: Advanced Planning
```
Inputs: GNN embeddings + risk scores + topology
├─ Target Selection:
│  ├─ Multi-objective optimization
│  ├─ Consider: exploitability, impact, ease-of-patch
│  └─ Generate attack trees
├─ Action Planning:
│  ├─ Identify attack paths
│  ├─ Sequence pentest steps
│  ├─ Predict outcomes (with GNN)
│  └─ Optimize for maximum coverage
├─ Resource Allocation:
│  ├─ Distribute scanning efforts
│  ├─ Manage tool execution windows
│  ├─ Handle concurrent targets
│  └─ Track execution state
└─ Result: Prioritized pentest plan with:
   ├─ Target selection (sorted by risk)
   ├─ Tool sequence (optimal order)
   ├─ Expected outcomes
   └─ Resource requirements
```

---

### **Step 7: Action Execution** (PHASE 1.0 + 2.0)

**Purpose**: Execute pentest tools based on plan

#### Phase 1.0: Nuclei Execution
```
Current: Tool stubs in Phase 9
├─ Endpoint: POST /tools/nuclei/cve
├─ Status: Lab-only, not integrated

Phase 1.0 Implementation:
├─ NEW Endpoint: POST /nuclei/scan
│  ├─ Input: target, templates[], timeout
│  ├─ Validation: ALLOWED_TARGETS whitelist
│  ├─ Execution:
│  │  ├─ Call Nuclei CLI with templates
│  │  ├─ Capture JSON output
│  │  ├─ Parse findings (Step 2 normalization)
│  │  └─ Store in Neo4j (Step 3)
│  └─ Output: {scan_id, status, findings[]}
├─ Features:
│  ├─ Async execution (don't block response)
│  ├─ Progress tracking
│  ├─ Timeout handling
│  ├─ Error recovery
│  └─ Webhook callback when done
├─ Storage: PostgreSQL (scan jobs) + MinIO (raw output)
└─ Integration: Returns to graph update (Step 8)

Implementation Code Structure:
app/services/nuclei_execution_service.py
├─ run_nuclei_scan(target, templates, timeout)
├─ poll_scan_status(scan_id)
└─ get_scan_results(scan_id)

app/api/v1/routers/nuclei.py
├─ POST /nuclei/scan → start scan
├─ GET /nuclei/scan/{id} → check status
├─ GET /nuclei/scan/{id}/results → get results
└─ DELETE /nuclei/scan/{id} → cancel scan
```

**Security Considerations**:
```
✅ Whitelist targets (ALLOWED_TARGETS in .env)
✅ Rate limit scanning (max concurrent scans)
✅ Timeout protection (MAX_TOOL_TIMEOUT)
✅ Audit logging (all scan requests)
✅ Webhook auth (verify callback source)
✅ DVWA-only for Phase 1 (lab environment)
```

#### Phase 2.0: Multi-Tool Execution
```
Tool Registry Pattern:
├─ Nmap adapter (network discovery)
├─ Nessus adapter (vulnerability scanning)
├─ Burp adapter (web app scanning)
├─ Metasploit adapter (exploitation, optional)
└─ Custom adapter framework

Orchestration:
├─ Tool selection based on target type
├─ Parallel vs sequential execution
├─ Output normalization (all → graph facts)
├─ Error handling & recovery
└─ Results aggregation
```

---

### **Step 8: Result Update & Feedback Loop** (PHASE 1.0 + 2.0)

**Purpose**: Store results back to graph and create continuous loop

#### Phase 1.0: Basic Feedback
```
Current: Linear pipeline (no feedback)
├─ Phases 4→5→6→7→8→9 (one direction)

Phase 1.0 Change: Add feedback loop
├─ Step 1: Data Collection (Nuclei scan results)
│          ↓ (Step 7 execution)
├─ Step 8: Result Update (store in Neo4j)
│          ↓ (new loop back)
├─ Step 3: Enhanced GraphRAG (query includes new findings)
│          ↓ (enables)
├─ Step 6: Enhanced Reasoning (finds more issues)
│          ↓ (may trigger)
└─ Step 1: Next scan iteration (continuous improvement)

Implementation:
1. Store scan results
   └─ app/services/nuclei_integration_service.py
      └─ store_scan_results(scan_id, findings[])

2. Update Neo4j with findings
   └─ Call graph service to upsert :DiscoveredVulnerability nodes

3. Create result metadata
   ├─ scan_timestamp
   ├─ tool_version (Nuclei version)
   ├─ templates_used
   ├─ target_url
   └─ findings_count

4. Trigger optional next step
   ├─ IF findings.severity >= CRITICAL
   ├─ THEN auto-trigger report generation
   └─ ELSE wait for user input

Database Schema Update:
PostgreSQL.nuclei_scans:
├─ id (UUID)
├─ target_url
├─ status (pending, running, completed, failed)
├─ started_at
├─ completed_at
├─ findings_count
├─ raw_output_path (MinIO)
└─ neo4j_upsert_status

Neo4j Updates:
├─ Create :DiscoveredVulnerability nodes
├─ Create relationships to :CVE/:CWE
├─ Add scan metadata as properties
├─ Index by template_id, severity, timestamp
└─ Enable aggregation queries

Example: "What changed since last scan?"
MATCH (finding:DiscoveredVulnerability)
WHERE finding.scan_timestamp > $previous_scan_time
RETURN finding, count(*) as new_findings
```

#### Phase 2.0: Advanced Feedback Loop
```
Continuous Loop Implementation:
1. Scan execution (Step 7)
   ↓
2. Results stored (Step 8)
   ↓
3. KG completion runs (Step 4)
   ├─ Predict missing relationships
   ├─ Enhance graph understanding
   └─ Confidence scores updated
   ↓
4. GNN reasoning updates (Step 5)
   ├─ Recalculate risk scores
   ├─ Update attack paths
   └─ Identify new targets
   ↓
5. New actions generated (Step 6)
   ├─ Higher-priority targets identified
   ├─ New attack paths discovered
   └─ Next scan suggested
   ↓
6. Auto-execution (Step 7)
   ├─ Run next scan automatically
   ├─ Or notify user for approval
   └─ Repeat from Step 1

Scheduling & Monitoring:
├─ Background job scheduler (APScheduler/Celery)
├─ Trigger policies:
│  ├─ Time-based: "Run daily scan at 2 AM"
│  ├─ Event-based: "New CVE found → re-scan"
│  ├─ Risk-based: "Risk > threshold → priority scan"
│  └─ Manual: "User triggered scan"
├─ State tracking:
│  ├─ Iteration count
│  ├─ Last action timestamp
│  ├─ Coverage metrics
│  └─ Success rate
└─ Dashboard metrics:
   ├─ Scan history
   ├─ Finding trends
   ├─ Loop efficiency
   └─ Risk trajectory
```

---

## 📋 Phase Mapping Summary

### **Phase 1.0 (6-8 weeks, 2-3 FTE)**

| 8-Step | Task | Status | File/Service |
|--------|------|--------|--------------|
| 1 | Nuclei data collection | NEW | `app/adapters/nuclei_parser/` |
| 2 | Normalization to graph facts | NEW | `app/services/nuclei_integration_service.py` |
| 3 | GraphRAG storage + enhanced retrieval | ENHANCED | Neo4j label separation + `/retrieve/query` |
| 4 | KG Completion | ❌ Deferred | — |
| 5 | GNN Reasoning | ❌ Deferred | — |
| 6 | Reasoning Engine (basic) | ENHANCED | LangGraph DAG + finding analysis |
| 7 | Nuclei execution | NEW | `app/services/nuclei_execution_service.py` |
| 8 | Result update + basic loop | NEW | PostgreSQL + Neo4j update + webhook |

**Deliverables**:
- ✅ Nuclei parser module
- ✅ Neo4j label separation
- ✅ Finding storage & correlation
- ✅ Enhanced retrieval
- ✅ Nuclei scan API
- ✅ Result feedback mechanism
- ✅ Feature flags for gradual rollout
- ✅ Documentation + tests

**Testing**:
- DVWA environment (Docker)
- HackTheBox lab (manual)
- Unit tests (parser, normalization)
- Integration tests (end-to-end)

---

### **Phase 2.0 (8-12 weeks, 3-4 FTE)**

| 8-Step | Task | Status | Notes |
|--------|------|--------|-------|
| 1 | Multi-tool collection | NEW | Nmap, Nessus, Burp |
| 2 | Normalize all tools | NEW | Tool adapter factory |
| 3 | Full GraphRAG | COMPLETE | Build on Phase 1 |
| 4 | KG Completion model | NEW | CSNT-style ML |
| 5 | GNN Reasoning | NEW | GPRP-style embeddings |
| 6 | Advanced Reasoning | NEW | Attack planning |
| 7 | Multi-tool execution | NEW | Tool orchestration |
| 8 | Full feedback loop | NEW | Autonomous continuous scan |

**Deliverables**:
- Multi-tool adapters
- ML model servers
- Advanced reasoning engine
- Full autonomous loop
- Dashboard with metrics

---

## 🔧 Implementation Roadmap

### **Week 1-2: Foundation**
```
✅ Nuclei parser module (base.py, models.py, nuclei_parser.py)
✅ Neo4j label separation schema
✅ API endpoints (POST /nuclei/scan, GET status)
```

### **Week 2-3: Integration**
```
✅ Normalization service (entity creation, relationship mapping)
✅ Graph storage (upsert to Neo4j)
✅ Result tracking (PostgreSQL)
```

### **Week 3-4: Retrieval & Workflow**
```
✅ Enhanced retrieval (findings + knowledge combined)
✅ Workflow DAG update (finding analyzer node)
✅ Basic reasoning on findings
```

### **Week 4-5: Execution & Feedback**
```
✅ Nuclei execution service (async + polling)
✅ Result storage + Neo4j update
✅ Webhook callback mechanism
```

### **Week 5-6: Testing & Validation**
```
✅ DVWA test environment
✅ Unit tests (all components)
✅ Integration tests (full flow)
✅ HackTheBox manual validation
```

### **Week 6-8: Polish & Deployment**
```
✅ Feature flags (gradual rollout)
✅ Documentation (API + architecture)
✅ Canary deployment (10% → 50% → 100%)
✅ Monitoring + alerting
```

---

## 🎯 Recommended Integration Approach

### **Approach 1: Isolated Nuclei Service (Recommended ✅)**

```
Pros:
- Phase 1.0 focused on Nuclei only
- Minimal changes to existing phases
- Easy to test independently
- Clear separation of concerns
- Reduces risk

Cons:
- Limited to one tool (but that's Phase 1 scope)

Implementation:
app/services/
├─ nuclei_integration_service.py (NEW)
│  ├─ Parse + normalize
│  ├─ Create entities
│  └─ Store in Neo4j
├─ nuclei_execution_service.py (NEW)
│  ├─ Run Nuclei CLI
│  ├─ Track results
│  └─ Trigger callbacks
└─ (Existing services unchanged)

app/api/v1/routers/
├─ nuclei.py (NEW)
│  ├─ POST /nuclei/scan
│  ├─ GET /nuclei/scan/{id}
│  └─ GET /nuclei/scan/{id}/results
└─ (Existing routers unchanged)

Database:
├─ PostgreSQL.nuclei_scans (NEW table)
├─ PostgreSQL.nuclei_findings (NEW table)
├─ Neo4j :DiscoveredVulnerability (NEW label)
└─ (Existing data unchanged)

Phases Affected:
├─ Phase 4: Enhanced (Nuclei as new input source)
├─ Phase 5-6: Enhanced (normalization + storage)
├─ Phase 7: Enhanced (findings in retrieval)
├─ Phase 8: Enhanced (finding analysis node)
└─ Phase 9: Enhanced (Nuclei execution)
```

### **Approach 2: Generic Tool Adapter (Future)**

```
For Phase 2.0+: Build general tool adapter framework
├─ AbstractToolAdapter base class
├─ Tool-specific implementations (NmapAdapter, NessusAdapter, etc.)
├─ Standardized output format
├─ Plugin system for new tools
└─ Unified execution/tracking

Not recommended for Phase 1.0 (over-engineering)
```

---

## ✅ Integration Checklist

### **Phase 1.0 Deliverables**

- [ ] **Architecture & Design**
  - [ ] Technical design document (this file)
  - [ ] Data model for DiscoveredVulnerability
  - [ ] API specification (OpenAPI)
  - [ ] Database schema additions

- [ ] **Code Implementation**
  - [ ] Parser module (`app/adapters/nuclei_parser/`)
  - [ ] Integration service (`app/services/nuclei_integration_service.py`)
  - [ ] Execution service (`app/services/nuclei_execution_service.py`)
  - [ ] API routes (`app/api/v1/routers/nuclei.py`)
  - [ ] Neo4j adapter enhancements

- [ ] **Database Updates**
  - [ ] PostgreSQL: nuclei_scans table
  - [ ] PostgreSQL: nuclei_findings table
  - [ ] Neo4j: DiscoveredVulnerability label + indexes
  - [ ] Migration scripts

- [ ] **Testing**
  - [ ] Unit tests (parser, normalization, service)
  - [ ] Integration tests (full pipeline)
  - [ ] DVWA environment setup
  - [ ] Test fixtures + sample data

- [ ] **Feature Flags**
  - [ ] `NUCLEI_PARSER_ENABLED`
  - [ ] `HYBRID_FINDINGS_SEARCH`
  - [ ] `TOOL_INTEGRATION_V2`
  - [ ] Configuration in settings.py

- [ ] **Documentation**
  - [ ] API documentation (OpenAPI)
  - [ ] Architecture guide
  - [ ] Deployment guide
  - [ ] Troubleshooting guide

- [ ] **Deployment**
  - [ ] Docker image updates
  - [ ] docker-compose.yml updates
  - [ ] Environment variable documentation
  - [ ] Migration scripts

### **Phase 2.0 Planning**

- [ ] KG Completion module design
- [ ] GNN Reasoning module design
- [ ] Multi-tool adapter framework
- [ ] Advanced reasoning engine
- [ ] Autonomous loop implementation
- [ ] ML infrastructure setup

---

## 📊 Success Metrics

### **Phase 1.0 KPIs**

| Metric | Target | Monitoring |
|--------|--------|-----------|
| Parser accuracy | >99% | Unit tests |
| Finding correlation | >95% CVEs linked | Graph queries |
| Scan execution time | <5 min per scan | PostgreSQL logs |
| API availability | >99.9% | Health checks |
| Neo4j query performance | <500ms | Slow query log |
| Feature flag adoption | 100% by week 8 | Metrics endpoint |

### **Phase 2.0 Roadmap KPIs**

| Metric | Target | Notes |
|--------|--------|-------|
| KG Completion | >85% precision | ML model validation |
| Risk score accuracy | >80% correlation with real risk | Blind test |
| Attack path prediction | >70% useful recommendations | User feedback |
| Autonomous loop efficiency | >3 iterations/day | Execution logs |

---

## 🎓 Conclusion

### **Why This Approach?**

1. **Aligned with existing architecture**: Uses FastAPI, Neo4j, PostgreSQL (no new tech)
2. **Low risk**: Nuclei-only Phase 1.0, phased rollout with feature flags
3. **Backward compatible**: Existing CVE system untouched
4. **Scalable foundation**: Phase 1.0 enables Phase 2.0 naturally
5. **Time-bound**: 6-8 weeks to MVP, 8-12 weeks to full vision
6. **Resource-efficient**: 2-3 FTE Phase 1, can scale to 3-4 FTE Phase 2

### **Next Steps**

1. **Review & Approve** (This document)
2. **Technical Design Detail** (Data models, API spec)
3. **Implementation Sprint** (Week 1-2 foundation)
4. **Testing & Validation** (Week 5-6)
5. **Deployment** (Week 7-8)
6. **Phase 2.0 Planning** (Parallel to Phase 1.0 testing)

---

## 📞 Questions & Discussion

**Key Decision Points for Clarification**:

1. Should Phase 1.0 include auto-triggered scanning, or manual-only? (Recommend: Manual for safety)
2. Should findings be deduplicated across scans, or keep full history? (Recommend: Keep history with timestamps)
3. How aggressive should feedback loop be in Phase 2.0? (Recommend: User-approved initially)
4. Should we implement custom GNN or use existing embeddings? (Recommend: Use pre-trained first, custom later)

---

**Document Status**: Ready for review  
**Last Updated**: April 28, 2026  
**Recommendation**: Proceed with Phase 1.0 implementation
