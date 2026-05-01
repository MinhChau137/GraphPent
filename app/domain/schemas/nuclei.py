"""Nuclei API Schemas - Request/Response Models.

Pydantic models for REST API validation and serialization.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class SeverityEnum(str, Enum):
    """Severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ScanStatusEnum(str, Enum):
    """Scan status values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Neo4jStatusEnum(str, Enum):
    """Neo4j processing status."""
    PENDING = "pending"
    UPSERTED = "upserted"
    FAILED = "failed"


# ==================== Request Models ====================

class CreateScanRequest(BaseModel):
    """Request to create a new scan."""
    target_url: str = Field(..., description="Target URL/IP to scan")
    scan_type: str = Field("full", description="Scan type: full, web, api")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        schema_extra = {
            "example": {
                "target_url": "http://192.168.1.100",
                "scan_type": "full",
                "metadata": {"tags": ["internal", "prod"]}
            }
        }


class ProcessNucleiOutputRequest(BaseModel):
    """Request to process Nuclei output."""
    nuclei_output: str = Field(..., description="Nuclei output (JSONL, JSON, or list)")
    target_url: Optional[str] = Field(None, description="Target URL for context")
    scan_id: Optional[str] = Field(None, description="Custom scan ID (UUID generated if not provided)")

    class Config:
        schema_extra = {
            "example": {
                "nuclei_output": '{"template-id":"sql-injection","severity":"critical","host":"192.168.1.100"}',
                "target_url": "http://192.168.1.100",
                "scan_id": None
            }
        }


class FindingsQueryRequest(BaseModel):
    """Request to query findings."""
    severity: Optional[SeverityEnum] = Field(None, description="Filter by severity")
    host: Optional[str] = Field(None, description="Filter by target host")
    template_id: Optional[str] = Field(None, description="Filter by Nuclei template")
    limit: int = Field(100, ge=1, le=1000, description="Max results to return")
    offset: int = Field(0, ge=0, description="Pagination offset")

    class Config:
        schema_extra = {
            "example": {
                "severity": "CRITICAL",
                "host": "192.168.1.100",
                "template_id": None,
                "limit": 50,
                "offset": 0
            }
        }


# ==================== Response Models ====================

class ScanMetadata(BaseModel):
    """Scan metadata response."""
    id: str = Field(..., description="Scan ID (UUID)")
    target_url: str = Field(..., description="Target URL")
    status: ScanStatusEnum = Field(..., description="Current scan status")
    scan_type: str = Field(..., description="Type of scan")
    findings_count: int = Field(default=0, description="Number of findings")
    neo4j_status: Neo4jStatusEnum = Field(..., description="Neo4j processing status")
    started_at: Optional[datetime] = Field(None, description="When scan started")
    completed_at: Optional[datetime] = Field(None, description="When scan completed")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "target_url": "http://192.168.1.100",
                "status": "completed",
                "scan_type": "full",
                "findings_count": 5,
                "neo4j_status": "upserted",
                "started_at": "2026-04-28T10:00:00Z",
                "completed_at": "2026-04-28T10:05:00Z",
                "error_message": None
            }
        }


class FindingResponse(BaseModel):
    """Individual finding response."""
    id: str = Field(..., description="Finding UUID")
    scan_id: str = Field(..., description="Parent scan ID")
    template_id: str = Field(..., description="Nuclei template ID")
    severity: SeverityEnum = Field(..., description="Severity level")
    host: str = Field(..., description="Target host")
    url: str = Field(..., description="Target URL")
    matched_at: Optional[datetime] = Field(None, description="When found")
    cve_ids: List[str] = Field(default_factory=list, description="Related CVEs")
    cwe_ids: List[str] = Field(default_factory=list, description="Related CWEs")
    neo4j_id: Optional[str] = Field(None, description="UUID in Neo4j")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "scan_id": "550e8400-e29b-41d4-a716-446655440000",
                "template_id": "sql-injection",
                "severity": "CRITICAL",
                "host": "192.168.1.100",
                "url": "http://192.168.1.100/api/search",
                "matched_at": "2026-04-28T10:02:00Z",
                "cve_ids": ["CVE-2024-1234"],
                "cwe_ids": ["CWE-89"],
                "neo4j_id": "neo4j-uuid",
                "metadata": {}
            }
        }


class ProcessingResult(BaseModel):
    """Result of processing Nuclei output."""
    scan_id: str = Field(..., description="Scan identifier")
    findings_count: int = Field(..., description="Total findings parsed")
    findings_stored: int = Field(..., description="Successfully stored findings")
    findings_failed: int = Field(default=0, description="Failed to store")
    cve_relationships: int = Field(default=0, description="CVE relationships created")
    cwe_relationships: int = Field(default=0, description="CWE relationships created")
    status: str = Field(..., description="Processing status")
    parser_warnings: int = Field(default=0, description="Parser warnings")
    relationship_errors: int = Field(default=0, description="Relationship errors")

    class Config:
        schema_extra = {
            "example": {
                "scan_id": "550e8400-e29b-41d4-a716-446655440000",
                "findings_count": 5,
                "findings_stored": 5,
                "findings_failed": 0,
                "cve_relationships": 3,
                "cwe_relationships": 4,
                "status": "completed",
                "parser_warnings": 0,
                "relationship_errors": 0
            }
        }


class FindingsResponse(BaseModel):
    """Paginated findings response."""
    total: int = Field(..., description="Total findings matching query")
    count: int = Field(..., description="Findings in this response")
    limit: int = Field(..., description="Limit parameter")
    offset: int = Field(..., description="Offset parameter")
    findings: List[FindingResponse] = Field(..., description="Finding list")

    class Config:
        schema_extra = {
            "example": {
                "total": 25,
                "count": 10,
                "limit": 10,
                "offset": 0,
                "findings": []
            }
        }


class ScansResponse(BaseModel):
    """Paginated scans response."""
    total: int = Field(..., description="Total scans")
    count: int = Field(..., description="Scans in this response")
    scans: List[ScanMetadata] = Field(..., description="Scan list")

    class Config:
        schema_extra = {
            "example": {
                "total": 50,
                "count": 10,
                "scans": []
            }
        }


class StatisticsResponse(BaseModel):
    """System statistics response."""
    total_scans: int = Field(..., description="Total scans executed")
    total_findings: int = Field(..., description="Total findings discovered")
    critical_findings: int = Field(..., description="Critical severity findings")
    scans_completed: int = Field(..., description="Successfully completed scans")
    last_scan: Optional[datetime] = Field(None, description="Time of last scan")
    findings_by_severity: Dict[str, int] = Field(default_factory=dict, description="Distribution by severity")
    findings_by_host: Dict[str, int] = Field(default_factory=dict, description="Distribution by host")

    class Config:
        schema_extra = {
            "example": {
                "total_scans": 100,
                "total_findings": 523,
                "critical_findings": 45,
                "scans_completed": 95,
                "last_scan": "2026-04-28T10:05:00Z",
                "findings_by_severity": {
                    "CRITICAL": 45,
                    "HIGH": 120,
                    "MEDIUM": 200,
                    "LOW": 150,
                    "INFO": 8
                },
                "findings_by_host": {
                    "192.168.1.100": 150,
                    "192.168.1.101": 200,
                    "192.168.1.102": 173
                }
            }
        }


class ErrorResponse(BaseModel):
    """Error response."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    status_code: int = Field(..., description="HTTP status code")

    class Config:
        schema_extra = {
            "example": {
                "error": "Scan not found",
                "detail": "Scan ID 550e8400-e29b-41d4-a716-446655440000 does not exist",
                "status_code": 404
            }
        }


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    neo4j: str = Field(..., description="Neo4j connection status")
    postgres: str = Field(..., description="PostgreSQL connection status")
    version: str = Field(..., description="API version")

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "neo4j": "connected",
                "postgres": "connected",
                "version": "1.0.0"
            }
        }
