# 🗓️ PHASE 2.0: Future Roadmap (Attack Loop - DEFERRED)

**Status**: Planning document for future phases (NOT Phase 1.0)  
**Estimated Timeline**: 8-12 weeks (after Phase 1.0 validation)  
**Estimated Resources**: 4-5 FTE  

---

## 📋 Overview

### Why Deferred?
1. **Phase 1.0 Foundation**: Need Nuclei parser working first
2. **Scope Clarity**: Start with single tool, expand gradually
3. **Risk Reduction**: Test & stabilize before full attack loop
4. **Team Bandwidth**: Phase 1.0 needs focus

### What Phase 2.0 Adds
- Multi-tool integration (Nmap, Nikto, Metasploit)
- Attack state graph (IP:Port:Service:Vulnerability)
- Dynamic decision-making with LLM
- Cyclic workflow (iterative attack chains)
- Tool execution orchestration

---

## 🏗️ Phase 2.0 Architecture

### From Linear DAG → Cyclic Loop

```
PHASE 1.0 (Current - No Loop):
┌──────────────┐
│ Nuclei Scan  │
└──────┬───────┘
       ↓
┌──────────────┐
│ Parse Output │
└──────┬───────┘
       ↓
┌──────────────┐
│ Store in DB  │
└──────┬───────┘
       ↓
┌──────────────┐
│ End          │
└──────────────┘


PHASE 2.0 (Future - Cyclic):
       ┌─────────────────────────────────┐
       ↓                                 │
   ┌─────────────────────┐              │
   │  Define Goal        │              │
   │  (Find critical CVE)│              │
   └──────────┬──────────┘              │
              ↓                         │
   ┌─────────────────────┐              │
   │ Query Graph+Vector  │              │
   │ (Current state +    │              │
   │  available exploits)│              │
   └──────────┬──────────┘              │
              ↓                         │
   ┌─────────────────────┐              │
   │ LLM Decision        │              │
   │ What to scan next?  │              │
   │ (Nmap/Nikto/MSF)   │              │
   └──────────┬──────────┘              │
              ↓                         │
   ┌─────────────────────┐              │
   │ Execute Tool        │              │
   │ (Nmap/Nikto/Metasploit) │          │
   └──────────┬──────────┘              │
              ↓                         │
   ┌─────────────────────┐              │
   │ Parse Output        │              │
   │ (Log Parser)        │              │
   └──────────┬──────────┘              │
              ↓                         │
   ┌─────────────────────┐              │
   │ Update Graph        │              │
   │ (New entities)      │              │
   └──────────┬──────────┘              │
              ↓                         │
   ┌─────────────────────┐              │
   │ Goal Achieved?      │              │
   │ Max steps reached?  │              │
   └──────────┬──────────┘              │
              ↓                         │
        ┌─────┴─────┐                   │
        │           │                   │
       YES         NO ──────────────────┘
        │
        ↓
   ┌─────────────────────┐
   │ Generate Report     │
   └─────────────────────┘
```

---

## 📊 Phase 2.0 Phases (Sub-phases)

### Phase 2.1: Multi-Tool Parser (Weeks 1-2)

**Goal**: Implement Nmap + Nikto + Metasploit parsers

**Components**:
```
app/adapters/parsers/
├── nmap_parser.py
│  └─ Extract IPs, Ports, Services, OS fingerprints
│
├── nikto_parser.py
│  └─ Extract web vulnerabilities, plugin results
│
└── metasploit_parser.py
   └─ Extract exploit sessions, payloads, post-exploitation
```

**Deliverables**:
- [ ] Nmap parser with >80% coverage
- [ ] Nikto parser with >80% coverage
- [ ] Metasploit parser with >80% coverage
- [ ] Unified parser interface
- [ ] Integration tests for each

**Testing**:
- Parse real outputs from DVWA
- Validate entity extraction
- Compare with known vulnerabilities

---

### Phase 2.2: Attack State Graph (Weeks 2-3)

**Goal**: Refactor Neo4j schema for attack progression tracking

