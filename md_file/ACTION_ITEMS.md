# ✅ ACTION ITEMS: Chỉnh Sửa Project Cụ Thể

## 📝 Summary: What Changed?

**Original Project**: CVE/CWE knowledge management system  
**New Direction**: Automated penetration testing engine with dynamic attack loops

**Core Changes**:
1. ✅ **ADD**: Log Parser Module (NEW critical component)
2. ✅ **REFACTOR**: Neo4j schema for attack state tracking
3. ✅ **SHIFT**: Vector DB from CVE chunks → attack techniques
4. ✅ **REDESIGN**: LangGraph from linear DAG → cyclic loop
5. ✅ **EXPAND**: Tool integration from stubs → real execution

---

## 🔧 Concrete Changes Needed

### 1. NEW FILE: Log Parser Module

**Location**: `app/adapters/log_parser/`

```bash
app/adapters/log_parser/
├── __init__.py
├── base.py                 # Abstract base class
├── models.py              # Entity, Relationship, ParsedOutput
├── nmap_parser.py         # NEW
├── nikto_parser.py        # NEW
├── metasploit_parser.py   # NEW
└── generic_parser.py      # NEW
```

**Key Files to Create**:

**File 1**: `app/adapters/log_parser/models.py`
```python
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime

class Entity(BaseModel):
    id: str
    type: str  # "IP", "Port", "Service", "Vulnerability"
    value: str
    attributes: Dict[str, Any] = {}
    source: str
    confidence: float = 1.0
    timestamp: datetime

class Relationship(BaseModel):
    id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str  # "HAS_PORT", "RUNS_SERVICE"
    attributes: Dict[str, Any] = {}
    source: str
    timestamp: datetime

class ParsedOutput(BaseModel):
    entities: List[Entity]
    relationships: List[Relationship]
    summary: Dict[str, Any]
    parsing_status: str  # "success", "partial", "failed"
    errors: List[str] = []
```

**File 2**: `app/adapters/log_parser/base.py`
```python
from abc import ABC, abstractmethod
from .models import ParsedOutput

class AbstractParser(ABC):
    @abstractmethod
    async def parse(self, raw_data: str, target: str) -> ParsedOutput:
        pass
```

**File 3**: `app/adapters/log_parser/nmap_parser.py`
```python
import json
from .base import AbstractParser
from .models import Entity, Relationship, ParsedOutput

class NmapParser(AbstractParser):
    async def parse(self, raw_data: str, target: str) -> ParsedOutput:
        entities = []
        relationships = []
        
        try:
            nmap_json = json.loads(raw_data)
            
            # Extract IPs, Ports, Services
            for ip, data in nmap_json.get('scan', {}).items():
                # Create IP entity
                ip_entity = Entity(
                    id=f"ip_{ip}",
                    type="IP",
                    value=ip,
                    attributes={
                        "os": data.get('osmatch', [{}])[0].get('name', 'Unknown')
                    },
                    source="nmap"
                )
                entities.append(ip_entity)
                
                # Create Port entities & relationships
                for port_data in data.get('ports', []):
                    port_num = port_data['port']
                    port_entity = Entity(
                        id=f"port_{ip}_{port_num}",
                        type="Port",
                        value=f"{ip}:{port_num}",
                        attributes={
                            "protocol": port_data['protocol'],
                            "state": port_data['state']['state']
                        },
                        source="nmap"
                    )
                    entities.append(port_entity)
                    
                    # IP:HAS_PORT relationship
                    relationships.append(Relationship(
                        id=f"rel_ip_port_{ip}_{port_num}",
                        source_entity_id=ip_entity.id,
                        target_entity_id=port_entity.id,
                        relation_type="HAS_PORT",
                        source="nmap"
                    ))
                    
                    # Create Service entity if available
                    service_name = port_data.get('service', {}).get('name', 'unknown')
                    if service_name != 'unknown':
                        service_entity = Entity(
                            id=f"service_{service_name}",
                            type="Service",
                            value=service_name,
                            attributes={
                                "version": port_data.get('service', {}).get('version', '')
                            },
                            source="nmap"
                        )
                        entities.append(service_entity)
                        
                        # Port:RUNS_SERVICE relationship
                        relationships.append(Relationship(
                            id=f"rel_port_service_{port_num}_{service_name}",
                            source_entity_id=port_entity.id,
                            target_entity_id=service_entity.id,
                            relation_type="RUNS_SERVICE",
                            source="nmap"
                        ))
            
            return ParsedOutput(
                entities=entities,
                relationships=relationships,
                summary={"total_ips": len(set(e.value for e in entities if e.type == "IP")),
                        "total_ports": len([e for e in entities if e.type == "Port"])},
                parsing_status="success"
            )
        
        except Exception as e:
            return ParsedOutput(
                entities=[],
                relationships=[],
                summary={},
                parsing_status="failed",
                errors=[str(e)]
            )
```

