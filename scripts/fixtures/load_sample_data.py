#!/usr/bin/env python3
"""Load sample data cho demo end-to-end."""

import asyncio
import json
from pathlib import Path
from app.services.ingestion_service import IngestionService
from app.services.extraction_service import ExtractionService

async def load_sample():
    service = IngestionService()
    extract_service = ExtractionService()

    # 1. Ingest sample CVE JSON
    with open("scripts/fixtures/sample_cve.json", "rb") as f:
        content = f.read()

    result = await service.ingest_document(
        file_bytes=content,
        filename="CVE-1999-0001.json",
        content_type="application/json"
    )
    print("✅ Ingested:", result)

    # 2. Extract chunk đầu tiên
    # Giả sử chunk_id = 1 sau ingest
    extract_result = await extract_service.extract_from_chunk(1)
    print("✅ Extracted entities:", len(extract_result.entities))

if __name__ == "__main__":
    asyncio.run(load_sample())