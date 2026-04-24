#!/usr/bin/env python3
"""Batch ingestion script for CWE XML and CVE JSON data."""

import asyncio
import sys
import argparse
import warnings
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logger import logger
from app.services.ingestion_service import IngestionService
from app.utils.batch_loader import BatchDataLoader, get_data_statistics


async def ingest_cwe_xml(ingestion_service: IngestionService) -> dict:
    """Ingest CWE XML data."""
    logger.info("Starting CWE XML ingestion...")
    
    loader = BatchDataLoader()
    cwe_data = await loader.load_cwe_xml()
    
    if not cwe_data:
        logger.error("CWE XML data not found")
        return {"status": "failed", "reason": "CWE XML not found"}
    
    try:
        result = await ingestion_service.ingest_document(
            file_bytes=cwe_data["data"],
            filename=cwe_data["filename"],
            content_type=cwe_data["content_type"],
            metadata={
                "source": "cwe_xml",
                "data_type": "cwe",
                "batch_import": True
            }
        )
        logger.info("✅ CWE XML ingestion completed", **result)
        return result
    except Exception as e:
        logger.error("CWE XML ingestion failed", error=str(e))
        return {"status": "failed", "reason": str(e)}


async def ingest_nvd_cve_json(ingestion_service: IngestionService) -> dict:
    """Ingest NVD CVE JSON data."""
    logger.info("Starting NVD CVE JSON ingestion...")
    
    loader = BatchDataLoader()
    nvd_data = await loader.load_nvd_cve_json()
    
    if not nvd_data:
        logger.error("NVD CVE JSON data not found")
        return {"status": "failed", "reason": "NVD CVE JSON not found"}
    
    try:
        result = await ingestion_service.ingest_document(
            file_bytes=nvd_data["data"],
            filename=nvd_data["filename"],
            content_type=nvd_data["content_type"],
            metadata={
                "source": "nvd_cve_json",
                "data_type": "cve",
                "batch_import": True
            }
        )
        logger.info("✅ NVD CVE JSON ingestion completed", **result)
        return result
    except Exception as e:
        logger.error("NVD CVE JSON ingestion failed", error=str(e))
        return {"status": "failed", "reason": str(e)}


async def ingest_cve_v5_files(ingestion_service: IngestionService, limit: Optional[int] = None) -> dict:
    """Ingest CVE v5 JSON files."""
    logger.info("Starting CVE v5 JSON files ingestion...")
    
    loader = BatchDataLoader()
    
    stats = {
        "total_files": 0,
        "successful": 0,
        "failed": 0,
        "errors": []
    }
    
    count = 0
    async for file_data in loader.load_cve_v5_files():
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
                    "batch_import": True
                }
            )
            
            if result.get("status") == "success":
                stats["successful"] += 1
                if count % 10 == 0:
                    logger.info(f"Progress: {count}/{limit or '?'} files ingested")
            else:
                stats["failed"] += 1
                if result.get("status") == "duplicate":
                    logger.debug(f"Skipped duplicate: {file_data['filename']}")
        except Exception as e:
            stats["failed"] += 1
            error_msg = f"{file_data['filename']}: {str(e)}"
            stats["errors"].append(error_msg)
            logger.error(f"Failed to ingest CVE file", filename=file_data["filename"], error=str(e))
    
    logger.info("✅ CVE v5 ingestion completed", **stats)
    return stats


async def show_data_statistics():
    """Show available data statistics."""
    logger.info("Gathering data statistics...")
    stats = await get_data_statistics()
    
    print("\n" + "="*60)
    print("📊 DATA STATISTICS")
    print("="*60)
    
    if stats["cwe_xml"]:
        print(f"\n✅ CWE XML:")
        print(f"   - File: {stats['cwe_xml']['filename']}")
        print(f"   - Size: {stats['cwe_xml']['size_mb']:.2f} MB")
    else:
        print(f"\n❌ CWE XML: Not found")
    
    if stats["nvd_cve_json"]:
        print(f"\n✅ NVD CVE JSON:")
        print(f"   - File: {stats['nvd_cve_json']['filename']}")
        print(f"   - Size: {stats['nvd_cve_json']['size_mb']:.2f} MB")
    else:
        print(f"\n❌ NVD CVE JSON: Not found")
    
    print(f"\n✅ CVE v5 JSON Files:")
    print(f"   - Count: {stats['cve_v5_files_count']}")
    
    if stats["cve_delta"]:
        print(f"\n✅ CVE Delta Changes:")
        print(f"   - New: {stats['cve_delta']['new']}")
        print(f"   - Updated: {stats['cve_delta']['updated']}")
    else:
        print(f"\n❌ CVE Delta: Not found")
    
    print("\n" + "="*60 + "\n")


async def main():
    """Main batch ingestion function."""
    parser = argparse.ArgumentParser(
        description="Batch ingest CWE XML and CVE JSON data into GraphRAG"
    )
    parser.add_argument(
        "--mode",
        choices=["stats", "cwe", "nvd", "cv5", "all"],
        default="stats",
        help="Ingestion mode (default: stats)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files to ingest (for CVE v5)"
    )
    parser.add_argument(
        "--cve-dir",
        type=str,
        default=None,
        help="Path to CVE v5 directory"
    )
    
    args = parser.parse_args()
    
    if args.mode == "stats":
        await show_data_statistics()
        return
    
    ingestion_service = IngestionService()
    results = {}
    
    try:
        if args.mode in ["cwe", "all"]:
            logger.info("\n" + "="*60)
            logger.info("INGESTING CWE XML")
            logger.info("="*60)
            results["cwe"] = await ingest_cwe_xml(ingestion_service)
        
        if args.mode in ["nvd", "all"]:
            logger.info("\n" + "="*60)
            logger.info("INGESTING NVD CVE JSON")
            logger.info("="*60)
            results["nvd"] = await ingest_nvd_cve_json(ingestion_service)
        
        if args.mode in ["cv5", "all"]:
            logger.info("\n" + "="*60)
            logger.info("INGESTING CVE v5 JSON FILES")
            logger.info("="*60)
            results["cv5"] = await ingest_cve_v5_files(ingestion_service, limit=args.limit)
        
        # Print summary
        print("\n" + "="*60)
        print("📊 INGESTION SUMMARY")
        print("="*60)
        for mode, result in results.items():
            print(f"\n{mode.upper()}: {result}")
        print("\n" + "="*60 + "\n")
        
    except Exception as e:
        logger.error("Batch ingestion failed", error=str(e))
        sys.exit(1)
    finally:
        # Cleanup pending tasks
        await asyncio.sleep(0.1)  # Allow pending tasks to complete


if __name__ == "__main__":
    # Suppress resource warnings during shutdown (they're from asyncio cleanup)
    warnings.filterwarnings("ignore", category=ResourceWarning)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Batch ingestion interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Batch ingestion failed: {str(e)}")
        sys.exit(1)
