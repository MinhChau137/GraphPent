#!/usr/bin/env python3
"""Batch extraction script - Extract entities/relations from ingested chunks and populate Neo4j."""

import asyncio
import sys
import argparse
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logger import logger
from app.services.extraction_service import ExtractionService
from app.adapters.postgres import AsyncSessionLocal, Chunk
from sqlalchemy import select, func


async def extract_all_chunks(batch_size: int = 10, limit: Optional[int] = None) -> dict:
    """Extract entities/relations from all ingested chunks with concurrent processing."""
    logger.info("Starting batch extraction...", batch_size=batch_size, limit=limit, concurrent_workers=batch_size)
    
    extraction_service = ExtractionService()
    
    stats = {
        "total_chunks": 0,
        "extracted": 0,
        "failed": 0,
        "skipped": 0,
        "errors": []
    }
    
    async with AsyncSessionLocal() as session:
        # Count total chunks
        count_result = await session.execute(select(func.count(Chunk.id)))
        total = count_result.scalar() or 0
        
        if limit:
            total = min(total, limit)
        
        stats["total_chunks"] = total
        logger.info(f"Found {total} chunks to extract")
        
        # Get chunks in batches
        query = select(Chunk).limit(limit) if limit else select(Chunk)
        result = await session.execute(query)
        chunks = result.scalars().all()
        
        # Process chunks sequentially with better error handling
        for idx, chunk in enumerate(chunks, 1):
            try:
                logger.info(f"Extracting chunk {idx}/{total}...", chunk_id=chunk.id)
                
                extraction_result = await extraction_service.extract_from_chunk(chunk.id)
                
                if extraction_result.error:
                    stats["failed"] += 1
                    error_msg = f"Chunk {chunk.id}: {extraction_result.error}"
                    stats["errors"].append(error_msg)
                    logger.error(f"Extraction error for chunk {chunk.id}", error=extraction_result.error)
                else:
                    stats["extracted"] += 1
                    logger.info(
                        f"Extracted chunk {chunk.id}",
                        entities=len(extraction_result.entities),
                        relations=len(extraction_result.relations)
                    )
                
                # Progress update every 10 chunks
                if idx % 10 == 0:
                    logger.info(f"Progress: {idx}/{total} - Extracted: {stats['extracted']}, Failed: {stats['failed']}")
                    
            except asyncio.TimeoutError:
                stats["failed"] += 1
                error_msg = f"Chunk {chunk.id}: Timeout (LLM response took too long)"
                stats["errors"].append(error_msg)
                logger.error(f"Timeout extracting chunk {chunk.id}")
            except Exception as e:
                stats["failed"] += 1
                error_msg = f"Chunk {chunk.id}: {str(e)}"
                stats["errors"].append(error_msg)
                logger.error(f"Failed to extract chunk {chunk.id}", error=str(e), error_type=type(e).__name__)
    
    logger.info("Batch extraction completed", **stats)
    return stats


async def show_extraction_stats() -> dict:
    """Show extraction statistics."""
    logger.info("Gathering extraction statistics...")
    
    stats = {
        "total_chunks": 0,
        "extracted_chunks": 0,
        "pending_chunks": 0
    }
    
    async with AsyncSessionLocal() as session:
        # Count total chunks
        total_result = await session.execute(select(func.count(Chunk.id)))
        stats["total_chunks"] = total_result.scalar() or 0
        
        # For now, assume all chunks need extraction (we'd check extraction_jobs table if it exists)
        # This is a placeholder - would need proper tracking in database
        stats["pending_chunks"] = stats["total_chunks"]
    
    print("\n" + "="*60)
    print("📊 EXTRACTION STATISTICS")
    print("="*60)
    print(f"\n✅ Total Chunks Available:")
    print(f"   - Count: {stats['total_chunks']}")
    print(f"\n⏳ Pending Extraction:")
    print(f"   - Count: {stats['pending_chunks']}")
    print("\n" + "="*60 + "\n")
    
    return stats


async def main():
    """Main batch extraction function."""
    parser = argparse.ArgumentParser(
        description="Batch extract entities/relations from ingested chunks and populate Neo4j"
    )
    parser.add_argument(
        "--mode",
        choices=["stats", "extract"],
        default="stats",
        help="Mode: stats (show info) or extract (run extraction)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of chunks to extract"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Batch size for processing"
    )
    
    args = parser.parse_args()
    
    if args.mode == "stats":
        await show_extraction_stats()
        return
    
    if args.mode == "extract":
        logger.info("\n" + "="*60)
        logger.info("EXTRACTING ENTITIES & RELATIONS")
        logger.info("="*60)
        
        stats = await extract_all_chunks(batch_size=args.batch_size, limit=args.limit)
        
        # Print summary
        print("\n" + "="*60)
        print("📊 EXTRACTION SUMMARY")
        print("="*60)
        print(f"\nTotal Chunks: {stats['total_chunks']}")
        print(f"Successfully Extracted: {stats['extracted']}")
        print(f"Failed: {stats['failed']}")
        if stats['errors']:
            print(f"\nErrors:")
            for error in stats['errors'][:10]:  # Show first 10 errors
                print(f"  - {error}")
        print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    import warnings
    
    # Suppress resource warnings during shutdown
    warnings.filterwarnings("ignore", category=ResourceWarning)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Batch extraction interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Batch extraction failed: {str(e)}")
        sys.exit(1)
