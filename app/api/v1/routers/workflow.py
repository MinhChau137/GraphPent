"""Workflow Router - Phase 8."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.agents.langgraph.graph import graph

router = APIRouter(prefix="/workflow", tags=["Workflow"])

class WorkflowRequest(BaseModel):
    query: str

@router.post("/run")
async def run_workflow(request: WorkflowRequest):
    """Chạy full multi-agent workflow."""
    try:
        initial_state = {
            "query": request.query,
            "current_step": "start",
            "ingested_documents": [],
            "extracted_chunks": [],
            "graph_context": {},
            "retrieval_results": [],
            "tool_results": [],
            "report_draft": None,
            "human_approval": False,
            "final_answer": None,
            "error": None
        }

        result = await graph.ainvoke(initial_state)
        return {
            "status": "success",
            "final_answer": result.get("final_answer"),
            "retrieval_count": len(result.get("retrieval_results", [])),
            "steps_completed": result.get("current_step")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow error: {str(e)}")