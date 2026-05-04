"""Workflow Router - Phase 8 + Phase 10-13 (complete)."""

import json
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.langgraph.graph import run_workflow as run_langgraph_workflow
from app.core.logger import logger
from app.core.security import audit_log
from app.domain.schemas.pentest import PentestWorkflowRequest, PentestWorkflowResponse
from app.services.pentest_orchestrator import PentestOrchestratorService

router = APIRouter(prefix="/workflow", tags=["Workflow"])

orchestrator_service = PentestOrchestratorService()

# ---------------------------------------------------------------- Redis status store

def _get_redis():
    """Lazy-import redis to avoid import errors when Redis is down."""
    try:
        import redis.asyncio as aioredis
        from app.config.settings import settings
        return aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        return None


async def _store_status(workflow_id: str, payload: Dict) -> None:
    r = _get_redis()
    if r:
        try:
            await r.set(f"workflow:{workflow_id}", json.dumps(payload), ex=3600)
        except Exception:
            pass
        finally:
            await r.aclose()


async def _load_status(workflow_id: str) -> Optional[Dict]:
    r = _get_redis()
    if not r:
        return None
    try:
        raw = await r.get(f"workflow:{workflow_id}")
        return json.loads(raw) if raw else None
    except Exception:
        return None
    finally:
        await r.aclose()


# ---------------------------------------------------------------- schemas

class MultiAgentWorkflowRequest(BaseModel):
    query: str
    user_id: Optional[str] = "anonymous"
    scan_target: Optional[str] = None          # Phase 10: Nmap target
    max_loop_iterations: int = 3               # Phase 10: feedback loop cap
    use_langgraph: bool = True


class MultiAgentWorkflowResponse(BaseModel):
    workflow_id: str
    status: str
    final_answer: Optional[str] = None
    retrieval_results: Optional[list] = None
    tool_results: Optional[list] = None
    report: Optional[Dict[str, Any]] = None
    collection_summary: Optional[Dict[str, Any]] = None
    loop_iterations: int = 0
    timestamp: str
    latency_ms: float


# ---------------------------------------------------------------- endpoints

@router.post("/run", response_model=PentestWorkflowResponse)
@router.post("/pentest/run", response_model=PentestWorkflowResponse)
async def run_pentest_workflow(request: PentestWorkflowRequest):
    """Legacy: Run the end-to-end pentest loop (backward compatible)."""
    try:
        return await orchestrator_service.run_pipeline(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Workflow error: {str(exc)}")


@router.post("/multi-agent", response_model=MultiAgentWorkflowResponse)
async def run_multi_agent_workflow(request: MultiAgentWorkflowRequest):
    """
    Phase 8 + 10-13: Multi-agent workflow with collection + feedback loop.

    Flow:
      collection_node (Nmap, optional) →
      planner (risk-aware, Phase 13) →
      retrieval → graph_reasoning →
      tool (Nuclei) → report → human_approval →
      [feedback loop if new findings]
    """
    workflow_id = str(uuid4())
    start_time = datetime.now()

    await _store_status(workflow_id, {
        "workflow_id": workflow_id,
        "status": "running",
        "query": request.query[:100],
        "scan_target": request.scan_target,
        "started_at": start_time.isoformat(),
    })

    try:
        logger.info("Starting multi-agent workflow",
                    workflow_id=workflow_id,
                    query=request.query[:100],
                    scan_target=request.scan_target)

        await audit_log("workflow_start", {
            "workflow_id": workflow_id,
            "query": request.query[:100],
            "user": request.user_id,
            "scan_target": request.scan_target,
        })

        result = await run_langgraph_workflow(
            query=request.query,
            user_id=request.user_id,
            scan_target=request.scan_target,
            max_loop_iterations=request.max_loop_iterations,
        )

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        loop_iters = result.get("loop_iteration", 0)

        collection_summary = None
        col_results = result.get("collection_results", [])
        if col_results:
            collection_summary = col_results[0]

        await _store_status(workflow_id, {
            "workflow_id": workflow_id,
            "status": "success",
            "loop_iterations": loop_iters,
            "completed_at": datetime.now().isoformat(),
            "latency_ms": elapsed_ms,
        })

        logger.info("Workflow completed",
                    workflow_id=workflow_id,
                    iterations=loop_iters,
                    latency_ms=f"{elapsed_ms:.0f}")

        await audit_log("workflow_complete", {
            "workflow_id": workflow_id,
            "status": "success",
            "latency_ms": elapsed_ms,
            "loop_iterations": loop_iters,
        })

        return MultiAgentWorkflowResponse(
            workflow_id=workflow_id,
            status="success",
            final_answer=result.get("final_answer"),
            retrieval_results=result.get("retrieval_results"),
            tool_results=result.get("tool_results"),
            report=result.get("report"),
            collection_summary=collection_summary,
            loop_iterations=loop_iters,
            timestamp=datetime.now().isoformat(),
            latency_ms=elapsed_ms,
        )

    except Exception as exc:
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        logger.error(f"Workflow failed: {exc}", workflow_id=workflow_id)

        await _store_status(workflow_id, {
            "workflow_id": workflow_id,
            "status": "failed",
            "error": str(exc),
            "completed_at": datetime.now().isoformat(),
        })
        await audit_log("workflow_failed", {"workflow_id": workflow_id, "error": str(exc)})

        raise HTTPException(status_code=500, detail=f"Workflow error: {str(exc)}")


@router.get("/status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """
    Get execution status for a previously launched workflow.
    Status is stored in Redis for up to 1 hour after completion.
    """
    status = await _load_status(workflow_id)
    if status:
        return status
    return {
        "workflow_id": workflow_id,
        "status": "not_found",
        "message": "Workflow not found or expired (>1h). Launch via POST /workflow/multi-agent.",
    }
