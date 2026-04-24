"""API endpoints for batch data ingestion operations."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict
import asyncio

from app.core.logger import logger
from app.services.ingestion_service import IngestionService
from app.utils.batch_loader import BatchDataLoader, get_data_statistics


router = APIRouter(prefix="/api/v1/batch", tags=["batch_operations"])

ingestion_service = IngestionService()
batch_loader = BatchDataLoader()


@router.get("/stats", response_model=Dict)
async def get_batch_stats():
    """Get statistics about available data for batch operations.
    
    Returns:
        - cwe_xml: CWE XML file info
        - nvd_cve_json: NVD CVE JSON file info
        - cve_v5_files_count: Number of CVE v5 files
        - cve_delta: Delta changes info
    """
    try:
        stats = await get_data_statistics()
        return {
            "status": "success",
            "data": stats
        }
    except Exception as e:
        logger.error("Failed to get batch stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/cwe")
async def ingest_cwe_batch():
    """Ingest CWE XML data.
    
    Returns:
        - document_id
        - chunks_count
        - status
    """
    try:
        logger.info("Starting CWE XML batch ingestion via API")
        cwe_data = await batch_loader.load_cwe_xml()
        
        if not cwe_data:
            raise HTTPException(status_code=404, detail="CWE XML file not found")
        
        result = await ingestion_service.ingest_document(
            file_bytes=cwe_data["data"],
            filename=cwe_data["filename"],
            content_type=cwe_data["content_type"],
            metadata={
                "source": "cwe_xml",
                "data_type": "cwe",
                "batch_import": True,
                "import_method": "api"
            }
        )
        
        logger.info("CWE XML batch ingestion completed", **result)
        return {"status": "success", "data": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("CWE batch ingestion failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/nvd")
async def ingest_nvd_batch():
    """Ingest NVD CVE JSON data.
    
    Returns:
        - document_id
        - chunks_count
        - status
    """
    try:
        logger.info("Starting NVD CVE JSON batch ingestion via API")
        nvd_data = await batch_loader.load_nvd_cve_json()
        
        if not nvd_data:
            raise HTTPException(status_code=404, detail="NVD CVE JSON file not found")
        
        result = await ingestion_service.ingest_document(
            file_bytes=nvd_data["data"],
            filename=nvd_data["filename"],
            content_type=nvd_data["content_type"],
            metadata={
                "source": "nvd_cve_json",
                "data_type": "cve",
                "batch_import": True,
                "import_method": "api"
            }
        )
        
        logger.info("NVD CVE JSON batch ingestion completed", **result)
        return {"status": "success", "data": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("NVD batch ingestion failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/cve-v5")
async def ingest_cve_v5_batch(limit: Optional[int] = Query(None, description="Limit number of files to ingest")):
    """Ingest CVE v5 JSON files.
    
    Query Parameters:
        - limit: Maximum number of files to ingest
    
    Returns:
        - total_files: Total files processed
        - successful: Successfully ingested
        - failed: Failed ingestions
        - errors: Error messages
    """
    try:
        logger.info("Starting CVE v5 batch ingestion via API", limit=limit)
        
        stats = {
            "total_files": 0,
            "successful": 0,
            "failed": 0,
            "errors": []
        }
        
        count = 0
        async for file_data in batch_loader.load_cve_v5_files():
            if limit and count >= limit:
                logger.info(f"Reached ingestion limit: {limit}")
                break
            
            count += 1
            stats["total_files"] += 1
            
            try:
                result = await ingestion_service.ingest_document(
                    file_bytes=file_data["data"],
                    filename=file_data["filename"],
                    content_type=file_data["content_type"],
                    metadata={
                        "source": "cve_v5_json",
                        "data_type": "cve",
                        "filepath": file_data.get("filepath"),
                        "batch_import": True,
                        "import_method": "api"
                    }
                )
                
                if result.get("status") == "success":
                    stats["successful"] += 1
                else:
                    stats["failed"] += 1
                    
            except Exception as e:
                stats["failed"] += 1
                error_msg = f"{file_data['filename']}: {str(e)}"
                stats["errors"].append(error_msg)
                logger.error(f"Failed to ingest CVE file", filename=file_data["filename"], error=str(e))
        
        logger.info("CVE v5 batch ingestion completed", **stats)
        return {"status": "success", "data": stats}
        
    except Exception as e:
        logger.error("CVE v5 batch ingestion failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/all")
async def ingest_all_batch(limit_cve_v5: Optional[int] = Query(None, description="Limit CVE v5 files")):
    """Ingest all available data (CWE + NVD + CVE v5).
    
    Query Parameters:
        - limit_cve_v5: Maximum CVE v5 files to ingest
    
    Returns:
        - cwe: CWE ingestion result
        - nvd: NVD ingestion result
        - cve_v5: CVE v5 ingestion result
    """
    try:
        logger.info("Starting full batch ingestion via API", limit_cve_v5=limit_cve_v5)
        
        results = {
            "cwe": None,
            "nvd": None,
            "cve_v5": None
        }
        
        # CWE
        try:
            cwe_data = await batch_loader.load_cwe_xml()
            if cwe_data:
                result = await ingestion_service.ingest_document(
                    file_bytes=cwe_data["data"],
                    filename=cwe_data["filename"],
                    content_type=cwe_data["content_type"],
                    metadata={
                        "source": "cwe_xml",
                        "data_type": "cwe",
                        "batch_import": True,
                        "import_method": "api"
                    }
                )
                results["cwe"] = result
        except Exception as e:
            logger.error("CWE batch ingestion failed", error=str(e))
            results["cwe"] = {"status": "failed", "error": str(e)}
        
        # NVD
        try:
            nvd_data = await batch_loader.load_nvd_cve_json()
            if nvd_data:
                result = await ingestion_service.ingest_document(
                    file_bytes=nvd_data["data"],
                    filename=nvd_data["filename"],
                    content_type=nvd_data["content_type"],
                    metadata={
                        "source": "nvd_cve_json",
                        "data_type": "cve",
                        "batch_import": True,
                        "import_method": "api"
                    }
                )
                results["nvd"] = result
        except Exception as e:
            logger.error("NVD batch ingestion failed", error=str(e))
            results["nvd"] = {"status": "failed", "error": str(e)}
        
        # CVE v5
        try:
            stats = {
                "total_files": 0,
                "successful": 0,
                "failed": 0
            }
            
            count = 0
            async for file_data in batch_loader.load_cve_v5_files():
                if limit_cve_v5 and count >= limit_cve_v5:
                    break
                
                count += 1
                stats["total_files"] += 1
                
                try:
                    result = await ingestion_service.ingest_document(
                        file_bytes=file_data["data"],
                        filename=file_data["filename"],
                        content_type=file_data["content_type"],
                        metadata={
                            "source": "cve_v5_json",
                            "data_type": "cve",
                            "filepath": file_data.get("filepath"),
                            "batch_import": True,
                            "import_method": "api"
                        }
                    )
                    
                    if result.get("status") == "success":
                        stats["successful"] += 1
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    stats["failed"] += 1
            
            results["cve_v5"] = stats
        except Exception as e:
            logger.error("CVE v5 batch ingestion failed", error=str(e))
            results["cve_v5"] = {"status": "failed", "error": str(e)}
        
        logger.info("Full batch ingestion completed", results=results)
        return {"status": "success", "data": results}
        
    except Exception as e:
        logger.error("Full batch ingestion failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
