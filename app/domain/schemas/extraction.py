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

    @model_validator(mode='before')
    @classmethod
    def fallback_relation_ids(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("id") is None or str(data.get("id")).strip() == "":
                data["id"] = str(uuid.uuid4())

            # Keep invalid relations fail-safe: normalize missing IDs to empty strings
            # so the extraction layer can reject them before graph storage.
            if data.get("source_id") is None:
                data["source_id"] = ""
            if data.get("target_id") is None:
                data["target_id"] = ""

            if data.get("source") is not None and not data.get("source_id"):
                data["source_id"] = str(data.get("source"))
            if data.get("target") is not None and not data.get("target_id"):
                data["target_id"] = str(data.get("target"))

            if data.get("type") is None or str(data.get("type")).strip() == "":
                data["type"] = "RELATED_TO"
        return data

class ExtractionResult(BaseModel):
    entities: List[Entity] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    raw_llm_output: Optional[str] = None
    error: Optional[str] = None
    chunk_id: Optional[int] = None