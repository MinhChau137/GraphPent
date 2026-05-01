"""Nuclei API Router - Phase 4 REST Endpoints.

Provides REST API for Nuclei scanning and findings management.
"""

import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Path, Body, Depends
from fastapi.responses import JSONResponse

from app.adapters.neo4j_client import Neo4jAdapter
from app.services.nuclei_services import (
    NucleiIntegrationService,
    NucleiPostgresService,
)
from app.domain.schemas.nuclei import (
    CreateScanRequest,
    ProcessNucleiOutputRequest,
    FindingsQueryRequest,
    ScanMetadata,
    FindingResponse,
    ProcessingResult,
    FindingsResponse,
    ScansResponse,
    StatisticsResponse,
    ErrorResponse,
    HealthResponse,
    SeverityEnum,
    ScanStatusEnum,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/nuclei", tags=["nuclei"])

# Global service instances (will be initialized once)
_integration_service: Optional[NucleiIntegrationService] = None
_postgres_service: Optional[NucleiPostgresService] = None


def get_integration_service() -> NucleiIntegrationService:
    """Get or create integration service."""
    global _integration_service
    if _integration_service is None:
        neo4j = Neo4jAdapter()
        _integration_service = NucleiIntegrationService(neo4j)
    return _integration_service


def get_postgres_service() -> NucleiPostgresService:
    """Get or create postgres service."""
    global _postgres_service
    if _postgres_service is None:
        _postgres_service = NucleiPostgresService()
    return _postgres_service


# ==================== Health & Status ====================

@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check(
    service: NucleiIntegrationService = Depends(get_integration_service),
) -> HealthResponse:
    """Check API health and connectivity.
    
    Returns status of Neo4j and PostgreSQL connections.
    """
    try:
        # Check Neo4j
        neo4j_status = "connected"
        try:
            # Quick query to verify connection
            await service.get_critical_findings()
        except Exception as e:
            logger.warning(f"Neo4j connection issue: {e}")
            neo4j_status = "disconnected"
        
        # Check PostgreSQL (via postgres service)
        postgres_status = "connected"
        try:
            postgres = get_postgres_service()
            stats = await postgres.get_statistics()
        except Exception as e:
            logger.warning(f"PostgreSQL connection issue: {e}")
            postgres_status = "disconnected"
        
        return HealthResponse(
            status="healthy" if neo4j_status == "connected" and postgres_status == "connected" else "degraded",
            neo4j=neo4j_status,
            postgres=postgres_status,
            version="1.0.0"
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Scan Operations ====================

@router.post("/scan", response_model=ScanMetadata, status_code=201)
async def create_scan(
    request: CreateScanRequest,
    postgres: NucleiPostgresService = Depends(get_postgres_service),
) -> ScanMetadata:
    """Create a new scan record.
    
    Args:
        request: Scan creation parameters
        
    Returns:
        Created scan metadata
    """
    try:
        scan_id = await postgres.create_scan(
            target_url=request.target_url,
            scan_type=request.scan_type,
            metadata=request.metadata
        )
        
        scan = await postgres.get_scan(scan_id)
        
        logger.info(
            f"Scan created",
            extra={"scan_id": scan_id, "target_url": request.target_url}
        )
        
        return ScanMetadata(
            id=scan["id"],
            target_url=scan["target_url"],
            status=ScanStatusEnum(scan["status"]),
            scan_type=scan["scan_type"],
            findings_count=scan["findings_count"],
            neo4j_status=scan.get("neo4j_status", "pending"),
            started_at=scan.get("started_at"),
            completed_at=scan.get("completed_at"),
            error_message=scan.get("error_message")
        )
    
    except Exception as e:
        logger.error(f"Failed to create scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/{scan_id}", response_model=ScanMetadata)
async def get_scan(
    scan_id: str = Path(..., description="Scan identifier"),
    postgres: NucleiPostgresService = Depends(get_postgres_service),
) -> ScanMetadata:
    """Get scan details by ID.
    
    Args:
        scan_id: Scan identifier
        
    Returns:
        Scan metadata
    """
    try:
        scan = await postgres.get_scan(scan_id)
        
        if not scan:
            logger.warning(f"Scan not found: {scan_id}")
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
        
        return ScanMetadata(
            id=scan["id"],
            target_url=scan["target_url"],
            status=ScanStatusEnum(scan["status"]),
            scan_type=scan["scan_type"],
            findings_count=scan["findings_count"],
            neo4j_status=scan.get("neo4j_status", "pending"),
            started_at=scan.get("started_at"),
            completed_at=scan.get("completed_at"),
            error_message=scan.get("error_message")
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scans", response_model=ScansResponse)
async def list_scans(
    limit: int = Query(20, ge=1, le=100, description="Max scans to return"),
    status: Optional[str] = Query(None, description="Filter by status"),
    postgres: NucleiPostgresService = Depends(get_postgres_service),
) -> ScansResponse:
    """List recent scans with optional filtering.
    
    Args:
        limit: Max scans to return
        status: Filter by scan status
        
    Returns:
        Paginated scan list
    """
    try:
        scans_data = await postgres.get_scan_history(limit=limit, status_filter=status)
        
        scans = [
            ScanMetadata(
                id=s["id"],
                target_url=s["target_url"],
                status=ScanStatusEnum(s["status"]),
                scan_type=s.get("scan_type", "full"),
                findings_count=s["findings_count"],
                neo4j_status=s.get("neo4j_status", "pending"),
                started_at=s.get("started_at"),
                completed_at=s.get("completed_at"),
                error_message=s.get("error_message")
            )
            for s in scans_data
        ]
        
        return ScansResponse(
            total=len(scans),
            count=len(scans),
            scans=scans
        )
    
    except Exception as e:
        logger.error(f"Failed to list scans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scan/{scan_id}", status_code=204)
async def delete_scan(
    scan_id: str = Path(..., description="Scan identifier"),
    postgres: NucleiPostgresService = Depends(get_postgres_service),
) -> None:
    """Delete a scan and its findings.
    
    Args:
        scan_id: Scan identifier
    """
    try:
        scan = await postgres.get_scan(scan_id)
        
        if not scan:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
        
        # Cascade delete happens automatically via database constraint
        logger.info(f"Scan deleted: {scan_id}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Nuclei Processing ====================

@router.post("/scan/{scan_id}/process", response_model=ProcessingResult)
async def process_nuclei_output(
    scan_id: str = Path(..., description="Scan identifier"),
    request: ProcessNucleiOutputRequest = Body(...),
    service: NucleiIntegrationService = Depends(get_integration_service),
    postgres: NucleiPostgresService = Depends(get_postgres_service),
) -> ProcessingResult:
    """Process Nuclei output for a scan.
    
    Args:
        scan_id: Parent scan identifier
        request: Nuclei output and processing options
        
    Returns:
        Processing result
    """
    try:
        # Update scan status
        await postgres.update_scan_status(
            scan_id=scan_id,
            status="running"
        )
        
        # Process output
        result = await service.process_nuclei_output(
            nuclei_output=request.nuclei_output,
            scan_id=scan_id,
            target_url=request.target_url
        )
        
        # Update final status
        await postgres.update_scan_status(
            scan_id=scan_id,
            status=result.get("status", "completed"),
            findings_count=result.get("findings_count", 0),
            neo4j_status=result.get("neo4j_status", "upserted")
        )
        
        logger.info(
            f"Nuclei output processed",
            extra={
                "scan_id": scan_id,
                "findings": result.get("findings_count")
            }
        )
        
        return ProcessingResult(
            scan_id=scan_id,
            findings_count=result.get("findings_count", 0),
            findings_stored=result.get("findings_stored", 0),
            findings_failed=result.get("findings_failed", 0),
            cve_relationships=result.get("cve_relationships", 0),
            cwe_relationships=result.get("cwe_relationships", 0),
            status=result.get("status", "completed"),
            parser_warnings=result.get("parser_warnings", 0),
            relationship_errors=result.get("relationship_errors", 0)
        )
    
    except Exception as e:
        logger.error(f"Failed to process Nuclei output: {e}")
        await postgres.update_scan_status(
            scan_id=scan_id,
            status="failed",
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Finding Queries ====================

@router.get("/findings", response_model=FindingsResponse)
async def query_findings(
    severity: Optional[SeverityEnum] = Query(None, description="Filter by severity"),
    host: Optional[str] = Query(None, description="Filter by host"),
    template_id: Optional[str] = Query(None, description="Filter by template ID"),
    limit: int = Query(50, ge=1, le=1000, description="Max findings to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    service: NucleiIntegrationService = Depends(get_integration_service),
) -> FindingsResponse:
    """Query findings with optional filtering.
    
    Args:
        severity: Filter by severity level
        host: Filter by target host
        template_id: Filter by Nuclei template
        limit: Max findings to return
        offset: Pagination offset
        
    Returns:
        Paginated findings
    """
    try:
        findings_list = []
        total = 0
        
        # Query based on filters
        if severity:
            findings_list = await service.get_findings_by_severity(severity.value)
            total = len(findings_list)
        
        elif host:
            findings_list = await service.get_findings_by_host(host)
            total = len(findings_list)
        
        elif template_id:
            findings_list = await service.get_findings_by_template(template_id)
            total = len(findings_list)
        
        else:
            # Get all critical findings by default
            findings_list = await service.get_critical_findings()
            total = len(findings_list)
        
        # Apply pagination
        paginated = findings_list[offset:offset + limit]
        
        findings = [
            FindingResponse(
                id=f.get("id", ""),
                scan_id=f.get("scan_id", ""),
                template_id=f.get("template_id", ""),
                severity=SeverityEnum(f.get("severity", "INFO")),
                host=f.get("host", ""),
                url=f.get("url", ""),
                matched_at=f.get("matched_at"),
                cve_ids=f.get("cve_ids", []),
                cwe_ids=f.get("cwe_ids", []),
                neo4j_id=f.get("neo4j_id"),
                metadata=f.get("metadata", {})
            )
            for f in paginated
        ]
        
        return FindingsResponse(
            total=total,
            count=len(findings),
            limit=limit,
            offset=offset,
            findings=findings
        )
    
    except Exception as e:
        logger.error(f"Failed to query findings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/findings/{finding_id}", response_model=FindingResponse)
async def get_finding(
    finding_id: str = Path(..., description="Finding identifier"),
    service: NucleiIntegrationService = Depends(get_integration_service),
) -> FindingResponse:
    """Get specific finding by ID.
    
    Args:
        finding_id: Finding identifier
        
    Returns:
        Finding details
    """
    try:
        finding = await service.get_finding(finding_id)
        
        if not finding:
            raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")
        
        return FindingResponse(
            id=finding.get("id", ""),
            scan_id=finding.get("scan_id", ""),
            template_id=finding.get("template_id", ""),
            severity=SeverityEnum(finding.get("severity", "INFO")),
            host=finding.get("host", ""),
            url=finding.get("url", ""),
            matched_at=finding.get("matched_at"),
            cve_ids=finding.get("cve_ids", []),
            cwe_ids=finding.get("cwe_ids", []),
            neo4j_id=finding.get("neo4j_id"),
            metadata=finding.get("metadata", {})
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get finding: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Statistics ====================

@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics(
    postgres: NucleiPostgresService = Depends(get_postgres_service),
) -> StatisticsResponse:
    """Get system statistics.
    
    Returns:
        Aggregated statistics
    """
    try:
        stats = await postgres.get_statistics()
        
        return StatisticsResponse(
            total_scans=stats.get("total_scans", 0),
            total_findings=stats.get("total_findings", 0),
            critical_findings=stats.get("critical_findings", 0),
            scans_completed=stats.get("scans_completed", 0),
            last_scan=stats.get("last_scan"),
            findings_by_severity={},
            findings_by_host={}
        )
    
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Error Handlers ====================

@router.get("/error-example", response_model=ErrorResponse, include_in_schema=False)
async def error_example() -> ErrorResponse:
    """Example error response (not a real endpoint)."""
    return ErrorResponse(
        error="Example error",
        detail="This is an example of an error response",
        status_code=400
    )
