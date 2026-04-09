import pytest
from app.services.ingestion_service import IngestionService

@pytest.mark.asyncio
async def test_ingest_cve_json(sample_cve_json):
    service = IngestionService()
    with open("scripts/fixtures/sample_cve.json", "rb") as f:
        content = f.read()

    result = await service.ingest_document(
        file_bytes=content,
        filename="test-cve.json",
        content_type="application/json"
    )
    assert result["status"] == "success"
    assert result["chunks_count"] > 0