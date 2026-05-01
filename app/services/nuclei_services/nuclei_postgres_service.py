"""PostgreSQL Service for Nuclei Scan Tracking - Phase 3.

Handles:
- Creating scan records
- Updating scan status
- Storing findings metadata
- Querying scan history
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.postgres import NucleiScan, NucleiFindings, AsyncSessionLocal

logger = logging.getLogger(__name__)


class NucleiPostgresService:
    """Service for PostgreSQL operations related to Nuclei scans."""

    async def create_scan(
        self,
        target_url: str,
        scan_type: str = "full",
        metadata: Dict = None
    ) -> str:
        """Create a new scan record.
        
        Args:
            target_url: Target URL/IP for scan
            scan_type: Type of scan (full, web, api)
            metadata: Additional scan metadata
            
        Returns:
            Scan ID (UUID string)
        """
        try:
            async with AsyncSessionLocal() as session:
                scan = NucleiScan(
                    target_url=target_url,
                    scan_type=scan_type,
                    status="running",
                    metadata=metadata or {}
                )
                
                session.add(scan)
                await session.commit()
                await session.refresh(scan)
                
                logger.info(
                    f"Scan created",
                    extra={"scan_id": scan.id, "target_url": target_url}
                )
                
                return scan.id
                
        except Exception as e:
            logger.error(f"Failed to create scan: {e}")
            raise

    async def update_scan_status(
        self,
        scan_id: str,
        status: str,
        findings_count: int = 0,
        error_message: str = None,
        neo4j_status: str = None
    ) -> bool:
        """Update scan status.
        
        Args:
            scan_id: Scan identifier
            status: New status (running, completed, failed)
            findings_count: Number of findings
            error_message: Error message if failed
            neo4j_status: Neo4j upsert status
            
        Returns:
            Success boolean
        """
        try:
            async with AsyncSessionLocal() as session:
                stmt = update(NucleiScan).where(
                    NucleiScan.id == scan_id
                ).values(
                    status=status,
                    findings_count=findings_count,
                    error_message=error_message,
                    completed_at=datetime.now() if status in ["completed", "failed"] else None,
                    neo4j_status=neo4j_status or "pending",
                    updated_at=datetime.now()
                )
                
                await session.execute(stmt)
                await session.commit()
                
                logger.info(
                    f"Scan status updated",
                    extra={"scan_id": scan_id, "status": status}
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to update scan status: {e}")
            return False

    async def get_scan(self, scan_id: str) -> Optional[Dict]:
        """Get scan details.
        
        Args:
            scan_id: Scan identifier
            
        Returns:
            Scan dictionary or None
        """
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(NucleiScan).where(NucleiScan.id == scan_id)
                result = await session.execute(stmt)
                scan = result.scalar_one_or_none()
                
                if scan:
                    return {
                        "id": scan.id,
                        "target_url": scan.target_url,
                        "status": scan.status,
                        "scan_type": scan.scan_type,
                        "findings_count": scan.findings_count,
                        "neo4j_status": scan.neo4j_status,
                        "started_at": scan.started_at.isoformat() if scan.started_at else None,
                        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
                        "error_message": scan.error_message
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get scan: {e}")
            return None

    async def create_finding(
        self,
        scan_id: str,
        finding_id: str,
        template_id: str,
        severity: str,
        host: str,
        url: str,
        matched_at: datetime = None,
        cve_ids: List[str] = None,
        cwe_ids: List[str] = None,
        metadata: Dict = None,
        neo4j_id: str = None
    ) -> bool:
        """Store finding metadata.
        
        Args:
            scan_id: Parent scan ID
            finding_id: Finding UUID from parser
            template_id: Nuclei template ID
            severity: Severity level
            host: Target host
            url: Target URL
            matched_at: When finding was discovered
            cve_ids: Related CVE IDs
            cwe_ids: Related CWE IDs
            metadata: Additional metadata
            neo4j_id: UUID in Neo4j
            
        Returns:
            Success boolean
        """
        try:
            async with AsyncSessionLocal() as session:
                finding = NucleiFindings(
                    scan_id=scan_id,
                    finding_id=finding_id,
                    template_id=template_id,
                    severity=severity,
                    host=host,
                    url=url,
                    matched_at=matched_at,
                    cve_ids=cve_ids or [],
                    cwe_ids=cwe_ids or [],
                    metadata=metadata or {},
                    neo4j_id=neo4j_id
                )
                
                session.add(finding)
                await session.commit()
                
                logger.debug(
                    f"Finding stored",
                    extra={"finding_id": finding_id, "severity": severity}
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to create finding: {e}")
            return False

    async def bulk_create_findings(
        self,
        scan_id: str,
        findings: List[Dict]
    ) -> Dict:
        """Bulk store findings.
        
        Args:
            scan_id: Parent scan ID
            findings: List of finding dictionaries
            
        Returns:
            Dictionary with stats (created, failed)
        """
        stats = {"created": 0, "failed": 0}
        
        try:
            async with AsyncSessionLocal() as session:
                for finding_dict in findings:
                    try:
                        finding = NucleiFindings(
                            scan_id=scan_id,
                            **finding_dict
                        )
                        session.add(finding)
                        stats["created"] += 1
                    except Exception as e:
                        logger.warning(f"Failed to add finding: {e}")
                        stats["failed"] += 1
                
                await session.commit()
                
                logger.info(
                    f"Bulk findings stored",
                    extra={
                        "scan_id": scan_id,
                        "created": stats["created"],
                        "failed": stats["failed"]
                    }
                )
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to bulk create findings: {e}")
            return stats

    async def get_scan_findings(
        self,
        scan_id: str,
        limit: int = 1000
    ) -> List[Dict]:
        """Get findings for a scan.
        
        Args:
            scan_id: Scan ID
            limit: Max findings to return
            
        Returns:
            List of finding dictionaries
        """
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(NucleiFindings).where(
                    NucleiFindings.scan_id == scan_id
                ).limit(limit)
                
                result = await session.execute(stmt)
                findings = result.scalars().all()
                
                return [
                    {
                        "id": f.id,
                        "finding_id": f.finding_id,
                        "template_id": f.template_id,
                        "severity": f.severity,
                        "host": f.host,
                        "url": f.url,
                        "cve_ids": f.cve_ids,
                        "cwe_ids": f.cwe_ids,
                        "matched_at": f.matched_at.isoformat() if f.matched_at else None
                    }
                    for f in findings
                ]
                
        except Exception as e:
            logger.error(f"Failed to get scan findings: {e}")
            return []

    async def get_scan_history(
        self,
        limit: int = 20,
        status_filter: str = None
    ) -> List[Dict]:
        """Get recent scan history.
        
        Args:
            limit: Number of scans to return
            status_filter: Filter by status (optional)
            
        Returns:
            List of scan dictionaries
        """
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(NucleiScan).order_by(
                    desc(NucleiScan.created_at)
                )
                
                if status_filter:
                    stmt = stmt.where(NucleiScan.status == status_filter)
                
                stmt = stmt.limit(limit)
                
                result = await session.execute(stmt)
                scans = result.scalars().all()
                
                return [
                    {
                        "id": s.id,
                        "target_url": s.target_url,
                        "status": s.status,
                        "findings_count": s.findings_count,
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                        "completed_at": s.completed_at.isoformat() if s.completed_at else None
                    }
                    for s in scans
                ]
                
        except Exception as e:
            logger.error(f"Failed to get scan history: {e}")
            return []

    async def query_findings_by_host(self, host: str) -> List[Dict]:
        """Query findings by host.
        
        Args:
            host: Target host
            
        Returns:
            List of finding dictionaries
        """
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(NucleiFindings).where(
                    NucleiFindings.host == host
                ).order_by(desc(NucleiFindings.matched_at))
                
                result = await session.execute(stmt)
                findings = result.scalars().all()
                
                return [
                    {
                        "id": f.id,
                        "scan_id": f.scan_id,
                        "template_id": f.template_id,
                        "severity": f.severity,
                        "url": f.url,
                        "matched_at": f.matched_at.isoformat() if f.matched_at else None
                    }
                    for f in findings
                ]
                
        except Exception as e:
            logger.error(f"Failed to query findings by host: {e}")
            return []

    async def query_findings_by_severity(self, severity: str) -> List[Dict]:
        """Query findings by severity.
        
        Args:
            severity: Severity level
            
        Returns:
            List of finding dictionaries
        """
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(NucleiFindings).where(
                    NucleiFindings.severity == severity
                ).order_by(desc(NucleiFindings.matched_at))
                
                result = await session.execute(stmt)
                findings = result.scalars().all()
                
                return [
                    {
                        "id": f.id,
                        "scan_id": f.scan_id,
                        "template_id": f.template_id,
                        "host": f.host,
                        "url": f.url,
                        "matched_at": f.matched_at.isoformat() if f.matched_at else None
                    }
                    for f in findings
                ]
                
        except Exception as e:
            logger.error(f"Failed to query findings by severity: {e}")
            return []

    async def get_statistics(self) -> Dict:
        """Get overall statistics.
        
        Returns:
            Dictionary with stats
        """
        try:
            async with AsyncSessionLocal() as session:
                # Total scans
                scans_stmt = select(NucleiScan)
                scans_result = await session.execute(scans_stmt)
                total_scans = len(scans_result.scalars().all())
                
                # Total findings
                findings_stmt = select(NucleiFindings)
                findings_result = await session.execute(findings_stmt)
                total_findings = len(findings_result.scalars().all())
                
                # Critical count
                critical_stmt = select(NucleiFindings).where(
                    NucleiFindings.severity == "CRITICAL"
                )
                critical_result = await session.execute(critical_stmt)
                critical_count = len(critical_result.scalars().all())
                
                return {
                    "total_scans": total_scans,
                    "total_findings": total_findings,
                    "critical_findings": critical_count,
                    "scans_completed": 0,  # Would query status='completed'
                    "last_scan": None
                }
                
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
