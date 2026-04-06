"""Hybrid Retriever Router - Phase 7."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from app.services.retriever_service import HybridRetrieverService

router = APIRouter(prefix="/retrieve", tags=["Retriever"])

retriever_service = HybridRetrieverService()

class RetrieveRequest(BaseModel):
    query: str
    limit: int = 15
    alpha: float = 0.7

class RetrieveResponse(BaseModel):
    results: List[Dict]
    total: int

@router.post("/query", response_model=RetrieveResponse)
async def hybrid_query(request: RetrieveRequest):
    """Hybrid retrieval (Vector + Graph + Fusion)."""
    try:
        results = await retriever_service.hybrid_retrieve(
            query=request.query,
            limit=request.limit,
            alpha=request.alpha
        )
        return {"results": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieve error: {str(e)}")