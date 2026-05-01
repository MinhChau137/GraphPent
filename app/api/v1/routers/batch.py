"""Batch operations endpoints (Phase 5.5)."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.services.batch_service import BatchService, get_batch_service
from app.domain.schemas.batch import (
    BatchJobCreate,
    BatchJobResponse,
    BatchJobListItem,
    BatchSearchRequest,
    BatchSearchResponse,
    BatchStatistics,
    BulkImportRequest,
    BulkImportResult,
    BatchExportRequest,
    BatchExportResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/batch", tags=["Batch Operations"])


def get_current_user(request) -> dict:
    """Get current user from request state."""
    return {
        "user_id": getattr(request, "user_id", None),
        "username": getattr(request, "username", None),
    }


# ==================== Batch Job Endpoints ====================


@router.post("/jobs", response_model=BatchJobResponse, status_code=status.HTTP_201_CREATED)
async def create_batch_job(
    batch_data: BatchJobCreate,
    batch_service: BatchService = Depends(get_batch_service),
    # current_user: dict = Depends(get_current_user),
):
    """Create new batch job with multiple targets.
    
    **Requires**: `jobs:batch` permission
    
    Example:
    ```json
    {
      "targets": [
        {"target_url": "https://example.com", "priority": 8},
        {"target_url": "https://api.example.com", "scan_type": "api"}
      ],
      "batch_name": "Example.com Scan",
      "description": "Full scan of example domains"
    }
    ```
    """
    try:
        # TODO: Get real user_id from current_user after auth integration
        user_id = "system"

        batch_job = await batch_service.create_batch_job(batch_data, user_id)
        logger.info(f"Batch job created: {batch_job.batch_id}")
        return batch_job
    except Exception as e:
        logger.error(f"Failed to create batch job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create batch job",
        )


@router.get("/jobs/{batch_id}", response_model=BatchJobResponse)
async def get_batch_job(
    batch_id: str,
    batch_service: BatchService = Depends(get_batch_service),
):
    """Get batch job status with aggregated results.
    
    **Requires**: `jobs:read` permission
    """
    batch_job = await batch_service.get_batch_status(batch_id)

    if not batch_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch job {batch_id} not found",
        )

    return batch_job


@router.get("/jobs", response_model=List[BatchJobListItem])
async def list_batch_jobs(
    status: str = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    batch_service: BatchService = Depends(get_batch_service),
):
    """List batch jobs (paginated).
    
    **Requires**: `jobs:read` permission
    """
    # TODO: Get real user_id after auth integration
    batches, total = await batch_service.list_batches(status=status, limit=limit, offset=offset)

    return [
        BatchJobListItem(
            batch_id=b.batch_id,
            batch_name=b.batch_name,
            status=b.status,
            created_by=b.created_by,
            total_targets=b.total_targets,
            completed_targets=b.completed_targets,
            failed_targets=b.failed_targets,
            success_rate=b.success_rate,
            created_at=b.created_at,
            completed_at=b.completed_at,
        )
        for b in batches
    ]


# ==================== Batch Search Endpoints ====================


@router.post("/search", response_model=BatchSearchResponse)
async def search_batch_results(
    search_request: BatchSearchRequest,
    batch_service: BatchService = Depends(get_batch_service),
):
    """Search across multiple batch jobs.
    
    **Requires**: `search:advanced` permission
    
    Example:
    ```json
    {
      "batch_ids": ["batch-1", "batch-2"],
      "query": "SQL injection",
      "severity": "CRITICAL"
    }
    ```
    """
    try:
        results = await batch_service.batch_search(search_request)
        logger.info(f"Searched {len(search_request.batch_ids)} batches, found {results.total} results")
        return results
    except Exception as e:
        logger.error(f"Batch search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch search failed",
        )


# ==================== Statistics Endpoints ====================


@router.get("/statistics", response_model=BatchStatistics)
async def get_batch_statistics(
    batch_service: BatchService = Depends(get_batch_service),
):
    """Get batch operations statistics.
    
    **Requires**: `jobs:read` permission
    """
    stats = await batch_service.get_batch_statistics()
    return stats


# ==================== Bulk Import/Export ====================


@router.post("/import", response_model=BulkImportResult)
async def bulk_import(
    import_data: BulkImportRequest,
    batch_service: BatchService = Depends(get_batch_service),
):
    """Bulk import scan data from external sources.
    
    **Requires**: `results:import` permission
    
    Example:
    ```json
    {
      "items": [
        {
          "target_url": "https://example.com",
          "scan_data": {"findings_count": 10, "severity_breakdown": {...}}
        }
      ],
      "skip_duplicates": true
    }
    ```
    """
    try:
        # TODO: Get real user_id after auth integration
        user_id = "system"

        result = await batch_service.bulk_import(import_data, user_id)
        logger.info(
            f"Bulk import: {result.imported_items} imported, {result.skipped_items} skipped, "
            f"{result.failed_items} failed"
        )
        return result
    except Exception as e:
        logger.error(f"Bulk import failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk import failed",
        )


@router.post("/export", response_model=BatchExportResponse)
async def export_batch_results(
    export_request: BatchExportRequest,
):
    """Export batch job results.
    
    **Requires**: `results:export` permission
    
    Returns download URL for exported data (CSV or JSON).
    """
    # TODO: Implement export functionality with file storage (S3/MinIO)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Export functionality coming in Phase 5.6",
    )


# ==================== Health Check ====================


@router.get("/health")
async def batch_health_check():
    """Check batch operations service health."""
    return {
        "status": "healthy",
        "service": "batch-operations",
        "version": "5.5.0",
    }
