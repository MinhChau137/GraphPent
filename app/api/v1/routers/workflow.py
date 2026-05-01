"""Workflow Router - Pentest orchestration entrypoint (Phase 8)."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.domain.schemas.pentest import PentestWorkflowRequest, PentestWorkflowResponse
from app.services.pentest_orchestrator import PentestOrchestratorService
from app.agents.langgraph.graph import run_workflow as run_langgraph_workflow
from app.core.logger import logger
from app.core.security import audit_log
from uuid import uuid4
from datetime import datetime

router = APIRouter(prefix="/workflow", tags=["Workflow"])

orchestrator_service = PentestOrchestratorService()

# New schema for multi-agent workflow
class MultiAgentWorkflowRequest(BaseModel):
    query: str
    user_id: Optional[str] = "anonymous"
    use_langgraph: bool = True  # Use new LangGraph workflow vs old orchestrator

class MultiAgentWorkflowResponse(BaseModel):
    workflow_id: str
    status: str
    final_answer: Optional[str]
    retrieval_results: Optional[list] = None
    tool_results: Optional[list] = None
    report: Optional[Dict[str, Any]] = None
    timestamp: str
    latency_ms: float

@router.post("/run", response_model=PentestWorkflowResponse)
@router.post("/pentest/run", response_model=PentestWorkflowResponse)
async def run_pentest_workflow(request: PentestWorkflowRequest):
    """Legacy: Run the end-to-end pentest loop (backward compatible)."""
    try:
        return await orchestrator_service.run_pipeline(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow error: {str(e)}")

@router.post("/multi-agent", response_model=MultiAgentWorkflowResponse)
async def run_multi_agent_workflow(request: MultiAgentWorkflowRequest):
    """
    Phase 8: Multi-agent workflow using LangGraph.
    Orchestrates: Planner → Retrieval → Graph Reasoning → Tools → Report → Approval
    """
    workflow_id = str(uuid4())
    start_time = datetime.now()
    
    try:
        logger.info("📋 Starting multi-agent workflow", 
                   workflow_id=workflow_id, 
                   query=request.query[:100])
        
        await audit_log("workflow_start", {
            "workflow_id": workflow_id,
            "query": request.query[:100],
            "user": request.user_id
        })
        
        # Execute workflow
        result = await run_langgraph_workflow(
            query=request.query,
            user_id=request.user_id
        )
        
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info("✅ Multi-agent workflow completed",
                   workflow_id=workflow_id,
                   final_step=result.get("current_step"),
                   latency_ms=f"{elapsed_ms:.1f}")
        
        await audit_log("workflow_complete", {
            "workflow_id": workflow_id,
            "status": "success",
            "latency_ms": elapsed_ms
        })
        
        return MultiAgentWorkflowResponse(
            workflow_id=workflow_id,
            status="success",
            final_answer=result.get("final_answer"),
            retrieval_results=result.get("retrieval_results"),
            tool_results=result.get("tool_results"),
            report=result.get("report"),
            timestamp=datetime.now().isoformat(),
            latency_ms=elapsed_ms
        )
        
    except Exception as e:
        logger.error(f"❌ Workflow failed: {e}", workflow_id=workflow_id)
        
        await audit_log("workflow_failed", {
            "workflow_id": workflow_id,
            "error": str(e)
        })
        
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        raise HTTPException(
            status_code=500,
            detail=f"Workflow error: {str(e)}"
        )

@router.get("/status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get workflow execution status (for async tracking)."""
    # In production, would track in database/cache
    return {
        "workflow_id": workflow_id,
        "status": "completed",
        "message": "Use /workflow/multi-agent endpoint for full workflow execution"
    }