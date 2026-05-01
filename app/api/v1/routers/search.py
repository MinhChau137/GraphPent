"""FastAPI router for advanced search and filtering endpoints."""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Query, Depends

from app.services.search_service import get_search_service
from app.domain.schemas.search import (
    SearchJobsRequest,
    SearchFindingsRequest,
    SearchJobsResponse,
    SearchFindingsResponse,
    SearchStatisticsResponse,
    SearchHealthResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/search",
    tags=["Search"],
)


@router.post(
    "/jobs",
    response_model=SearchJobsResponse,
    summary="Search jobs with filtering",
    responses={
        200: {"description": "Search results"},
        400: {"description": "Invalid search parameters"},
        500: {"description": "Search service error"},
    }
)
async def search_jobs(
    request: SearchJobsRequest,
    search_service = Depends(get_search_service),
) -> SearchJobsResponse:
    """
    Advanced search for jobs with filtering.

    **Query Parameters**:
    - `query`: Full-text search on target URL and error messages
    - `status`: Filter by job status (pending, running, completed, failed, cancelled)
    - `target_url`: Filter by target URL
    - `date_from`: Filter jobs created after this date
    - `date_to`: Filter jobs created before this date
    - `priority_min`: Minimum priority (1-10)
    - `priority_max`: Maximum priority (1-10)
    - `page`: Page number (1-based, default 1)
    - `size`: Results per page (default 20, max 100)

    **Example**:
    ```
    POST /api/v1/search/jobs
    {
        "query": "SQL injection",
        "status": "completed",
        "priority_min": 5,
        "date_from": "2026-04-01T00:00:00",
        "page": 1,
        "size": 20
    }
    ```

    **Response**:
    ```json
    {
        "results": [
            {
                "job_id": "uuid",
                "job_type": "scan",
                "status": "completed",
                "priority": 8,
                "target_url": "https://example.com",
                "findings_count": 42,
                "created_at": "2026-04-15T10:30:00",
                "duration_seconds": 120.5
            }
        ],
        "total": 150,
        "page": 1,
        "size": 20,
        "total_pages": 8,
        "has_more": true
    }
    ```
    """
    logger.info(f"Searching jobs: {request}")
    return await search_service.search_jobs(request)


