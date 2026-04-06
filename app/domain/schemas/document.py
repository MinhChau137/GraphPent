"""Pydantic schemas cho ingestion - Phase 4."""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

class DocumentMetadata(BaseModel):
    source: str = "upload"
    original_filename: str
    content_type: str
    size_bytes: Optional[int] = None
    uploaded_by: str = "system"
    sensitivity: str = "lab-internal"

class IngestRequest(BaseModel):
    metadata: Optional[DocumentMetadata] = Field(default_factory=DocumentMetadata)

class IngestResponse(BaseModel):
    document_id: Optional[int] = None
    filename: str
    chunks_count: int = 0
    status: str
    message: Optional[str] = None
    ingestion_job_id: Optional[str] = None