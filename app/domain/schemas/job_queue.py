"""Pydantic models for Job Queue management."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator


class JobStatusEnum(str, Enum):
    """Job execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class JobTypeEnum(str, Enum):
    """Type of background job."""

    NUCLEI_SCAN = "nuclei_scan"
    BATCH_SCAN = "batch_scan"
    NEO4J_UPSERT = "neo4j_upsert"
    REPORT_GENERATION = "report_generation"
    RESULT_IMPORT = "result_import"


class JobPriorityEnum(int, Enum):
    """Job priority levels (1-10)."""

    LOWEST = 1
    LOW = 3
    NORMAL = 5
    HIGH = 7
    CRITICAL = 10


class CreateJobRequest(BaseModel):
    """Request to create a new async job."""

    target_url: str = Field(..., description="Target URL for scanning", min_length=1)
    scan_type: str = Field(
        default="full",
        description="Type of scan (full, web, api)",
        pattern="^(full|web|api)$",
    )
    priority: int = Field(
        default=5,
        description="Job priority (1-10)",
        ge=1,
        le=10,
    )
    job_type: JobTypeEnum = Field(
        default=JobTypeEnum.NUCLEI_SCAN,
        description="Type of job to execute",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata",
    )
    callback_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for job completion notification",
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retries on failure",
        ge=0,
        le=10,
    )

    class Config:
        schema_extra = {
            "example": {
                "target_url": "http://localhost:3000",
                "scan_type": "full",
                "priority": 7,
                "job_type": "nuclei_scan",
                "metadata": {"custom_field": "value"},
                "callback_url": "http://webhook.example.com/notify",
                "max_retries": 3,
            }
        }


class JobMetadata(BaseModel):
    """Job metadata and execution details."""

    job_id: str = Field(..., description="Celery task ID")
    target_url: str
    scan_type: str
    priority: int
    payload: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    max_retries: int = 3
    started_at: Optional[datetime] = None
    error_message: Optional[str] = None


class JobResponse(BaseModel):
    """Response with job information."""

    id: UUID = Field(..., description="Job queue ID")
    job_id: str = Field(..., description="Celery task ID")
    status: JobStatusEnum = Field(..., description="Current job status")
    job_type: JobTypeEnum = Field(..., description="Type of job")
    target_url: Optional[str] = None
    priority: int
    progress: Optional[int] = Field(
        default=None,
        description="Progress percentage (0-100)",
    )
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    eta_seconds: Optional[int] = Field(
        default=None,
        description="Estimated seconds until completion",
    )

    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "job_id": "abc123def456",
                "status": "running",
                "job_type": "nuclei_scan",
                "target_url": "http://localhost:3000",
                "priority": 7,
                "progress": 45,
                "retry_count": 0,
                "created_at": "2026-04-29T10:00:00Z",
                "started_at": "2026-04-29T10:01:00Z",
                "eta_seconds": 300,
            }
        }


class JobResultResponse(BaseModel):
    """Response containing job result."""

    job_id: str = Field(..., description="Celery task ID")
    status: JobStatusEnum = Field(..., description="Job status")
    result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Job result data",
    )
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "job_id": "abc123def456",
                "status": "completed",
                "result": {
                    "scan_id": "scan-uuid",
                    "findings_count": 24,
                    "severity_breakdown": {
                        "CRITICAL": 2,
                        "HIGH": 5,
                        "MEDIUM": 12,
                        "LOW": 5,
                        "INFO": 0,
                    },
                    "neo4j_status": "upserted",
                },
                "completed_at": "2026-04-29T10:15:23Z",
            }
        }


class JobsListResponse(BaseModel):
    """Paginated list of jobs."""

    total: int = Field(..., description="Total number of jobs")
    count: int = Field(..., description="Number of jobs in this page")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Current page offset")
    jobs: List[JobResponse] = Field(..., description="List of jobs")

    class Config:
        schema_extra = {
            "example": {
                "total": 150,
                "count": 20,
                "limit": 20,
                "offset": 0,
                "jobs": [],
            }
        }


class JobHistoryResponse(BaseModel):
    """Job history for a target."""

    target_url: str
    total_jobs: int
    completed: int
    failed: int
    running: int
    jobs: List[JobResponse] = Field(..., description="Recent jobs")

    class Config:
        schema_extra = {
            "example": {
                "target_url": "http://localhost:3000",
                "total_jobs": 15,
                "completed": 12,
                "failed": 2,
                "running": 1,
                "jobs": [],
            }
        }


class QueueStatisticsResponse(BaseModel):
    """Queue statistics and metrics."""

    total_jobs: int = Field(..., description="Total jobs in queue")
    pending_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    cancelled_jobs: int
    average_completion_time: Optional[float] = Field(
        default=None,
        description="Average completion time in seconds",
    )
    success_rate: Optional[float] = Field(
        default=None,
        description="Success rate percentage (0-100)",
    )
    queue_size: int = Field(..., description="Current queue size")
    worker_count: int = Field(..., description="Active worker count")

    class Config:
        schema_extra = {
            "example": {
                "total_jobs": 1500,
                "pending_jobs": 45,
                "running_jobs": 12,
                "completed_jobs": 1380,
                "failed_jobs": 53,
                "cancelled_jobs": 10,
                "average_completion_time": 125.5,
                "success_rate": 92.3,
                "queue_size": 45,
                "worker_count": 4,
            }
        }


class ErrorResponse(BaseModel):
    """Error response format."""

    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")
    status_code: int = Field(..., description="HTTP status code")

    class Config:
        schema_extra = {
            "example": {
                "error": "JobNotFound",
                "detail": "Job with ID abc123 not found",
                "status_code": 404,
            }
        }


class CancelJobResponse(BaseModel):
    """Response after cancelling a job."""

    job_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="New status after cancellation")
    message: str = Field(..., description="Cancellation message")

    class Config:
        schema_extra = {
            "example": {
                "job_id": "abc123def456",
                "status": "cancelled",
                "message": "Job cancelled successfully",
            }
        }


class RetryJobResponse(BaseModel):
    """Response after retrying a job."""

    original_job_id: str = Field(..., description="Original job ID")
    new_job_id: str = Field(..., description="New Celery task ID")
    new_db_job_id: UUID = Field(..., description="New database job ID")
    status: str = Field(..., description="Status of new job")
    message: str = Field(..., description="Retry message")

    class Config:
        schema_extra = {
            "example": {
                "original_job_id": "abc123def456",
                "new_job_id": "xyz789uvw123",
                "new_db_job_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "pending",
                "message": "Job queued for retry",
            }
        }
