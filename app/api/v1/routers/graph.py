"""Graph router - Phase 6."""

from fastapi import APIRouter, HTTPException, status
from app.services.graph_service import GraphService
from app.domain.schemas.extraction import ExtractionResult

router = APIRouter(prefix="/graph", tags=["Graph"])

graph_service = GraphService()

@router.post("/upsert")
async def upsert_from_extraction(extraction_result: ExtractionResult):
    """Upsert entities & relations từ extraction result."""
    try:
        result = await graph_service.process_extraction_result(extraction_result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_graph_stats():
    """Thống kê đơn giản Neo4j."""
    # TODO: Triển khai query count nodes/relations ở phase sau
    return {"message": "Graph stats endpoint - sẽ triển khai chi tiết ở Phase 7"}