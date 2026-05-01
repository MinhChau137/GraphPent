"""Integration tests for Phase 5.1: Job Queue."""

import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from app.adapters.postgres import AsyncSessionLocal, JobQueue
from app.services.job_queue_service import JobQueueService
from app.domain.schemas.job_queue import (
    JobStatusEnum,
    JobTypeEnum,
    CreateJobRequest,
)


@pytest.fixture
async def job_queue_service():
    """Get JobQueueService instance."""
    return JobQueueService()


@pytest.fixture
async def sample_create_request():
    """Sample CreateJobRequest."""
    return CreateJobRequest(
        target_url="http://localhost:3000",
        scan_type="full",
        priority=5,
        metadata={"test": "data"},
    )


class TestJobSubmission:
    """Test job submission and creation."""

    @pytest.mark.asyncio
    async def test_submit_nuclei_scan(self, job_queue_service, sample_create_request):
        """Test submitting a Nuclei scan job."""
        response = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url=sample_create_request.target_url,
            scan_type=sample_create_request.scan_type,
            priority=sample_create_request.priority,
            metadata=sample_create_request.metadata,
        )

        assert response.id is not None
        assert response.job_id is not None
        assert response.status == JobStatusEnum.PENDING
        assert response.target_url == sample_create_request.target_url
        assert response.priority == sample_create_request.priority

    @pytest.mark.asyncio
    async def test_submit_job_with_callback(self, job_queue_service):
        """Test submitting job with callback URL."""
        callback_url = "http://webhook.example.com/callback"
        response = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target.com",
            callback_url=callback_url,
        )

        assert response.id is not None
        
        # Verify callback URL saved in database
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(JobQueue).filter(JobQueue.id == response.id)
            )
            job = result.scalars().first()
            assert job.callback_url == callback_url

    @pytest.mark.asyncio
    async def test_submit_job_invalid_priority(self, job_queue_service):
        """Test submitting job with invalid priority."""
        with pytest.raises(ValueError):
            await job_queue_service.submit_job(
                job_type=JobTypeEnum.NUCLEI_SCAN,
                target_url="http://target.com",
                priority=15,  # Invalid: > 10
            )

    @pytest.mark.asyncio
    async def test_submit_job_invalid_retries(self, job_queue_service):
        """Test submitting job with invalid max_retries."""
        with pytest.raises(ValueError):
            await job_queue_service.submit_job(
                job_type=JobTypeEnum.NUCLEI_SCAN,
                target_url="http://target.com",
                max_retries=15,  # Invalid: > 10
            )

    @pytest.mark.asyncio
    async def test_submit_multiple_jobs_same_target(self, job_queue_service):
        """Test submitting multiple jobs for same target."""
        target = "http://target.com"
        
        job1 = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url=target,
            priority=3,
        )
        
        job2 = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url=target,
            priority=7,
        )

        assert job1.id != job2.id
        assert job1.job_id != job2.job_id
        assert job1.priority == 3
        assert job2.priority == 7


class TestJobStatusTracking:
    """Test job status tracking and retrieval."""

    @pytest.mark.asyncio
    async def test_get_job_status_pending(self, job_queue_service, sample_create_request):
        """Test getting status of pending job."""
        submitted = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url=sample_create_request.target_url,
        )

        status = await job_queue_service.get_job_status(submitted.id)
        
        assert status.id == submitted.id
        assert status.status == JobStatusEnum.PENDING
        assert status.created_at is not None

    @pytest.mark.asyncio
    async def test_get_job_status_not_found(self, job_queue_service):
        """Test getting status of non-existent job."""
        with pytest.raises(ValueError):
            await job_queue_service.get_job_status("non-existent-id")

    @pytest.mark.asyncio
    async def test_get_job_status_updates(self, job_queue_service):
        """Test that job status is updateable in database."""
        submitted = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target.com",
        )

        # Manually update status in database
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(JobQueue)
                .where(JobQueue.id == submitted.id)
                .values(
                    status=JobStatusEnum.RUNNING.value,
                    started_at=datetime.utcnow(),
                )
            )
            await session.commit()

        # Verify status updated
        status = await job_queue_service.get_job_status(submitted.id)
        assert status.status == JobStatusEnum.RUNNING
        assert status.started_at is not None


