"""Batch operations schemas (Phase 5.5)."""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator


class BatchStatusEnum(str, Enum):
    """Batch job status."""
    
    PENDING = "pending"
    PROCESSING = "processing"
    PARTIAL_SUCCESS = "partial_success"
    COMPLETED = "completed"
    FAILED = "failed"


class BatchTargetItem(BaseModel):
    """Single target for batch submission."""
    
    target_url: str = Field(..., description="Target URL")
    scan_type: str = Field(default="full", description="Scan type: full, web, api")
    priority: int = Field(default=5, ge=1, le=10, description="Priority 1-10")
    custom_metadata: Optional[Dict[str, Any]] = None


class BatchJobCreate(BaseModel):
    """Create batch job request."""
    
    targets: List[BatchTargetItem] = Field(..., min_items=1, max_items=100, description="Targets for batch scan")
    batch_name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    notify_on_completion: bool = False
    notification_url: Optional[str] = None
    
    @validator("targets")
    def validate_targets(cls, v):
        """Validate batch targets."""
        if len(v) > 100:
            raise ValueError("Maximum 100 targets per batch")
        return v


class BatchTargetResult(BaseModel):
    """Result for single target in batch."""
    
    target_url: str
    job_id: str
    status: str
    findings_count: Optional[int] = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class BatchJobResponse(BaseModel):
    """Batch job response."""
    
    batch_id: str = Field(..., description="Batch job ID")
    batch_name: str
    status: BatchStatusEnum
    created_by: str
    total_targets: int
    completed_targets: int
    failed_targets: int
    success_rate: float = Field(..., description="Percentage of successful jobs")
    results: List[BatchTargetResult] = []
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    class Config:
        from_attributes = True


class BatchJobListItem(BaseModel):
    """Batch job list item."""
    
    batch_id: str
    batch_name: str
    status: BatchStatusEnum
    created_by: str
    total_targets: int
    completed_targets: int
    failed_targets: int
    success_rate: float
    created_at: datetime
    completed_at: Optional[datetime] = None


class BatchSearchRequest(BaseModel):
    """Batch search across multiple jobs."""
    
    batch_ids: List[str] = Field(..., description="Batch IDs to search", max_items=10)
    query: Optional[str] = None
    severity: Optional[str] = None
    cve_id: Optional[str] = None
    page: int = Field(1, ge=1, description="Page number")
    size: int = Field(20, ge=1, le=100, description="Results per page")


class AggregatedFindings(BaseModel):
    """Aggregated findings across batches."""
    
    total_findings: int
    by_severity: Dict[str, int] = Field(description="Severity distribution")
    by_job: Dict[str, int] = Field(description="Findings per job")
    unique_templates: int
    unique_cvEs: int
    
    class Config:
        from_attributes = True


class BatchSearchResponse(BaseModel):
    """Batch search response."""
    
    batch_ids: List[str]
    aggregated_findings: AggregatedFindings
    results: List[Dict[str, Any]]
    total: int
    page: int
    total_pages: int
    has_more: bool


class BatchStatistics(BaseModel):
    """Batch job statistics."""
    
    total_batches: int
    active_batches: int
    completed_batches: int
    total_jobs_submitted: int
    total_jobs_completed: int
    average_targets_per_batch: float
    average_success_rate: float
    average_job_duration_seconds: float
    total_findings_discovered: int


class BulkImportItem(BaseModel):
    """Single item for bulk import."""
    
    target_url: str
    scan_data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class BulkImportRequest(BaseModel):
    """Bulk import request."""
    
    items: List[BulkImportItem] = Field(..., min_items=1, max_items=1000)
    skip_duplicates: bool = True
    merge_results: bool = True


class BulkImportResult(BaseModel):
    """Bulk import result."""
    
    total_items: int
    imported_items: int
    skipped_items: int
    failed_items: int
    errors: List[Dict[str, str]] = []


class BatchExportRequest(BaseModel):
    """Request to export batch results."""
    
    batch_id: str
    format: str = Field("json", pattern="^(json|csv)$")
    include_details: bool = True
    include_metadata: bool = True


class BatchExportResponse(BaseModel):
    """Batch export response."""
    
    batch_id: str
    format: str
    download_url: str
    created_at: datetime
    expires_at: datetime
    size_bytes: int
