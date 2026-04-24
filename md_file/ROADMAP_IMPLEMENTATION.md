# 📅 Project Refactor Roadmap: Current → Proposed Model

## Executive Summary

**Transition Goal**: Convert GraphRAG Pentest Platform from **CVE Knowledge Management System** to **Automated Penetration Testing Engine with Dynamic Attack Loops**.

**Timeline**: 8-12 weeks  
**Effort**: 4-5 FTE  
**Risk**: Medium (major architectural changes)

---

## Phase Breakdown

### PHASE 1: Foundation (Weeks 1-2) - Log Parser Module

#### Objective
Build the critical log parsing layer that extracts structured entities from tool outputs.

#### Deliverables
- [ ] **Nmap Parser** (`app/adapters/log_parser/nmap_parser.py`)
  - Parse JSON output → Extract IPs, Ports, Services, OS
  - Handle: Multiple ports, service versions, OS fingerprinting
  - Test: With real Nmap outputs

- [ ] **Nikto Parser** (`app/adapters/log_parser/nikto_parser.py`)
  - Parse XML/JSON → Extract vulnerabilities, descriptions
  - Handle: CVE linking, URI extraction
  - Test: With real Nikto outputs

- [ ] **Metasploit Parser** (`app/adapters/log_parser/metasploit_parser.py`)
  - Parse JSON sessions → Extract exploit results, payloads
  - Handle: Session info, exploit names, payload types
  - Test: With real MSF results

- [ ] **Generic Parser** (`app/adapters/log_parser/generic_parser.py`)
  - Regex-based fallback for custom tools
  - Customizable rules for new tools

- [ ] **Parser Interface** (`app/adapters/log_parser_client.py`)
  - Auto-detect tool type
  - Route to appropriate parser
  - Return uniform ParsedOutput

#### Code Structure
```python
app/adapters/log_parser/
├── __init__.py
├── base.py              # AbstractParser class
├── models.py            # Entity, Relationship, ParsedOutput
├── nmap_parser.py
├── nikto_parser.py
├── metasploit_parser.py
├── generic_parser.py
└── utils.py             # Helper functions
```

#### Testing
- [ ] Unit tests for each parser (fixtures/)
- [ ] Integration test: Parse → Output validation
- [ ] Edge cases: Empty results, malformed outputs

#### Acceptance Criteria
- ✅ All parsers handle sample outputs without errors
- ✅ Entities & relationships correctly extracted
- ✅ Unit test coverage > 80%

---

### PHASE 2: Neo4j Graph Refactor (Weeks 2-4) - Attack State Graph

#### Objective
Redesign Neo4j schema from CVE knowledge graph to Attack state graph.

#### Decision Point
**Option A: Single Neo4j with separate labels**
- Labels: CVE, CWE, IP, Port, Service, Vulnerability (attack-specific)
- Pros: Single database, simple
- Cons: Mixed concerns (knowledge + state)

**Option B: Separate Neo4j instances**
- DB1: CVE/CWE knowledge (keep existing)
- DB2: Attack state (new)
- Pros: Clean separation
- Cons: More complex, more resources

**Recommendation**: **Option A** (Single Neo4j with clear label separation) for MVP

#### Deliverables

**1. Schema Design** (`docs/neo4j_schema.md`)
```cypher
-- Attack State Nodes
CREATE (ip:IP {address: "192.168.1.1", hostname: "router", os: "Linux"})
CREATE (port:Port {number: 22, protocol: "tcp", state: "open"})
CREATE (service:Service {name: "SSH", version: "7.4", product: "OpenSSH"})
CREATE (vuln:Vulnerability {cve_id: "CVE-2024-1234", severity: "high"})

-- Knowledge Base Nodes (existing)
CREATE (cwe:CWE {id: "CWE-89", name: "SQL Injection"})
CREATE (technique:Technique {name: "SQL Injection via OR 1=1", tool: "metasploit"})

-- Relationships
(ip)-[:HAS_PORT]->(port)
(port)-[:RUNS_SERVICE]->(service)
(service)-[:HAS_VULNERABILITY]->(vuln)
(vuln)-[:TRIGGERED_BY]->(technique)
(vuln)-[:CORRESPONDS_TO]->(cwe)  # Link attack-specific to knowledge base
```

