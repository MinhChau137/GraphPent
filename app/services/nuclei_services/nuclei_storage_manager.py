"""Neo4j Storage Manager for Nuclei Findings - Phase 3.

Handles:
- Creating :DiscoveredVulnerability nodes
- Creating relationships with :CVE and :CWE nodes
- Querying findings
- Bulk operations
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from uuid import UUID
from app.adapters.neo4j_client import Neo4jAdapter
from app.adapters.nuclei_parser.models import Finding

logger = logging.getLogger(__name__)


class NucleiStorageManager:
    """Manager for Neo4j operations related to Nuclei findings."""

    def __init__(self, neo4j_adapter: Neo4jAdapter):
        """Initialize with Neo4j adapter.
        
        Args:
            neo4j_adapter: Neo4jAdapter instance for database operations
        """
        self.neo4j = neo4j_adapter

    async def create_finding_node(self, finding: Finding) -> Dict:
        """Create a :DiscoveredVulnerability node in Neo4j.
        
        Args:
            finding: Finding object from parser
            
        Returns:
            Dictionary with creation result (id, success status, error if any)
        """
        finding_dict = {
            "id": str(finding.id),
            "template_id": finding.template_id,
            "severity": finding.severity.value,
            "host": finding.host,
            "url": finding.url,
            "matched_at": finding.matched_at.isoformat() if finding.matched_at else None,
            "source": finding.source,
            "metadata": finding.metadata or {},
        }
        
        result = await self.neo4j.create_discovered_vulnerability(finding_dict)
        return result

    async def create_cve_relationship(self, finding_id: UUID, cve_id: str) -> Dict:
        """Create CORRELATES_TO relationship between Finding and CVE.
        
        Args:
            finding_id: UUID of finding
            cve_id: CVE identifier (e.g., "CVE-2024-1234")
            
        Returns:
            Dictionary with operation result
        """
        result = await self.neo4j.create_finding_cve_relationship(str(finding_id), cve_id)
        return result

    async def create_cwe_relationship(self, finding_id: UUID, cwe_id: str) -> Dict:
        """Create CLASSIFIED_AS relationship between Finding and CWE.
        
        Args:
            finding_id: UUID of finding
            cwe_id: CWE identifier (e.g., "CWE-89")
            
        Returns:
            Dictionary with operation result
        """
        result = await self.neo4j.create_finding_cwe_relationship(str(finding_id), cwe_id)
        return result

    async def bulk_create_findings(self, findings: List[Finding]) -> Dict:
        """Create multiple findings in Neo4j.
        
        Args:
            findings: List of Finding objects
            
        Returns:
            Dictionary with bulk operation statistics
        """
        stats = {
            "total": len(findings),
            "created": 0,
            "failed": 0,
            "errors": []
        }
        
        for finding in findings:
            result = await self.create_finding_node(finding)
            
            if result["success"]:
                stats["created"] += 1
            else:
                stats["failed"] += 1
                stats["errors"].append(result)
        
        logger.info(
            f"Bulk finding creation completed",
            extra={
                "total": stats["total"],
                "created": stats["created"],
                "failed": stats["failed"]
            }
        )
        
        return stats

    async def create_finding_relationships(self, finding: Finding) -> Dict:
        """Create all relationships for a finding (CVE and CWE).
        
        Args:
            finding: Finding object
            
        Returns:
            Dictionary with relationship creation results
        """
        stats = {
            "cve_created": 0,
            "cwe_created": 0,
            "cve_failed": 0,
            "cwe_failed": 0,
            "errors": []
        }
        
        # Create CVE relationships
        for cve_id in finding.cve_ids:
            result = await self.create_cve_relationship(finding.id, cve_id)
            if result["success"]:
                stats["cve_created"] += 1
            else:
                stats["cve_failed"] += 1
                stats["errors"].append(result)
        
        # Create CWE relationships
        for cwe_id in finding.cwe_ids:
            result = await self.create_cwe_relationship(finding.id, cwe_id)
            if result["success"]:
                stats["cwe_created"] += 1
            else:
                stats["cwe_failed"] += 1
                stats["errors"].append(result)
        
        logger.info(
            f"Finding relationships created",
            extra={
                "finding_id": str(finding.id),
                "cve_created": stats["cve_created"],
                "cwe_created": stats["cwe_created"]
            }
        )
        
        return stats

    async def query_findings_by_severity(self, severity: str) -> List[Dict]:
        """Query findings by severity level.
        
        Args:
            severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO)
            
        Returns:
            List of finding dictionaries
        """
        result = await self.neo4j.query_findings_by_severity(severity)
        return result or []

    async def query_findings_by_host(self, host: str) -> List[Dict]:
        """Query findings by host/target.
        
        Args:
            host: Host/target address
            
        Returns:
            List of finding dictionaries
        """
        result = await self.neo4j.query_findings_by_host(host)
        return result or []

    async def query_findings_by_template(self, template_id: str) -> List[Dict]:
        """Query findings by Nuclei template ID.
        
        Args:
            template_id: Nuclei template identifier
            
        Returns:
            List of finding dictionaries
        """
        result = await self.neo4j.query_findings_by_template(template_id)
        return result or []

    async def get_finding_by_id(self, finding_id: str) -> Optional[Dict]:
        """Get a specific finding by ID.
        
        Args:
            finding_id: UUID of the finding
            
        Returns:
            Finding dictionary or None if not found
        """
        result = await self.neo4j.get_finding_by_id(finding_id)
        return result

    async def delete_findings_by_template(self, template_id: str) -> Dict:
        """Delete findings by template ID.
        
        Args:
            template_id: Nuclei template identifier
            
        Returns:
            Dictionary with deletion statistics
        """
        result = await self.neo4j.delete_findings_by_template(template_id)
        return result