class TestJobCancellation:
    """Test job cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_pending_job(self, job_queue_service):
        """Test cancelling a pending job."""
        submitted = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target.com",
        )

        result = await job_queue_service.cancel_job(submitted.id)
        
        assert result["status"] == JobStatusEnum.CANCELLED.value
        assert "successfully" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_cancel_running_job(self, job_queue_service):
        """Test cancelling a running job."""
        submitted = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target.com",
        )

        # Mark as running
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(JobQueue)
                .where(JobQueue.id == submitted.id)
                .values(status=JobStatusEnum.RUNNING.value)
            )
            await session.commit()

        result = await job_queue_service.cancel_job(submitted.id)
        assert result["status"] == JobStatusEnum.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_completed_job_fails(self, job_queue_service):
        """Test cancelling completed job raises error."""
        submitted = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target.com",
        )

        # Mark as completed
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(JobQueue)
                .where(JobQueue.id == submitted.id)
                .values(status=JobStatusEnum.COMPLETED.value)
            )
            await session.commit()

        with pytest.raises(ValueError):
            await job_queue_service.cancel_job(submitted.id)

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job_fails(self, job_queue_service):
        """Test cancelling non-existent job raises error."""
        with pytest.raises(ValueError):
            await job_queue_service.cancel_job("non-existent-id")


class TestJobRetry:
    """Test job retry functionality."""

    @pytest.mark.asyncio
    async def test_retry_failed_job(self, job_queue_service):
        """Test retrying a failed job."""
        original = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target.com",
            priority=5,
            metadata={"custom": "data"},
        )

        # Mark as failed
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(JobQueue)
                .where(JobQueue.id == original.id)
                .values(
                    status=JobStatusEnum.FAILED.value,
                    error_message="Test error",
                )
            )
            await session.commit()

        result = await job_queue_service.retry_failed_job(original.id)
        
        assert result["original_job_id"] == original.job_id
        assert result["new_job_id"] is not None
        assert result["new_db_job_id"] is not None
        assert result["new_db_job_id"] != original.id
        assert "retry" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_retry_pending_job_fails(self, job_queue_service):
        """Test retrying pending job raises error."""
        submitted = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target.com",
        )

        with pytest.raises(ValueError):
            await job_queue_service.retry_failed_job(submitted.id)

    @pytest.mark.asyncio
    async def test_retry_preserves_parameters(self, job_queue_service):
        """Test that retry preserves original job parameters."""
        original = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target.com",
            scan_type="web",
            priority=8,
            metadata={"test": "data"},
        )

        # Mark as failed
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(JobQueue)
                .where(JobQueue.id == original.id)
                .values(status=JobStatusEnum.FAILED.value)
            )
            await session.commit()

        retry_result = await job_queue_service.retry_failed_job(original.id)
        new_job_id = retry_result["new_db_job_id"]
        
        # Verify parameters preserved
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(JobQueue).filter(JobQueue.id == new_job_id)
            )
            retry_job = result.scalars().first()
            
            assert retry_job.payload["target_url"] == "http://target.com"
            assert retry_job.payload["scan_type"] == "web"
            assert retry_job.priority == 8


class TestJobListing:
    """Test job listing and pagination."""

    @pytest.mark.asyncio
    async def test_list_all_jobs(self, job_queue_service):
        """Test listing all jobs."""
        # Create multiple jobs
        job1 = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target1.com",
        )
        
        job2 = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://target2.com",
        )

        result = await job_queue_service.list_jobs(limit=50)
        
        assert result["total"] >= 2
        assert result["count"] >= 2
        assert len(result["jobs"]) >= 2
        assert result["limit"] == 50
        assert result["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_jobs_with_pagination(self, job_queue_service):
        """Test listing jobs with pagination."""
        # Create 5 jobs
        for i in range(5):
            await job_queue_service.submit_job(
                job_type=JobTypeEnum.NUCLEI_SCAN,
                target_url=f"http://target{i}.com",
            )

        # First page
        page1 = await job_queue_service.list_jobs(limit=2, offset=0)
        assert page1["count"] == 2
        assert page1["offset"] == 0

        # Second page
        page2 = await job_queue_service.list_jobs(limit=2, offset=2)
        assert page2["count"] == 2
        assert page2["offset"] == 2

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_status(self, job_queue_service):
        """Test filtering jobs by status."""
        # Create jobs with different statuses
        pending = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://pending.com",
        )
        
        completed = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url="http://completed.com",
        )

        # Mark one as completed
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(JobQueue)
                .where(JobQueue.id == completed.id)
                .values(status=JobStatusEnum.COMPLETED.value)
            )
            await session.commit()

        # Filter by pending
        result = await job_queue_service.list_jobs(status=JobStatusEnum.PENDING.value)
        
        # Should have pending job
        assert any(j.id == pending.id for j in result["jobs"])


class TestJobHistory:
    """Test job history retrieval."""

    @pytest.mark.asyncio
    async def test_get_job_history_for_target(self, job_queue_service):
        """Test getting job history for target."""
        target = "http://target.com"
        
        job1 = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url=target,
        )
        
        job2 = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url=target,
        )

        history = await job_queue_service.get_job_history(target)
        
        assert history["target_url"] == target
        assert history["total_jobs"] >= 2
        assert len(history["jobs"]) >= 2

    @pytest.mark.asyncio
    async def test_get_job_history_with_limit(self, job_queue_service):
        """Test getting job history with limit."""
        target = "http://target.com"
        
        # Create 5 jobs
        for i in range(5):
            await job_queue_service.submit_job(
                job_type=JobTypeEnum.NUCLEI_SCAN,
                target_url=target,
            )

        history = await job_queue_service.get_job_history(target, limit=3)
        
        assert len(history["jobs"]) == 3

    @pytest.mark.asyncio
    async def test_job_history_statistics(self, job_queue_service):
        """Test that job history includes statistics."""
        target = "http://target.com"
        
        completed = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url=target,
        )
        
        failed = await job_queue_service.submit_job(
            job_type=JobTypeEnum.NUCLEI_SCAN,
            target_url=target,
        )

        # Mark as completed/failed
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(JobQueue)
                .where(JobQueue.id == completed.id)
                .values(status=JobStatusEnum.COMPLETED.value)
            )
            await session.execute(
                update(JobQueue)
                .where(JobQueue.id == failed.id)
                .values(status=JobStatusEnum.FAILED.value)
            )
            await session.commit()

        history = await job_queue_service.get_job_history(target)
        
        assert history["completed"] >= 1
        assert history["failed"] >= 1


class TestQueueStatistics:
    """Test queue statistics."""

    @pytest.mark.asyncio
    async def test_get_queue_statistics(self, job_queue_service):
        """Test getting queue statistics."""
        stats = await job_queue_service.get_queue_statistics()
        
        assert stats.total_jobs >= 0
        assert stats.pending_jobs >= 0
        assert stats.running_jobs >= 0
        assert stats.completed_jobs >= 0
        assert stats.failed_jobs >= 0

    @pytest.mark.asyncio
    async def test_queue_stats_success_rate(self, job_queue_service):
        """Test queue statistics includes success rate."""
        # Create jobs with different statuses
        for i in range(3):
            await job_queue_service.submit_job(
                job_type=JobTypeEnum.NUCLEI_SCAN,
                target_url=f"http://target{i}.com",
            )

        stats = await job_queue_service.get_queue_statistics()
        
        # Stats should be calculated
        assert hasattr(stats, "success_rate")
        assert hasattr(stats, "average_completion_time")