**Current Schema** (CVE-focused):
```cypher
:CVE, :CWE, :Weakness
Relationships: related_to, classified_as
```

**New Schema** (Attack state + CVE knowledge):
```cypher
# Attack state nodes
:IP {address, hostname, os, scanned_at}
:Port {number, protocol, state, service}
:Service {name, version, product}
:Vulnerability {cve_id, cwe_id, severity}

# Knowledge base (keep existing)
:CVE {id, description, score}
:CWE {id, name}

# Relationships
IP -[:HAS_PORT]-> Port
Port -[:RUNS_SERVICE]-> Service
Service -[:HAS_VULNERABILITY]-> Vulnerability
Vulnerability -[:EXPLOITABLE_BY]-> Exploit
Exploit -[:REFERENCES]-> CVE
```

**Migration Strategy**:
1. Add new labels alongside existing
2. Feature flags to switch between queries
3. Dual-write for data consistency
4. Gradual migration of queries

**Deliverables**:
- [ ] Neo4j schema documented
- [ ] Migration scripts (non-breaking)
- [ ] New Cypher queries for LLM
- [ ] Performance testing & optimization

---

### Phase 2.3: Vector DB Enhancements (Weeks 3-4)

**Goal**: Populate vector DB with attack techniques

**Current Content** (CVE knowledge):
```
- CVE descriptions
- CWE definitions
- Vulnerability text
```

**New Content** (Techniques + CVEs):
```
Primary: Attack techniques/payloads
- HackTricks writeups
- Exploit-DB entries
- Metasploit modules
- OWASP techniques

Secondary: CVE knowledge (keep for reference)
```

**Implementation**:
1. Create ETL pipeline for technique ingestion
2. Implement semantic chunking for techniques
3. Create embeddings for similarity search
4. Optimize reranking for hybrid queries

**Deliverables**:
- [ ] Technique ingestion pipeline
- [ ] 1000+ techniques in Weaviate
- [ ] Semantic search validation
- [ ] Hybrid search ranking optimized

---

### Phase 2.4: LangGraph Cyclic Workflow (Weeks 4-5)

**Goal**: Implement cyclic attack loop with LLM decision-making

**Architecture**:
```python
from langgraph.graph import StateGraph, END

class AttackState(BaseModel):
    target: str
    current_step: int
    max_steps: int = 10
    discovered_ips: List[str]
    discovered_vulns: List[Dict]
    goal_achieved: bool
    next_action: Dict

async def decide_node(state: AttackState):
    """LLM decides next tool to execute"""
    context = await graph.query_current_state(state.target)
    techniques = await vector_db.find_applicable_exploits(context)
    decision = await llm.decide_action(context, techniques)
    state.next_action = decision
    return state

async def execute_node(state: AttackState):
    """Execute chosen tool"""
    result = await tool_executor.execute(
        tool=state.next_action['tool'],
        params=state.next_action['params']
    )
    state.last_result = result
    return state

async def parse_node(state: AttackState):
    """Parse tool output & update state"""
    parsed = await parser_factory.parse(
        tool=state.attack_history[-1]['tool'],
        output=state.last_result
    )
    await graph.update_attack_state(parsed)
    state.goal_achieved = check_goal(state)
    state.current_step += 1
    return state

# Build graph
workflow = StateGraph(AttackState)
workflow.add_node("decide", decide_node)
workflow.add_node("execute", execute_node)
workflow.add_node("parse", parse_node)

workflow.set_entry_point("decide")
workflow.add_edge("decide", "execute")
workflow.add_edge("execute", "parse")

# Conditional: Loop or END?
def should_continue(state):
    if state.goal_achieved or state.current_step >= state.max_steps:
        return END
    return "decide"

workflow.add_conditional_edges("parse", should_continue)
graph = workflow.compile()
```

**Deliverables**:
- [ ] State machine implemented
- [ ] LLM integration for decisions
- [ ] Tool executor framework
- [ ] Loop termination logic

---

