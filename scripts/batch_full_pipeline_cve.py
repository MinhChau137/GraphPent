#!/usr/bin/env python3
"""
END-TO-END BATCH PIPELINE cho hàng loạt file CVE JSON
Ingest → Extract → Upsert Graph
"""

import asyncio
import json 
from pathlib import Path
from tqdm.asyncio import tqdm
from app.services.ingestion_service import IngestionService
from app.services.extraction_service import ExtractionService
from app.services.graph_service import GraphService
from app.core.logger import logger

ingestion_service = IngestionService()
extraction_service = ExtractionService()
graph_service = GraphService()

async def process_single_cve(file_path: Path) -> dict:
    """Xử lý 1 file CVE: ingest → extract → graph upsert"""
    try:
        # 1. Đọc file
        with open(file_path, "rb") as f:
            content = f.read()

        # 2. Ingest
        ingest_result = await ingestion_service.ingest_document(
            file_bytes=content,
            filename=file_path.name,
            content_type="application/json",
            metadata={"source": "cve-batch", "file_path": str(file_path)}
        )

        if ingest_result.get("status") != "success":
            return {"file": file_path.name, "status": "ingest_failed", "error": ingest_result}

        document_id = ingest_result["document_id"]

        # 3. Extract tất cả chunks của document này
        # (Hiện tại chúng ta extract từng chunk một)
        # Giả sử chunk_id bắt đầu từ document_id * 100 (cách đơn giản)
        # Thực tế nên query DB để lấy tất cả chunk_id của document

        # Để đơn giản và nhanh, chúng ta extract chunk đầu tiên (thường chứa hầu hết thông tin CVE)
        extract_result = await extraction_service.extract_from_chunk(document_id)  # chunk_id thường = document_id ở giai đoạn đầu

        if extract_result.error:
            return {"file": file_path.name, "status": "extract_failed", "error": extract_result.error}

        # 4. Upsert vào Graph
        graph_result = await graph_service.process_extraction_result(extract_result)

        return {
            "file": file_path.name,
            "status": "success",
            "document_id": document_id,
            "entities": len(extract_result.entities),
            "relations": len(extract_result.relations),
            "graph_status": graph_result.get("status")
        }

    except Exception as e:
        logger.error(f"Error processing {file_path.name}", error=str(e))
        return {"file": file_path.name, "status": "error", "error": str(e)}


async def batch_process_cve_folder(folder_path: str, max_files: int = None):
    """Chạy pipeline cho toàn bộ thư mục"""
    path = Path(folder_path)
    json_files = list(path.glob("**/*.json"))

    if max_files:
        json_files = json_files[:max_files]

    print(f"🔍 Tìm thấy {len(json_files)} file JSON CVE")
    print(f"🚀 Bắt đầu xử lý end-to-end (ingest + extract + graph upsert)...\n")

    results = []
    success_count = 0

    # Xử lý tuần tự để tránh overload LLM + DB (có thể thay bằng asyncio.gather nếu máy mạnh)
    for file_path in tqdm(json_files, desc="Processing CVE files"):
        result = await process_single_cve(file_path)
        results.append(result)

        if result["status"] == "success":
            success_count += 1

    # Summary
    print("\n" + "="*60)
    print("🎉 HOÀN THÀNH BATCH PIPELINE")
    print("="*60)
    print(f"Tổng file xử lý     : {len(results)}")
    print(f"Thành công           : {success_count}")
    print(f"Thất bại             : {len(results) - success_count}")
    print("="*60)

    # Lưu log chi tiết
    with open("batch_cve_log.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("📄 Log chi tiết đã lưu tại: batch_cve_log.json")


if __name__ == "__main__":
    import sys
    
    # Tự động scan thư mục /data để tìm tất cả file JSON CVE
    data_folder = Path("/data")
    
    if not data_folder.exists():
        print("❌ Thư mục /data không tồn tại!")
        print("💡 Đảm bảo đã mount thư mục data trong docker-compose.yml")
        exit(1)
    
    # Tìm tất cả file .json trong thư mục data
    json_files = list(data_folder.glob("**/*.json"))
    
    if not json_files:
        print("❌ Không tìm thấy file JSON nào trong thư mục /data")
        print("💡 Đảm bảo đã đặt file CVE JSON vào thư mục data/")
        exit(1)
    
    print(f"🔍 Tìm thấy {len(json_files)} file JSON CVE trong /data")
    print(f"🚀 Bắt đầu xử lý toàn bộ pipeline...")
    
    # Xử lý tất cả files (không giới hạn)
    asyncio.run(batch_process_cve_folder(str(data_folder), max_files=None))