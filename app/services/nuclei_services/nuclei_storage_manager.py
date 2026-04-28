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
        try:
            cypher = """
            MERGE (f:DiscoveredVulnerability {id: $finding_id})
            ON CREATE SET 
                f.template_id = $template_id,
                f.severity = $severity,
                f.host = $host,
                f.url = $url,
                f.matched_at = $matched_at,
                f.source = $source,
                f.created_at = datetime(),
                f.metadata = $metadata
            ON MATCH SET
                f.updated_at = datetime()
            RETURN f.id as id, f.template_id as template_id
            """
            
            params = {
                "finding_id": str(finding.id),
                "template_id": finding.template_id,
                "severity": finding.severity.value,
                "host": finding.host,
                "url": finding.url,
                "matched_at": finding.matched_at.isoformat() if finding.matched_at else None,
                "source": finding.source,
                "metadata": finding.metadata or {},
            }
            
            # Execute with async session
            result = await self.neo4j.execute_write(cypher, params)
            
            logger.info(
                f"Created DiscoveredVulnerability node: {finding.id}",
                extra={"template_id": finding.template_id, "severity": finding.severity.value}
            )
            
            return {
                "id": str(finding.id),
                "success": True,
                "error": None
            }
            
        except Exception as e:
            logger.error(
                f"Failed to create finding node: {e}",
                extra={"finding_id": str(finding.id), "error": str(e)}
            )
            return {
                "id": str(finding.id),
                "success": False,
                "error": str(e)
            }

    async def create_cve_relationship(self, finding_id: UUID, cve_id: str) -> Dict:
        """Create CORRELATES_TO relationship between Finding and CVE.
        
        Args:
            finding_id: UUID of finding
            cve_id: CVE identifier (e.g., "CVE-2024-1234")
            
        Returns:
            Dictionary with operation result
        """
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {id: $finding_id})
            MERGE (c:CVE {id: $cve_id})
            MERGE (f)-[r:CORRELATES_TO]->(c)
            ON CREATE SET 
                r.created_at = datetime(),
                r.confidence = 0.95
            RETURN f.id as finding_id, c.id as cve_id, type(r) as rel_type
            """
            
            params = {
                "finding_id": str(finding_id),
                "cve_id": cve_id,
            }
            
            result = await self.neo4j.execute_write(cypher, params)
            
            logger.info(
                f"Created CORRELATES_TO relationship: {finding_id} -> {cve_id}",
                extra={"finding_id": str(finding_id), "cve_id": cve_id}
            )
            
            return {
                "finding_id": str(finding_id),
                "cve_id": cve_id,
                "success": True,
                "error": None
            }
            
        except Exception as e:
            logger.error(
                f"Failed to create CVE relationship: {e}",
                extra={"finding_id": str(finding_id), "cve_id": cve_id, "error": str(e)}
            )
            return {
                "finding_id": str(finding_id),
                "cve_id": cve_id,
                "success": False,
                "error": str(e)
            }

    async def create_cwe_relationship(self, finding_id: UUID, cwe_id: str) -> Dict:
        """Create CLASSIFIED_AS relationship between Finding and CWE.
        
        Args:
            finding_id: UUID of finding
            cwe_id: CWE identifier (e.g., "CWE-89")
            
        Returns:
            Dictionary with operation result
        """
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {id: $finding_id})
            MERGE (w:CWE {id: $cwe_id})
            MERGE (f)-[r:CLASSIFIED_AS]->(w)
            ON CREATE SET 
                r.created_at = datetime(),
                r.confidence = 0.90
            RETURN f.id as finding_id, w.id as cwe_id, type(r) as rel_type
            """
            
            params = {
                "finding_id": str(finding_id),
                "cwe_id": cwe_id,
            }
            
            result = await self.neo4j.execute_write(cypher, params)
            
            logger.info(
                f"Created CLASSIFIED_AS relationship: {finding_id} -> {cwe_id}",
                extra={"finding_id": str(finding_id), "cwe_id": cwe_id}
            )
            
            return {
                "finding_id": str(finding_id),
                "cwe_id": cwe_id,
                "success": True,
                "error": None
            }
            
        except Exception as e:
            logger.error(
                f"Failed to create CWE relationship: {e}",
                extra={"finding_id": str(finding_id), "cwe_id": cwe_id, "error": str(e)}
            )
            return {
                "finding_id": str(finding_id),
                "cwe_id": cwe_id,
                "success": False,
                "error": str(e)
            }

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
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {severity: $severity})
            OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
            OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
            RETURN f.id as id, f.template_id as template_id, f.severity as severity,
                   f.host as host, f.url as url, f.matched_at as matched_at,
                   collect(c.id) as cve_ids, collect(w.id) as cwe_ids
            """
            
            params = {"severity": severity}
            result = await self.neo4j.execute_read(cypher, params)
            
            return result or []
            
        except Exception as e:
            logger.error(f"Query by severity failed: {e}")
            return []

    async def query_findings_by_host(self, host: str) -> List[Dict]:
        """Query findings by host/target.
        
        Args:
            host: Host/target address
            
        Returns:
            List of finding dictionaries
        """
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {host: $host})
            OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
            OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
            RETURN f.id as id, f.template_id as template_id, f.severity as severity,
                   f.host as host, f.url as url, f.matched_at as matched_at,
                   collect(c.id) as cve_ids, collect(w.id) as cwe_ids
            ORDER BY f.matched_at DESC
            """
            
            params = {"host": host}
            result = await self.neo4j.execute_read(cypher, params)
            
            return result or []
            
        except Exception as e:
            logger.error(f"Query by host failed: {e}")
            return []

    async def query_findings_by_template(self, template_id: str) -> List[Dict]:
        """Query findings by Nuclei template ID.
        
        Args:
            template_id: Nuclei template identifier
            
        Returns:
            List of finding dictionaries
        """
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {template_id: $template_id})
            OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
            OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
            RETURN f.id as id, f.template_id as template_id, f.severity as severity,
                   f.host as host, f.url as url, f.matched_at as matched_at,
                   collect(c.id) as cve_ids, collect(w.id) as cwe_ids
            """
            
            params = {"template_id": template_id}
            result = await self.neo4j.execute_read(cypher, params)
            
            return result or []
            
        except Exception as e:
            logger.error(f"Query by template failed: {e}")
            return []

    async def get_finding_by_id(self, finding_id: str) -> Optional[Dict]:
        """Get a specific finding by ID.
        
        Args:
            finding_id: UUID of the finding
            
        Returns:
            Finding dictionary or None if not found
        """
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {id: $finding_id})
            OPTIONAL MATCH (f)-[:CORRELATES_TO]->(c:CVE)
            OPTIONAL MATCH (f)-[:CLASSIFIED_AS]->(w:CWE)
            RETURN f.id as id, f.template_id as template_id, f.severity as severity,
                   f.host as host, f.url as url, f.matched_at as matched_at,
                   f.source as source, f.metadata as metadata,
                   collect(c.id) as cve_ids, collect(w.id) as cwe_ids
            """
            
            params = {"finding_id": finding_id}
            result = await self.neo4j.execute_read(cypher, params)
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Get finding by ID failed: {e}")
            return None

    async def delete_findings_by_template(self, template_id: str) -> Dict:
        """Delete findings by template ID.
        
        Args:
            template_id: Nuclei template identifier
            
        Returns:
            Dictionary with deletion statistics
        """
        try:
            cypher = """
            MATCH (f:DiscoveredVulnerability {template_id: $template_id})
            DETACH DELETE f
            RETURN count(f) as deleted_count
            """
            
            params = {"template_id": template_id}
            result = await self.neo4j.execute_write(cypher, params)
            
            logger.info(
                f"Deleted findings by template: {template_id}",
                extra={"deleted_count": result.get("deleted_count", 0)}
            )
            
            return {
                "template_id": template_id,
                "deleted_count": result.get("deleted_count", 0),
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Delete findings failed: {e}")
            return {
                "template_id": template_id,
                "deleted_count": 0,
                "success": False,
                "error": str(e)
            }
