"""Ingestion router - Phase 4."""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from app.services.ingestion_service import IngestionService
from app.domain.schemas.document import IngestResponse
from app.core.logger import logger

router = APIRouter(prefix="/ingest", tags=["Ingestion"])

ingestion_service = IngestionService()

@router.post("/document", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
):
    """Upload và ingest document."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")

    content = await file.read()

    try:
        result = await ingestion_service.ingest_document(
            file_bytes=content,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
        )
        return result
    except Exception as e:
        logger.error("Ingestion failed", filename=file.filename, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))