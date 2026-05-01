"""Pydantic schemas for advanced search and filtering."""

from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SeverityEnum(str, Enum):
    """Severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class JobStatusFilterEnum(str, Enum):
    """Job status filter options."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class SearchJobsRequest(BaseModel):
    """Request model for job search."""
    
    query: Optional[str] = Field(
        None,
        description="Full-text search query (searches target_url and error_message)",
        example="example.com SQL"
    )
    status: Optional[JobStatusFilterEnum] = Field(
        None,
        description="Filter by job status"
    )
    target_url: Optional[str] = Field(
        None,
        description="Filter by target URL",
        example="https://example.com"
    )
    date_from: Optional[datetime] = Field(
        None,
        description="Filter jobs created after this date"
    )
    date_to: Optional[datetime] = Field(
        None,
        description="Filter jobs created before this date"
    )
    priority_min: Optional[int] = Field(
        None,
        ge=1,
        le=10,
        description="Minimum priority (1-10)"
    )
    priority_max: Optional[int] = Field(
        None,
        ge=1,
        le=10,
        description="Maximum priority (1-10)"
    )
    page: int = Field(
        1,
        ge=1,
        description="Page number (1-based)"
    )
    size: int = Field(
        20,
        ge=1,
        le=100,
        description="Results per page"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "SQL injection",
                "status": "completed",
                "date_from": "2026-04-01T00:00:00",
                "date_to": "2026-04-30T23:59:59",
                "priority_min": 5,
                "priority_max": 10,
                "page": 1,
                "size": 20
            }
        }


class JobSearchResult(BaseModel):
    """Single job search result."""
    
    job_id: str = Field(..., description="Unique job ID")
    job_type: str = Field(..., description="Type of job")
    status: str = Field(..., description="Current status")
    priority: int = Field(..., description="Priority level (1-10)")
    target_url: str = Field(..., description="Target URL scanned")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    findings_count: int = Field(..., description="Total findings")
    created_at: datetime = Field(..., description="Creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    duration_seconds: Optional[float] = Field(None, description="Execution duration")


class SearchJobsResponse(BaseModel):
    """Response model for job search."""
    
    results: List[JobSearchResult] = Field(..., description="Search results")
    total: int = Field(..., description="Total matching jobs")
    page: int = Field(..., description="Current page")
    size: int = Field(..., description="Results per page")
    total_pages: int = Field(..., description="Total pages")
    has_more: bool = Field(..., description="Whether more results available")


class SearchFindingsRequest(BaseModel):
    """Request model for findings search."""
    
    query: Optional[str] = Field(
        None,
        description="Full-text search query (searches URL and description)",
        example="CVE-2024 SQL"
    )
    severity: Optional[SeverityEnum] = Field(
        None,
        description="Filter by severity"
    )
    job_id: Optional[str] = Field(
        None,
        description="Filter by job ID"
    )
    target_url: Optional[str] = Field(
        None,
        description="Filter by target URL",
        example="https://example.com"
    )
    cve_id: Optional[str] = Field(
        None,
        description="Filter by CVE ID",
        example="CVE-2024-1234"
    )
    cwe_id: Optional[str] = Field(
        None,
        description="Filter by CWE ID",
        example="CWE-89"
    )
    date_from: Optional[datetime] = Field(
        None,
        description="Filter findings created after this date"
    )
    date_to: Optional[datetime] = Field(
        None,
        description="Filter findings created before this date"
    )
    page: int = Field(
        1,
        ge=1,
        description="Page number (1-based)"
    )
    size: int = Field(
        20,
        ge=1,
        le=100,
        description="Results per page"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "SQL injection",
                "severity": "CRITICAL",
                "cve_id": "CVE-2024-1234",
                "date_from": "2026-04-01T00:00:00",
                "date_to": "2026-04-30T23:59:59",
                "page": 1,
                "size": 20
            }
        }


class FindingSearchResult(BaseModel):
    """Single finding search result."""
    
    finding_id: str = Field(..., description="Unique finding ID")
    job_id: str = Field(..., description="Associated job ID")
    template_id: str = Field(..., description="Nuclei template ID")
    target_url: str = Field(..., description="Target URL")
    severity: str = Field(..., description="Severity level")
    host: str = Field(..., description="Host")
    url: str = Field(..., description="Finding URL")
    matched_at: Optional[datetime] = Field(None, description="Match timestamp")
    cve_ids: List[str] = Field(default_factory=list, description="CVE IDs")
    cwe_ids: List[str] = Field(default_factory=list, description="CWE IDs")
    description: Optional[str] = Field(None, description="Finding description")
    created_at: datetime = Field(..., description="Creation timestamp")


class SearchFindingsResponse(BaseModel):
    """Response model for findings search."""
    
    results: List[FindingSearchResult] = Field(..., description="Search results")
    total: int = Field(..., description="Total matching findings")
    page: int = Field(..., description="Current page")
    size: int = Field(..., description="Results per page")
    total_pages: int = Field(..., description="Total pages")
    has_more: bool = Field(..., description="Whether more results available")


class SearchStatisticsResponse(BaseModel):
    """Response model for search statistics."""
    
    total_findings: int = Field(..., description="Total findings indexed")
    average_findings_per_job: float = Field(
        ...,
        description="Average findings per job"
    )
    total_jobs_indexed: int = Field(..., description="Total jobs indexed")
    severity_distribution: Dict[str, int] = Field(
        ...,
        description="Distribution of findings by severity"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_findings": 1542,
                "average_findings_per_job": 38.5,
                "total_jobs_indexed": 40,
                "severity_distribution": {
                    "CRITICAL": 15,
                    "HIGH": 145,
                    "MEDIUM": 782,
                    "LOW": 600
                }
            }
        }


class SearchHealthResponse(BaseModel):
    """Health check response for Elasticsearch."""
    
    status: str = Field(..., description="Service status")
    elasticsearch_status: bool = Field(
        ...,
        description="Elasticsearch connection status"
    )
    indexes: Dict[str, Any] = Field(
        ...,
        description="Index information"
    )
