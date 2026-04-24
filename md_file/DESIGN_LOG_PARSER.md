# 🛠️ Design Document: Log Parser Module (NEW CORE COMPONENT)

## I. Overview

**Purpose**: Transform raw tool outputs (Nmap, Nikto, Metasploit) into structured entities & relationships for Graph/Vector DB updates.

**Why Critical**: 
- Current project has NO structured parsing → can't update graph properly
- PentestGPT learned that feeding raw logs to LLM causes "confused retrieval"
- Solution: Extract entities first, then update stores

---

## II. Architecture

```
Raw Tool Output
      ↓
┌──────────────────────────────┐
│   Tool Detector              │
│   (Identify tool type)       │
└──────────────────────────────┘
      ↓
   ┌──────────────┬──────────────┬──────────────┐
   ↓              ↓              ↓              ↓
[Nmap Parser] [Nikto Parser] [MSF Parser] [Custom Parser]
   ↓              ↓              ↓              ↓
   └──────────────┴──────────────┴──────────────┘
      ↓
┌──────────────────────────────────────────┐
│  Entity Extractor                        │
│  ├─ IP addresses                         │
│  ├─ Ports & protocols                    │
│  ├─ Services & versions                  │
│  └─ Vulnerabilities (CVE, CWE)          │
└──────────────────────────────────────────┘
      ↓
┌──────────────────────────────────────────┐
│  Relationship Builder                    │
│  ├─ IP:HAS_PORT → Port                  │
│  ├─ Port:RUNS_SERVICE → Service         │
│  ├─ Service:HAS_VULN → Vulnerability    │
│  └─ Vulnerability:EXPLOITABLE_BY → Tech │
└──────────────────────────────────────────┘
      ↓
┌──────────────────────────────────────────┐
│  Parsed Output (Structured)              │
│  {                                       │
│    entities: [...],                      │
│    relationships: [...],                 │
│    metadata: {...}                       │
│  }                                       │
└──────────────────────────────────────────┘
```

---

## III. Data Models

### Input: Raw Tool Outputs

```python
class ToolOutput:
    tool_name: str  # "nmap", "nikto", "metasploit", "custom"
    raw_data: str  # JSON/XML/Text output
    timestamp: datetime
    target: str  # Target IP or hostname
    metadata: dict  # Additional context
```

### Output: Structured Entities

```python
class Entity:
    id: str  # Unique identifier
    type: str  # "IP", "Port", "Service", "Vulnerability", "Technique"
    value: str  # Actual value (192.168.1.1, 80, http, CVE-2024-1234)
    attributes: dict  # {os: "Linux", version: "2.4", severity: "high"}
    source: str  # Which tool detected this
    confidence: float  # 0.0-1.0
    timestamp: datetime

class Relationship:
    id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str  # "HAS_PORT", "RUNS_SERVICE", "HAS_VULNERABILITY"
    attributes: dict  # Additional properties
    source: str  # Which tool/parser created this
    timestamp: datetime

class ParsedOutput:
    entities: List[Entity]
    relationships: List[Relationship]
    summary: dict  # Stats: total_ips, total_vulns, etc
    parsing_status: str  # "success", "partial", "failed"
    errors: List[str]  # Any parsing errors
```

---

## IV. Parser Implementations

### 1. Nmap Parser

**Input**: Nmap JSON output
```json
{
  "scan": {
    "192.168.1.1": {
      "status": {"state": "up"},
      "osmatch": [{"name": "Linux 4.15", "accuracy": "95"}],
      "ports": [
        {
          "port": 22,
          "protocol": "tcp",
          "state": {"state": "open"},
          "service": {"name": "ssh", "product": "OpenSSH", "version": "7.4"}
        }
      ]
    }
  }
}
```

**Extraction Logic**:
```python
def parse_nmap(raw_json):
    entities = []
    relationships = []
    
    for ip, data in raw_json['scan'].items():
        # 1. Create IP node
        ip_entity = Entity(
            type="IP",
            value=ip,
            attributes={
                "os": data['osmatch'][0]['name'] if data.get('osmatch') else "Unknown"
            }
        )
        entities.append(ip_entity)
        
        # 2. Create Port nodes & relationships
        for port_data in data.get('ports', []):
            port = port_data['port']
            service_name = port_data.get('service', {}).get('name', 'unknown')
            
            port_entity = Entity(
                type="Port",
                value=f"{ip}:{port}",
                attributes={
                    "protocol": port_data['protocol'],
                    "state": port_data['state']['state']
                }
            )
            entities.append(port_entity)
            
            # Relationship: IP:HAS_PORT → Port
            relationships.append(Relationship(
                source_entity_id=ip_entity.id,
                target_entity_id=port_entity.id,
                relation_type="HAS_PORT"
            ))
            
            # 3. Create Service node
            service_entity = Entity(
                type="Service",
                value=service_name,
                attributes={
                    "version": port_data.get('service', {}).get('version', ''),
                    "product": port_data.get('service', {}).get('product', '')
                }
            )
            entities.append(service_entity)
            
            # Relationship: Port:RUNS_SERVICE → Service
            relationships.append(Relationship(
                source_entity_id=port_entity.id,
                target_entity_id=service_entity.id,
                relation_type="RUNS_SERVICE"
            ))
    
    return ParsedOutput(entities=entities, relationships=relationships)
```