**File 4**: `app/adapters/log_parser_client.py`
```python
from .log_parser.nmap_parser import NmapParser
from .log_parser.nikto_parser import NmapParser
# ... etc

class LogParserClient:
    def __init__(self):
        self.parsers = {
            "nmap": NmapParser(),
            "nikto": NiktoParser(),
            "metasploit": MetasploitParser(),
        }
    
    async def parse(self, tool_name: str, raw_data: str, target: str):
        if tool_name not in self.parsers:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        return await self.parsers[tool_name].parse(raw_data, target)
```

---

### 2. REFACTOR: Neo4j Schema & Queries

**Location**: `app/adapters/neo4j_client.py` + `docs/neo4j_schema.md`

**Changes**:

**Old Schema** (CVE-focused):
```cypher
MATCH (n:CWE|CVE|Weakness) RETURN n
```

**New Schema** (Attack state-focused):
```cypher
-- Attack state nodes
:IP {address, hostname, os}
:Port {number, protocol, state}
:Service {name, version, product}
:Vulnerability {cve_id, severity}

-- Knowledge base (keep existing)
:CWE {id, name}
:CVE {id, description}

-- Relationships
IP-[:HAS_PORT]->Port
Port-[:RUNS_SERVICE]->Service
Service-[:HAS_VULNERABILITY]->Vulnerability
```

**New Methods in GraphService**:
```python
class GraphService:
    # NEW: Update attack state from parsed output
    async def update_attack_state(self, parsed_output: ParsedOutput):
        """Upsert entities & relationships from log parser"""
        pass
    
    # NEW: Query current system state
    async def get_target_state(self, target_ip: str) -> dict:
        """Return: {ips, ports, services, vulnerabilities}"""
        pass
    
    # NEW: Query exploits for vulnerability
    async def get_exploits_for_vulnerability(self, cve_id: str) -> List[Technique]:
        """Query CVE knowledge + find matching exploits"""
        pass
    
    # EXISTING: Keep all current CVE queries
```

---

### 3. SHIFT: Vector DB Content

**Location**: `scripts/ingest_techniques.py` (NEW), `app/adapters/weaviate_client.py` (refactor)

**What to Change**:

**Current Weaviate Content**:
- Collection: "Chunks"
- Documents: CVE/CWE text chunks

**New Weaviate Content**:
- Collection: "Techniques"
- Documents: Payloads, exploits, attack tricks
- Source: HackTricks, Exploit-DB, Metasploit modules

**New Script**: `scripts/ingest_techniques.py`
```python
async def ingest_techniques():
    """
    1. Fetch HackTricks writeups
    2. Parse Exploit-DB entries
    3. Extract Metasploit modules
    4. Ingest into Weaviate "Techniques" collection
    """
    techniques = [
        {
            "id": "sql_injection_union",
            "type": "payload",
            "content": "SQL Injection via UNION SELECT: ..."
            "vulnerability_types": ["SQL Injection", "CWE-89"],
            "difficulty": "medium"
        },
        # ... more techniques
    ]
    
    for technique in techniques:
        await vector_client.upsert_technique(technique)
```

**WeaviateClient Changes**:
```python
class WeaviateAdapter:
    # OLD
    async def upsert_chunk(self, chunk_id, content, metadata):
        pass
    
    # NEW
    async def upsert_technique(self, technique_id, content, metadata):
        """Store attack technique for semantic search"""
        pass
    
    # OLD
    async def vector_search(self, query: str, limit: int):
        pass
    
    # NEW - for finding exploits
    async def find_exploits_for_vulnerability(self, cve_id: str, limit: int = 5):
        """Semantic search: Find best exploits for CVE"""
        query = f"Exploit payload for {cve_id}"
        return await self.vector_search(query, limit)
```

---

### 4. REDESIGN: LangGraph Attack Loop

**Location**: `app/agents/langgraph/` (major refactor)

**Current Structure**:
```
graph.py → DAG: planner → retrieval → reasoning → tool → report → approval → END
nodes.py → 6 simple nodes
```

**New Structure**:
```
attack_graph.py → Cyclic: decide → execute → parse → (loop or END)
attack_nodes.py → 3 main nodes with complex logic
attack_state.py → Extended state tracking
```

**New Files**:

**File**: `app/agents/langgraph/attack_state.py`
```python
from pydantic import BaseModel
from typing import List, Dict

class AttackState(BaseModel):
    target: str
    current_step: int = 0
    max_steps: int = 10
    discovered_ips: List[str] = []
    discovered_vulns: List[Dict] = []
    attack_history: List[Dict] = []
    goal_achieved: bool = False
    next_action: Dict = {}
    last_result: str = ""
```

