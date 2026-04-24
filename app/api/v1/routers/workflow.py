"""Workflow Router - Pentest orchestration entrypoint."""

from fastapi import APIRouter, HTTPException

from app.domain.schemas.pentest import PentestWorkflowRequest, PentestWorkflowResponse
from app.services.pentest_orchestrator import PentestOrchestratorService

router = APIRouter(prefix="/workflow", tags=["Workflow"])

orchestrator_service = PentestOrchestratorService()


@router.post("/run", response_model=PentestWorkflowResponse)
@router.post("/pentest/run", response_model=PentestWorkflowResponse)
async def run_workflow(request: PentestWorkflowRequest):
    """Run the end-to-end pentest loop over the supplied evidence and query."""
    try:
        return await orchestrator_service.run_pipeline(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow error: {str(e)}")