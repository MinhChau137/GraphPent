"""Export/Import endpoints (Phase 5.6)."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.services.export_service import get_export_service, ExportService
from app.services.import_service import get_import_service, ImportService
from app.domain.schemas.export_import import (
    ExportJob,
    ExportJobResponse,
    ExportTemplate,
    ExportTemplateResponse,
    SavedSearchCreate,
    SavedSearchResponse,
    ImportJob,
    ImportJobResponse,
    DataIntegrityReport,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Export/Import"])


# ==================== Export Endpoints ====================


@router.post("/exports", response_model=ExportJobResponse, status_code=status.HTTP_201_CREATED)
async def create_export(
    export_config: ExportJob,
    export_service: ExportService = Depends(get_export_service),
):
    """Create export job for scan results.
    
    **Requires**: `results:export` permission
    
    Example:
    ```json
    {
      "name": "Batch Export",
      "source": "batch",
      "source_id": "batch-123",
      "format": "json",
      "include_metadata": true,
      "include_findings": true
    }
    ```
    """
    try:
        # TODO: Get real user_id from auth context
        user_id = "system"

        export_job = await export_service.create_export(export_config, user_id)
        logger.info(f"Export created: {export_job.export_id}")
        return export_job
    except Exception as e:
        logger.error(f"Failed to create export: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create export",
        )


@router.get("/exports/{export_id}", response_model=ExportJobResponse)
async def get_export_status(
    export_id: str,
    export_service: ExportService = Depends(get_export_service),
):
    """Get export job status.
    
    **Requires**: `results:read` permission
    """
    export_job = await export_service.get_export_status(export_id)

    if not export_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export {export_id} not found",
        )

    return export_job


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: str,
    export_service: ExportService = Depends(get_export_service),
):
    """Download exported file.
    
    **Requires**: `results:read` permission
    """
    export_job = await export_service.get_export_status(export_id)

    if not export_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export {export_id} not found",
        )

    if export_job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Export is not ready for download (status: {export_job.status})",
        )

    file_content = await export_service.download_export(export_id)

    return {
        "filename": f"{export_job.name}.{export_job.format}",
        "content_type": f"application/{export_job.format}",
        "content": file_content,
        "size_bytes": export_job.file_size_bytes,
    }


@router.get("/exports", response_model=List[ExportJobResponse])
async def list_exports(
    limit: int = Query(20, ge=1, le=100),
    export_service: ExportService = Depends(get_export_service),
):
    """List export jobs.
    
    **Requires**: `results:read` permission
    """
    # TODO: Get real user_id from auth context
    user_id = "system"

    exports = await export_service.list_exports(user_id, limit)
    return exports


# ==================== Saved Searches ====================


@router.post("/saved-searches", response_model=SavedSearchResponse, status_code=status.HTTP_201_CREATED)
async def create_saved_search(
    search_data: SavedSearchCreate,
    export_service: ExportService = Depends(get_export_service),
):
    """Create and save search query.
    
    **Requires**: `search:basic` permission
    
    Example:
    ```json
    {
      "name": "Critical CVEs",
      "query": "CRITICAL AND (CVE OR vulnerability)",
      "filters": {"severity": "CRITICAL"},
      "is_public": false
    }
    ```
    """
    try:
        # TODO: Get real user_id from auth context
        user_id = "system"

        saved_search = await export_service.create_saved_search(search_data, user_id)
        logger.info(f"Saved search created: {saved_search.search_id}")
        return saved_search
    except Exception as e:
        logger.error(f"Failed to create saved search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create saved search",
        )


@router.get("/saved-searches/{search_id}", response_model=SavedSearchResponse)
async def get_saved_search(
    search_id: str,
    export_service: ExportService = Depends(get_export_service),
):
    """Get saved search details."""
    saved_search = await export_service.get_saved_search(search_id)

    if not saved_search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved search {search_id} not found",
        )

    return saved_search


@router.get("/saved-searches", response_model=List[SavedSearchResponse])
async def list_saved_searches(
    include_public: bool = True,
    export_service: ExportService = Depends(get_export_service),
):
    """List saved searches.
    
    **Requires**: `search:basic` permission
    """
    # TODO: Get real user_id from auth context
    user_id = "system"

    searches = await export_service.list_saved_searches(user_id, include_public)
    return searches


@router.delete("/saved-searches/{search_id}")
async def delete_saved_search(
    search_id: str,
    export_service: ExportService = Depends(get_export_service),
):
    """Delete saved search."""
    deleted = await export_service.delete_saved_search(search_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved search {search_id} not found",
        )

    return {"message": f"Saved search {search_id} deleted"}


# ==================== Export Templates ====================


@router.post("/export-templates", response_model=ExportTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_export_template(
    template_data: ExportTemplate,
    export_service: ExportService = Depends(get_export_service),
):
    """Create reusable export template.
    
    **Requires**: `results:export` permission
    """
    template = await export_service.create_export_template(template_data)
    return template


@router.get("/export-templates/{template_id}", response_model=ExportTemplateResponse)
async def get_export_template(
    template_id: str,
    export_service: ExportService = Depends(get_export_service),
):
    """Get export template details."""
    template = await export_service.get_export_template(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export template {template_id} not found",
        )

    return template


@router.get("/export-templates", response_model=List[ExportTemplateResponse])
async def list_export_templates(
    export_service: ExportService = Depends(get_export_service),
):
    """List export templates."""
    templates = await export_service.list_export_templates()
    return templates


@router.delete("/export-templates/{template_id}")
async def delete_export_template(
    template_id: str,
    export_service: ExportService = Depends(get_export_service),
):
    """Delete export template."""
    deleted = await export_service.delete_export_template(template_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export template {template_id} not found",
        )

    return {"message": f"Export template {template_id} deleted"}


# ==================== Import Endpoints ====================


@router.post("/imports", response_model=ImportJobResponse, status_code=status.HTTP_201_CREATED)
async def create_import_job(
    import_config: ImportJob,
    import_service: ImportService = Depends(get_import_service),
):
    """Create import job for external data.
    
    **Requires**: `results:import` permission
    
    Example:
    ```json
    {
      "job_name": "Import from CVSS DB",
      "source": {
        "source_type": "file",
        "source_location": "/uploads/findings.json",
        "format": "json"
      },
      "merge_mode": "merge",
      "validate_data": true
    }
    ```
    """
    try:
        # TODO: Get real user_id from auth context
        user_id = "system"

        import_job = await import_service.create_import_job(import_config, user_id)
        logger.info(f"Import job created: {import_job.import_id}")
        return import_job
    except Exception as e:
        logger.error(f"Failed to create import job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create import job",
        )


@router.get("/imports/{import_id}", response_model=ImportJobResponse)
async def get_import_status(
    import_id: str,
    import_service: ImportService = Depends(get_import_service),
):
    """Get import job status.
    
    **Requires**: `results:read` permission
    """
    import_job = await import_service.get_import_status(import_id)

    if not import_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import job {import_id} not found",
        )

    return import_job


@router.get("/imports", response_model=List[ImportJobResponse])
async def list_imports(
    limit: int = Query(20, ge=1, le=100),
    import_service: ImportService = Depends(get_import_service),
):
    """List import jobs.
    
    **Requires**: `results:read` permission
    """
    # TODO: Get real user_id from auth context
    user_id = "system"

    imports = await import_service.list_imports(user_id, limit)
    return imports


# ==================== Data Integrity ====================


@router.post("/data-integrity/check", response_model=DataIntegrityReport)
async def check_data_integrity(
    import_service: ImportService = Depends(get_import_service),
):
    """Check data integrity and consistency.
    
    **Requires**: `results:read` permission
    """
    report = await import_service.check_data_integrity()
    return report


# ==================== Health Check ====================


@router.get("/export-import/health")
async def export_import_health_check():
    """Check export/import service health."""
    return {
        "status": "healthy",
        "service": "export-import",
        "version": "5.6.0",
    }