**File**: `app/agents/langgraph/attack_graph.py`
```python
from langgraph.graph import StateGraph, END
from .attack_state import AttackState
from .attack_nodes import decision_node, execute_node, parse_node

def build_attack_graph():
    workflow = StateGraph(AttackState)
    
    # Add nodes
    workflow.add_node("decide", decision_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("parse", parse_node)
    
    # Set entry point
    workflow.set_entry_point("decide")
    
    # Linear flow
    workflow.add_edge("decide", "execute")
    workflow.add_edge("execute", "parse")
    
    # Conditional: Continue loop or end?
    def should_continue(state: AttackState):
        if state.goal_achieved:
            return END
        if state.current_step >= state.max_steps:
            return END
        return "decide"  # Loop back
    
    workflow.add_conditional_edges("parse", should_continue)
    
    return workflow.compile()

graph = build_attack_graph()
```

**File**: `app/agents/langgraph/attack_nodes.py`
```python
async def decision_node(state: AttackState):
    """LLM decides next action"""
    # Query Graph: What's the current state?
    current_vulns = await graph_service.get_target_state(state.target)
    
    # Query Vector: What exploits available?
    # LLM: What to do next?
    decision = await llm.decide_attack(state, current_vulns)
    
    state.next_action = decision
    return state

async def execute_node(state: AttackState):
    """Execute tool based on LLM decision"""
    tool = state.next_action['tool']  # "nmap", "nikto", "metasploit"
    params = state.next_action['params']
    
    result = await toolset.execute(tool, params)
    
    state.last_result = result
    state.attack_history.append({
        "tool": tool,
        "params": params,
        "timestamp": datetime.now()
    })
    return state

async def parse_node(state: AttackState):
    """Parse output & update stores"""
    parsed = await log_parser.parse(
        tool_name=state.attack_history[-1]['tool'],
        raw_data=state.last_result,
        target=state.target
    )
    
    # Update Graph with new entities
    await graph_service.update_attack_state(parsed)
    
    # Check if critical vulnerability found (goal)
    vulns = await graph_service.get_target_state(state.target)
    critical = [v for v in vulns if v.severity == "critical"]
    state.goal_achieved = len(critical) > 0
    
    # Increment
    state.current_step += 1
    state.discovered_vulns.extend(parsed.entities)
    
    return state
```

**Router Changes**: `app/api/v1/routers/workflow.py`
```python
# OLD
@router.post("/workflow/run")
async def run_workflow(request: WorkflowRequest):
    # Used linear DAG

# NEW - Use cyclic attack graph
@router.post("/workflow/attack")
async def run_attack(request: AttackRequest):
    """Run automated pentest workflow"""
    initial_state = AttackState(
        target=request.target_ip,
        max_steps=request.max_steps or 10
    )
    
    result = await attack_graph.ainvoke(initial_state)
    
    return {
        "target": request.target_ip,
        "steps_completed": result.current_step,
        "vulnerabilities_found": len(result.discovered_vulns),
        "goal_achieved": result.goal_achieved,
        "history": result.attack_history
    }
```

---

### 5. EXPAND: Tool Execution Layer

**Location**: `app/adapters/tool_executor.py` (NEW), `app/adapters/tools/` (new package)

**New Files**:

**File**: `app/adapters/tool_executor.py`
```python
import subprocess
import json
from typing import Dict, Any

class ToolExecutor:
    async def execute_nmap(self, target: str, ports: str = None) -> str:
        """Execute Nmap and return JSON output"""
        cmd = ["nmap", "-sV", "-oX", "-", target]
        if ports:
            cmd.extend(["-p", ports])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout
    
    async def execute_nikto(self, url: str) -> str:
        """Execute Nikto and return XML output"""
        cmd = ["nikto", "-h", url, "-Format", "xml"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout
    
    async def execute_metasploit(self, payload: Dict[str, Any]) -> Dict:
        """Execute Metasploit exploit (requires MSF service)"""
        # Would connect to Metasploit RPC service
        # For MVP: Stub or use Python exploitation libraries
        pass
```

---

### 6. UPDATE: README.md

**What to Add/Change**:

#### New Section: Attack Loop Workflow
```markdown
## 🔄 Attack Loop Workflow (NEW)

### How It Works
1. **LLM Decision**: Decide next attack step
2. **Tool Execution**: Run Nmap, Nikto, etc.
3. **Log Parsing**: Extract entities from tool output
4. **Graph Update**: Track attack state
5. **Loop**: Repeat until goal achieved

### Example
```bash
POST /workflow/attack
{
  "target_ip": "192.168.1.1",
  "max_steps": 10
}

Returns:
{
  "target": "192.168.1.1",
  "steps_completed": 5,
  "vulnerabilities_found": 3,
  "goal_achieved": true,
  "history": [...]
}
```

#### Update: Architecture Diagram
```
OLD: Ingest CVE → Extract entities → Store in graph → Query

