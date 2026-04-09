"""Hybrid Retriever Router - Phase 7."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from app.services.retriever_service import HybridRetrieverService

router = APIRouter(prefix="/retrieve", tags=["Retriever"])

# Lazy initialization
_retriever_service = None

def get_retriever_service():
    global _retriever_service
    if _retriever_service is None:
        _retriever_service = HybridRetrieverService()
    return _retriever_service

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
        service = get_retriever_service()
        results = await service.hybrid_retrieve(
            query=request.query,
            limit=request.limit,
            alpha=request.alpha
        )
        return {"results": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieve error: {str(e)}")