@router.get(
    "/jobs",
    response_model=SearchJobsResponse,
    summary="Search jobs (query string parameters)",
)
async def search_jobs_get(
    query: Optional[str] = Query(None, description="Full-text search query"),
    status: Optional[str] = Query(None, description="Filter by status"),
    target_url: Optional[str] = Query(None, description="Filter by target URL"),
    date_from: Optional[datetime] = Query(None, description="Filter from date"),
    date_to: Optional[datetime] = Query(None, description="Filter to date"),
    priority_min: Optional[int] = Query(None, ge=1, le=10, description="Min priority"),
    priority_max: Optional[int] = Query(None, ge=1, le=10, description="Max priority"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Results per page"),
    search_service = Depends(get_search_service),
) -> SearchJobsResponse:
    """
    Search jobs with query string parameters.

    Convenience endpoint for GET requests instead of POST.
    """
    request = SearchJobsRequest(
        query=query,
        status=status,
        target_url=target_url,
        date_from=date_from,
        date_to=date_to,
        priority_min=priority_min,
        priority_max=priority_max,
        page=page,
        size=size,
    )
    return await search_service.search_jobs(request)


@router.post(
    "/findings",
    response_model=SearchFindingsResponse,
    summary="Search findings with filtering",
    responses={
        200: {"description": "Search results"},
        400: {"description": "Invalid search parameters"},
        500: {"description": "Search service error"},
    }
)
async def search_findings(
    request: SearchFindingsRequest,
    search_service = Depends(get_search_service),
) -> SearchFindingsResponse:
    """
    Advanced search for findings with filtering.

    **Query Parameters**:
    - `query`: Full-text search on finding URL and description
    - `severity`: Filter by severity (CRITICAL, HIGH, MEDIUM, LOW, INFO)
    - `job_id`: Filter by job ID
    - `target_url`: Filter by target URL
    - `cve_id`: Filter by CVE ID
    - `cwe_id`: Filter by CWE ID
    - `date_from`: Filter findings created after this date
    - `date_to`: Filter findings created before this date
    - `page`: Page number (1-based, default 1)
    - `size`: Results per page (default 20, max 100)

    **Example**:
    ```
    POST /api/v1/search/findings
    {
        "query": "XSS vulnerability",
        "severity": "CRITICAL",
        "cve_id": "CVE-2024-1234",
        "date_from": "2026-04-01T00:00:00",
        "page": 1,
        "size": 20
    }
    ```

    **Response**:
    ```json
    {
        "results": [
            {
                "finding_id": "uuid",
                "job_id": "job-uuid",
                "template_id": "xss-reflection",
                "target_url": "https://example.com",
                "severity": "CRITICAL",
                "url": "https://example.com/search?q=alert",
                "cve_ids": ["CVE-2024-1234"],
                "cwe_ids": ["CWE-79"],
                "created_at": "2026-04-15T10:30:00"
            }
        ],
        "total": 350,
        "page": 1,
        "size": 20,
        "total_pages": 18,
        "has_more": true
    }
    ```
    """
    logger.info(f"Searching findings: {request}")
    return await search_service.search_findings(request)


@router.get(
    "/findings",
    response_model=SearchFindingsResponse,
    summary="Search findings (query string parameters)",
)
async def search_findings_get(
    query: Optional[str] = Query(None, description="Full-text search query"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    job_id: Optional[str] = Query(None, description="Filter by job ID"),
    target_url: Optional[str] = Query(None, description="Filter by target URL"),
    cve_id: Optional[str] = Query(None, description="Filter by CVE ID"),
    cwe_id: Optional[str] = Query(None, description="Filter by CWE ID"),
    date_from: Optional[datetime] = Query(None, description="Filter from date"),
    date_to: Optional[datetime] = Query(None, description="Filter to date"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Results per page"),
    search_service = Depends(get_search_service),
) -> SearchFindingsResponse:
    """
    Search findings with query string parameters.

    Convenience endpoint for GET requests instead of POST.
    """
    request = SearchFindingsRequest(
        query=query,
        severity=severity,
        job_id=job_id,
        target_url=target_url,
        cve_id=cve_id,
        cwe_id=cwe_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
    )
    return await search_service.search_findings(request)


@router.get(
    "/statistics",
    response_model=SearchStatisticsResponse,
    summary="Get search statistics",
    responses={
        200: {"description": "Statistics"},
        500: {"description": "Search service error"},
    }
)
async def get_statistics(
    job_id: Optional[str] = Query(None, description="Filter to specific job"),
    date_from: Optional[datetime] = Query(None, description="Filter from date"),
    date_to: Optional[datetime] = Query(None, description="Filter to date"),
    search_service = Depends(get_search_service),
) -> SearchStatisticsResponse:
    """
    Get aggregated statistics from search indexes.

    **Query Parameters**:
    - `job_id`: Filter statistics to a specific job
    - `date_from`: Filter from date
    - `date_to`: Filter to date

    **Response**:
    ```json
    {
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
    ```
    """
    logger.info(f"Getting statistics: job_id={job_id}, date_from={date_from}, date_to={date_to}")
    return await search_service.get_statistics(
        job_id=job_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/health",
    response_model=SearchHealthResponse,
    summary="Search service health check",
)
async def search_health(
    search_service = Depends(get_search_service),
) -> SearchHealthResponse:
    """
    Check Elasticsearch and search service health.

    **Response**:
    ```json
    {
        "status": "healthy",
        "elasticsearch_status": true,
        "indexes": {
            "jobs": {"status": "green", "doc_count": 150},
            "findings": {"status": "green", "doc_count": 3500},
            "results": {"status": "green", "doc_count": 150}
        }
    }
    ```
    """
    is_healthy = await search_service.health_check()

    return SearchHealthResponse(
        status="healthy" if is_healthy else "unhealthy",
        elasticsearch_status=is_healthy,
        indexes={
            "jobs": {"status": "green" if is_healthy else "red"},
            "findings": {"status": "green" if is_healthy else "red"},
            "results": {"status": "green" if is_healthy else "red"},
        },
    )
