"""Collection Router - Phase 10: Nmap scan → Knowledge Graph ingestion."""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional

from app.services.collection_service import CollectionService
from app.agents.langgraph.graph import run_workflow
from app.core.security import audit_log
from app.core.logger import logger

router = APIRouter(prefix="/collect", tags=["Data Collection (Phase 10)"])

collection_service = CollectionService()

# ------------------------------------------------------------------ schemas

class NmapScanRequest(BaseModel):
    target: str
    nmap_options: Optional[List[str]] = None

class NmapScanResponse(BaseModel):
    target: str
    hosts: int
    open_ports: int
    services: int
    relations: int
    entities_upserted: int
    relations_created: int
    new_findings_count: int
    host_ips: List[str]
    service_names: List[str]

class CollectAndAnalyzeRequest(BaseModel):
    target: str
    query: str = "Analyze discovered hosts and services for vulnerabilities"
    nmap_options: Optional[List[str]] = None
    max_loop_iterations: int = 3
    user_id: str = "anonymous"

# ------------------------------------------------------------------ endpoints

@router.post("/nmap/scan", response_model=NmapScanResponse)
async def nmap_scan(request: NmapScanRequest):
    """
    Phase 10.1: Run Nmap scan and store results in the Knowledge Graph.
    Returns a summary of discovered hosts, ports, services, and graph facts created.
    Target must be in ALLOWED_TARGETS.
    """
    try:
        result = await collection_service.collect_and_store(
            target=request.target,
            nmap_options=request.nmap_options,
        )
        await audit_log("nmap_scan_endpoint", {
            "target": request.target,
            "entities": result.get("entities_upserted", 0),
        })
        return result
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(f"Nmap scan failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/nmap/upload-xml", response_model=NmapScanResponse)
async def upload_nmap_xml(file: UploadFile = File(...)):
    """
    Phase 10.1b: Upload an existing Nmap XML file and ingest into the Knowledge Graph.
    Useful when Nmap was run externally or on a different machine.
    """
    try:
        xml_data = (await file.read()).decode("utf-8")
        result = await collection_service.collect_from_xml_string(
            xml_data=xml_data,
            label=file.filename or "upload",
        )
        await audit_log("nmap_upload_endpoint", {
            "filename": file.filename,
            "entities": result.get("entities_upserted", 0),
        })
        return result
    except Exception as exc:
        logger.error(f"Nmap XML upload failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/nmap/scan-and-analyze")
async def scan_and_analyze(request: CollectAndAnalyzeRequest):
    """
    Phase 10.2: Full pipeline — Nmap scan → KG ingest → multi-agent analysis with feedback loop.
    Triggers the LangGraph workflow with collection_node active.
    The workflow will loop up to max_loop_iterations times when new findings are discovered.
    """
    try:
        final_state = await run_workflow(
            query=request.query,
            user_id=request.user_id,
            scan_target=request.target,
            max_loop_iterations=request.max_loop_iterations,
        )
        await audit_log("scan_and_analyze_endpoint", {
            "target": request.target,
            "total_iterations": final_state.get("loop_iteration", 0),
        })
        return {
            "target": request.target,
            "query": request.query,
            "total_iterations": final_state.get("loop_iteration", 0),
            "collection_summary": final_state.get("collection_results", [{}])[0] if final_state.get("collection_results") else {},
            "report_markdown": final_state.get("report_markdown"),
            "final_answer": final_state.get("final_answer"),
            "error": final_state.get("error"),
        }
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error(f"Scan-and-analyze failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def collection_health():
    """Health check for the collection service."""
    return {
        "status": "healthy",
        "services": {
            "nmap": "available_via_subprocess",
            "neo4j": "connected",
        },
        "version": "Phase 10",
    }
