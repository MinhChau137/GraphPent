"""Advanced search and filtering service using Elasticsearch."""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from app.adapters.elasticsearch_client import get_elasticsearch_client
from app.domain.schemas.search import (
    SearchJobsRequest,
    SearchFindingsRequest,
    SearchJobsResponse,
    SearchFindingsResponse,
    JobSearchResult,
    FindingSearchResult,
    SearchStatisticsResponse,
)

logger = logging.getLogger(__name__)


class SearchService:
    """Service for advanced search and filtering."""

    def __init__(self):
        """Initialize search service."""
        self.es_client = None

    async def _get_es_client(self):
        """Lazy-load Elasticsearch client."""
        if self.es_client is None:
            self.es_client = await get_elasticsearch_client()
        return self.es_client

    async def search_jobs(
        self, request: SearchJobsRequest
    ) -> SearchJobsResponse:
        """
        Search jobs with advanced filtering.

        Args:
            request: Search request parameters

        Returns:
            Search results response
        """
        try:
            es_client = await self._get_es_client()

            results, total = es_client.search_jobs(
                query=request.query,
                status=request.status,
                target_url=request.target_url,
                date_from=request.date_from,
                date_to=request.date_to,
                priority_min=request.priority_min,
                priority_max=request.priority_max,
                page=request.page,
                size=request.size,
            )

            # Convert to response models
            search_results = [JobSearchResult(**job) for job in results]

            # Calculate pagination
            total_pages = (total + request.size - 1) // request.size

            return SearchJobsResponse(
                results=search_results,
                total=total,
                page=request.page,
                size=request.size,
                total_pages=total_pages,
                has_more=request.page < total_pages,
            )

        except Exception as e:
            logger.error(f"Error searching jobs: {str(e)}")
            return SearchJobsResponse(
                results=[],
                total=0,
                page=request.page,
                size=request.size,
                total_pages=0,
                has_more=False,
            )

    async def search_findings(
        self, request: SearchFindingsRequest
    ) -> SearchFindingsResponse:
        """
        Search findings with advanced filtering.

        Args:
            request: Search request parameters

        Returns:
            Search results response
        """
        try:
            es_client = await self._get_es_client()

            results, total = es_client.search_findings(
                query=request.query,
                severity=request.severity,
                job_id=request.job_id,
                target_url=request.target_url,
                cve_id=request.cve_id,
                cwe_id=request.cwe_id,
                date_from=request.date_from,
                date_to=request.date_to,
                page=request.page,
                size=request.size,
            )

            # Convert to response models
            search_results = [FindingSearchResult(**finding) for finding in results]

            # Calculate pagination
            total_pages = (total + request.size - 1) // request.size

            return SearchFindingsResponse(
                results=search_results,
                total=total,
                page=request.page,
                size=request.size,
                total_pages=total_pages,
                has_more=request.page < total_pages,
            )

        except Exception as e:
            logger.error(f"Error searching findings: {str(e)}")
            return SearchFindingsResponse(
                results=[],
                total=0,
                page=request.page,
                size=request.size,
                total_pages=0,
                has_more=False,
            )

    async def get_statistics(
        self,
        job_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> SearchStatisticsResponse:
        """
        Get aggregated statistics.

        Args:
            job_id: Filter to specific job
            date_from: Date range start
            date_to: Date range end

        Returns:
            Statistics response
        """
        try:
            es_client = await self._get_es_client()

            stats = es_client.get_statistics(
                job_id=job_id, date_from=date_from, date_to=date_to
            )

            # Parse severity distribution
            severity_distribution = {}
            for bucket in stats.get("severity_distribution", []):
                severity_distribution[bucket["key"]] = bucket["doc_count"]

            return SearchStatisticsResponse(
                total_findings=stats.get("total_findings", 0),
                average_findings_per_job=stats.get("average_findings", 0),
                total_jobs_indexed=stats.get("documents_count", 0),
                severity_distribution=severity_distribution,
            )

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return SearchStatisticsResponse(
                total_findings=0,
                average_findings_per_job=0,
                total_jobs_indexed=0,
                severity_distribution={},
            )

    async def index_job_from_queue(
        self,
        job_id: str,
        job_type: str,
        status: str,
        priority: int,
        target_url: str,
        error_message: Optional[str] = None,
        findings_count: int = 0,
        created_at: Optional[datetime] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> bool:
        """
        Index a job from the queue.

        Args:
            job_id: Job ID
            job_type: Job type
            status: Job status
            priority: Priority (1-10)
            target_url: Target URL
            error_message: Error message if failed
            findings_count: Number of findings
            created_at: Creation timestamp
            started_at: Start timestamp
            completed_at: Completion timestamp

        Returns:
            True if successful
        """
        try:
            es_client = await self._get_es_client()

            # Calculate duration if completed
            duration_seconds = None
            if completed_at and started_at:
                duration_seconds = (completed_at - started_at).total_seconds()

            job_data = {
                "job_id": job_id,
                "job_type": job_type,
                "status": status,
                "priority": priority,
                "target_url": target_url,
                "error_message": error_message,
                "findings_count": findings_count,
                "created_at": created_at or datetime.utcnow(),
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_seconds": duration_seconds,
            }

            return es_client.index_job(job_id, job_data)

        except Exception as e:
            logger.error(f"Error indexing job {job_id}: {str(e)}")
            return False

    async def index_job_result(
        self,
        job_id: str,
        target_url: str,
        findings_count: int,
        severity_breakdown: Dict[str, int],
        neo4j_status: str,
        neo4j_count: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ) -> bool:
        """
        Index a job result.

        Args:
            job_id: Job ID
            target_url: Target URL
            findings_count: Total findings
            severity_breakdown: Breakdown by severity
            neo4j_status: Neo4j sync status
            neo4j_count: Findings in Neo4j
            created_at: Creation timestamp

        Returns:
            True if successful
        """
        try:
            es_client = await self._get_es_client()

            result_data = {
                "job_id": job_id,
                "target_url": target_url,
                "findings_count": findings_count,
                "severity_critical": severity_breakdown.get("critical", 0),
                "severity_high": severity_breakdown.get("high", 0),
                "severity_medium": severity_breakdown.get("medium", 0),
                "severity_low": severity_breakdown.get("low", 0),
                "severity_info": severity_breakdown.get("info", 0),
                "neo4j_status": neo4j_status,
                "neo4j_count": neo4j_count,
                "created_at": created_at or datetime.utcnow(),
            }

            return es_client.index_result(job_id, result_data)

        except Exception as e:
            logger.error(f"Error indexing result {job_id}: {str(e)}")
            return False

    async def index_finding(
        self,
        finding_id: str,
        job_id: str,
        template_id: str,
        target_url: str,
        severity: str,
        host: str,
        url: str,
        matched_at: Optional[datetime] = None,
        cve_ids: Optional[List[str]] = None,
        cwe_ids: Optional[List[str]] = None,
        description: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> bool:
        """
        Index a finding.

        Args:
            finding_id: Finding ID
            job_id: Associated job ID
            template_id: Nuclei template ID
            target_url: Target URL
            severity: Severity level
            host: Host
            url: Finding URL
            matched_at: Match timestamp
            cve_ids: List of CVE IDs
            cwe_ids: List of CWE IDs
            description: Finding description
            created_at: Creation timestamp

        Returns:
            True if successful
        """
        try:
            es_client = await self._get_es_client()

            finding_data = {
                "finding_id": finding_id,
                "job_id": job_id,
                "template_id": template_id,
                "target_url": target_url,
                "severity": severity,
                "host": host,
                "url": url,
                "matched_at": matched_at,
                "cve_ids": cve_ids or [],
                "cwe_ids": cwe_ids or [],
                "description": description,
                "created_at": created_at or datetime.utcnow(),
            }

            return es_client.index_finding(finding_id, finding_data)

        except Exception as e:
            logger.error(f"Error indexing finding {finding_id}: {str(e)}")
            return False

    async def delete_job_all_data(self, job_id: str) -> bool:
        """
        Delete all indexed data for a job.

        Args:
            job_id: Job ID

        Returns:
            True if successful
        """
        try:
            es_client = await self._get_es_client()
            return es_client.delete_job_data(job_id)
        except Exception as e:
            logger.error(f"Error deleting job data {job_id}: {str(e)}")
            return False

    async def health_check(self) -> bool:
        """
        Check Elasticsearch health.

        Returns:
            True if healthy
        """
        try:
            es_client = await self._get_es_client()
            return es_client.health_check()
        except Exception as e:
            logger.error(f"Elasticsearch health check failed: {str(e)}")
            return False


# Singleton instance
_search_service_instance: Optional[SearchService] = None


async def get_search_service() -> SearchService:
    """Get or create search service singleton."""
    global _search_service_instance
    if _search_service_instance is None:
        _search_service_instance = SearchService()
    return _search_service_instance