**2. Cypher Query Library** (`app/adapters/neo4j/queries.py`)
```python
# Query: Get all vulnerabilities for target IP
QUERY_VULNS_FOR_IP = """
MATCH (ip:IP {address: $target})-[:HAS_PORT]->(port)-[:RUNS_SERVICE]->(svc)
  -[:HAS_VULNERABILITY]->(vuln)
RETURN vuln
"""

# Query: Get exploits for vulnerability
QUERY_EXPLOITS_FOR_VULN = """
MATCH (vuln:Vulnerability {cve_id: $cve})<-[:TRIGGERED_BY]-(tech:Technique)
RETURN tech
"""

# Query: Get attack path from IP to goal
QUERY_ATTACK_PATH = """
MATCH path = (ip:IP {address: $start})-[*]-(goal:Goal)
RETURN path
"""
```

**3. Migration Script** (`scripts/migrate_neo4j_schema.py`)
- Keep existing CVE/CWE data
- Add index on new fields (address, port, service, etc)
- Populate initial nodes from tool outputs

**4. CRUD Services** (`app/services/graph_service.py` refactor)
```python
class GraphService:
    # Attack state updates
    async def update_attack_state(self, parsed_output: ParsedOutput)
    async def query_vulnerabilities(self, target_ip: str)
    async def query_exploits(self, cve_id: str)
    
    # Knowledge base queries (existing)
    async def query_cwe(self, cwe_id: str)
    async def query_related_vulnerabilities(self, query: str)
```

#### Testing
- [ ] Schema validation: All nodes/relationships exist
- [ ] Query validation: Cypher queries return expected results
- [ ] Migration test: Existing CVE data intact
- [ ] Performance: Index on frequently queried fields

#### Acceptance Criteria
- ✅ Attack state nodes created from parsed outputs
- ✅ Relationships properly linked
- ✅ Queries return correct results
- ✅ Query time < 100ms for typical queries

---

### PHASE 3: Vector DB Content Shift (Weeks 3-4) - Technique/Payload Store

#### Objective
Replace CVE document embeddings with attack technique/payload embeddings.

#### Current State
- Weaviate has chunks from CVE documents
- Not optimal for "what payload for this vuln?" queries

#### Proposed State
- Weaviate stores attack techniques & payloads
- Optimized for semantic search: "SQL injection payload" → best match

#### Deliverables

**1. Content Ingestion** (`scripts/ingest_techniques.py`)
```python
# Sources to ingest:
sources = [
    "HackTricks (https://book.hacktricks.xyz/)",
    "Exploit-DB (exploitdb.com)",
    "Metasploit modules",
    "Custom payload library"
]

# Each document:
{
    "id": "payload_001",
    "type": "payload",  # or "technique", "trick"
    "content": "SQL Injection: Use UNION SELECT ... to extract data",
    "vulnerability_types": ["SQL Injection", "CWE-89"],
    "tool": "metasploit",
    "difficulty": "medium",
    "tags": ["automation", "database"]
}
```

**2. Weaviate Collection Redesign**
```python
# Instead of: "Chunks" collection with CVE documents
# Use: "Techniques" collection with payload/trick documents

collection_config = {
    "name": "Techniques",
    "vectorizer": "text2vec-openai",  # or local embedding
    "properties": [
        {"name": "content", "type": "text", "vectorizePropertyName": true},
        {"name": "vulnerability_type", "type": "string"},
        {"name": "tool", "type": "string"},
        {"name": "difficulty", "type": "string"},
        {"name": "tags", "type": "text[]"},
    ]
}
```

**3. Search Optimization**
```python
# Old query: Find CVEs matching "SQL injection"
# New query: Find payloads for SQL injection vulnerability

async def find_exploit_for_vulnerability(cve_id: str):
    # 1. Get CVE details from Neo4j (knowledge base)
    cve = await graph.query_cve(cve_id)
    
    # 2. Search Weaviate for matching techniques
    query = f"Exploit payload for {cve.name} {cve.description}"
    techniques = await vector.semantic_search(query, limit=5)
    
    # 3. Return ranked techniques
    return techniques
```

#### Testing
- [ ] Ingest sample payloads
- [ ] Search works: "SQL injection" → relevant payloads
- [ ] Performance: < 200ms for semantic search
- [ ] Validation: Results relevant to query

#### Acceptance Criteria
- ✅ Weaviate collection populated with techniques
- ✅ Semantic search returns relevant payloads
- ✅ Integration with LLM for exploit selection

