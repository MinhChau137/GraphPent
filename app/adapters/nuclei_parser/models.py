"""
Nuclei Parser Data Models

Models for parsing and normalizing Nuclei vulnerability scan outputs.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import uuid4


class SeverityEnum(str, Enum):
    """Severity levels for vulnerabilities"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class NucleiRawOutput(BaseModel):
    """Raw Nuclei JSON output - maps directly from Nuclei JSON"""
    
    # Core fields
    template_id: str = Field(..., alias="template-id")
    type: str
    host: str
    matched_at: str = Field(..., alias="matched-at")
    severity: str
    
    # Optional fields
    cve_id: Optional[str] = Field(default=None, alias="cve-id")
    cwe_id: Optional[str] = Field(default=None, alias="cwe-id")
    template_url: Optional[str] = Field(default=None, alias="template-url")
    matcher_name: Optional[str] = Field(default=None, alias="matcher-name")
    
    # Nested info
    info: Optional[Dict[str, Any]] = None
    extracted_results: Optional[Dict[str, Any]] = Field(default=None, alias="extracted-results")
    
    class Config:
        populate_by_name = True  # Allow both underscores and hyphens


class NucleiTemplate(BaseModel):
    """Nuclei template metadata"""
    
    name: str
    type: str
    severity: SeverityEnum
    cve_id: Optional[str] = None
    cwe_id: Optional[str] = None
    description: Optional[str] = None


class NucleiMatched(BaseModel):
    """Single matched result from Nuclei"""
    
    template_id: str
    template_url: Optional[str]
    host: str
    matched_at: str
    severity: SeverityEnum
    cve_id: Optional[List[str]] = []
    cwe_id: Optional[List[str]] = []
    description: Optional[str]
    matcher_name: Optional[str]
    extracted_results: Optional[Dict[str, Any]] = {}


class Finding(BaseModel):
    """Normalized Finding entity for Neo4j storage"""
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    template_id: str
    severity: SeverityEnum
    host: str
    url: str
    cve_ids: List[str] = Field(default_factory=list)
    cwe_ids: List[str] = Field(default_factory=list)
    matched_at: datetime
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Tracking fields
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source: str = "nuclei"


class NormalizationResult(BaseModel):
    """Result of normalization process"""
    
    findings: List[Finding]
    normalized_count: int
    failed_count: int = 0
    errors: List[str] = Field(default_factory=list)


class ScanMetadata(BaseModel):
    """Metadata for a Nuclei scan"""
    
    scan_id: str = Field(default_factory=lambda: str(uuid4()))
    target_url: str
    templates: Optional[List[str]] = None
    timeout: int = 300
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed
    findings_count: int = 0
    raw_output_path: Optional[str] = None  # MinIO path
    error_message: Optional[str] = None


class ScanResult(BaseModel):
    """Result of scan execution"""
    
    scan_id: str
    status: str
    target_url: str
    findings_count: int
    findings: List[Finding] = Field(default_factory=list)
    error: Optional[str] = None


class CorrelationResult(BaseModel):
    """Result of CVE/CWE correlation"""
    
    finding_id: str
    cve_ids_matched: List[str]
    cwe_ids_matched: List[str]
    correlation_confidence: float
