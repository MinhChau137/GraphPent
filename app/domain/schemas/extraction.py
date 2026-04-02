"""Pydantic schemas cho Entity & Relation extraction - Phase 5."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class Provenance(BaseModel):
    source_chunk_id: Optional[int] = None
    document_id: Optional[int] = None
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    llm_model: str = "llama3.1:8b"
    tool_origin: str = "graphrag-extraction"
    sensitivity: str = "lab-internal"

class Entity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str  # Asset, Host, IP, Domain, URL, Service, Application, APIEndpoint, Vulnerability, CVE, CWE, TTP, Credential, Finding, Evidence, Remediation, Tool, Report
    name: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)

class Relation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str  # AFFECTS, HOSTED_ON, EXPOSES, HAS_VULN, LINKED_TO_CVE, CONFIRMED_BY, OBSERVED_IN, REMEDIATED_BY, REACHABLE_VIA, DEPENDS_ON, EXPLOITS, POST_EXPLOIT, GENERATED_BY, DESCRIBED_IN
    source_id: str
    target_id: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)

class ExtractionResult(BaseModel):
    entities: List[Entity] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    raw_llm_output: Optional[str] = None
    error: Optional[str] = None
    chunk_id: Optional[int] = None