---

### PHASE 4: Dynamic Decision Loop (Weeks 4-6) - LangGraph Refactor

#### Objective
Replace linear DAG workflow with cyclic decision loop for continuous attack iteration.

#### Current Architecture
```
Linear DAG (one-pass):
planner → retrieval → reasoning → tool → report → approval → END
```

#### Proposed Architecture
```
Cyclic Loop (iterative):
      ┌─────────────────┐
      │                 │
      ↓                 │
[LLM Decision Node]     │
      │                 │
      ├─→ Graph Query   │
      ├─→ Vector Query  │
      └─→ Select action │
      ↓                 │
[Execute Tool Node]     │
      │                 │
      ├─→ Run scanner   │
      ├─→ Get output    │
      └─→ Store result  │
      ↓                 │
[Parse Output Node]     │
      │                 │
      ├─→ Extract entities
      ├─→ Update Graph  │
      ├─→ Update Vector │
      ├─→ Check goal    │
      └─→ Continue? ────┘
           │
           └─→ Goal reached? → END
```

#### Deliverables

**1. New LangGraph Structure** (`app/agents/langgraph/attack_graph.py`)
```python
from langgraph.graph import StateGraph, END
from .nodes import decision_node, execute_node, parse_node

class AttackState:
    target: str
    current_step: int
    max_steps: int
    discovered_ips: List[str]
    discovered_vulns: List[str]
    attack_history: List[dict]
    goal_achieved: bool

def build_attack_graph():
    workflow = StateGraph(AttackState)
    
    # Add nodes
    workflow.add_node("decide", decision_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("parse", parse_node)
    
    # Add edges (cyclic)
    workflow.set_entry_point("decide")
    workflow.add_edge("decide", "execute")
    workflow.add_edge("execute", "parse")
    
    # Conditional edge: Continue or End?
    def should_continue(state: AttackState):
        if state.goal_achieved or state.current_step >= state.max_steps:
            return END
        return "decide"
    
    workflow.add_conditional_edges("parse", should_continue)
    
    return workflow.compile()
```

**2. Decision Node** (`app/agents/langgraph/nodes.py`)
```python
async def decision_node(state: AttackState, graph_service, vector_service, llm):
    """LLM decides next action"""
    
    # 1. Query current state
    current_vulns = await graph_service.query_vulnerabilities(state.target)
    
    # 2. Find exploits
    unexploited = [v for v in current_vulns if not v.exploited]
    
    # 3. LLM decides next step
    decision = await llm.decide_next_action(
        graph_state=current_vulns,
        available_techniques=techniques,
        target=state.target,
        history=state.attack_history
    )
    
    # 4. Update state
    state.next_action = decision
    return state
```

**3. Execute Node**
```python
async def execute_node(state: AttackState, toolset):
    """Execute tool based on decision"""
    
    tool_name = state.next_action['tool']  # "nmap", "nikto", "metasploit"
    tool_params = state.next_action['params']
    
    result = await toolset.execute(tool_name, tool_params)
    
    state.last_result = result
    state.attack_history.append({
        "tool": tool_name,
        "time": datetime.now(),
        "params": tool_params
    })
    
    return state
```

**4. Parse Node**
```python
async def parse_node(state: AttackState, parser, graph_svc, vector_svc):
    """Parse output & update stores"""
    
    parsed = parser.parse(
        tool_name=state.attack_history[-1]['tool'],
        raw_data=state.last_result
    )
    
    # Update Graph
    await graph_svc.upsert_from_parsed_output(parsed)
    
    # Check if goal achieved
    vulns = await graph_svc.query_vulnerabilities(state.target)
    critical_found = any(v.severity == "critical" for v in vulns)
    
    state.goal_achieved = critical_found
    state.current_step += 1
    state.discovered_vulns.extend([v.cve_id for v in parsed.entities 
                                   if v.type == "Vulnerability"])
    
    return state
```

#### Testing
- [ ] Cyclic workflow completes
- [ ] State updates correctly
- [ ] Termination conditions work
- [ ] Loop doesn't infinite

#### Acceptance Criteria
- ✅ Decision loop executes correctly
- ✅ Graph/Vector updates persist
- ✅ Max iterations respected
- ✅ Goal detection works

---

### PHASE 5: Tool Integration & Execution Layer (Weeks 5-7)

#### Objective
Implement robust execution of actual penetration testing tools.

