#!/usr/bin/env python3
"""
DEBUG VERSION - Batch Extract + Upsert CWE XML
Chạy tuần tự, có print rõ ràng từng chunk
"""

import sys
sys.path.insert(0, '/app')

import asyncio
import sys
from sqlalchemy import select
from app.adapters.postgres import Chunk, AsyncSessionLocal
from app.services.extraction_service import ExtractionService
from app.services.graph_service import GraphService
from app.core.logger import logger

extraction_service = ExtractionService()
graph_service = GraphService()

async def main(start_chunk: int = 1, end_chunk: int = 10):
    print(f"🔍 Đang lấy chunks từ {start_chunk} đến {end_chunk}...")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chunk).where(Chunk.id >= start_chunk).where(Chunk.id <= end_chunk).order_by(Chunk.id)
        )
        chunks = result.scalars().all()

    print(f"✅ Tìm thấy {len(chunks)} chunks")

    success = 0
    for i, chunk in enumerate(chunks, 1):
        print(f"\n[{i}/{len(chunks)}] Đang xử lý chunk {chunk.id}...")

        try:
            # Extract
            extract_result = await extraction_service.extract_from_chunk(chunk.id)
            
            if extract_result.error:
                print(f"   ❌ Extract thất bại: {extract_result.error[:200]}")
                continue

            print(f"   ✅ Extract thành công: {len(extract_result.entities)} entities, {len(extract_result.relations)} relations")

            # Upsert
            upsert_result = await graph_service.process_extraction_result(extract_result)
            
            if upsert_result.get("status") == "success":
                print(f"   ✅ Upsert thành công: {upsert_result.get('entities_upserted')} entities")
                success += 1
            else:
                print(f"   ⚠️  Upsert không thành công: {upsert_result}")

        except Exception as e:
            print(f"   ❌ Lỗi khi xử lý chunk {chunk.id}: {e}")

    print("\n" + "="*60)
    print(f"🎉 HOÀN THÀNH!")
    print(f"Thành công: {success}/{len(chunks)} chunks")
    print("="*60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, default=1, help='Start chunk ID')
    parser.add_argument('--end', type=int, default=10, help='End chunk ID')
    args = parser.parse_args()
    
    asyncio.run(main(args.start, args.end))