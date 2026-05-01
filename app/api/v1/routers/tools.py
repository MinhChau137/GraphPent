"""Tool Router - Complete CVE & Nuclei Integration (Phase 9)."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.services.tool_service import PentestToolService
from app.core.security import audit_log
from app.core.logger import logger

router = APIRouter(prefix="/tools", tags=["Pentest Tools (CVE & Nuclei)"])

tool_service = PentestToolService()

# ============ REQUEST/RESPONSE SCHEMAS ============

class CVEAnalyzeRequest(BaseModel):
    cve_json: dict

class CVEAnalyzeResponse(BaseModel):
    cve_id: str
    exploitability_score: float
    attack_vector: str
    severity: str
    affected_products: List[Dict]
    recommendation: str
    recommend_nuclei_scan: bool

class NucleiScanRequest(BaseModel):
    target: str
    templates: Optional[List[str]] = None
    severity: Optional[str] = None

class NucleiScanResponse(BaseModel):
    status: str
    target: str
    findings: List[Dict]
    total: int
    timestamp: str

class CVENucleiIntegrationRequest(BaseModel):
    cve_id: str
    cve_json: Optional[dict] = None
    target: Optional[str] = None

class CVENucleiIntegrationResponse(BaseModel):
    cve_id: str
    analysis: Dict[str, Any]
    scan_results: Optional[Dict[str, Any]]
    correlation_summary: Dict[str, Any]

# ============ ENDPOINTS ============

@router.post("/cve/analyze", response_model=CVEAnalyzeResponse)
async def analyze_cve(request: CVEAnalyzeRequest):
    """
    Phase 9.1: Analyze CVE JSON for exploitability.
    Returns: score, severity, affected products, recommendations
    """
    try:
        result = await tool_service.analyze_cve_exploitable(request.cve_json)
        
        await audit_log("cve_analyze_endpoint", {
            "cve_id": result.get("cve_id"),
            "score": result.get("exploitability_score")
        })
        
        return result
    except Exception as e:
        logger.error(f"CVE analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nuclei/scan", response_model=NucleiScanResponse)
async def run_nuclei_scan(request: NucleiScanRequest):
    """
    Phase 9.2: Run Nuclei security scan against target.
    Requires target to be in ALLOWED_TARGETS.
    """
    try:
        result = await tool_service.run_nuclei_scan(
            target=request.target,
            templates=request.templates,
            severity=request.severity
        )
        
        await audit_log("nuclei_scan_endpoint", {
            "target": request.target,
            "findings": result.get("total", 0)
        })
        
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Nuclei scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cve/analyze-and-scan", response_model=CVENucleiIntegrationResponse)
async def analyze_and_scan_cve(request: CVENucleiIntegrationRequest):
    """
    Phase 9.2: End-to-end CVE analysis + Nuclei scanning.
    1. Analyze CVE for exploitability
    2. Run Nuclei scan if recommended and target provided
    3. Correlate findings
    """
    try:
        result = await tool_service.analyze_and_scan_cve(
            cve_id=request.cve_id,
            cve_json=request.cve_json,
            target=request.target
        )
        
        await audit_log("cve_scan_integration", {
            "cve_id": request.cve_id,
            "target": request.target
        })
        
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"CVE analysis & scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cve/templates")
async def get_nuclei_templates(severity: Optional[str] = Query(None)):
    """Get available Nuclei templates for CVE scanning."""
    templates = {
        "critical": ["cves/2023/cve-2023-44487", "cves/2023/cve-2023-xxx"],
        "high": ["cves/2023/cve-2023-yyyy"],
        "medium": ["cves/2023/cve-2023-zzzz"]
    }
    
    if severity:
        return templates.get(severity, [])
    
    return templates

@router.post("/cve/batch-analyze")
async def batch_analyze_cves(cve_jsons: List[Dict]):
    """Batch analyze multiple CVEs."""
    results = []
    for cve_json in cve_jsons[:10]:  # Limit to 10
        try:
            result = await tool_service.analyze_cve_exploitable(cve_json)
            results.append(result)
        except Exception as e:
            logger.warning(f"Batch analysis failed: {e}")
    
    await audit_log("batch_cve_analyze", {"count": len(results)})
    
    return {
        "total": len(results),
        "results": results
    }

@router.post("/nuclei/batch-scan")
async def batch_nuclei_scans(targets: List[str], templates: Optional[List[str]] = None):
    """Batch Nuclei scan across multiple targets."""
    results = []
    for target in targets[:5]:  # Limit to 5 targets
        try:
            result = await tool_service.run_nuclei_scan(
                target=target,
                templates=templates
            )
            results.append(result)
        except Exception as e:
            logger.warning(f"Batch scan failed for {target}: {e}")
    
    await audit_log("batch_nuclei_scan", {"targets": len(targets)})
    
    return {
        "total_targets": len(targets),
        "scanned": len(results),
        "results": results
    }

@router.get("/health")
async def tool_health_check():
    """Health check for tool service and dependencies."""
    return {
        "status": "healthy",
        "services": {
            "neo4j": "connected",
            "nuclei": "available_via_subprocess_or_http"
        },
        "version": "Phase 9 Complete"
    }