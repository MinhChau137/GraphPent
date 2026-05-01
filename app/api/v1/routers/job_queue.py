"""FastAPI router for job queue management."""

import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.services.job_queue_service import get_job_queue_service
from app.domain.schemas.job_queue import (
    CreateJobRequest,
    JobResponse,
    JobResultResponse,
    JobsListResponse,
    JobHistoryResponse,
    QueueStatisticsResponse,
    ErrorResponse,
    CancelJobResponse,
    RetryJobResponse,
    JobTypeEnum,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["Job Queue"],
    responses={
        404: {"model": ErrorResponse, "description": "Not found"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)


@router.post(
    "/scan",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobResponse,
    summary="Submit async Nuclei scan",
    description="Submit a Nuclei scan to run in background",
)
async def submit_scan(
    request: CreateJobRequest,
    service=Depends(get_job_queue_service),
) -> JobResponse:
    """
    Submit an async Nuclei scan job.
    
    Returns 202 Accepted with job ID for polling.
    
    - **target_url**: URL to scan
    - **scan_type**: Type of scan (full, web, api)
    - **priority**: Job priority (1-10, higher = more urgent)
    - **metadata**: Additional metadata
    - **callback_url**: Optional webhook for completion
    - **max_retries**: Max retries on failure (0-10)
    """
    try:
        job = await service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url=request.target_url,
            scan_type=request.scan_type,
            priority=request.priority,
            metadata=request.metadata,
            callback_url=request.callback_url,
            max_retries=request.max_retries,
        )
        logger.info(f"Scan submitted: {job.id}")
        return job
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error submitting scan: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit scan job",
        )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status",
    description="Get current status and progress of a job",
)
async def get_job_status(
    job_id: str,
    service=Depends(get_job_queue_service),
) -> JobResponse:
    """
    Get the current status of a job.
    
    - **job_id**: Database job ID (UUID)
    
    Returns job status, progress (if running), and result (if completed).
    """
    try:
        job = await service.get_job_status(job_id)
        return job
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get job status",
        )


@router.get(
    "/{job_id}/result",
    response_model=JobResultResponse,
    summary="Get job result",
    description="Get result of a completed job",
)
async def get_job_result(
    job_id: str,
    service=Depends(get_job_queue_service),
) -> JobResultResponse:
    """
    Get the result of a completed job.
    
    - **job_id**: Database job ID (UUID)
    
    Only works for completed or failed jobs.
    """
    try:
        result = await service.get_job_result(job_id)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error getting job result: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get job result",
        )


@router.delete(
    "/{job_id}",
    response_model=CancelJobResponse,
    summary="Cancel job",
    description="Cancel a pending or running job",
)
async def cancel_job(
    job_id: str,
    service=Depends(get_job_queue_service),
) -> CancelJobResponse:
    """
    Cancel a pending or running job.
    
    - **job_id**: Database job ID (UUID)
    
    Returns error if job cannot be cancelled (e.g., already completed).
    """
    try:
        result = await service.cancel_job(job_id)
        return CancelJobResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error cancelling job: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel job",
        )


@router.get(
    "",
    response_model=JobsListResponse,
    summary="List jobs",
    description="Get paginated list of jobs",
)
async def list_jobs(
    status: Optional[str] = Query(
        None,
        description="Filter by status (pending, running, completed, failed, cancelled, retrying)",
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Items per page",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Page offset",
    ),
    service=Depends(get_job_queue_service),
) -> JobsListResponse:
    """
    List jobs with optional filtering and pagination.
    
    Query Parameters:
    - **status**: Filter by status (optional)
    - **limit**: Items per page (1-100, default 20)
    - **offset**: Page offset (default 0)
    """
    try:
        result = await service.list_jobs(
            status=status,
            limit=limit,
            offset=offset,
        )
        return JobsListResponse(**result)
    except Exception as e:
        logger.error(f"Error listing jobs: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list jobs",
        )


@router.get(
    "/history/{target_url}",
    response_model=JobHistoryResponse,
    summary="Get job history",
    description="Get job history for a specific target",
)
async def get_job_history(
    target_url: str,
    limit: int = Query(10, ge=1, le=100, description="Number of jobs to return"),
    service=Depends(get_job_queue_service),
) -> JobHistoryResponse:
    """
    Get job history for a specific target.
    
    - **target_url**: Target URL to query
    - **limit**: Number of recent jobs to return
    """
    try:
        result = await service.get_job_history(
            target_url=target_url,
            limit=limit,
        )
        return JobHistoryResponse(**result)
    except Exception as e:
        logger.error(f"Error getting job history: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get job history",
        )


@router.post(
    "/{job_id}/retry",
    response_model=RetryJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry failed job",
    description="Retry a failed job",
)
async def retry_job(
    job_id: str,
    max_retries: int = Query(3, ge=0, le=10, description="Max retries for new job"),
    service=Depends(get_job_queue_service),
) -> RetryJobResponse:
    """
    Retry a failed job.
    
    - **job_id**: Original job ID (UUID)
    - **max_retries**: Max retries for the new job (0-10, default 3)
    
    Returns 202 Accepted with new job details.
    """
    try:
        result = await service.retry_failed_job(
            job_id=job_id,
            max_retries=max_retries,
        )
        return RetryJobResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error retrying job: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retry job",
        )


@router.get(
    "/stats",
    response_model=QueueStatisticsResponse,
    summary="Queue statistics",
    description="Get queue statistics and metrics",
)
async def get_queue_stats(
    service=Depends(get_job_queue_service),
) -> QueueStatisticsResponse:
    """
    Get queue statistics and performance metrics.
    
    Returns:
    - Total jobs, pending, running, completed, failed
    - Average completion time
    - Success rate
    - Queue size
    - Active worker count
    """
    try:
        stats = await service.get_queue_statistics()
        return stats
    except Exception as e:
        logger.error(f"Error getting queue stats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get queue statistics",
        )