### Phase 2.5: Tool Executor + Sandboxing (Weeks 5-6)

**Goal**: Execute real penetration testing tools safely

**Implementation**:
```
┌────────────────────────────┐
│    LLM Decision            │
│ "Run Nmap on 192.168.1.0/24"
└────────────┬───────────────┘
             ↓
┌────────────────────────────┐
│  Tool Executor Service     │
├────────────────────────────┤
│  - Validate parameters     │
│  - Build command line      │
│  - Execute in container    │
│  - Timeout management      │
│  - Resource limits         │
└────────────┬───────────────┘
             ↓
┌────────────────────────────┐
│  Docker Container          │
│  (Isolated execution)      │
│  - Limited network access  │
│  - Resource constraints    │
│  - Audit logging           │
└────────────┬───────────────┘
             ↓
┌────────────────────────────┐
│  Tool Output               │
│  (Captured & parsed)       │
└────────────────────────────┘
```

**Tools to Support**:
1. **Nmap** (network reconnaissance)
   - Host discovery
   - Port scanning
   - OS fingerprinting
   - Service version detection

2. **Nikto** (web application scanning)
   - Web server detection
   - Vulnerability scanning
   - Plugin results

3. **Metasploit** (exploitation)
   - Payload generation
   - Exploit execution
   - Session management

