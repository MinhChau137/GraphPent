"""Extraction router - Phase 5."""

from fastapi import APIRouter, HTTPException, status
from app.services.extraction_service import ExtractionService
from app.domain.schemas.extraction import ExtractionResult

router = APIRouter(prefix="/extract", tags=["Extraction"])

extraction_service = ExtractionService()

@router.post("/chunk/{chunk_id}", response_model=ExtractionResult)
async def extract_chunk(chunk_id: int):
    """Trigger extraction cho một chunk cụ thể."""
    try:
        result = await extraction_service.extract_from_chunk(chunk_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction error: {str(e)}")