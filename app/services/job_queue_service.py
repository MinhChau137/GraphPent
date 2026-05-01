"""Service for managing async job queue."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from sqlalchemy import select, update, desc, and_, or_
from sqlalchemy.orm import selectinload

from app.adapters.postgres import AsyncSessionLocal, JobQueue
from app.workers.config import celery_app
from app.workers.nuclei_tasks import (
    scan_target_async,
    process_scan_results,
    upsert_to_neo4j_async,
    generate_report,
)
from app.domain.schemas.job_queue import (
    JobStatusEnum,
    JobTypeEnum,
    CreateJobRequest,
    JobResponse,
    JobResultResponse,
    QueueStatisticsResponse,
)

# Phase 5.3: Auto-indexing to Elasticsearch
try:
    from app.services.search_service import get_search_service
    SEARCH_SERVICE_AVAILABLE = True
except ImportError:
    SEARCH_SERVICE_AVAILABLE = False

logger = logging.getLogger(__name__)


class JobQueueService:
    """Service for managing async job queue and Celery tasks."""

    async def submit_job(
        self,
        job_type: JobTypeEnum,
        target_url: str,
        scan_type: str = "full",
        priority: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
        callback_url: Optional[str] = None,
        max_retries: int = 3,
    ) -> JobResponse:
        """
        Submit a new job to the queue.
        
        Args:
            job_type: Type of job
            target_url: Target URL for scanning
            scan_type: Scan type (full, web, api)
            priority: Job priority (1-10)
            metadata: Additional metadata
            callback_url: Webhook for completion
            max_retries: Maximum retries on failure
            
        Returns:
            JobResponse with job details
            
        Raises:
            ValueError: On invalid input
        """
        if priority < 1 or priority > 10:
            raise ValueError("Priority must be between 1 and 10")
        
        if max_retries < 0 or max_retries > 10:
            raise ValueError("Max retries must be between 0 and 10")
        
        # Create database record
        job_db_id = str(uuid.uuid4())
        payload = {
            "target_url": target_url,
            "scan_type": scan_type,
            "metadata": metadata or {},
        }
        
        async with AsyncSessionLocal() as session:
            # Submit to Celery based on job type
            celery_task = None
            
            if job_type == JobTypeEnum.NUCLEI_SCAN:
                celery_task = scan_target_async.apply_async(
                    args=[job_db_id, target_url, scan_type, metadata],
                    priority=priority,
                    queue="scans",
                    max_retries=max_retries,
                )
            elif job_type == JobTypeEnum.NEO4J_UPSERT:
                celery_task = upsert_to_neo4j_async.apply_async(
                    args=[job_db_id, "", []],
                    priority=priority,
                    queue="default",
                    max_retries=max_retries,
                )
            elif job_type == JobTypeEnum.REPORT_GENERATION:
                celery_task = generate_report.apply_async(
                    args=[job_db_id, ""],
                    priority=priority,
                    queue="default",
                )
            else:
                raise ValueError(f"Unknown job type: {job_type}")
            
            # Create JobQueue record
            job_queue = JobQueue(
                id=job_db_id,
                job_id=celery_task.id,
                job_type=job_type.value,
                status=JobStatusEnum.PENDING.value,
                priority=priority,
                target_url=target_url,
                payload=payload,
                retry_count=0,
                max_retries=max_retries,
                callback_url=callback_url,
                metadata=metadata or {},
                created_at=datetime.utcnow(),
            )
            
            session.add(job_queue)
            await session.commit()
            await session.refresh(job_queue)
            
            logger.info(f"Job submitted: {job_db_id} (Celery: {celery_task.id})")
            
            # Phase 5.3: Auto-index job for searching
            if SEARCH_SERVICE_AVAILABLE:
                try:
                    search_service = await get_search_service()
                    await search_service.index_job_from_queue(
                        job_id=job_db_id,
                        job_type=job_type.value,
                        status=JobStatusEnum.PENDING.value,
                        priority=priority,
                        target_url=target_url,
                        findings_count=0,
                        created_at=datetime.utcnow(),
                    )
                except Exception as e:
                    logger.warning(f"Failed to index job {job_db_id} to Elasticsearch: {e}")
            
            return self._job_queue_to_response(job_queue)

    async def get_job_status(self, job_id: str) -> JobResponse:
        """
        Get current job status.
        
        Args:
            job_id: Database job ID
            
        Returns:
            JobResponse with current status
            
        Raises:
            ValueError: Job not found
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobQueue).filter(JobQueue.id == job_id)
            )
            job_queue = result.scalars().first()
            
            if not job_queue:
                raise ValueError(f"Job {job_id} not found")
            
            # Update status from Celery if running
            if job_queue.status == JobStatusEnum.RUNNING.value:
                celery_task = celery_app.AsyncResult(job_queue.job_id)
                
                if celery_task.state == "PROGRESS":
                    info = celery_task.info or {}
                    progress = info.get("progress", 0)
                    eta_seconds = info.get("eta_seconds")
                    
                    # Update database with progress
                    await session.execute(
                        update(JobQueue)
                        .where(JobQueue.id == job_id)
                        .values(job_metadata={**job_queue.job_metadata, **{"progress": progress}})
                    )
                    await session.commit()
            
            return self._job_queue_to_response(job_queue)

    async def get_job_result(self, job_id: str) -> JobResultResponse:
        """
        Get job result (only if completed).
        
        Args:
            job_id: Database job ID
            
        Returns:
            JobResultResponse with result
            
        Raises:
            ValueError: Job not found or still running
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobQueue).filter(JobQueue.id == job_id)
            )
            job_queue = result.scalars().first()
            
            if not job_queue:
                raise ValueError(f"Job {job_id} not found")
            
            if job_queue.status not in [
                JobStatusEnum.COMPLETED.value,
                JobStatusEnum.FAILED.value,
            ]:
                raise ValueError(
                    f"Job {job_id} is still {job_queue.status}, "
                    "cannot retrieve result yet"
                )
            
            return JobResultResponse(
                job_id=job_queue.job_id,
                status=job_queue.status,
                result=job_queue.result,
                completed_at=job_queue.completed_at,
                error_message=job_queue.error_message,
            )

    async def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """
        Cancel a pending or running job.
        
        Args:
            job_id: Database job ID
            
        Returns:
            Dict with cancellation result
            
        Raises:
            ValueError: Job not found or cannot be cancelled
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobQueue).filter(JobQueue.id == job_id)
            )
            job_queue = result.scalars().first()
            
            if not job_queue:
                raise ValueError(f"Job {job_id} not found")
            
            if job_queue.status not in [
                JobStatusEnum.PENDING.value,
                JobStatusEnum.RUNNING.value,
                JobStatusEnum.RETRYING.value,
            ]:
                raise ValueError(
                    f"Cannot cancel job with status: {job_queue.status}"
                )
            
            # Revoke Celery task
            celery_app.control.revoke(job_queue.job_id, terminate=True)
            
            # Update database
            await session.execute(
                update(JobQueue)
                .where(JobQueue.id == job_id)
                .values(
                    status=JobStatusEnum.CANCELLED.value,
                    completed_at=datetime.utcnow(),
                )
            )
            await session.commit()
            
            logger.info(f"Job cancelled: {job_id}")
            
            return {
                "job_id": job_queue.job_id,
                "status": JobStatusEnum.CANCELLED.value,
                "message": "Job cancelled successfully",
            }

    async def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        List jobs with pagination.
        
        Args:
            status: Filter by status (optional)
            limit: Items per page
            offset: Page offset
            
        Returns:
            Dict with jobs list and pagination info
        """
        if limit < 1 or limit > 100:
            limit = 20
        
        if offset < 0:
            offset = 0
        
        async with AsyncSessionLocal() as session:
            # Build query
            query = select(JobQueue)
            
            if status:
                query = query.filter(JobQueue.status == status)
            
            # Get total count
            count_result = await session.execute(
                select(JobQueue).filter(
                    JobQueue.status == status if status else True
                )
            )
            total = len(count_result.scalars().all())
            
            # Get paginated results
            query = query.order_by(desc(JobQueue.created_at))
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            jobs = result.scalars().all()
            
            return {
                "total": total,
                "count": len(jobs),
                "limit": limit,
                "offset": offset,
                "jobs": [self._job_queue_to_response(job) for job in jobs],
            }

    async def get_job_history(
        self,
        target_url: str,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Get job history for a target.
        
        Args:
            target_url: Target URL
            limit: Number of jobs to return
            
        Returns:
            Dict with job history
        """
        async with AsyncSessionLocal() as session:
            # Get all jobs for target
            result = await session.execute(
                select(JobQueue)
                .filter(JobQueue.target_url == target_url)
                .order_by(desc(JobQueue.created_at))
            )
            all_jobs = result.scalars().all()
            
            # Get statistics
            completed = len([j for j in all_jobs if j.status == JobStatusEnum.COMPLETED.value])
            failed = len([j for j in all_jobs if j.status == JobStatusEnum.FAILED.value])
            running = len([j for j in all_jobs if j.status == JobStatusEnum.RUNNING.value])
            
            # Get limited jobs
            recent_jobs = all_jobs[:limit]
            
            return {
                "target_url": target_url,
                "total_jobs": len(all_jobs),
                "completed": completed,
                "failed": failed,
                "running": running,
                "jobs": [self._job_queue_to_response(job) for job in recent_jobs],
            }

    async def retry_failed_job(
        self,
        job_id: str,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Retry a failed job.
        
        Args:
            job_id: Original job ID
            max_retries: Max retries for new job
            
        Returns:
            Dict with new job info
            
        Raises:
            ValueError: Job not found or cannot be retried
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobQueue).filter(JobQueue.id == job_id)
            )
            original_job = result.scalars().first()
            
            if not original_job:
                raise ValueError(f"Job {job_id} not found")
            
            if original_job.status != JobStatusEnum.FAILED.value:
                raise ValueError(
                    f"Cannot retry job with status: {original_job.status}"
                )
            
            # Create new job with same parameters
            payload = original_job.payload or {}
            new_job_response = await self.submit_job(
                job_type=JobTypeEnum(original_job.job_type),
                target_url=payload.get("target_url", ""),
                scan_type=payload.get("scan_type", "full"),
                priority=original_job.priority,
                metadata=payload.get("metadata"),
                callback_url=original_job.callback_url,
                max_retries=max_retries,
            )
            
            logger.info(
                f"Job retried: {job_id} -> {new_job_response.id}"
            )
            
            return {
                "original_job_id": original_job.job_id,
                "new_job_id": new_job_response.job_id,
                "new_db_job_id": new_job_response.id,
                "status": new_job_response.status,
                "message": "Job queued for retry",
            }

    async def get_queue_statistics(self) -> QueueStatisticsResponse:
        """
        Get queue statistics.
        
        Returns:
            QueueStatisticsResponse with metrics
        """
        async with AsyncSessionLocal() as session:
            # Get all jobs
            result = await session.execute(select(JobQueue))
            all_jobs = result.scalars().all()
            
            # Count by status
            by_status = {}
            for job in all_jobs:
                status = job.status
                by_status[status] = by_status.get(status, 0) + 1
            
            # Calculate metrics
            total_jobs = len(all_jobs)
            completed_jobs = by_status.get(JobStatusEnum.COMPLETED.value, 0)
            failed_jobs = by_status.get(JobStatusEnum.FAILED.value, 0)
            
            # Average completion time
            completed = [j for j in all_jobs if j.status == JobStatusEnum.COMPLETED.value]
            avg_completion_time = None
            if completed:
                total_time = sum(
                    (j.completed_at - j.created_at).total_seconds()
                    for j in completed
                    if j.completed_at and j.created_at
                )
                avg_completion_time = total_time / len(completed) if completed else None
            
            # Success rate
            success_rate = None
            if completed_jobs + failed_jobs > 0:
                success_rate = (completed_jobs / (completed_jobs + failed_jobs)) * 100
            
            # Get queue size and worker count
            queue_size = by_status.get(JobStatusEnum.PENDING.value, 0)
            
            # Get active worker count (from Celery)
            inspect = celery_app.control.inspect()
            active_workers = len(inspect.active() or {})
            
            return QueueStatisticsResponse(
                total_jobs=total_jobs,
                pending_jobs=by_status.get(JobStatusEnum.PENDING.value, 0),
                running_jobs=by_status.get(JobStatusEnum.RUNNING.value, 0),
                completed_jobs=completed_jobs,
                failed_jobs=failed_jobs,
                cancelled_jobs=by_status.get(JobStatusEnum.CANCELLED.value, 0),
                average_completion_time=avg_completion_time,
                success_rate=success_rate,
                queue_size=queue_size,
                worker_count=active_workers,
            )

    def _job_queue_to_response(self, job_queue: JobQueue) -> JobResponse:
        """Convert JobQueue ORM to JobResponse Pydantic model."""
        # Calculate progress from metadata
        progress = job_queue.job_metadata.get("progress") if job_queue.job_metadata else None
        
        # Calculate ETA
        eta_seconds = None
        if job_queue.status == JobStatusEnum.RUNNING.value and progress:
            if progress > 0:
                elapsed = (datetime.utcnow() - job_queue.started_at).total_seconds()
                total_estimated = (elapsed / progress) * 100
                eta_seconds = int(total_estimated - elapsed)
        
        return JobResponse(
            id=job_queue.id,
            job_id=job_queue.job_id,
            status=JobStatusEnum(job_queue.status),
            job_type=JobTypeEnum(job_queue.job_type),
            target_url=job_queue.target_url,
            priority=job_queue.priority,
            progress=progress,
            result=job_queue.result,
            error_message=job_queue.error_message,
            retry_count=job_queue.retry_count,
            created_at=job_queue.created_at,
            started_at=job_queue.started_at,
            completed_at=job_queue.completed_at,
            eta_seconds=eta_seconds,
        )


# Singleton instance
_job_queue_service_instance: Optional[JobQueueService] = None


async def get_job_queue_service() -> JobQueueService:
    """Get or create JobQueueService singleton."""
    global _job_queue_service_instance
    if _job_queue_service_instance is None:
        _job_queue_service_instance = JobQueueService()
    return _job_queue_service_instance
