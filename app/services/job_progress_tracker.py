"""Real-time job progress tracker for WebSocket updates."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import select, update

from app.adapters.postgres import AsyncSessionLocal, JobQueue
from app.domain.schemas.websocket import (
    JobProgressData,
    JobStatusData,
    JobResultData,
    QueueMetricsData,
)
from app.domain.schemas.job_queue import JobStatusEnum
from app.services.websocket_manager import get_ws_manager

logger = logging.getLogger(__name__)


class JobProgressTracker:
    """Tracks job progress and broadcasts updates via WebSocket."""

    def __init__(self):
        """Initialize progress tracker."""
        self.job_status_cache: Dict[str, Dict[str, Any]] = {}
        self.job_progress_cache: Dict[str, int] = {}

    async def update_job_progress(
        self,
        job_id: str,
        progress: int,
        current_task: Optional[str] = None,
        processed_items: Optional[int] = None,
        total_items: Optional[int] = None,
    ):
        """
        Update job progress and broadcast to WebSocket subscribers.
        
        Args:
            job_id: Job ID
            progress: Progress percentage (0-100)
            current_task: Current task description
            processed_items: Items processed so far
            total_items: Total items to process
        """
        try:
            if not (0 <= progress <= 100):
                logger.warning(f"Invalid progress {progress} for job {job_id}")
                return
            
            # Cache progress
            self.job_progress_cache[job_id] = progress
            
            # Calculate ETA if we have items
            estimated_remaining = None
            if total_items and processed_items and progress > 0:
                remaining_items = total_items - processed_items
                seconds_per_item = 1.0 / (processed_items / max(progress / 100, 0.01))
                estimated_remaining = int(remaining_items * seconds_per_item)
            
            # Create progress data
            progress_data = JobProgressData(
                job_id=job_id,
                status="running",
                progress=progress,
                current_task=current_task,
                estimated_remaining_seconds=estimated_remaining,
                processed_items=processed_items,
                total_items=total_items,
            )
            
            # Update database metadata
            async with AsyncSessionLocal() as session:
                metadata = {
                    "progress": progress,
                    "current_task": current_task,
                    "processed_items": processed_items,
                    "total_items": total_items,
                    "last_update": datetime.utcnow().isoformat(),
                }
                
                await session.execute(
                    update(JobQueue)
                    .where(JobQueue.id == job_id)
                    .values(job_metadata=metadata)
                )
                await session.commit()
            
            # Broadcast to WebSocket subscribers
            ws_manager = await get_ws_manager()
            await ws_manager.broadcast_progress_update(job_id, progress_data)
            
            logger.debug(f"Progress updated for job {job_id}: {progress}%")
            
        except Exception as e:
            logger.error(f"Error updating progress for job {job_id}: {str(e)}")

    async def update_job_status(
        self,
        job_id: str,
        new_status: str,
        error_message: Optional[str] = None,
    ):
        """
        Update job status and broadcast to WebSocket subscribers.
        
        Args:
            job_id: Job ID
            new_status: New status
            error_message: Error message if failed
        """
        try:
            # Get current status from database
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(JobQueue).filter(JobQueue.id == job_id)
                )
                job = result.scalars().first()
                
                if not job:
                    logger.warning(f"Job {job_id} not found")
                    return
                
                previous_status = job.status
                
                # Update database
                if new_status == JobStatusEnum.RUNNING.value:
                    await session.execute(
                        update(JobQueue)
                        .where(JobQueue.id == job_id)
                        .values(
                            status=new_status,
                            started_at=datetime.utcnow(),
                        )
                    )
                elif new_status in [
                    JobStatusEnum.COMPLETED.value,
                    JobStatusEnum.FAILED.value,
                    JobStatusEnum.CANCELLED.value,
                ]:
                    await session.execute(
                        update(JobQueue)
                        .where(JobQueue.id == job_id)
                        .values(
                            status=new_status,
                            completed_at=datetime.utcnow(),
                            error_message=error_message,
                        )
                    )
                else:
                    await session.execute(
                        update(JobQueue)
                        .where(JobQueue.id == job_id)
                        .values(status=new_status)
                    )
                
                await session.commit()
            
            # Create status data
            status_data = JobStatusData(
                job_id=job_id,
                previous_status=previous_status,
                current_status=new_status,
                error_message=error_message,
            )
            
            # Broadcast to WebSocket subscribers
            ws_manager = await get_ws_manager()
            await ws_manager.broadcast_status_update(job_id, status_data)
            
            logger.info(f"Job {job_id} status changed: {previous_status} → {new_status}")
            
        except Exception as e:
            logger.error(f"Error updating status for job {job_id}: {str(e)}")

    async def mark_job_complete(
        self,
        job_id: str,
        target_url: str,
        findings_count: int,
        severity_breakdown: Dict[str, int],
        neo4j_status: str,
        neo4j_count: Optional[int] = None,
        completion_time_seconds: Optional[float] = None,
    ):
        """
        Mark job as complete and broadcast result.
        
        Args:
            job_id: Job ID
            target_url: Target URL
            findings_count: Total findings
            severity_breakdown: Breakdown by severity
            neo4j_status: Neo4j sync status
            neo4j_count: Findings in Neo4j
            completion_time_seconds: Total time taken
        """
        try:
            # Create result data
            result_data = JobResultData(
                job_id=job_id,
                target_url=target_url,
                findings_count=findings_count,
                severity_breakdown=severity_breakdown,
                neo4j_status=neo4j_status,
                neo4j_count=neo4j_count,
                completion_time_seconds=completion_time_seconds,
            )
            
            # Broadcast to WebSocket subscribers
            ws_manager = await get_ws_manager()
            await ws_manager.broadcast_result_ready(job_id, result_data)
            
            logger.info(f"Job {job_id} completed: {findings_count} findings")
            
        except Exception as e:
            logger.error(f"Error marking job complete: {str(e)}")

    async def broadcast_metrics_update(self):
        """
        Broadcast current queue metrics to all WebSocket connections.
        """
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(JobQueue))
                all_jobs = result.scalars().all()
                
                # Calculate metrics
                total = len(all_jobs)
                pending = len([j for j in all_jobs if j.status == JobStatusEnum.PENDING.value])
                running = len([j for j in all_jobs if j.status == JobStatusEnum.RUNNING.value])
                completed = len([j for j in all_jobs if j.status == JobStatusEnum.COMPLETED.value])
                failed = len([j for j in all_jobs if j.status == JobStatusEnum.FAILED.value])
                
                # Calculate success rate
                success_rate = None
                if completed + failed > 0:
                    success_rate = (completed / (completed + failed)) * 100
                
                # Calculate average completion time
                avg_time = None
                if completed > 0:
                    total_time = sum(
                        (j.completed_at - j.created_at).total_seconds()
                        for j in all_jobs
                        if j.status == JobStatusEnum.COMPLETED.value
                        and j.completed_at
                        and j.created_at
                    )
                    avg_time = total_time / completed if completed else None
            
            # Create metrics data
            metrics_data = QueueMetricsData(
                total_jobs=total,
                pending_jobs=pending,
                running_jobs=running,
                completed_jobs=completed,
                failed_jobs=failed,
                success_rate=success_rate,
                average_completion_time_seconds=avg_time,
            )
            
            # Broadcast to all connections
            ws_manager = await get_ws_manager()
            await ws_manager.broadcast_metrics_update(metrics_data)
            
        except Exception as e:
            logger.error(f"Error broadcasting metrics: {str(e)}")


# Singleton instance
_progress_tracker_instance: Optional[JobProgressTracker] = None


async def get_progress_tracker() -> JobProgressTracker:
    """Get or create progress tracker singleton."""
    global _progress_tracker_instance
    if _progress_tracker_instance is None:
        _progress_tracker_instance = JobProgressTracker()
    return _progress_tracker_instance


# Background task to periodically update metrics
async def metrics_update_loop(interval_seconds: int = 30):
    """
    Periodic task to broadcast queue metrics.
    
    Args:
        interval_seconds: Update interval in seconds
    """
    tracker = await get_progress_tracker()
    
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await tracker.broadcast_metrics_update()
        except Exception as e:
            logger.error(f"Error in metrics update loop: {str(e)}")
