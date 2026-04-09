"""Tool Router - CVE-focused (Phase 9)."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.services.tool_service import PentestToolService
from app.core.security import audit_log

router = APIRouter(prefix="/tools", tags=["Pentest Tools (CVE)"])

tool_service = PentestToolService()

class CVEAnalyzeRequest(BaseModel):
    cve_json: dict

class NucleiRequest(BaseModel):
    cve_id: str
    target: str
    templates: list[str] = None

@router.post("/cve/analyze")
async def analyze_cve(request: CVEAnalyzeRequest):
    """Phân tích CVE JSON xem có khai thác được không."""
    result = await tool_service.analyze_cve_exploitable(request.cve_json)
    return result

@router.post("/nuclei/cve")
async def run_nuclei_cve(request: NucleiRequest):
    """Chạy Nuclei scan cho CVE cụ thể (lab only)."""
    try:
        result = await tool_service.run_nuclei_for_cve(
            cve_id=request.cve_id,
            target=request.target,
            templates=request.templates
        )
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))