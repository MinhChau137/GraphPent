"""Nuclei Integration Service - Phase 3 Main Service.

Orchestrates the end-to-end integration between:
1. NucleiParser (Phase 2) - Parsing Nuclei output
2. NucleiStorageManager - Neo4j operations
3. NucleiPostgresService - PostgreSQL scan tracking
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from uuid import uuid4, UUID

from app.adapters.nuclei_parser.nuclei_parser import NucleiParser
from app.adapters.nuclei_parser.models import Finding, NormalizationResult, ScanResult, SeverityEnum
from app.adapters.neo4j_client import Neo4jAdapter
from app.services.nuclei_services.nuclei_storage_manager import NucleiStorageManager
from app.services.nuclei_services.nuclei_postgres_service import NucleiPostgresService
from app.adapters.postgres import AsyncSessionLocal, Document, Chunk

logger = logging.getLogger(__name__)


class NucleiIntegrationService:
    """Main service for Nuclei findings integration.
    
    Responsibilities:
    - Parse Nuclei output using Phase 2 parser
    - Store findings in Neo4j with label separation
    - Create relationships with existing CVE/CWE nodes
    - Track scans in PostgreSQL
    - Provide query interfaces
    """

    def __init__(self, neo4j_adapter: Neo4jAdapter):
        """Initialize integration service.
        
        Args:
            neo4j_adapter: Neo4jAdapter instance
        """
        self.parser = NucleiParser()
        self.storage = NucleiStorageManager(neo4j_adapter)
        self.postgres = NucleiPostgresService()
        self.neo4j = neo4j_adapter

    async def process_nuclei_output(
        self,
        nuclei_output: str | Dict | List,
        scan_id: Optional[str] = None,
        target_url: Optional[str] = None
    ) -> Dict:
        """Process Nuclei output end-to-end.
        
        Pipeline:
        1. Parse Nuclei output into Finding objects
        2. Create finding entities in Neo4j
        3. Create CVE/CWE relationships
        4. Track scan in PostgreSQL
        
        Args:
            nuclei_output: Raw Nuclei output (JSONL, dict, or list)
            scan_id: Unique scan identifier (generated if not provided)
            target_url: Target URL being scanned
            
        Returns:
            Dictionary with processing results:
            {
                "scan_id": str,
                "findings_count": int,
                "findings_stored": int,
                "findings_failed": int,
                "cve_relationships": int,
                "cwe_relationships": int,
                "status": str,
                "error": str (optional)
            }
        """
        # Generate scan ID if not provided
        if not scan_id:
            scan_id = str(uuid4())
        
        logger.info(
            f"Starting Nuclei processing",
            extra={
                "scan_id": scan_id,
                "target_url": target_url
            }
        )
        
        try:
            # Step 1: Parse Nuclei output
            logger.info(f"Step 1: Parsing Nuclei output", extra={"scan_id": scan_id})
            
            norm_result: NormalizationResult = await self.parser.normalize(nuclei_output)
            
            if norm_result.failed_count > 0:
                logger.warning(
                    f"Parser encountered errors",
                    extra={
                        "scan_id": scan_id,
                        "failed_count": norm_result.failed_count,
                        "errors": norm_result.errors[:5]  # Log first 5 errors
                    }
                )
            
            findings = norm_result.findings
            logger.info(
                f"Parsing completed",
                extra={
                    "scan_id": scan_id,
                    "total_findings": len(findings),
                    "normalized_count": norm_result.normalized_count
                }
            )
            
            # Step 2: Create finding entities in Neo4j
            logger.info(f"Step 2: Creating findings in Neo4j", extra={"scan_id": scan_id})
            
            create_stats = await self.storage.bulk_create_findings(findings)
            
            logger.info(
                f"Findings created in Neo4j",
                extra={
                    "scan_id": scan_id,
                    "created": create_stats["created"],
                    "failed": create_stats["failed"]
                }
            )
            
            # Step 3: Create CVE/CWE relationships
            logger.info(
                f"Step 3: Creating relationships",
                extra={"scan_id": scan_id}
            )
            
            total_cve_rels = 0
            total_cwe_rels = 0
            rel_errors = []
            
            for finding in findings:
                rel_result = await self.storage.create_finding_relationships(finding)
                total_cve_rels += rel_result.get("cve_created", 0)
                total_cwe_rels += rel_result.get("cwe_created", 0)
                if rel_result.get("errors"):
                    rel_errors.extend(rel_result["errors"])
            
            logger.info(
                f"Relationships created",
                extra={
                    "scan_id": scan_id,
                    "cve_relationships": total_cve_rels,
                    "cwe_relationships": total_cwe_rels
                }
            )
            
            # Step 4: Track scan metadata in PostgreSQL
            logger.info(
                f"Step 4: Updating PostgreSQL metadata",
                extra={"scan_id": scan_id}
            )
            
            await self._save_scan_metadata(
                scan_id=scan_id,
                target_url=target_url,
                findings_count=len(findings),
                status="completed"
            )
            
            # Prepare result
            result = {
                "scan_id": scan_id,
                "findings_count": len(findings),
                "findings_stored": create_stats["created"],
                "findings_failed": create_stats["failed"],
                "cve_relationships": total_cve_rels,
                "cwe_relationships": total_cwe_rels,
                "status": "completed",
                "parser_warnings": len(norm_result.errors),
                "relationship_errors": len(rel_errors)
            }
            
            logger.info(
                f"Nuclei processing completed successfully",
                extra=result
            )
            
            return result
            
        except Exception as e:
            logger.error(
                f"Nuclei processing failed: {e}",
                extra={"scan_id": scan_id, "error": str(e)},
                exc_info=True
            )
            
            # Update scan status to failed
            try:
                await self._save_scan_metadata(
                    scan_id=scan_id,
                    target_url=target_url,
                    findings_count=0,
                    status="failed",
                    error_message=str(e)
                )
            except Exception as db_error:
                logger.error(f"Failed to update scan status in DB: {db_error}")
            
            return {
                "scan_id": scan_id,
                "findings_count": 0,
                "findings_stored": 0,
                "findings_failed": 0,
                "status": "failed",
                "error": str(e)
            }

    async def get_findings_by_severity(self, severity: str) -> List[Dict]:
        """Get all findings by severity level.
        
        Args:
            severity: CRITICAL, HIGH, MEDIUM, LOW, or INFO
            
        Returns:
            List of finding dictionaries
        """
        logger.info(f"Querying findings by severity: {severity}")
        
        # Validate severity
        try:
            SeverityEnum[severity.upper()]
        except KeyError:
            logger.error(f"Invalid severity: {severity}")
            return []
        
        results = await self.storage.query_findings_by_severity(severity.upper())
        logger.info(f"Found {len(results)} findings with severity {severity}")
        
        return results

    async def get_findings_by_host(self, host: str) -> List[Dict]:
        """Get all findings for a specific host.
        
        Args:
            host: Host/IP address
            
        Returns:
            List of finding dictionaries
        """
        logger.info(f"Querying findings for host: {host}")
        
        results = await self.storage.query_findings_by_host(host)
        logger.info(f"Found {len(results)} findings for host {host}")
        
        return results

    async def get_findings_by_template(self, template_id: str) -> List[Dict]:
        """Get all findings for a specific Nuclei template.
        
        Args:
            template_id: Nuclei template identifier
            
        Returns:
            List of finding dictionaries
        """
        logger.info(f"Querying findings by template: {template_id}")
        
        results = await self.storage.query_findings_by_template(template_id)
        logger.info(f"Found {len(results)} findings for template {template_id}")
        
        return results

    async def get_finding(self, finding_id: str) -> Optional[Dict]:
        """Get a specific finding by ID.
        
        Args:
            finding_id: UUID of the finding
            
        Returns:
            Finding dictionary or None
        """
        logger.info(f"Fetching finding: {finding_id}")
        
        result = await self.storage.get_finding_by_id(finding_id)
        
        if result:
            logger.info(f"Found finding: {finding_id}")
        else:
            logger.warning(f"Finding not found: {finding_id}")
        
        return result

    async def get_critical_findings(self) -> List[Dict]:
        """Get all critical findings.
        
        Returns:
            List of critical finding dictionaries
        """
        return await self.get_findings_by_severity("CRITICAL")

    async def get_high_findings(self) -> List[Dict]:
        """Get all high severity findings.
        
        Returns:
            List of high severity finding dictionaries
        """
        return await self.get_findings_by_severity("HIGH")

    async def delete_findings_by_template(self, template_id: str) -> Dict:
        """Delete all findings for a specific template.
        
        Args:
            template_id: Nuclei template identifier
            
        Returns:
            Dictionary with deletion results
        """
        logger.info(f"Deleting findings for template: {template_id}")
        
        result = await self.storage.delete_findings_by_template(template_id)
        
        logger.info(
            f"Findings deleted",
            extra={"template_id": template_id, "deleted_count": result.get("deleted_count", 0)}
        )
        
        return result

    # ==================== PostgreSQL Operations ====================

    async def _save_scan_metadata(
        self,
        scan_id: str,
        target_url: Optional[str] = None,
        findings_count: int = 0,
        status: str = "pending",
        error_message: Optional[str] = None
    ) -> None:
        """Save or update scan metadata in PostgreSQL.
        
        Args:
            scan_id: Unique scan identifier
            target_url: Target being scanned
            findings_count: Number of findings discovered
            status: Scan status (pending, running, completed, failed)
            error_message: Error message if scan failed
        """
        try:
            await self.postgres.update_scan_status(
                scan_id=scan_id,
                status=status,
                findings_count=findings_count,
                error_message=error_message,
                neo4j_status="upserted" if status == "completed" else "pending"
            )
            
            logger.info(
                f"Scan metadata saved to PostgreSQL",
                extra={
                    "scan_id": scan_id,
                    "target_url": target_url,
                    "findings_count": findings_count,
                    "status": status
                }
            )
        except Exception as e:
            logger.error(f"Failed to save scan metadata: {e}")

    async def save_finding_batch(
        self,
        scan_id: str,
        findings: List[Finding]
    ) -> Dict:
        """Save findings to PostgreSQL after Neo4j insertion.
        
        Args:
            scan_id: Parent scan ID
            findings: List of Finding objects
            
        Returns:
            Dictionary with storage stats
        """
        try:
            finding_dicts = [
                {
                    "finding_id": str(f.id),
                    "template_id": f.template_id,
                    "severity": f.severity.value,
                    "host": f.host,
                    "url": f.url,
                    "matched_at": f.matched_at,
                    "cve_ids": f.cve_ids,
                    "cwe_ids": f.cwe_ids,
                    "metadata": f.metadata or {}
                }
                for f in findings
            ]
            
            stats = await self.postgres.bulk_create_findings(scan_id, finding_dicts)
            
            logger.info(
                f"Findings saved to PostgreSQL",
                extra={
                    "scan_id": scan_id,
                    "created": stats.get("created", 0),
                    "failed": stats.get("failed", 0)
                }
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to save findings: {e}")
            return {"created": 0, "failed": len(findings)}

    async def get_scan_history(self, limit: int = 10) -> List[Dict]:
        """Get recent scan history.
        
        Args:
            limit: Number of recent scans to return
            
        Returns:
            List of scan records
        """
        try:
            return await self.postgres.get_scan_history(limit)
        except Exception as e:
            logger.error(f"Failed to get scan history: {e}")
            return []

    async def get_scan_details(self, scan_id: str) -> Optional[Dict]:
        """Get details of a specific scan.
        
        Args:
            scan_id: Unique scan identifier
            
        Returns:
            Scan details or None
        """
        try:
            return await self.postgres.get_scan(scan_id)
        except Exception as e:
            logger.error(f"Failed to get scan details: {e}")
            return None
