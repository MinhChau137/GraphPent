"""Pydantic schemas cho Entity & Relation - FIXED validation (Phase 5+6)."""

from pydantic import BaseModel, Field, model_validator
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
    type: str                    # Có thể là: Weakness, CWE, Category, Mitigation, Consequence, Vulnerability, CVE, ...
    name: str = Field(..., min_length=1)
    properties: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode='before')
    @classmethod
    def fallback_id_and_name(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Fix id
            if data.get("id") is None or str(data.get("id")).strip() == "":
                data["id"] = str(uuid.uuid4())
            
            # Fix name cho CWE
            if not data.get("name") or str(data.get("name")).strip() == "":
                data["name"] = (
                    data.get("value")
                    or data.get("Name")           # từ XML CWE
                    or data.get("cweId")
                    or data.get("id")
                    or f"unknown-{data.get('type', 'entity')}"
                )
        return data

class Relation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
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