**Deliverables**:
- [ ] Tool executor framework
- [ ] Docker container management
- [ ] Security policies (what can/can't execute)
- [ ] Output capture & formatting

---

### Phase 2.6: Integration & E2E Testing (Weeks 6-7)

**Goal**: Validate complete attack workflow

**Test Scenarios**:

**Scenario 1: DVWA (Web Application)**
```
1. User: "Find SQL injection vulnerabilities on DVWA"
2. System:
   - Nmap scan DVWA server
   - Nikto scan DVWA web app
   - Find SQL injection entries
   - Attempt Metasploit exploitation
   - Parse results
3. Output: Report of vulnerabilities + exploitation attempts
```

**Scenario 2: HackTheBox Machine**
```
1. User: "Compromise target machine"
2. System:
   - Nmap: Discover services
   - Nikto: Find web vuln (if web service)
   - Research: Find applicable exploits
   - Metasploit: Execute exploits
   - Post-exploitation: Gather data
3. Output: Attack chain documentation
```

**Deliverables**:
- [ ] DVWA scenarios pass
- [ ] HackTheBox scenarios pass
- [ ] Performance baselines met
- [ ] Security audit passed

---

### Phase 2.7: Documentation & Deployment (Weeks 7-8)

**Goal**: Document Phase 2.0 and deploy to production

**Documentation**:
- [ ] Architecture guide
- [ ] API documentation
- [ ] Tool integration guide
- [ ] Troubleshooting guide
- [ ] Security best practices

**Deployment**:
- [ ] Staging environment setup
- [ ] Load testing
- [ ] Production deployment
- [ ] Monitoring setup
- [ ] Incident response playbook

---

## 🎯 Success Criteria (Phase 2.0)

### Functional
✅ Execute multi-step attack chains  
✅ LLM makes reasonable tactical decisions  
✅ All 3 tools integrated and tested  
✅ Attack state accurately tracked  
✅ Finding correlation working  

### Performance
✅ Decision loop < 30s per iteration  
✅ Tool execution < 5 min (configurable)  
✅ Graph queries < 100ms  
✅ Vector search < 200ms  

### Quality
✅ Test coverage > 80%  
✅ E2E tests pass on DVWA + HackTheBox  
✅ Zero security issues in execution  
✅ Production monitoring active  

---

## 📋 Decision Gates

### Gate 1: After Phase 1.0 (Nuclei Parser)
**Questions to Answer**:
- Is Nuclei parser stable? (>99% uptime)
- Is CVE correlation accurate? (>90%)
- Are there regressions? (No)

**Decision**: Proceed to Phase 2.1 or iterate on Phase 1.0?

### Gate 2: After Phase 2.1 (Multi-Tool Parsers)
**Questions to Answer**:
- Are all 3 parsers working? (>80% accuracy)
- Is performance acceptable? (<10s per 1000 findings)
- Can we safely add more tools?

**Decision**: Proceed to Phase 2.2 or refine parsers?

### Gate 3: After Phase 2.4 (LangGraph Loop)
**Questions to Answer**:
- Does LLM make reasonable decisions? (Manual review >80%)
- Is loop termination working? (No infinite loops)
- Is the workflow stable? (>95% success rate)

**Decision**: Proceed to Phase 2.5 or refine workflow?

---

## 🔮 Vision: What Phase 2.0 Enables

### Automated Reconnaissance
```
User: "Scan target.com for vulnerabilities"

System:
1. Run Nmap → Discover 15 open ports
2. Run Nikto → Find 8 web vulnerabilities
3. Run searchsploit → Find 3 public exploits
4. Report: "3 critical issues found"
```

### Intelligent Exploitation
```
User: "Exploit critical vulnerability"

System:
1. Query: "What exploits for CVE-2021-44228?"
2. LLM Decision: "Metasploit module available"
3. Execute: Run exploit in sandbox
4. Parse: Capture results
5. Report: "Exploitation successful, access gained"
```

### Attack Chain Documentation
```
User: "Document complete attack chain"

System:
1. Iterate through reconnaissance → exploitation
2. Log each step with timeline
3. Generate attack graph in Neo4j
4. Create visual report of attack path
5. Provide remediation recommendations
```

---

## ⏱️ Phase 2.0 Timeline Summary

| Phase | Component | Duration | FTE |
|-------|-----------|----------|-----|
| 2.1 | Multi-Tool Parsers | 2 weeks | 2 |
| 2.2 | Attack State Graph | 2 weeks | 2 |
| 2.3 | Vector DB Techniques | 2 weeks | 1 |
| 2.4 | LangGraph Loop | 2 weeks | 2 |
| 2.5 | Tool Executor | 2 weeks | 2 |
| 2.6 | E2E Testing | 2 weeks | 2 |
| 2.7 | Documentation | 2 weeks | 1 |
| **TOTAL** | | **8-12 weeks** | **4-5 FTE** |

---

## 📝 Assumptions & Dependencies

### Assumptions
- Phase 1.0 (Nuclei parser) completed successfully
- CVE database remains stable
- LLM performance acceptable for decisions
- Security approval obtained for tool execution
- Test environment (DVWA + HackTheBox) available

### Dependencies
- Phase 1.0 completion (required)
- DevOps support for Docker/sandboxing
- Security team approval for pentest tools
- Business decision on attack automation scope

---

## ⚠️ Risks (Phase 2.0)

| Risk | Mitigation |
|------|-----------|
| LLM makes poor decisions | Human approval gate, extensive logging |
| Tool execution failures | Sandboxing, error handling, fallback |
| False positives in attacks | Whitelist safe operations, validation |
| Performance degradation | Caching, profiling, optimization |
| Security vulnerabilities | Code review, penetration testing |

---

## 🔗 Relationship to Phase 1.0

```
PHASE 1.0 (Nuclei)
├─ Nuclei parser ready
├─ Neo4j with DiscoveredVulnerability
├─ Hybrid search working
└─ Feature flags for gradual rollout
   ↓
PHASE 2.0 (Attack Loop)
├─ Extends parser to Nmap/Nikto/Metasploit
├─ Extends Neo4j to attack state
├─ Adds LLM decision-making
├─ Implements cyclic workflow
└─ Result: Automated attack chains
```

---

## 📞 Decision Required

**For Phase 1.0**: Proceed or modify?  
**For Phase 2.0**: Start planning or defer?  

Recommend: **Approve Phase 1.0 now, plan Phase 2.0 after validation**

---

**Status**: Planning document (NOT approved for Phase 1.0)  
**Review By**: After Phase 1.0 completion  
**Questions?**: See EXECUTIVE_SUMMARY.md or DOCUMENTATION_INDEX.md