NEW: 
  ┌──────────────────────────────────┐
  │  Define Attack Target            │
  └──────────────────────────────────┘
           ↓
  ┌──────────────────────────────────┐
  │  LLM Decision (Query Graph+Vector)
  └──────────────────────────────────┘
           ↓
  ┌──────────────────────────────────┐
  │  Execute Tool (Nmap, Nikto, etc) │
  └──────────────────────────────────┘
           ↓
  ┌──────────────────────────────────┐
  │  Log Parser (Extract entities)   │
  └──────────────────────────────────┘
           ↓
    ┌──────────────┬──────────────┐
    ↓              ↓              ↓
  [Graph]   [Vector]    [Session]
  (Update)   (Learn)      (Save)
    ↓              ↓              ↓
    └──────────────┴──────────────┘
           ↓
  ┌──────────────────────────────────┐
  │ Goal Achieved? → Loop or End     │
  └──────────────────────────────────┘
```

#### Add: Phase 0 (Tool Setup)
```markdown
### Phase 0: Tool Setup (REQUIRED)
Before running attack workflows, ensure these tools are available:
- Nmap: `apt-get install nmap`
- Nikto: `apt-get install nikto`
- Metasploit: Docker image or local install

Verify:
```bash
nmap --version
nikto --version
```
```

---

## 📋 Summary of File Changes

### NEW Files
- ✅ `app/adapters/log_parser/__init__.py`
- ✅ `app/adapters/log_parser/base.py`
- ✅ `app/adapters/log_parser/models.py`
- ✅ `app/adapters/log_parser/nmap_parser.py`
- ✅ `app/adapters/log_parser/nikto_parser.py`
- ✅ `app/adapters/log_parser/metasploit_parser.py`
- ✅ `app/adapters/log_parser/generic_parser.py`
- ✅ `app/adapters/log_parser_client.py`
- ✅ `app/adapters/tool_executor.py`
- ✅ `app/agents/langgraph/attack_state.py`
- ✅ `app/agents/langgraph/attack_graph.py`
- ✅ `app/agents/langgraph/attack_nodes.py`
- ✅ `scripts/ingest_techniques.py`
- ✅ `docs/neo4j_schema.md`

### REFACTOR Files
- 🔄 `app/adapters/neo4j_client.py` → Add attack state methods
- 🔄 `app/adapters/weaviate_client.py` → Shift to technique storage
- 🔄 `app/services/graph_service.py` → Add attack queries
- 🔄 `app/agents/langgraph/graph.py` → Use new cyclic graph
- 🔄 `app/agents/langgraph/nodes.py` → Simplify (old nodes removed)
- 🔄 `app/api/v1/routers/workflow.py` → Add `/workflow/attack` endpoint
- 🔄 `README.md` → Add attack workflow section

### DELETE/DEPRECATE
- ❌ `app/agents/langgraph/nodes.py` (old linear nodes) → Replace with attack_nodes.py
- ❌ Phase 4-6 endpoints become optional (kept for CVE knowledge)

---

## 🎯 Quick Start: What to Do First

**Priority 1 (Week 1)**: Implement Log Parser
```bash
# This is the foundation. Everything depends on it.
# Focus on Nmap parser first, then Nikto, then Metasploit
```

**Priority 2 (Week 2-3)**: Neo4j Schema Refactor
```bash
# Update graph to track attack state (IPs, Ports, Services)
# Add Cypher queries for LLM decision-making
```

**Priority 3 (Week 3-4)**: Vector DB Shift
```bash
# Move from CVE chunks to attack techniques
# Ingest payloads from HackTricks
```

**Priority 4 (Week 4-6)**: Attack Loop
```bash
# Implement cyclic LangGraph
# Add decision + execute + parse nodes
```

---

## ✅ Validation Checklist

After implementing each phase, verify:

### Phase 1: Log Parser
- [ ] Parse Nmap output → Extract IPs, ports, services
- [ ] Parse Nikto output → Extract vulnerabilities
- [ ] Parse Metasploit → Extract exploit results
- [ ] Unit tests pass (>80% coverage)

### Phase 2: Neo4j Schema
- [ ] Graph contains IP, Port, Service, Vulnerability nodes
- [ ] Relationships correctly linked
- [ ] Cypher queries return expected results
- [ ] Query performance < 100ms

### Phase 3: Vector DB
- [ ] Weaviate has "Techniques" collection
- [ ] Search "SQL injection" → Returns relevant payloads
- [ ] Semantic search works accurately

### Phase 4: Attack Loop
- [ ] Cyclic workflow executes without errors
- [ ] State updates persist across iterations
- [ ] Loop terminates after max_steps or goal achievement
- [ ] E2E test with DVWA passes