### 2. Nikto Parser

**Input**: Nikto XML output
```xml
<nikto scan_start="..." scan_end="...">
  <site host="192.168.1.1:80" port="80">
    <item id="..." method="GET" osvdb="">
      <description>Interesting File Found: /admin.php</description>
      <uri>/admin.php</uri>
    </item>
    <item id="..." osvdb="90005" cve="CVE-2009-3867">
      <description>Apache 2.4.1 - 2.4.12 multiple XSS</description>
    </item>
  </site>
</nikto>
```

**Extraction Logic**:
```python
def parse_nikto(raw_xml):
    entities = []
    relationships = []
    root = ET.fromstring(raw_xml)
    
    for site in root.findall('site'):
        host = site.get('host')
        port = site.get('port')
        
        # Already have Port node from Nmap, just link vulnerabilities
        for item in site.findall('item'):
            cve = item.get('cve')
            description = item.find('description').text
            
            if cve:
                vuln_entity = Entity(
                    type="Vulnerability",
                    value=cve,
                    attributes={
                        "title": description,
                        "source": "nikto",
                        "uri": item.find('uri').text if item.find('uri') is not None else ""
                    }
                )
                entities.append(vuln_entity)
                
                # Link to Port
                port_entity_id = f"{host}:{port}"  # Reference Nmap's Port entity
                relationships.append(Relationship(
                    source_entity_id=port_entity_id,
                    target_entity_id=vuln_entity.id,
                    relation_type="HAS_VULNERABILITY"
                ))
    
    return ParsedOutput(entities=entities, relationships=relationships)
```

### 3. Metasploit Parser

**Input**: Metasploit JSON results (after successful exploit)
```json
{
  "sessions": [
    {
      "id": 1,
      "type": "shell",
      "target": "192.168.1.5",
      "target_port": 445,
      "exploit": "exploit/windows/smb/ms17_010_eternalblue",
      "payload": "windows/meterpreter/reverse_tcp",
      "established_at": "2024-04-20T10:30:00Z"
    }
  ]
}
```

**Extraction Logic**:
```python
def parse_metasploit(raw_json):
    entities = []
    relationships = []
    
    for session in raw_json.get('sessions', []):
        target_ip = session['target']
        target_port = session['target_port']
        exploit_name = session['exploit']
        
        # Create Technique/Exploit node
        exploit_entity = Entity(
            type="Technique",
            value=exploit_name,
            attributes={
                "payload": session['payload'],
                "type": "metasploit_exploit"
            }
        )
        entities.append(exploit_entity)
        
        # Link to Port (already exists from Nmap)
        port_entity_id = f"{target_ip}:{target_port}"
        relationships.append(Relationship(
            source_entity_id=exploit_entity.id,
            target_entity_id=port_entity_id,
            relation_type="EXPLOITABLE_BY"
        ))
    
    return ParsedOutput(entities=entities, relationships=relationships)
```

---

## V. Implementation Plan

### File Structure
```
app/adapters/
├── log_parser/
│   ├── __init__.py
│   ├── base.py              # Abstract parser
│   ├── nmap_parser.py       # Nmap implementation
│   ├── nikto_parser.py      # Nikto implementation
│   ├── metasploit_parser.py # Metasploit implementation
│   └── generic_parser.py    # Fallback regex parser
│
└── log_parser_client.py     # Main interface
```

### Usage Example

```python
from app.adapters.log_parser_client import LogParserClient

parser = LogParserClient()

# Parse Nmap output
nmap_output = '{"scan": {...}}'
parsed = parser.parse(
    tool_name="nmap",
    raw_data=nmap_output,
    target="192.168.1.0/24"
)

# parsed.entities → [IP nodes, Port nodes, Service nodes]
# parsed.relationships → [IP:HAS_PORT, Port:RUNS_SERVICE, etc]

# Update Graph
await graph_service.upsert_from_parsed_output(parsed)

# Update Vector DB (optional, for techniques)
await vector_service.upsert_techniques(parsed)
```

---

## VI. Integration with Current Project

### Current Phase 4-6 (CVE Ingestion)
**Status**: Keep as-is
- Focus: Ingest CVE/CWE knowledge

### New Flow (Attack Execution)
```
LLM Decision → Execute Tool (Nmap/Nikto/MSF)
              ↓
           Log Parser (NEW)
              ↓
        Split outputs:
        ├─ Graph: Update attack state
        └─ Vector: Store new techniques
              ↓
        LLM Queries: Graph (state?) + Vector (exploit?)
              ↓
        LOOP
```

---

## VII. Testing Strategy

### Unit Tests
- [ ] Nmap parser with sample outputs
- [ ] Nikto parser with sample outputs
- [ ] Metasploit parser with sample outputs
- [ ] Entity deduplication
- [ ] Relationship linking

### Integration Tests
- [ ] Parse → Graph upsert → Query
- [ ] Parse → Vector upsert → Search
- [ ] Multiple sequential parses (state accumulation)

### Sample Test Data
```
tests/
├── fixtures/
│   ├── nmap_output.json
│   ├── nikto_output.xml
│   ├── metasploit_output.json
│   └── expected_entities.json
```

