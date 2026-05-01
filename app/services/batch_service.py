"""Batch operations service (Phase 5.5)."""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from functools import lru_cache

from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload

from app.adapters.postgres import AsyncSessionLocal, BatchJob, JobQueue, User
from app.services.job_queue_service import get_job_queue_service
from app.domain.schemas.batch import (
    BatchJobCreate,
    BatchJobResponse,
    BatchTargetResult,
    BatchStatusEnum,
    BatchSearchRequest,
    BatchSearchResponse,
    BatchStatistics,
    BulkImportRequest,
    BulkImportResult,
)

logger = logging.getLogger(__name__)


class BatchService:
    """Service for managing batch operations."""

    async def create_batch_job(
        self,
        batch_data: BatchJobCreate,
        created_by: str,
    ) -> BatchJobResponse:
        """Create new batch job with multiple targets."""
        job_queue_service = await get_job_queue_service()
        job_ids = []

        # Submit jobs for each target
        for target in batch_data.targets:
            try:
                job_response = await job_queue_service.submit_job(
                    job_type="nuclei_scan",
                    target_url=target.target_url,
                    scan_type=target.scan_type,
                    priority=target.priority,
                    metadata=target.custom_metadata,
                )
                job_ids.append(job_response.job_id)
            except Exception as e:
                logger.error(f"Failed to submit job for {target.target_url}: {e}")

        # Create batch record
        async with AsyncSessionLocal() as session:
            batch_job = BatchJob(
                batch_name=batch_data.batch_name,
                description=batch_data.description,
                created_by=created_by,
                status=BatchStatusEnum.PROCESSING.value if job_ids else BatchStatusEnum.FAILED.value,
                total_targets=len(batch_data.targets),
                job_ids=job_ids,
            )

            session.add(batch_job)
            await session.commit()
            await session.refresh(batch_job)

            logger.info(
                f"Batch job created: {batch_job.id} with {len(job_ids)} jobs for user {created_by}"
            )

            return self._batch_to_response(batch_job)

    async def get_batch_status(self, batch_id: str) -> Optional[BatchJobResponse]:
        """Get batch job status and aggregated results."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BatchJob).filter(BatchJob.id == batch_id)
            )
            batch_job = result.scalars().first()

            if not batch_job:
                return None

            # Get status of all jobs in batch
            job_results = []
            total_findings = 0
            completed_count = 0
            failed_count = 0

            for job_id in batch_job.job_ids:
                job_result = await session.execute(
                    select(JobQueue).filter(JobQueue.job_id == job_id)
                )
                job_queue = job_result.scalars().first()

                if job_queue:
                    status = job_queue.status
                    findings_count = 0
                    error = None

                    if status == "completed":
                        completed_count += 1
                        if job_queue.result:
                            findings_count = job_queue.result.get("findings_count", 0)
                            total_findings += findings_count
                    elif status == "failed":
                        failed_count += 1
                        error = job_queue.error_message

                    job_results.append(
                        BatchTargetResult(
                            target_url=job_queue.target_url,
                            job_id=job_id,
                            status=status,
                            findings_count=findings_count,
                            error=error,
                            started_at=job_queue.started_at,
                            completed_at=job_queue.completed_at,
                            duration_seconds=(
                                (job_queue.completed_at - job_queue.started_at).total_seconds()
                                if job_queue.completed_at and job_queue.started_at
                                else None
                            ),
                        )
                    )

            # Update batch status
            batch_job.completed_targets = completed_count
            batch_job.failed_targets = failed_count

            if completed_count + failed_count == len(batch_job.job_ids):
                batch_job.status = (
                    BatchStatusEnum.COMPLETED.value
                    if failed_count == 0
                    else (
                        BatchStatusEnum.PARTIAL_SUCCESS.value
                        if completed_count > 0
                        else BatchStatusEnum.FAILED.value
                    )
                )
                batch_job.completed_at = datetime.utcnow()

            session.add(batch_job)
            await session.commit()

            response = self._batch_to_response(batch_job)
            response.results = job_results
            return response

    async def list_batches(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[BatchJobResponse], int]:
        """List batch jobs."""
        async with AsyncSessionLocal() as session:
            query = select(BatchJob)

            if user_id:
                query = query.filter(BatchJob.created_by == user_id)

            if status:
                query = query.filter(BatchJob.status == status)

            # Get total count
            count_result = await session.execute(select(BatchJob).filter(*query.whereclause.clauses))
            total = len(count_result.scalars().all()) if hasattr(query.whereclause, 'clauses') else 0

            # Get paginated results
            result = await session.execute(
                query.order_by(BatchJob.created_at.desc()).limit(limit).offset(offset)
            )
            batch_jobs = result.scalars().all()

            return [self._batch_to_response(batch) for batch in batch_jobs], total

    async def batch_search(
        self,
        search_request: BatchSearchRequest,
    ) -> BatchSearchResponse:
        """Search across multiple batches."""
        from app.services.search_service import get_search_service
        from app.domain.schemas.search import SearchFindingsRequest

        search_service = await get_search_service()
        all_results = []
        total_findings = 0
        severity_distribution = {}
        job_findings = {}

        # Search in each batch
        for batch_id in search_request.batch_ids:
            batch = await self.get_batch_status(batch_id)

            if not batch:
                continue

            for job_result in batch.results:
                # Search findings for each job
                findings_request = SearchFindingsRequest(
                    query=search_request.query,
                    severity=search_request.severity,
                    cve_id=search_request.cve_id,
                    job_id=job_result.job_id,
                )

                findings_response = await search_service.search_findings(findings_request)
                all_results.extend(findings_response.results)
                total_findings += len(findings_response.results)

                # Aggregate by job
                job_findings[job_result.job_id] = len(findings_response.results)

                # Aggregate by severity
                if findings_response.results:
                    for result in findings_response.results:
                        severity = result.get("severity", "INFO")
                        severity_distribution[severity] = severity_distribution.get(severity, 0) + 1

        # Calculate pagination
        total_pages = (len(all_results) + search_request.size - 1) // search_request.size
        start = (search_request.page - 1) * search_request.size
        end = start + search_request.size
        paginated_results = all_results[start:end]

        return BatchSearchResponse(
            batch_ids=search_request.batch_ids,
            aggregated_findings={
                "total_findings": total_findings,
                "by_severity": severity_distribution,
                "by_job": job_findings,
                "unique_templates": len(set(r.get("template_id") for r in all_results)),
                "unique_cves": len(set(cve for r in all_results for cve in r.get("cve_ids", []))),
            },
            results=paginated_results,
            total=len(all_results),
            page=search_request.page,
            total_pages=total_pages,
            has_more=search_request.page < total_pages,
        )

    async def get_batch_statistics(self) -> BatchStatistics:
        """Get batch job statistics."""
        async with AsyncSessionLocal() as session:
            # Get total batches
            batch_result = await session.execute(select(BatchJob))
            all_batches = batch_result.scalars().all()

            total_batches = len(all_batches)
            active_batches = len([b for b in all_batches if b.status != "completed"])
            completed_batches = len([b for b in all_batches if b.status == "completed"])

            total_jobs = sum(len(b.job_ids) for b in all_batches)
            total_completed = sum(b.completed_targets for b in all_batches)

            avg_targets = total_jobs / total_batches if total_batches > 0 else 0
            avg_success_rate = (
                sum(
                    (b.completed_targets / len(b.job_ids) * 100)
                    for b in all_batches
                    if len(b.job_ids) > 0
                )
                / total_batches
                if total_batches > 0
                else 0
            )

            # Calculate average job duration
            durations = []
            for batch in all_batches:
                if batch.completed_at and batch.created_at:
                    duration = (batch.completed_at - batch.created_at).total_seconds()
                    durations.append(duration)

            avg_duration = sum(durations) / len(durations) if durations else 0

            # Get total findings (estimate from all jobs)
            job_result = await session.execute(select(JobQueue))
            all_jobs = job_result.scalars().all()
            total_findings = sum(
                j.result.get("findings_count", 0)
                for j in all_jobs
                if j.result
            )

            return BatchStatistics(
                total_batches=total_batches,
                active_batches=active_batches,
                completed_batches=completed_batches,
                total_jobs_submitted=total_jobs,
                total_jobs_completed=total_completed,
                average_targets_per_batch=avg_targets,
                average_success_rate=avg_success_rate,
                average_job_duration_seconds=avg_duration,
                total_findings_discovered=total_findings,
            )

    async def bulk_import(
        self,
        import_data: BulkImportRequest,
        user_id: str,
    ) -> BulkImportResult:
        """Bulk import scan data."""
        imported = 0
        skipped = 0
        failed = 0
        errors = []

        for item in import_data.items:
            try:
                async with AsyncSessionLocal() as session:
                    # Check for duplicates if skip_duplicates is True
                    if import_data.skip_duplicates:
                        existing = await session.execute(
                            select(JobQueue).filter(
                                JobQueue.target_url == item.target_url
                            )
                        )
                        if existing.scalars().first():
                            skipped += 1
                            continue

                    # Create job queue entry
                    job = JobQueue(
                        job_id=f"import-{item.target_url}",
                        job_type="imported",
                        status="completed",
                        target_url=item.target_url,
                        payload=item.scan_data,
                        result=item.scan_data,
                        job_metadata=item.metadata or {},
                        created_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                    )

                    session.add(job)
                    await session.commit()
                    imported += 1

            except Exception as e:
                failed += 1
                errors.append({"target": item.target_url, "error": str(e)})
                logger.error(f"Failed to import {item.target_url}: {e}")

        return BulkImportResult(
            total_items=len(import_data.items),
            imported_items=imported,
            skipped_items=skipped,
            failed_items=failed,
            errors=errors,
        )

    @staticmethod
    def _batch_to_response(batch_job: BatchJob) -> BatchJobResponse:
        """Convert BatchJob ORM to response model."""
        duration_seconds = None
        if batch_job.completed_at and batch_job.created_at:
            duration_seconds = (batch_job.completed_at - batch_job.created_at).total_seconds()

        success_rate = (
            (batch_job.completed_targets / batch_job.total_targets * 100)
            if batch_job.total_targets > 0
            else 0
        )

        return BatchJobResponse(
            batch_id=batch_job.id,
            batch_name=batch_job.batch_name,
            status=BatchStatusEnum(batch_job.status),
            created_by=batch_job.created_by,
            total_targets=batch_job.total_targets,
            completed_targets=batch_job.completed_targets,
            failed_targets=batch_job.failed_targets,
            success_rate=success_rate,
            results=[],
            created_at=batch_job.created_at,
            updated_at=batch_job.updated_at,
            completed_at=batch_job.completed_at,
            duration_seconds=duration_seconds,
        )


@lru_cache(maxsize=1)
async def get_batch_service() -> BatchService:
    """Get or create batch service singleton."""
    return BatchService()
