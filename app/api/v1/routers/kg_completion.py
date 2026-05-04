"""KG Completion Router - Phase 11: LLM-based relation prediction & conflict detection."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from app.services.kg_completion_service import KGCompletionService
from app.core.security import audit_log
from app.core.logger import logger

router = APIRouter(prefix="/kg", tags=["KG Completion (Phase 11)"])

kg_service = KGCompletionService()


class CompletionRequest(BaseModel):
    max_entities: int = 10
    max_degree: int = 2


class CompletionResponse(BaseModel):
    entities_processed: int
    relations_predicted: int
    relations_stored: int


class ConflictRequest(BaseModel):
    entity_ids: Optional[List[str]] = None
    limit: int = 20


@router.post("/complete", response_model=CompletionResponse)
async def complete_graph(request: CompletionRequest):
    """
    Phase 11.1: Run KG Completion pass.
    Finds low-degree entities and uses the LLM to predict missing relationships.
    Predicted relations are stored in Neo4j with inferred=True flag.
    """
    try:
        result = await kg_service.complete_graph(
            max_entities=request.max_entities,
            max_degree=request.max_degree,
        )
        await audit_log("kg_complete_endpoint", result)
        return result
    except Exception as exc:
        logger.error(f"KG completion failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/conflicts")
async def detect_conflicts(request: ConflictRequest):
    """
    Phase 11.2: Detect contradictory or suspicious relations in the graph.
    Returns a list of conflict reports. Empty array means no conflicts found.
    """
    try:
        conflicts = await kg_service.detect_conflicts(
            entity_ids=request.entity_ids,
            limit=request.limit,
        )
        await audit_log("kg_conflict_endpoint", {"conflicts_found": len(conflicts)})
        return {"conflicts": conflicts, "total": len(conflicts)}
    except Exception as exc:
        logger.error(f"Conflict detection failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def kg_health():
    return {"status": "healthy", "version": "Phase 11"}
