"""Hybrid Retriever Router - Phase 7 Complete."""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
from app.services.retriever_service import HybridRetrieverService
from app.core.logger import logger
from app.core.security import audit_log

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
    mode: str = "hybrid"  # hybrid, vector_only, graph_only
    use_cache: bool = True

class RetrieveResponse(BaseModel):
    results: List[Dict]
    total: int
    mode: str
    alpha: float

class RetrieveModeRequest(BaseModel):
    query: str
    limit: int = 15

@router.post("/query", response_model=RetrieveResponse)
async def hybrid_query(request: RetrieveRequest):
    """
    Hybrid retrieval with 3 modes:
    - hybrid (default): Blend vector & graph (alpha controls weight)
    - vector_only: Pure vector similarity search
    - graph_only: Pure knowledge graph traversal
    """
    try:
        # Validate mode
        if request.mode not in ["hybrid", "vector_only", "graph_only"]:
            raise ValueError(f"Invalid mode: {request.mode}")
        
        # Adjust alpha based on mode
        alpha = request.alpha
        if request.mode == "vector_only":
            alpha = 1.0
        elif request.mode == "graph_only":
            alpha = 0.0
        
        service = get_retriever_service()
        results = await service.hybrid_retrieve(
            query=request.query,
            limit=request.limit,
            alpha=alpha,
            mode=request.mode,
            use_cache=request.use_cache
        )
        
        await audit_log("retrieve_query", {
            "query": request.query[:100],
            "mode": request.mode,
            "results": len(results)
        })
        
        return {
            "results": results,
            "total": len(results),
            "mode": request.mode,
            "alpha": alpha
        }
    except Exception as e:
        logger.error(f"Retrieve error: {e}")
        raise HTTPException(status_code=500, detail=f"Retrieve error: {str(e)}")

@router.post("/vector-only", response_model=RetrieveResponse)
async def vector_only_query(request: RetrieveModeRequest):
    """Pure vector similarity search."""
    try:
        service = get_retriever_service()
        results = await service.hybrid_retrieve(
            query=request.query,
            limit=request.limit,
            alpha=1.0,
            mode="vector_only"
        )
        return {"results": results, "total": len(results), "mode": "vector_only", "alpha": 1.0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/graph-only", response_model=RetrieveResponse)
async def graph_only_query(request: RetrieveModeRequest):
    """Pure graph traversal search."""
    try:
        service = get_retriever_service()
        results = await service.hybrid_retrieve(
            query=request.query,
            limit=request.limit,
            alpha=0.0,
            mode="graph_only"
        )
        return {"results": results, "total": len(results), "mode": "graph_only", "alpha": 0.0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_retrieval_stats(hours: int = Query(24, ge=1, le=720)):
    """Get retrieval performance statistics for dashboard."""
    try:
        service = get_retriever_service()
        stats = await service.get_retrieval_stats(hours=hours)
        return stats
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache-clear")
async def clear_cache():
    """Clear retrieval cache (admin only in production)."""
    try:
        service = get_retriever_service()
        if service._redis_client:
            service._redis_client.delete_pattern("retrieve:*")
            return {"status": "success", "message": "Cache cleared"}
        else:
            return {"status": "warning", "message": "Redis not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))