#### Deliverables

**1. Tool Executor** (`app/adapters/tool_executor.py`)
```python
class ToolExecutor:
    async def execute_nmap(self, target: str, params: dict) -> str
    async def execute_nikto(self, target: str, params: dict) -> str
    async def execute_metasploit(self, session: MSFSession, payload: dict) -> dict
    async def execute_generic(self, tool_name: str, cmd: str) -> str
```

**2. Tool Catalog** (`app/adapters/tools/catalog.py`)
```python
TOOLS = {
    "nmap": {
        "command": "nmap",
        "parser": "nmap_parser",
        "required_params": ["target"],
        "optional_params": ["-p", "-sV", "-O"]
    },
    "nikto": {
        "command": "nikto",
        "parser": "nikto_parser",
        "required_params": ["-h"],
        "optional_params": ["-port", "-output"]
    },
    # ... more tools
}
```

**3. Sandboxed Execution** (Security layer)
- Run tools in Docker containers for isolation
- Resource limits (CPU, memory, timeout)
- Network access control

#### Testing
- [ ] Each tool executes correctly
- [ ] Output parsing works
- [ ] Sandboxing prevents escapes
- [ ] Timeouts enforced

---

### PHASE 6: Integration & Validation (Weeks 7-8)

#### Objective
Integrate all components, end-to-end testing.

#### Deliverables
- [ ] All components communicate
- [ ] E2E workflow succeeds
- [ ] Performance acceptable
- [ ] Real pentest scenario tests

#### Test Scenarios
1. **DVWA (Damn Vulnerable Web App)**
   - Target: DVWA instance
   - Expected: Discover SQL injection, XSS vulnerabilities
   - Validate: Graph populated, exploits retrieved

2. **HackTheBox Lab**
   - Target: HTB machine
   - Expected: Complete attack chain
   - Validate: Compromise detected, reported

---

### PHASE 7: Documentation & Deployment (Weeks 8-12)

#### Deliverables
- [ ] Architecture documentation
- [ ] API documentation
- [ ] Deployment guide
- [ ] Training materials

---

## Implementation Strategy

### How to Minimize Disruption

1. **Keep Existing Features**: Current CVE ingestion (Phase 4-6) stays intact
2. **Parallel Development**: New components (log parser, attack loop) developed separately
3. **Feature Flags**: Use feature flags to toggle old vs new flow
4. **Gradual Migration**: Don't force all users to new model immediately

### Suggested Git Workflow
```bash
# Create feature branches
git checkout -b feature/log-parser
git checkout -b feature/neo4j-attack-schema
git checkout -b feature/vector-techniques
git checkout -b feature/attack-loop

# Merge when each phase complete
# Final integration in main branch
```

---

## Risk Mitigation

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Breaking existing API | High | Versioning (v1, v2), feature flags |
| Tool execution failures | High | Sandboxing, error handling, fallbacks |
| Graph state explosion | Medium | Pruning policies, TTL |
| LLM decision quality | High | Approval gates, logging |
| Performance degradation | Medium | Caching, indexing, profiling |

---

## Success Metrics

### Functional
- ✅ System can execute complete attack chain autonomously
- ✅ Graph accurately tracks attack state
- ✅ Log parser correctly extracts entities from tools
- ✅ LLM makes reasonable attack decisions

### Performance
- ✅ Decision loop completes in < 30s per iteration
- ✅ Tool execution < 5 min (configurable)
- ✅ Graph queries < 100ms
- ✅ Vector search < 200ms

### Quality
- ✅ Unit test coverage > 80%
- ✅ Integration test coverage > 60%
- ✅ E2E tests on DVWA + HackTheBox
- ✅ Zero security issues in tool execution

---

## Resource Requirements

| Phase | Roles | FTE | Tools |
|-------|-------|-----|-------|
| 1 | Backend Engineer | 2 | Python, Pytest |
| 2 | Backend Engineer + DevOps | 2 | Neo4j, CYPHER |
| 3 | ML Engineer | 1 | Weaviate, Embeddings |
| 4 | Backend Engineer | 2 | LangGraph, Python |
| 5 | Backend + DevOps | 2 | Docker, security |
| 6 | QA Engineer | 1 | Test labs (DVWA, HackTheBox) |
| 7 | Technical Writer | 1 | Documentation |

**Total**: ~4-5 FTE, 8-12 weeks

