"""Celery task definitions for Nuclei scanning and processing."""

import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from app.workers.config import celery_app
from app.adapters.postgres import AsyncSessionLocal, JobQueue
from app.services.nuclei_services import (
    NucleiIntegrationService,
    NucleiPostgresService,
)
from app.services.graph_service import GraphService
from sqlalchemy import update, select

# Phase 5.3: Auto-indexing to Elasticsearch
try:
    from app.services.search_service import get_search_service
    SEARCH_SERVICE_AVAILABLE = True
except ImportError:
    SEARCH_SERVICE_AVAILABLE = False

logger = logging.getLogger(__name__)


async def _get_job_queue_record(job_db_id: str):
    """Get JobQueue record from database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(JobQueue).filter(JobQueue.id == job_db_id)
        )
        return result.scalars().first()


async def _update_job_status(
    job_db_id: str,
    status: str,
    **kwargs
):
    """Update job status in database."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(JobQueue)
            .where(JobQueue.id == job_db_id)
            .values(
                status=status,
                updated_at=datetime.utcnow(),
                **kwargs
            )
        )
        await session.commit()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def scan_target_async(
    self,
    job_db_id: str,
    target_url: str,
    scan_type: str = "full",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Background task to execute Nuclei scan on target.
    
    Args:
        job_db_id: Database job ID
        target_url: Target URL to scan
        scan_type: Type of scan (full, web, api)
        metadata: Additional metadata
        
    Returns:
        Dict with scan results
        
    Raises:
        Exception: On scan failure (triggers retry)
    """
    import asyncio
    
    try:
        # Update job status to running
        asyncio.run(_update_job_status(
            job_db_id,
            "running",
            started_at=datetime.utcnow(),
        ))
        
        logger.info(f"Starting scan for {target_url} (job: {job_db_id})")
        
        # Initialize services
        integration_service = NucleiIntegrationService()
        postgres_service = NucleiPostgresService()
        
        # Create scan record
        scan_result = asyncio.run(integration_service.execute_nuclei_scan(
            target_url=target_url,
            scan_type=scan_type,
            metadata=metadata or {},
        ))
        
        logger.info(
            f"Scan completed for {target_url}: "
            f"{scan_result['findings_count']} findings"
        )
        
        # Prepare result
        result = {
            "scan_id": scan_result.get("scan_id"),
            "target_url": target_url,
            "findings_count": scan_result.get("findings_count", 0),
            "severity_breakdown": scan_result.get("severity_breakdown", {}),
            "neo4j_status": scan_result.get("neo4j_status", "pending"),
            "completed_at": datetime.utcnow().isoformat(),
        }
        
        # Update job with result
        asyncio.run(_update_job_status(
            job_db_id,
            "completed",
            result=result,
            completed_at=datetime.utcnow(),
        ))
        
        # Phase 5.3: Auto-index job result to Elasticsearch
        if SEARCH_SERVICE_AVAILABLE:
            try:
                import asyncio
                
                async def _index_job_completion():
                    """Index job completion and findings."""
                    search_service = await get_search_service()
                    
                    # Index the job result
                    await search_service.index_job_result(
                        job_id=job_db_id,
                        target_url=target_url,
                        findings_count=result.get("findings_count", 0),
                        severity_breakdown=result.get("severity_breakdown", {}),
                        neo4j_status=result.get("neo4j_status", "pending"),
                    )
                    
                    # Index individual findings if available
                    findings = scan_result.get("findings", [])
                    for idx, finding in enumerate(findings):
                        await search_service.index_finding(
                            finding_id=finding.get("id", f"{job_db_id}-{idx}"),
                            job_id=job_db_id,
                            template_id=finding.get("template_id", "unknown"),
                            target_url=target_url,
                            severity=finding.get("severity", "INFO"),
                            host=finding.get("host", target_url),
                            url=finding.get("url", target_url),
                            cve_ids=finding.get("cve_ids", []),
                            cwe_ids=finding.get("cwe_ids", []),
                        )
                    
                    logger.info(f"Indexed job {job_db_id} and {len(findings)} findings to Elasticsearch")
                
                asyncio.run(_index_job_completion())
            except Exception as e:
                logger.warning(f"Failed to index job {job_db_id} results to Elasticsearch: {e}")
        
        return result
        
    except Exception as exc:
        logger.error(f"Scan failed for {target_url}: {str(exc)}", exc_info=True)
        
        # Update job status to retrying
        retry_count = self.request.retries
        if retry_count < self.max_retries:
            asyncio.run(_update_job_status(
                job_db_id,
                "retrying",
                retry_count=retry_count + 1,
                error_message=str(exc),
            ))
        else:
            # Final failure
            asyncio.run(_update_job_status(
                job_db_id,
                "failed",
                retry_count=retry_count,
                error_message=str(exc),
                completed_at=datetime.utcnow(),
            ))
        
        # Trigger retry with exponential backoff
        countdown = 2 ** self.request.retries  # 1, 2, 4, 8 seconds
        raise self.retry(exc=exc, countdown=countdown)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_scan_results(
    self,
    job_db_id: str,
    scan_id: str,
) -> Dict[str, Any]:
    """
    Post-process scan results (extract relationships, etc).
    
    Args:
        job_db_id: Database job ID
        scan_id: Nuclei scan ID
        
    Returns:
        Processing result
    """
    import asyncio
    
    try:
        logger.info(f"Processing results for scan {scan_id}")
        
        postgres_service = NucleiPostgresService()
        
        # Get scan details
        scan = asyncio.run(postgres_service.get_scan(scan_id))
        
        if not scan:
            raise ValueError(f"Scan {scan_id} not found")
        
        # Get findings
        findings = asyncio.run(postgres_service.get_scan_findings(scan_id))
        
        # Extract CVE/CWE relationships
        cve_count = sum(1 for f in findings if f["cve_ids"])
        cwe_count = sum(1 for f in findings if f["cwe_ids"])
        
        result = {
            "scan_id": scan_id,
            "findings_processed": len(findings),
            "cve_relationships": cve_count,
            "cwe_relationships": cwe_count,
            "processed_at": datetime.utcnow().isoformat(),
        }
        
        logger.info(f"Processing completed: {result}")
        return result
        
    except Exception as exc:
        logger.error(f"Processing failed: {str(exc)}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    acks_late=True,
)
def upsert_to_neo4j_async(
    self,
    job_db_id: str,
    scan_id: str,
    findings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Async Neo4j upsert with retry logic.
    
    Args:
        job_db_id: Database job ID
        scan_id: Nuclei scan ID
        findings: List of findings to upsert
        
    Returns:
        Upsert result with statistics
    """
    import asyncio
    
    try:
        logger.info(f"Upserting {len(findings)} findings to Neo4j")
        
        integration_service = NucleiIntegrationService()
        
        # Perform Neo4j upsert
        upsert_result = asyncio.run(
            integration_service.save_finding_batch(
                scan_id=scan_id,
                findings=findings,
            )
        )
        
        result = {
            "scan_id": scan_id,
            "findings_upserted": upsert_result.get("upserted_count", 0),
            "relationships_created": upsert_result.get("relationships_created", 0),
            "errors": upsert_result.get("errors", []),
            "upserted_at": datetime.utcnow().isoformat(),
        }
        
        logger.info(f"Neo4j upsert completed: {result}")
        return result
        
    except Exception as exc:
        logger.error(f"Neo4j upsert failed: {str(exc)}", exc_info=True)
        
        retry_count = self.request.retries
        if retry_count < self.max_retries:
            countdown = 2 ** retry_count  # Exponential backoff
            raise self.retry(exc=exc, countdown=countdown)
        else:
            # Log permanent failure
            logger.error(
                f"Neo4j upsert permanently failed after {self.max_retries} retries: "
                f"{str(exc)}"
            )
            raise


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def generate_report(
    self,
    job_db_id: str,
    scan_id: str,
) -> Dict[str, Any]:
    """
    Generate report for completed scan.
    
    Args:
        job_db_id: Database job ID
        scan_id: Nuclei scan ID
        
    Returns:
        Report generation result
    """
    import asyncio
    
    try:
        logger.info(f"Generating report for scan {scan_id}")
        
        postgres_service = NucleiPostgresService()
        
        # Get scan
        scan = asyncio.run(postgres_service.get_scan(scan_id))
        
        if not scan:
            raise ValueError(f"Scan {scan_id} not found")
        
        # Get findings and statistics
        findings = asyncio.run(postgres_service.get_scan_findings(scan_id))
        stats = asyncio.run(postgres_service.get_statistics())
        
        # Generate report data
        report = {
            "scan_id": scan_id,
            "target": scan.get("target_url"),
            "scan_type": scan.get("scan_type"),
            "total_findings": len(findings),
            "severity_breakdown": {
                "CRITICAL": len([f for f in findings if f["severity"] == "CRITICAL"]),
                "HIGH": len([f for f in findings if f["severity"] == "HIGH"]),
                "MEDIUM": len([f for f in findings if f["severity"] == "MEDIUM"]),
                "LOW": len([f for f in findings if f["severity"] == "LOW"]),
                "INFO": len([f for f in findings if f["severity"] == "INFO"]),
            },
            "completion_time": (
                datetime.fromisoformat(scan["completed_at"]) - 
                datetime.fromisoformat(scan["created_at"])
            ).total_seconds() if scan.get("completed_at") else None,
            "generated_at": datetime.utcnow().isoformat(),
        }
        
        logger.info(f"Report generated: {len(findings)} findings")
        return report
        
    except Exception as exc:
        logger.error(f"Report generation failed: {str(exc)}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task
def cleanup_old_jobs(days: int = 7) -> Dict[str, int]:
    """
    Cleanup old completed/failed jobs.
    
    Args:
        days: Delete jobs older than this many days
        
    Returns:
        Cleanup statistics
    """
    import asyncio
    from sqlalchemy import delete
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        async def _cleanup():
            async with AsyncSessionLocal() as session:
                # Delete old completed/failed/cancelled jobs
                result = await session.execute(
                    delete(JobQueue).where(
                        (JobQueue.completed_at < cutoff_date) |
                        (
                            (JobQueue.status.in_(["failed", "cancelled"])) &
                            (JobQueue.created_at < cutoff_date)
                        )
                    )
                )
                await session.commit()
                return result.rowcount
        
        deleted_count = asyncio.run(_cleanup())
        
        logger.info(f"Cleaned up {deleted_count} old jobs")
        return {"deleted_jobs": deleted_count}
        
    except Exception as exc:
        logger.error(f"Job cleanup failed: {str(exc)}", exc_info=True)
        return {"deleted_jobs": 0, "error": str(exc)}
